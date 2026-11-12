"""The orders Lambda the agents invoke directly (lambdas/handler.py).

Kept separate from DataStack so code deploys never touch the stack that holds the tables.
The tables are passed in from DataStack; CDK turns that into cross-stack references.
"""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

LAMBDAS_DIR = Path(__file__).resolve().parents[2] / "lambdas"

# Fixed name so the AgentCore CDK app (a separate app) and agentcore/.env.local can refer to it
ORDERS_FUNCTION_NAME = "aws-rag-solution-orders"


class ToolsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        customers: dynamodb.ITableV2,
        orders: dynamodb.ITableV2,
        events: dynamodb.ITableV2,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "OrdersFunctionLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # handler.py only needs boto3, which the Lambda Python runtime already includes,
        # so the code asset is just the lambdas/ folder with no build step.
        self.orders_function = lambda_.Function(
            self,
            "OrdersFunction",
            function_name=ORDERS_FUNCTION_NAME,
            runtime=lambda_.Runtime.PYTHON_3_14,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(str(LAMBDAS_DIR), exclude=["__pycache__"]),
            timeout=Duration.seconds(10),
            memory_size=256,
            log_group=log_group,
            environment={
                "CUSTOMERS_TABLE": customers.table_name,
                "ORDERS_TABLE": orders.table_name,
                "EVENTS_TABLE": events.table_name,
                "LOG_LEVEL": "INFO",
            },
        )

        # Least privilege: read customers, read/update orders, append-only events
        customers.grant_read_data(self.orders_function)
        orders.grant_read_write_data(self.orders_function)
        events.grant_write_data(self.orders_function)

        # Set ORDERS_LAMBDA_NAME in agentcore/.env.local and agentcore.json to this value
        CfnOutput(self, "OrdersFunctionName", value=self.orders_function.function_name)
        CfnOutput(self, "OrdersFunctionArn", value=self.orders_function.function_arn)
