"""Load the test customers and orders from agents/app/agents/test_data.py into DynamoDB.

Run after `cdk deploy`:
    AWS_PROFILE=dev uv run python scripts/seed.py

Safe to re-run: PutItem overwrites items with the same key, so refunded orders go back to their test state.
"""

import importlib.util
from pathlib import Path

import boto3

STACK_NAME = "RagSolutionData"
TEST_DATA = (
    Path(__file__).resolve().parents[2] / "agents" / "app" / "agents" / "test_data.py"
)


def load_test_data():
    spec = importlib.util.spec_from_file_location("test_data", TEST_DATA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stack_outputs() -> dict[str, str]:
    """Return the stack's outputs as {OutputKey: OutputValue}, e.g. {"OrdersTableName": "..."}."""
    stack = boto3.client("cloudformation").describe_stacks(StackName=STACK_NAME)[
        "Stacks"
    ][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def put_all(table, items: list[dict]) -> None:
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"{table.name}: wrote {len(items)} items")


def main() -> None:
    data = load_test_data()
    outputs = stack_outputs()
    dynamodb = boto3.resource("dynamodb")
    put_all(dynamodb.Table(outputs["CustomersTableName"]), data.CUSTOMER_TABLE)
    put_all(dynamodb.Table(outputs["OrdersTableName"]), data.ORDER_TABLE)


if __name__ == "__main__":
    main()
