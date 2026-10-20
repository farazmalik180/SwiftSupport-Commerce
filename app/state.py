"""Shared graph state for the multi-agent system."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

TRIAGE = "triage"
CATALOG = "catalog"
ORDERS = "orders"


class AgentState(TypedDict):
    """`messages` is the full conversation; `active_agent` persists across turns."""

    messages: Annotated[list[BaseMessage], add_messages]
    active_agent: str
