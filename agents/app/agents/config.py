"""Central config for the agent app. Import values from here instead of calling os.environ directly.

Local dev:  values come from agentcore/.env.local (gitignored, outside the code bundle, so never deployed).
AgentCore:  values come from the runtime's envVars in agentcore/agentcore.json.
Real environment variables always take precedence over the .env.local file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# app/agents/config.py -> agents/agentcore/.env.local (no-op when the file is absent, e.g. in AgentCore Runtime)
_ENV_FILE = Path(__file__).resolve().parents[2] / "agentcore" / ".env.local"
load_dotenv(_ENV_FILE, override=False)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing env var {name}: set it in agentcore/.env.local (local) "
            f"or the runtime's envVars in agentcore/agentcore.json (deployed)"
        )
    return value


AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ORCHESTRATOR_MODEL_ID = _required("ORCHESTRATOR_MODEL_ID")
WORKER_MODEL_ID = _required("WORKER_MODEL_ID")
ORDERS_LAMBDA_NAME = _required("ORDERS_LAMBDA_NAME")