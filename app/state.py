"""Shared graph state for the multi-agent system."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

TRIAGE = "triage"
CATALOG = "catalog"
ORDERS = "orders"


class AgentState(TypedDict):
    """`messages` is the full conversation; `active_agent` persists across turns.

    `customer_id` is the authenticated customer. It is set by the application (never by the
    LLM) and injected into order tools so a customer can only access their own orders.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    active_agent: str
    customer_id: str
