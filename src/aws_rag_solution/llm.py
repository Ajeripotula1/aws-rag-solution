import boto3
from botocore.exceptions import ClientError

from aws_rag_solution import config

model_id = config.BEDROCK_MODEL_ID
aws_region = config.AWS_REGION
client = boto3.client("bedrock-runtime", region_name=aws_region)


# s = boto3.Session();
# print(s.profile_name, s.get_credentials().method)
# Structure the conversation history
def ask(prompt: str) -> str:
    messages = [{"role": "user", "content": [{"text": prompt}]}]

    try:
        # Send the conversation payload
        response = client.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig={"maxTokens": 500, "temperature": 0.7},
        )

        # Extract and print the response text
        # print("raw response:", json.dumps(response, indent=4))
        output_text = response["output"]["message"]["content"][0]["text"]
        total_tokens = response["usage"]["totalTokens"]
        print(f"Response: {output_text} \n Total Tokens: {total_tokens}")

    except ClientError as e:
        print(f"AWS Error: {e}")
