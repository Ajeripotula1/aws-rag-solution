# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A learning project, built up day by day (one git branch per day, e.g. `day1-bedrock`), heading toward an AWS multi-agent system with RAG on Bedrock Knowledge Bases, S3, and CI/CD, using Strands Agents and AgentCore. The README keeps a per-day log of progress; add each new day's work to it. `.gitignore` already has entries for CDK (Day 2+).

Current state (Day 1): a small CLI that sends one prompt to a Bedrock model through the Converse API.

## Commands

Uses `uv` (Python >= 3.14, `uv_build` backend, `src/` layout).

```bash
uv sync                                         # install deps into .venv
aws login --profile dev                         # AWS credentials (profile "dev")
uv run python -m aws_rag_solution.cli "prompt"  # invoke Bedrock from the CLI
uv run ruff check .                             # lint
uv run ruff format .                            # format
uv run pytest                                   # tests (none exist yet)
uv run pytest path/to/test_file.py::test_name   # single test
```

The `aws-rag-solution` console script in `pyproject.toml` points to `aws_rag_solution:main`, the placeholder "Hello" function in `__init__.py`, not to `cli.main`. Use `python -m aws_rag_solution.cli` to run the real CLI, or repoint the script.

If boto3 isn't using the `dev` profile, set `AWS_PROFILE=dev`.

## Architecture

- `config.py` loads `.env` via python-dotenv when imported and exposes `AWS_REGION` (default `us-east-1`), `BEDROCK_MODEL_ID` (default `us.amazon.nova-lite-v1:0`, a cross-region inference profile ID), and `LOG_LEVEL`. `.env` is gitignored; `.env.example` is meant to be committed but doesn't exist yet.
- `llm.py` creates a module-level `bedrock-runtime` boto3 client when imported, so region and model are fixed at import time. `ask()` calls `client.converse(...)` and prints the response text and token count. It is typed `-> str` but returns nothing, and it catches `ClientError` and prints it.
- `cli.py` is an argparse wrapper around `llm.ask`.
- `strands-agents` is a dependency, but no code uses it yet.
