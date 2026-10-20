"""Streamlit chat UI. Run: streamlit run streamlit_app.py"""
import os
import uuid

import streamlit as st

# Streamlit Cloud / HF Spaces: secrets -> env before app.config reads it.
try:
    if "GROQ_API_KEY" in st.secrets and not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except Exception:  # no secrets file locally
    pass

from app import config  # noqa: E402
from app.agents import SupportSystem  # noqa: E402

st.set_page_config(page_title="SwiftSupport Concierge", page_icon="🛍️", layout="centered")

AGENT_LABELS = {"triage": "🧭 Concierge", "catalog": "📦 Catalog", "orders": "🚚 Orders & Returns"}
SAMPLES = [
    "Do you have wireless headphones under $100?",
    "Where is my order ORD-10002?",
    "I want to return order ORD-10001",
    "Can I refund ORD-10005?",
    "Is the ErgoFlex chair in stock?",
]


@st.cache_resource(show_spinner=False)
def get_system() -> SupportSystem:
    return SupportSystem()


st.title("🛍️ SwiftSupport Concierge")
st.caption("Multi-agent e-commerce support · Groq + LangGraph")

if not config.get_api_key():
    st.error("`GROQ_API_KEY` is missing. Add it to `.env` locally or to your host's secrets.")
    st.stop()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = uuid.uuid4().hex
    st.session_state.history = []
    st.session_state.active = "triage"
    st.session_state.queued = None

with st.sidebar:
    st.subheader("Active agent")
    st.info(AGENT_LABELS[st.session_state.active])
    show_trace = st.toggle("Show agent reasoning", value=True)
    st.subheader("Try asking")
    for s in SAMPLES:
        if st.button(s, use_container_width=True):
            st.session_state.queued = s
    if st.button("🔄 New conversation", use_container_width=True):
        for k in ("thread_id", "history", "active", "queued"):
            st.session_state.pop(k, None)
        st.rerun()


def render_trace(trace):
    with st.expander(f"Reasoning ({len(trace)} steps)"):
        for s in trace:
            icon = {"Thought": "💭", "Tool Call": "🔧", "Observation": "👁️"}.get(s["kind"], "•")
            st.markdown(f"{icon} **{s['kind']}** `{s['agent']}`")
            st.code(s["text"], language=None)


for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if show_trace and msg.get("trace"):
            render_trace(msg["trace"])

prompt = st.chat_input("How can we help you today?") or st.session_state.queued
st.session_state.queued = None
if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            out = get_system().chat(prompt, st.session_state.thread_id)
        st.markdown(out["reply"])
        if show_trace and out["trace"]:
            render_trace(out["trace"])
    st.session_state.active = out["active_agent"]
    st.session_state.history.append(
        {"role": "assistant", "content": out["reply"], "trace": out["trace"]}
    )
    st.rerun()
