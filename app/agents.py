"""LangGraph multi-agent graph: Triage, Catalog, and Orders agents with handoffs."""
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app import config, tools as T
from app.prompts import PROMPTS
from app.state import CATALOG, ORDERS, TRIAGE, AgentState

# --------------------------------------------------------------------------- #
# Tool wrappers (LLM-facing schemas derive from these signatures/docstrings)
# --------------------------------------------------------------------------- #
@tool
def search_catalog(query: str) -> str:
    """Search the product catalog by keywords. Supports price hints like 'headphones under 100'."""
    return T.search_catalog(query)


@tool
def check_order_status(order_id: str) -> str:
    """Look up an order by ID (e.g. ORD-10001). Returns status, purchase date and tracking number."""
    return T.check_order_status(order_id)


@tool
def calculate_refund_eligibility(order_id: str) -> str:
    """Check whether an order is eligible for a refund under the 30-day return policy."""
    return T.calculate_refund_eligibility(order_id)


@tool
def process_refund(order_id: str) -> str:
    """Process a mock refund for an order. Only call after eligibility is Approved and the customer confirms."""
    return T.process_refund(order_id)


@tool
def transfer_to_catalog_agent(reason: str) -> str:
    """Hand the conversation to the Catalog agent for product discovery, availability and upsells."""
    return "handoff"


@tool
def transfer_to_orders_agent(reason: str) -> str:
    """Hand the conversation to the Orders agent for tracking, order lookups, returns and refunds."""
    return "handoff"


@tool
def transfer_to_triage(reason: str) -> str:
    """Hand the conversation back to the Triage concierge when the request is complete or unrelated."""
    return "handoff"


HANDOFFS = {
    "transfer_to_catalog_agent": CATALOG,
    "transfer_to_orders_agent": ORDERS,
    "transfer_to_triage": TRIAGE,
}

AGENT_TOOLS = {
    TRIAGE: [transfer_to_catalog_agent, transfer_to_orders_agent],
    CATALOG: [search_catalog, transfer_to_orders_agent, transfer_to_triage],
    ORDERS: [check_order_status, calculate_refund_eligibility, process_refund,
             transfer_to_catalog_agent, transfer_to_triage],
}
DATA_TOOLS = {t.name: t for ts in AGENT_TOOLS.values() for t in ts if t.name not in HANDOFFS}


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #
def _llm(model: str, agent: str) -> Any:
    return ChatGroq(model=model, temperature=0.2, api_key=config.get_api_key(), max_retries=2).bind_tools(
        AGENT_TOOLS[agent]
    )


def build_graph():
    primary = {a: _llm(config.get_model(), a) for a in AGENT_TOOLS}
    fallback = {a: _llm(config.get_fallback_model(), a) for a in AGENT_TOOLS}

    def make_agent_node(agent: str):
        def node(state: AgentState) -> Dict[str, Any]:
            messages = [SystemMessage(content=PROMPTS[agent])] + state["messages"]
            nudge = HumanMessage(
                content="(system) Your last reply was empty. Reply now: either a one-line 'Thought:' "
                "plus a tool call, or the final answer to the customer."
            )
            attempts = [(primary[agent], messages), (primary[agent], messages + [nudge]),
                        (fallback[agent], messages + [nudge])]
            response = None
            for llm, msgs in attempts:
                try:
                    candidate = llm.invoke(msgs)
                except Exception:  # noqa: BLE001 - malformed tool call, rate limit, etc.
                    continue
                if candidate.tool_calls or (candidate.content or "").strip():
                    response = candidate
                    break
            if response is None:
                response = AIMessage(
                    content="Sorry, I'm having trouble reaching my brain right now. Please try again in a moment."
                )
            response.additional_kwargs["agent"] = agent
            return {"messages": [response]}

        return node

    def tools_node(state: AgentState) -> Dict[str, Any]:
        last = state["messages"][-1]
        active = state["active_agent"]
        allowed = {t.name for t in AGENT_TOOLS[active]}
        out: List[ToolMessage] = []
        for call in last.tool_calls:
            name = call["name"]
            if name not in allowed:
                content = f"Error: tool '{name}' is not available to you. Available: {sorted(allowed)}."
            elif name in HANDOFFS:
                active = HANDOFFS[name]
                content = f"Transferred to the {active} agent. Continue helping with the customer's latest request."
            else:
                try:
                    content = str(DATA_TOOLS[name].invoke(call["args"]))
                except Exception as exc:  # noqa: BLE001
                    content = f"Error: tool '{name}' failed ({type(exc).__name__}). Check the arguments."
            out.append(ToolMessage(content=content, tool_call_id=call["id"], name=name))
        return {"messages": out, "active_agent": active}

    def after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(AgentState)
    for agent in AGENT_TOOLS:
        graph.add_node(agent, make_agent_node(agent))
        graph.add_conditional_edges(agent, after_agent, {"tools": "tools", END: END})
    graph.add_node("tools", tools_node)
    graph.add_conditional_edges(START, lambda s: s.get("active_agent") or TRIAGE,
                                {a: a for a in AGENT_TOOLS})
    graph.add_conditional_edges("tools", lambda s: s["active_agent"], {a: a for a in AGENT_TOOLS})
    return graph.compile(checkpointer=MemorySaver())


# --------------------------------------------------------------------------- #
# Public facade
# --------------------------------------------------------------------------- #
class SupportSystem:
    """Chat facade: `chat()` returns the reply plus a Thought/Tool/Observation trace."""

    def __init__(self) -> None:
        if not config.get_api_key():
            raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.graph = build_graph()

    def chat(self, message: str, thread_id: str = "default") -> Dict[str, Any]:
        cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}
        before = len(self.graph.get_state(cfg).values.get("messages", []))
        result = self.graph.invoke(
            {"messages": [HumanMessage(content=message)], "active_agent": self._active(cfg)}, cfg
        )
        new_messages = result["messages"][before + 1:]
        reply = ""
        for m in reversed(new_messages):
            if isinstance(m, AIMessage) and m.content and not m.tool_calls:
                reply = m.content
                break
        return {
            "reply": reply or "Sorry, I couldn't produce a response. Could you rephrase?",
            "active_agent": result.get("active_agent", TRIAGE),
            "trace": format_trace(new_messages),
        }

    def _active(self, cfg) -> str:
        return self.graph.get_state(cfg).values.get("active_agent") or TRIAGE


def format_trace(messages) -> List[Dict[str, str]]:
    """Flatten messages into Thought / Tool Call / Observation steps."""
    steps: List[Dict[str, str]] = []
    for m in messages:
        if isinstance(m, AIMessage):
            agent = m.additional_kwargs.get("agent", "agent")
            if m.tool_calls:
                thought = (m.content or m.additional_kwargs.get("reasoning_content") or "").strip()
                if thought:
                    steps.append({"agent": agent, "kind": "Thought", "text": thought})
                for c in m.tool_calls:
                    args = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
                    steps.append({"agent": agent, "kind": "Tool Call", "text": f"{c['name']}({args})"})
        elif isinstance(m, ToolMessage):
            steps.append({"agent": "tool", "kind": "Observation", "text": str(m.content)})
    return steps
