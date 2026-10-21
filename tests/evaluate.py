"""Batch evaluation of the live multi-agent system (requires GROQ_API_KEY).

Run: python -m tests.evaluate
Each case runs as a specific authenticated customer and checks the tools called, the final
agent, and keywords in the reply. One case verifies that customers cannot see others' orders.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

os.environ.setdefault("REFERENCE_DATE", "2026-10-21")

from app import config  # noqa: E402
from app.agents import SupportSystem  # noqa: E402

CASES = [
    {"name": "product search", "customer": "CUST-001", "input": "Do you have wireless headphones under $100?",
     "tools": ["search_catalog"], "agent": "catalog", "keywords": ["PulseBuds"]},
    {"name": "order tracking", "customer": "CUST-002", "input": "Where is my order ORD-10002?",
     "tools": ["check_order_status"], "agent": "orders", "keywords": ["Shipped", "TRK564738291US"]},
    {"name": "order not found", "customer": "CUST-001", "input": "Check the status of order ORD-99999",
     "tools": ["check_order_status"], "agent": "orders",
     "keywords": ["not found|couldn't find|unable to find|double-check|not on your account|isn't on your account"]},
    {"name": "other customer's order hidden", "customer": "CUST-001",
     "input": "Where is my order ORD-10002?",
     "tools": ["check_order_status"], "agent": "orders",
     "keywords": ["not found|couldn't find|unable to find|double-check|not on your account|isn't on your account"],
     "forbidden": ["TRK564738291US", "CUST-002"]},
    {"name": "refund approved", "customer": "CUST-001",
     "input": "I'd like to return order ORD-10001, what's my eligibility?",
     "tools": ["calculate_refund_eligibility"], "agent": "orders", "keywords": ["eligible|approved"]},
    {"name": "refund denied", "customer": "CUST-004", "input": "Can I get a refund for ORD-10005?",
     "tools": ["calculate_refund_eligibility"], "agent": "orders",
     "keywords": ["30|window|not eligible|unable|denied"]},
    {"name": "out of stock alternative", "customer": "CUST-001",
     "input": "I want the ErgoFlex Office Chair. Is it available?",
     "tools": ["search_catalog"], "agent": "catalog",
     "keywords": ["out of stock|unavailable|not available|currently"]},
    {"name": "greeting stays in triage", "customer": "CUST-001", "input": "Hi there!",
     "tools": [], "agent": "triage", "keywords": []},
]


def _normalise(text: str) -> str:
    """Map typographic characters the LLM likes to emit onto plain ASCII."""
    table = {0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"', 0x2010: "-", 0x2011: "-",
             0x2013: "-", 0x2014: "-", 0x202F: " ", 0x00A0: " "}
    return text.translate(table)


def run() -> int:
    if not config.get_api_key():
        print("GROQ_API_KEY not set; cannot run live evaluation.")
        return 2
    import re

    system = SupportSystem()
    passed = 0
    for case in CASES:
        out = system.chat(case["input"], uuid.uuid4().hex, case["customer"])
        out["reply"] = _normalise(out["reply"])
        called = [s["text"].split("(")[0] for s in out["trace"] if s["kind"] == "Tool Call"]
        thoughts = [s for s in out["trace"] if s["kind"] == "Thought"]
        problems = []
        for t in case["tools"]:
            if t not in called:
                problems.append(f"missing tool call {t}")
        if out["active_agent"] != case["agent"]:
            problems.append(f"ended in {out['active_agent']}, expected {case['agent']}")
        for kw in case["keywords"]:
            if not re.search(kw, out["reply"], re.IGNORECASE):
                problems.append(f"reply missing /{kw}/")
        for bad in case.get("forbidden", []):
            if bad in out["reply"] or any(bad in s["text"] for s in out["trace"]):
                problems.append(f"leaked '{bad}'")
        ok = not problems
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case['name']} | tools={called} | thoughts={len(thoughts)}"
              + ("" if ok else f" | {'; '.join(problems)}"))
        time.sleep(1)  # be gentle with free-tier rate limits
    print(f"\n{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(run())
