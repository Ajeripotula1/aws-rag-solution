"""Customer and order operations for the agents, invoked directly with lambda:InvokeFunction.

Request (the invoke Payload):
    {"tool": "check_refund", "arguments": {"customer_id": "C001", "order_id": "O001"}}

Response (the returned Payload, always a JSON object):
    success: the tool's result, e.g. {"eligible": true, "reason": null, "order": {...}}
    failure: {"error": "<message safe to show the agent>"}
A crash (unhandled exception) is reported by Lambda itself via the FunctionError field instead.

customer_id must come from the caller's code (agent state), never from the model.

Tables (names come from env vars, set by CDK):
    CUSTOMERS_TABLE  PK customer_id
    ORDERS_TABLE     PK customer_id, SK order_id   (keying by customer_id is the ownership check)
    EVENTS_TABLE     PK customer_id, SK created_at  (append-only audit log)

This mirrors agents/app/agents/orders_repo.py, which is the in-memory version used for local dev.
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

REFUND_WINDOW = timedelta(days=30)

# Created outside the handler so warm invocations reuse them
_dynamodb = boto3.resource("dynamodb")
customers_table = _dynamodb.Table(os.environ["CUSTOMERS_TABLE"])
orders_table = _dynamodb.Table(os.environ["ORDERS_TABLE"])
events_table = _dynamodb.Table(os.environ["EVENTS_TABLE"])


class ToolInputError(Exception):
    """Bad or missing arguments; the message is safe to show the agent."""


# ---------- helpers ----------


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _require(args: dict, name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"{name} is required and must be a non-empty string")
    return value.strip()


def _to_json(value):
    """DynamoDB returns numbers as Decimal, which isn't JSON-serializable."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json(v) for v in value]
    return value


def _get_order(customer_id: str, order_id: str) -> dict | None:
    return orders_table.get_item(
        Key={"customer_id": customer_id, "order_id": order_id}
    ).get("Item")


def _append_event(customer_id: str, event_type: str, **fields) -> None:
    events_table.put_item(
        Item={
            "customer_id": customer_id,
            "created_at": f"{_iso(_now())}#{uuid.uuid4().hex[:8]}",
            "type": event_type,
            **fields,
        }
    )


def refund_ineligibility_reason(
    order: dict | None, now: datetime | None = None
) -> str | None:
    """Return why an order can't be refunded, or None if it is eligible. Pure policy, no I/O."""
    if order is None:
        return "Order not found for this customer."
    status = order.get("status")
    if status == "refunded":
        return "This order has already been refunded."
    if status != "delivered":
        return f"Order status is '{status}'. Only delivered orders can be refunded."
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        return "Order has no delivery date on record, so the refund window can't be checked."
    delivered = datetime.fromisoformat(delivered_at)
    if (now or _now()) - delivered > REFUND_WINDOW:
        return f"Order was delivered on {delivered_at[:10]}, outside the {REFUND_WINDOW.days}-day refund window."
    return None


# ---------- tools (each takes the request's "arguments" dict) ----------


def get_customer(args: dict) -> dict:
    customer_id = _require(args, "customer_id")
    item = customers_table.get_item(Key={"customer_id": customer_id}).get("Item")
    if item is None:
        return {"error": f"No customer found with id {customer_id}"}
    return {"customer": item}


def list_orders(args: dict) -> dict:
    customer_id = _require(args, "customer_id")
    items, kwargs = [], {"KeyConditionExpression": Key("customer_id").eq(customer_id)}
    while True:  # Query returns at most 1 MB per page
        page = orders_table.query(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return {"orders": items}


def get_order(args: dict) -> dict:
    customer_id = _require(args, "customer_id")
    order_id = _require(args, "order_id")
    item = _get_order(customer_id, order_id)
    if item is None:
        return {"error": f"No order {order_id} found for this customer"}
    return {"order": item}


def check_refund(args: dict) -> dict:
    """Read-only eligibility check. Changes nothing."""
    customer_id = _require(args, "customer_id")
    order_id = _require(args, "order_id")
    order = _get_order(customer_id, order_id)
    reason = refund_ineligibility_reason(order)
    return {"eligible": reason is None, "reason": reason, "order": order}


def process_refund(args: dict) -> dict:
    """Refund a delivered order. Re-checks eligibility here, so the agent can't skip check_refund."""
    customer_id = _require(args, "customer_id")
    order_id = _require(args, "order_id")
    reason = args.get("reason") or "not given"

    order = _get_order(customer_id, order_id)
    why_not = refund_ineligibility_reason(order)

    if why_not is None:
        now = _now()
        try:
            # The condition repeats the policy inside the write, so a concurrent change
            # between the read above and this update can't produce a double refund.
            orders_table.update_item(
                Key={"customer_id": customer_id, "order_id": order_id},
                UpdateExpression="SET #status = :refunded, refunded_at = :now",
                ConditionExpression="#status = :delivered AND delivered_at >= :cutoff",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":refunded": "refunded",
                    ":delivered": "delivered",
                    ":now": _iso(now),
                    ":cutoff": _iso(now - REFUND_WINDOW),
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            why_not = "Order status changed before the refund could be processed."

    if why_not:
        logger.info(
            "refund_rejected customer_id=%s order_id=%s why=%r",
            customer_id,
            order_id,
            why_not,
        )
        _append_event(
            customer_id,
            "refund_rejected",
            order_id=order_id,
            reason=reason,
            rejection=why_not,
        )
        return {"refunded": False, "reason": why_not}

    logger.info("refund_processed customer_id=%s order_id=%s", customer_id, order_id)
    _append_event(
        customer_id,
        "refund_processed",
        order_id=order_id,
        item=order["item"],
        reason=reason,
        prev_status="delivered",
        new_status="refunded",
    )
    return {"refunded": True, "order_id": order_id, "item": order["item"]}


TOOLS = {
    "get_customer": get_customer,
    "list_orders": list_orders,
    "get_order": get_order,
    "check_refund": check_refund,
    "process_refund": process_refund,
}


# ---------- entry point ----------


def lambda_handler(event, context):
    if not isinstance(event, dict):
        return {"error": "Request must be a JSON object"}
    tool_name = event.get("tool")
    fn = TOOLS.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}. Valid tools: {', '.join(TOOLS)}"}
    arguments = event.get("arguments") or {}
    if not isinstance(arguments, dict):
        return {"error": "arguments must be a JSON object"}
    try:
        return _to_json(fn(arguments))
    except ToolInputError as e:
        return {"error": str(e)}
    except ClientError:
        logger.exception("DynamoDB error in %s", tool_name)
        return {"error": "Database error, try again later"}
