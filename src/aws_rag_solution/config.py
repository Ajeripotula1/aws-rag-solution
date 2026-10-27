import os

from dotenv import load_dotenv

load_dotenv()

# BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID")

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
