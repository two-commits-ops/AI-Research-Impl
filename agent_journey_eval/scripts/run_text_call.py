#!/usr/bin/env python
"""Phase 1 verification harness: drive the shopping agent as a plain text
conversation from the terminal, with every turn traced into SQLite.

    python -m scripts.run_text_call
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agent.flow import load_flow
from agent.loop import ShoppingSession
from agent.tracer import start_call
from server import db


def main() -> None:
    flow = load_flow()
    tracer = start_call(flow)
    session = ShoppingSession(tracer)

    print(f"Call started: {tracer.call_id}  (data/trajectories.db)")
    print("Type your side of the call. 'quit' to end.\n")

    try:
        while True:
            user_text = input("you> ").strip()
            if user_text.lower() in {"quit", "exit"}:
                break
            if not user_text:
                continue
            result = session.run_turn(user_text)
            print(f"agent> {result['agent_text']}")
            if result["drift_flag"]:
                print(f"  [drift] {result['drift_note']}")
            print(f"  (stage={result['stage_actual']} mood={result['caller_mood']} latency={result['latency_ms']:.0f}ms)\n")
    except (KeyboardInterrupt, EOFError):
        pass

    tracer.end_call()

    print("\nCall ended. Quick satisfaction check:")
    try:
        score = input("How satisfied were you with that call, 1-5? ").strip()
        comment = input("Anything you'd add? (optional) ").strip()
        if score:
            db.set_user_label(tracer.call_id, int(score), comment)
    except (KeyboardInterrupt, EOFError, ValueError):
        pass

    call = db.get_call(tracer.call_id)
    print(f"\nSaved. running_satisfaction={call['running_satisfaction']:.2f} drift_count={call['drift_count']}")


if __name__ == "__main__":
    main()
