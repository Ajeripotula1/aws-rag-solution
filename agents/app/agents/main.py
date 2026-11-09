from typing import Any
from collections import OrderedDict
from strands import Agent, tool
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
# Request-scoped values (e.g. customer_id) go in as builder arguments, so tools use them directly
# and the model never supplies them. Keep business logic at module level; tools stay thin wrappers.


## FAQ/RAG Agent
def build_faq_agent() -> Agent:
    system_prompt = """You are an FAQ research agent.
    Always call search_faqs before answering, and answer only from what it returns.
    If the FAQs don't cover the question, say so plainly instead of guessing."""

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID, region_name=config.AWS_REGION, temperature=0.1
    )

    # @tool(context=True)
    @tool
    def search_faqs(query:str, customer_id:str) -> str:
        """Search the FAQ knowledge base and return the most relevant Q&A entries.

        Args:
            query: A short search query describing what the customer is asking about.
        """
        
        # customer_id = tool_context.agent.state.get('customer_id')
        
        if not customer_id:
            return "Unable to retrieve order information: Customer ID not available"
        print("CUSTOMER ID", customer_id)
        results = faq_source.retrieve(query)
        log.info(f"search_faqs query={query!r} hits={len(results)}")
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
        callback_handler=None,  # don't stream sub-agent output to stdout; the orchestrator relays the answer
    )


### Account Agent: only reads information from customer or order table to gather context for other agents
def build_account_agent() -> Agent:
    system_prompt = """You are an Account Lookup  agent.
        Your only job is to lookup information from the table required for the task.
        You will return your findings in a clean and organized dictionary with no other 
        stray charcters or messages. If the infromation can not be found in the table, 
        or the entry does not exist, return empty dict
        DO NOT MAKE UP YOUR OWN DATA."""

    model = BedrockModel(
        model_id=config.WORKER_MODEL_ID, region_name=config.AWS_REGION, temperature=0.1
    )

    @tool(context=True)
    def lookup_customer(tool_context) -> str:
        """lookup customer information by customer_id and return infromation"""
        customer_id = tool_context.agent.state.get('customer_id')
        print("CUSTOMER ID", customer_id)
        if not customer_id:
            return "Unable to retrieve order information: Customer ID not available"
        
        match = next(
            (
                customer
                for customer in CUSTOMER_TABLE
                if customer.get("customer_id") == customer_id
            ),
            None,
        )
        if match:
            return match
        return {}

    @tool
    def lookup_all_orders(customer_id: str) -> str:
        """lookup all orders for a customer"""
        matches = [
            order for order in ORDER_TABLE if order.get("customer_id") == customer_id
        ]
        if matches:
            return matches
        return []

    @tool
    def lookup_single_order(order_id: str) -> str:
        """serach for a single order"""
        match = next(
            (order for order in ORDER_TABLE if order.get("order_id") == order_id), None
        )
        if match:
            return match
        return {}

    return Agent(
        name="faq_agent",
        description=(
            "Answer customer questions about account & login, billing & payments, shipping, orders, "
            "returns and refunds, using the company FAQ knowledge base. "
            "Pass the customer's question, rephrased to be self-contained."
        ),
        model=model,
        system_prompt=system_prompt,
        tools=[lookup_customer, lookup_all_orders, lookup_single_order],
        callback_handler=None,  # don't stream sub-agent output to stdout; the orchestrator relays the answer
    )


### Orchestrator Agent
def build_orchestrator_agent(specialists: list[Agent]) -> Agent:
    system_prompt = """You are an orchestrator agent with access to specialist agents exposed as tools.
    Route each question to the right specialist and turn its answer into a friendly final reply.
    Don't answer questions a specialist covers from your own knowledge."""

    model = BedrockModel(
        model_id=config.ORCHESTRATOR_MODEL_ID, region_name=config.AWS_REGION
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=specialists,
    )

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
    # prompt = payload.get("prompt")
    # customer_id = payload.get("customer_id")
    if not isinstance(prompt, str) or not prompt.strip() or not customer_id:
        return {"error": "prompt must be a non-empty string"}
    log.info("Invoking agent")

    # Build fresh agents per request; pass request-scoped values (e.g. customer_id) into the builders that need them
    orchestrator = build_orchestrator_agent(
        [
            build_faq_agent(),
            # build_account_agent(),
        ]
    )
    # set state for tool context
    # Store session_id, customer_id, and customer_name in agent state for tools to access
    
    # orchestrator.state.set("session_id", session_id)
    # orchestrator.state.set("customer_id", customer_id)
    
    # orchestrator.state.set("jwt_token", jwt_token)
    # if customer_name:
        # supervisor.state.set("customer_name", customer_name)
    result = await orchestrator.invoke_async(prompt)

    # Whatever is returned here is serialized as the JSON response body
    return {
        "response": str(result),
        "stop_reason": result.stop_reason,
    }


if __name__ == "__main__":
    app.run()
