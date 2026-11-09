from typing import Any
from dataclasses import dataclass
from collections import OrderedDict
from strands import Agent, ToolContext, tool
from strands.models import BedrockModel
import asyncio
from strands.agent.conversation_manager.null_conversation_manager import (
    NullConversationManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import config
import faq_source
from model.load import load_model
from mcp_client.client import get_streamable_http_mcp_client
from test_data import CUSTOMER_TABLE, ORDER_TABLE

app = BedrockAgentCoreApp()
log = app.logger
# Define a Streamable HTTP MCP Client
mcp_clients = [get_streamable_http_mcp_client()]


# Define a collection of tools used by the model
tools = []

_INLINE_FUNCTION_NAMES = set()


# Define a simple function tool
@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers"""
    return a + b


tools.append(add_numbers)


# # Add MCP client to tools if available
# for mcp_client in mcp_clients:
#     if mcp_client:
#         tools.append(mcp_client)

# Agents-as-tools: each specialist is one build_*_agent() function that holds its prompt and tools
# and returns an Agent with a name and description. Strands wraps an Agent passed in `tools` as a
# tool automatically; the description is what the orchestrator reads to decide when to route to it.
# Request-scoped values (e.g. customer_id) go in as builder arguments and are stored in the agent's
# `state` at construction. Tools declared with @tool(context=True) read them from
# tool_context.agent.state, so the model never sees or supplies them.
# State must be set at construction: when the orchestrator wraps a sub-agent it snapshots its state,
# and resets the sub-agent to that snapshot before every call.
# Keep business logic at module level; tools stay thin wrappers.


## FAQ/RAG Agent
def build_faq_agent(customer_id: str) -> Agent:
    system_prompt = """You are an FAQ research agent.
    Always call search_faqs before answering, and answer only from what it returns.
    If the FAQs don't cover the question, say so plainly instead of guessing."""

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID, region_name=config.AWS_REGION, temperature=0.1
    )

    @tool(context=True)
    def search_faqs(query: str, tool_context: ToolContext) -> str:
        """Search the FAQ knowledge base and return the most relevant Q&A entries.

        Args:
            query: A short search query describing what the customer is asking about.
        """
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return "Unable to search FAQs: customer ID not available"
        results = faq_source.retrieve(query)
        log.info(f"search_faqs customer_id={customer_id} query={query!r} hits={len(results)}")
        if not results:
            return "No relevant FAQ entries found."
        return "\n\n".join(f"[{r['source']['category']}]\n{r['text']}" for r in results)

    return Agent(
        name="faq_agent",
        description=(
            "Answer customer questions about account & login, billing & payments, shipping, orders, "
            "returns and refunds, using the company FAQ knowledge base. "
            "Pass the customer's question, rephrased to be self-contained."
        ),
        model=model,
        system_prompt=system_prompt,
        tools=[search_faqs],
        state={"customer_id": customer_id},
        callback_handler=None,  # don't stream sub-agent output to stdout; the orchestrator relays the answer
    )


### Account Agent: only reads information from customer or order table to gather context for other agents
def build_account_agent(customer_id: str) -> Agent:
    system_prompt = """You are an Account Lookup agent for the signed-in customer.
        Your tools already know who the customer is; never ask for a customer ID.
        Use lookup_customer for profile details (name, tier), lookup_all_orders for their orders,
        and lookup_single_order when a specific order_id is given.
        Return only the information requested, as a clean dictionary with no extra text.
        If nothing is found, return an empty dict. DO NOT MAKE UP YOUR OWN DATA."""

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID, region_name=config.AWS_REGION, temperature=0.1
    )

    @tool(context=True)
    def lookup_customer(tool_context: ToolContext) -> dict:
        """Look up the current customer's profile."""
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return {}
        return next(
            (c for c in CUSTOMER_TABLE if c.get("customer_id") == customer_id), {}
        )

    @tool(context=True)
    def lookup_all_orders(tool_context: ToolContext) -> list:
        """Look up all orders for the current customer."""
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return []
        return [o for o in ORDER_TABLE if o.get("customer_id") == customer_id]

    @tool(context=True)
    def lookup_single_order(order_id: str, tool_context: ToolContext) -> dict:
        """Look up a single order by order_id. Only returns orders that belong to the current customer.

        Args:
            order_id: The order ID to look up.
        """
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return {}
        return next(
            (
                o
                for o in ORDER_TABLE
                if o.get("order_id") == order_id and o.get("customer_id") == customer_id
            ),
            {},
        )

    return Agent(
        name="account_agent",
        description=(
            "Look up the signed-in customer's profile (name, tier) and their orders (all orders, or one "
            "order by order_id). It already knows who the customer is; no ID is needed. "
            "Pass a short description of what information is needed."
        ),
        model=model,
        system_prompt=system_prompt,
        tools=[lookup_customer, lookup_all_orders, lookup_single_order],
        state={"customer_id": customer_id},
        callback_handler=None,  # don't stream sub-agent output to stdout; the orchestrator relays the answer
    )


### Orchestrator Agent
def build_orchestrator_agent(specialists: list[Agent]) -> Agent:
    system_prompt = """You are an orchestrator agent with access to specialist agents exposed as tools.
    Route each question to the right specialist and turn its answer into a friendly final reply.
    Don't answer questions a specialist covers from your own knowledge.

    The customer is already signed in. The specialists already know who the customer is, so
    questions about "my account", "my tier", "my orders" etc. can be answered by calling them directly.
    Never ask the customer for their customer ID, name, or account details to identify them."""

    model = BedrockModel(
        model_id=config.ORCHESTRATOR_MODEL_ID, region_name=config.AWS_REGION
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=specialists,
    )

@dataclass(frozen=True)
class RequestContext:
    """Per-request values that come from the caller, not the model. Tools read these; the model never sees them."""

    session_id: str
    customer_id: str | None = None  # later: taken from the caller's JWT, not the payload

def from_request(payload: dict, context) -> RequestContext:
    customer_id = payload.get("customer_id")
    if customer_id is not None and (not isinstance(customer_id, str) or not customer_id.strip()):
        raise ValueError("customer_id must be a non-empty string")
    return RequestContext(session_id=context.session_id, customer_id=customer_id)

## Run Orchestrator Agent
@app.entrypoint
async def invoke(payload, context):
    # payload is the parsed JSON body, e.g. {"prompt": "...", "customer_id": "C001"}
    # print("payload:", payload, "session:", context.session_id, "\n\n")
    request_context = from_request(payload, context)
    prompt = payload.get("prompt")
    customer_id = request_context.customer_id
    session_id = request_context.session_id
    if not isinstance(prompt, str) or not prompt.strip():
        return {"error": "prompt must be a non-empty string"}
    if not customer_id:
        return {"error": "customer_id is required"}
    log.info(f"Invoking Orchestrator agent session_id={session_id}")

    # Build fresh agents per request. customer_id goes into each sub-agent's state at construction,
    # before the orchestrator wraps them (it snapshots sub-agent state at wrap time).
    orchestrator = build_orchestrator_agent(
        [
            build_faq_agent(customer_id),
            build_account_agent(customer_id),
        ]
    )
    result = await orchestrator.invoke_async(prompt)

    # Whatever is returned here is serialized as the JSON response body
    return {
        "response": str(result),
        "stop_reason": result.stop_reason,
    }


if __name__ == "__main__":
    app.run()
