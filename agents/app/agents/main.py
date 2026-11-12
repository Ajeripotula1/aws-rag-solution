import json
from dataclasses import dataclass

import boto3
import config
import faq_source
import orders_repo
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp_client.client import get_streamable_http_mcp_client
from strands import Agent, ToolContext, tool
from strands.models import BedrockModel

app = BedrockAgentCoreApp()
log = app.logger
# lambda client
lambda_client = boto3.client("lambda", region_name=config.AWS_REGION)

# Define a Streamable HTTP MCP Client
mcp_clients = [get_streamable_http_mcp_client()]


# generic Lambda caller
def call_orders_lambda(tool: str, **arguments) -> dict:
    response = lambda_client.invoke(
        FunctionName=config.ORDERS_LAMBDA_NAME,
        Payload=json.dumps({"tool": tool, "arguments": arguments}),
    )
    if "FunctionError" in response:
        log.error(f"orders lambda {tool} failed: {response['Payload'].read()!r}")
        return {"error": "Order service failed, try again later"}
    return json.loads(response["Payload"].read())


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
        log.info(
            f"search_faqs customer_id={customer_id} query={query!r} hits={len(results)}"
        )
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
        return call_orders_lambda("get_customer", customer_id=customer_id).get(
            "customer", {}
        )

    @tool(context=True)
    def lookup_all_orders(tool_context: ToolContext) -> list:
        """Look up all orders for the current customer."""
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return []
        return call_orders_lambda("list_orders", customer_id=customer_id).get(
            "orders", []
        )

    @tool(context=True)
    def lookup_single_order(order_id: str, tool_context: ToolContext) -> dict:
        """Look up a single order by order_id. Only returns orders that belong to the current customer.

        Args:
            order_id: The order ID to look up.
        """
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return {}
        result = call_orders_lambda(
            "get_order", customer_id=customer_id, order_id=order_id
        )
        return result.get("order", {})

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


### Refund Agent: checks eligibility and processes refunds for the signed-in customer's orders.
# The eligibility rules live in the orders Lambda (code), not in the prompt. process_refund re-runs every
# check itself, so a refund can't go through even if the model skips check_refund or is given a wrong order_id.
def build_refund_agent(customer_id: str) -> Agent:
    system_prompt = f"""You are a Refund agent for the signed-in customer.
        Your tools already know who the customer is; never ask for a customer ID.

        1. Identify the order. If you're given an order_id, use it. Otherwise call list_my_orders and
           match the item the customer describes. If more than one order matches, or none do,
           don't guess: say which orders could match and stop.
        2. Call check_refund on that order.
        3. Only if the request explicitly asks to refund the order AND check_refund says it is eligible,
           call process_refund. If the request only asks whether an order is eligible, don't process it.
        4. Report the outcome plainly: what was refunded, or why it can't be.

        Refund policy: delivered orders can be refunded within {orders_repo.REFUND_WINDOW.days} days of delivery,
        for a full refund minus shipping costs. Never promise a refund that process_refund did not confirm."""

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID, region_name=config.AWS_REGION, temperature=0.1
    )

    @tool(context=True)
    def list_my_orders(tool_context: ToolContext) -> list:
        """List the current customer's orders, to find the order_id for an item they describe."""
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return []
        return call_orders_lambda("list_orders", customer_id=customer_id).get(
            "orders", []
        )

    @tool(context=True)
    def check_refund(order_id: str, tool_context: ToolContext) -> dict:
        """Check whether one of the current customer's orders can be refunded. Changes nothing.

        Args:
            order_id: The order to check.
        """
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return {"eligible": False, "reason": "Customer not identified."}
        return call_orders_lambda(
            "check_refund", customer_id=customer_id, order_id=order_id
        )

    @tool(context=True)
    def process_refund(order_id: str, reason: str, tool_context: ToolContext) -> dict:
        """Refund one of the current customer's delivered orders and mark it refunded.
        Re-checks eligibility itself; refuses if the order isn't eligible.

        Args:
            order_id: The order to refund.
            reason: The customer's reason for the refund, in their words.
        """
        customer_id = tool_context.agent.state.get("customer_id")
        if not customer_id:
            return {"refunded": False, "reason": "Customer not identified."}
        # The Lambda re-checks eligibility, does the conditional write and logs the event
        return call_orders_lambda(
            "process_refund", customer_id=customer_id, order_id=order_id, reason=reason
        )

    return Agent(
        name="refund_agent",
        description=(
            "Check refund eligibility for, and process refunds of, the signed-in customer's orders. "
            "It already knows who the customer is and can find the order from an item description. "
            "Pass the item or order_id, whether the customer wants the refund processed or only an "
            "eligibility check, and the customer's reason if given."
        ),
        model=model,
        system_prompt=system_prompt,
        tools=[list_my_orders, check_refund, process_refund],
        state={"customer_id": customer_id},
        callback_handler=None,
    )


### Orchestrator Agent
def build_orchestrator_agent(specialists: list[Agent]) -> Agent:
    system_prompt = """You are an orchestrator agent with access to specialist agents exposed as tools.
    Route each question to the right specialist and turn its answer into a friendly final reply.
    Don't answer questions a specialist covers from your own knowledge.

    The customer is already signed in. The specialists already know who the customer is, so
    questions about "my account", "my tier", "my orders" etc. can be answered by calling them directly.
    Never ask the customer for their customer ID, name, or account details to identify them.

    Refunds: always call refund_agent for anything about refunds. It finds the order from an item
    description itself, so never ask the customer for an order ID or order details first.
    - A direct request such as "refund my X", "please refund X" or "I want a refund for X" is an explicit
      request: tell refund_agent to PROCESS the refund. Don't ask the customer to confirm first.
    - A question such as "can I refund X?" or "is X eligible?" is not a request: tell refund_agent to
      only CHECK eligibility.
    Pass the item or order_id and the customer's reason, if given. Relay refund_agent's outcome exactly;
    never say a refund was processed unless refund_agent confirmed it."""

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
    customer_id: str | None = (
        None  # later: taken from the caller's JWT, not the payload
    )


def from_request(payload: dict, context) -> RequestContext:
    customer_id = payload.get("customer_id")
    if customer_id is not None and (
        not isinstance(customer_id, str) or not customer_id.strip()
    ):
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
            build_refund_agent(customer_id),
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
