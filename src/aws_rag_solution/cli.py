import argparse

from aws_rag_solution.llm import ask


def main():

    parser = argparse.ArgumentParser(description="CLI testing for LLM Invocations")

    parser.add_argument("prompt", type=str, help="Query to Send to Bedrock Model")
    # 5. Parse the terminal arguments
    args = parser.parse_args()

    # 6. Execute the core logic with parsed values
    ask(prompt=args.prompt)


if __name__ == "__main__":
    main()
