"""Customer, order and event data access. The one source of truth that agent tools read and write.

Backed by the in-memory tables in test_data for now. Each function maps to one DynamoDB call, so this
module can switch to DynamoDB without the agents changing:

    get_customer   -> GetItem   (PK customer_id)
    list_orders    -> Query     (PK customer_id)
    get_order      -> GetItem   (PK customer_id, SK order_id). Keying by customer_id is the ownership check.
    mark_refunded  -> UpdateItem with ConditionExpression "#status = :delivered"
    append_event   -> PutItem   (PK customer_id, SK created_at#event_id), append-only

Every function takes customer_id from the caller (agent state), never from the model.
"""

import copy
import threading
import uuid
from datetime import UTC, datetime, timedelta

from test_data import CUSTOMER_TABLE, EVENTS_TABLE, ORDER_TABLE

REFUND_WINDOW = timedelta(days=30)

# Stands in for DynamoDB's conditional write: the check and the update happen as one step.
_write_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_customer(customer_id: str) -> dict | None:
    match = next((c for c in CUSTOMER_TABLE if c["customer_id"] == customer_id), None)
    return copy.deepcopy(match)


def list_orders(customer_id: str) -> list[dict]:
    return [copy.deepcopy(o) for o in ORDER_TABLE if o["customer_id"] == customer_id]


def _find_order(customer_id: str, order_id: str) -> dict | None:
    return next(
        (o for o in ORDER_TABLE if o["customer_id"] == customer_id and o["order_id"] == order_id),
        None,
    )


def get_order(customer_id: str, order_id: str) -> dict | None:
    """Return the order only if it belongs to customer_id."""
    return copy.deepcopy(_find_order(customer_id, order_id))


def refund_ineligibility_reason(order: dict | None, now: datetime | None = None) -> str | None:
    """Return why an order can't be refunded, or None if it is eligible. Pure policy, no I/O."""
    if order is None:
        return "Order not found for this customer."
    status = order["status"]
    if status == "refunded":
        return "This order has already been refunded."
    if status != "delivered":
        return f"Order status is '{status}'. Only delivered orders can be refunded."
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        return "Order has no delivery date on record, so the refund window can't be checked."
    delivered = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
    if (now or _now()) - delivered > REFUND_WINDOW:
        return f"Order was delivered on {delivered_at[:10]}, outside the {REFUND_WINDOW.days}-day refund window."
    return None


def mark_refunded(customer_id: str, order_id: str) -> bool:
    """Set status to 'refunded' only if the order belongs to customer_id and is still 'delivered'.

    Returns False if the condition fails (like DynamoDB's ConditionalCheckFailedException).
    """
    with _write_lock:
        order = _find_order(customer_id, order_id)
        if order is None or order["status"] != "delivered":
            return False
        order["status"] = "refunded"
        order["refunded_at"] = _iso(_now())
        return True


def append_event(customer_id: str, event_type: str, **fields) -> dict:
    """Append an audit event. Events are never updated or deleted."""
    now = _iso(_now())
    event = {
        "customer_id": customer_id,
        "created_at": f"{now}#{uuid.uuid4().hex[:8]}",
        "type": event_type,
        **fields,
    }
    EVENTS_TABLE.append(event)
    return copy.deepcopy(event)
