import os

import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.tools_stack import ToolsStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

data = DataStack(app, "RagSolutionData", env=env)
ToolsStack(
    app,
    "RagSolutionTools",
    customers=data.customers,
    orders=data.orders,
    events=data.events,
    env=env,
)

cdk.Tags.of(app).add("project", "aws-rag-solution")

app.synth()
