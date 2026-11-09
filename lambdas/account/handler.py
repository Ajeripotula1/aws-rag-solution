import logging
import os

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Created outside the handler so warm invocations reuse it
table = boto3.resource("dynamodb").Table(os.environ["CUSTOMERS_TABLE"])


def get_customer(args: dict) -> dict:
    customer_id = args.get("customer_id")
    if not customer_id:
        return {"error": "customer_id is required"}
    item = table.get_item(Key={"customer_id": customer_id}).get("Item")
    if item is None:
        return {"error": f"No customer found with id {customer_id}"}
    return {"customer": item}


def get_order(args: dict) -> dict:
    order_id = args.get("order_id")
    if not order_id:
        return {"error": "order_id is required"}
    item = table.get_item(Key={"order_id": order_id}).get("Item")
    if item is None:
        return {"error": f"No order found with id {order_id}"}
    return {"order": item}


def get_orders(args: dict) -> dict:
    customer_id = args.get("customer_id")
    if not customer_id:
        return {"error": "customer_id is required"}
    item = table.query(
        KeyConditionExpression=Key('customer_id').eq(customer_id)
    )
    if item is None:
        return {"error": f"No customer found with id {customer_id}"}
    return {"customer": item}



TOOLS = {
    "get_customer": get_customer,
    "create_customer": get_order,
    "delete_customer": get_orders,
}


def lambda_handler(event, context):
    full_name = context.client_context.custom["bedrockAgentCoreToolName"]
    tool_name = full_name.split("___")[-1]  # strip target prefix

    fn = TOOLS.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return fn(event)
    except ClientError:
        logger.exception("DynamoDB error in %s", tool_name)
        return {"error": "Database error, try again later"}