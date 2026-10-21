"""Command-line chat for SwiftSupport Commerce. Run: python main.py [--trace]"""
from __future__ import annotations

import getpass
import sys
import uuid

from app import auth
from app.agents import SupportSystem


def login():
    """Prompt for credentials; allow 3 attempts."""
    for _ in range(3):
        cid = input("Customer ID (e.g. CUST-001): ").strip()
        pin = getpass.getpass("PIN: ")
        customer = auth.authenticate(cid, pin)
        if customer:
            return customer
        print("Invalid credentials (or account temporarily locked).\n")
    return None


def main() -> None:
    show_trace = "--trace" in sys.argv
    try:
        system = SupportSystem()
    except RuntimeError as exc:
        sys.exit(str(exc))
    customer = login()
    if not customer:
        sys.exit("Too many failed attempts.")
    thread = uuid.uuid4().hex
    print(f"\nWelcome, {customer.name}! SwiftSupport Concierge (type 'quit' to exit)\n")
    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"quit", "exit"}:
            break
        if not user:
            continue
        out = system.chat(user, thread, customer.customer_id)
        if show_trace:
            for s in out["trace"]:
                print(f"   [{s['kind']}] ({s['agent']}) {s['text']}")
        print(f"[{out['active_agent']}] {out['reply']}\n")


if __name__ == "__main__":
    main()
