"""DynamoDB tables for customers, orders and the audit event log, plus the S3 bucket holding the FAQ
documents for the Knowledge Base.

Key design follows the access patterns in agents/app/agents/orders_repo.py:
    customers  PK customer_id                      GetItem
    orders     PK customer_id, SK order_id         Query (list), GetItem (one), conditional UpdateItem (refund)
    events     PK customer_id, SK created_at#id    PutItem (append), Query (history)

Only key attributes are declared; every other attribute is stored as written.
CloudFormation generates the table and bucket names; they are printed as stack outputs.

FAQ files in data/faqs/ (repo root) are uploaded to s3://<bucket>/faqs/ on every deploy.
Rebuild the PDF with `uv run scripts/build_faq_pdf.py`.
"""

from pathlib import Path

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

FAQ_DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "faqs"


def string_key(name: str) -> dynamodb.Attribute:
    return dynamodb.Attribute(name=name, type=dynamodb.AttributeType.STRING)


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Learning project: `cdk destroy` deletes the tables and their data.
        # For real data use RemovalPolicy.RETAIN and turn on point-in-time recovery.
        self.customers = dynamodb.TableV2(
            self,
            "CustomersTable",
            partition_key=string_key("customer_id"),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.orders = dynamodb.TableV2(
            self,
            "OrdersTable",
            partition_key=string_key("customer_id"),
            sort_key=string_key("order_id"),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.events = dynamodb.TableV2(
            self,
            "EventsTable",
            partition_key=string_key("customer_id"),
            sort_key=string_key("created_at"),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Source documents for the FAQ Knowledge Base.
        self.docs_bucket = s3.Bucket(
            self,
            "DocsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        s3deploy.BucketDeployment(
            self,
            "DeployFaqDocs",
            sources=[s3deploy.Source.asset(str(FAQ_DOCS_DIR))],
            destination_bucket=self.docs_bucket,
            destination_key_prefix="faqs/",
        )

        CfnOutput(self, "CustomersTableName", value=self.customers.table_name)
        CfnOutput(self, "OrdersTableName", value=self.orders.table_name)
        CfnOutput(self, "EventsTableName", value=self.events.table_name)
        CfnOutput(self, "DocsBucketName", value=self.docs_bucket.bucket_name)
