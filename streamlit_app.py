"""Streamlit chat UI with customer login. Run: streamlit run streamlit_app.py"""
import os
import uuid

import streamlit as st

# Streamlit Cloud / HF Spaces: secrets -> env before app.config reads it.
try:
    for _k in ("GROQ_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # no secrets file locally
    pass

from app import auth, config  # noqa: E402
from app.agents import SupportSystem  # noqa: E402

st.set_page_config(page_title="SwiftSupport Concierge", page_icon="🛍️", layout="centered")

AGENT_LABELS = {"triage": "🧭 Concierge", "catalog": "📦 Catalog", "orders": "🚚 Orders & Returns"}
SAMPLES = [
    "Do you have wireless headphones under $100?",
    "Where are my orders?",
    "I want to return my latest delivered order",
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


def reset_session(customer=None):
    for k in ("thread_id", "history", "active", "queued", "customer"):
        st.session_state.pop(k, None)
    if customer:
        st.session_state.customer = customer
        st.session_state.thread_id = uuid.uuid4().hex
        st.session_state.history = []
        st.session_state.active = "triage"
        st.session_state.queued = None


# ----------------------------- Login gate ----------------------------- #
if "customer" not in st.session_state:
    st.subheader("Sign in")
    st.caption("Customers can only see their own orders.")
    with st.form("login"):
        cid = st.text_input("Customer ID", placeholder="CUST-001")
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        customer = auth.authenticate(cid, pin)
        if customer:
            reset_session(customer)
            st.rerun()
        elif auth.is_locked(auth.normalize_customer_id(cid)):
            st.error("Too many failed attempts. Please try again in a few minutes.")
        else:
            st.error("Invalid customer ID or PIN.")
    with st.expander("Demo credentials"):
        st.markdown(
            "This is a demo with mock data. Customer `CUST-001` has PIN `1001`, "
            "`CUST-002` has `1002`, and so on up to `CUST-012` / `1012`."
        )
    st.stop()

customer = st.session_state.customer

with st.sidebar:
    st.subheader(f"👤 {customer.name}")
    st.caption(customer.customer_id)
    st.subheader("Active agent")
    st.info(AGENT_LABELS[st.session_state.active])
    show_trace = st.toggle("Show agent reasoning", value=True)
    if config.tracing_enabled():
        st.caption("🔎 LangSmith tracing is on")
    st.subheader("Try asking")
    for s in SAMPLES:
        if st.button(s, use_container_width=True):
            st.session_state.queued = s
    if st.button("🔄 New conversation", use_container_width=True):
        reset_session(customer)
        st.rerun()
    if st.button("🚪 Sign out", use_container_width=True):
        reset_session()
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
            out = get_system().chat(prompt, st.session_state.thread_id, customer.customer_id)
        st.markdown(out["reply"])
        if show_trace and out["trace"]:
            render_trace(out["trace"])
    st.session_state.active = out["active_agent"]
    st.session_state.history.append(
        {"role": "assistant", "content": out["reply"], "trace": out["trace"]}
    )
    st.rerun()
