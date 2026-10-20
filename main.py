"""Command-line chat for SwiftSupport Commerce. Run: python main.py [--trace]"""
from __future__ import annotations

import sys
import uuid

from app.agents import SupportSystem


def main() -> None:
    show_trace = "--trace" in sys.argv
    try:
        system = SupportSystem()
    except RuntimeError as exc:
        sys.exit(str(exc))
    thread = uuid.uuid4().hex
    print("SwiftSupport Concierge (type 'quit' to exit)\n")
    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"quit", "exit"}:
            break
        if not user:
            continue
        out = system.chat(user, thread)
        if show_trace:
            for s in out["trace"]:
                print(f"   [{s['kind']}] ({s['agent']}) {s['text']}")
        print(f"[{out['active_agent']}] {out['reply']}\n")


if __name__ == "__main__":
    main()
