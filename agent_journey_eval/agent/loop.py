"""The shopping agent's turn loop: Groq LLM + tool calling, everything logged
through a TrajectoryTracer as it happens."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List

from groq import Groq

from agent.prompts import AGENT_SYSTEM_PROMPT
from agent.tools.mock_tools import (
    MOCK_TOOL_SPECS,
    add_to_cart,
    cancel_order,
    check_inventory,
    check_order,
    checkout,
    get_delivery_time,
    save_design,
    shipping_estimate,
    view_order_history,
    view_store_location,
)
from agent.tools.product_search import PRODUCT_SEARCH_TOOL_SPEC, product_search
from agent.tracer import TrajectoryTracer
from server import db

log = logging.getLogger(__name__)

_MODEL = "openai/gpt-oss-120b"
_TOOLS = [PRODUCT_SEARCH_TOOL_SPEC, *MOCK_TOOL_SPECS]
_TOOL_SPECS_BY_NAME = {t["function"]["name"]: t for t in _TOOLS}

_CALL_ID_TOOLS = {"add_to_cart", "checkout", "view_order_history", "save_design"}


def _missing_required_args(name: str, args: Dict[str, Any]) -> List[str]:
    """Checked deterministically against the tool's own declared schema — not
    left for the judge to notice (or miss) from reading raw text."""
    spec = _TOOL_SPECS_BY_NAME.get(name)
    if not spec:
        return []
    required = spec["function"]["parameters"].get("required", [])
    missing = []
    for key in required:
        val = args.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(key)
    return missing


def _dispatch_tool(call_id: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    fn = {
        "product_search": lambda **a: {"products": [p.model_dump() for p in product_search(**a)]},
        "check_inventory": check_inventory,
        "add_to_cart": add_to_cart,
        "shipping_estimate": shipping_estimate,
        "checkout": checkout,
        "view_order_history": view_order_history,
        "check_order": check_order,
        "get_delivery_time": get_delivery_time,
        "cancel_order": cancel_order,
        "view_store_location": view_store_location,
        "save_design": save_design,
    }.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    if name in _CALL_ID_TOOLS:
        return fn(call_id=call_id, **args)
    return fn(**args)


class ShoppingSession:
    def __init__(self, tracer: TrajectoryTracer):
        self.tracer = tracer
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT}
        ]

    def run_turn(self, user_text: str) -> Dict[str, Any]:
        """Runs one full turn (tool-calling loop included) and returns everything
        the live UI needs: the reply text, which trace event to attach TTS audio
        to, and the judge's read on stage/drift/mood/satisfaction."""
        self.tracer.log_user_turn(user_text)
        self.messages.append({"role": "user", "content": user_text})

        last_tool_name = None
        tool_trace: List[Dict[str, Any]] = []
        started = time.time()

        # Tool-calling loop: keep letting the model call tools until it produces
        # a final spoken reply.
        for _ in range(6):
            completion = self.client.chat.completions.create(
                model=_MODEL, messages=self.messages, tools=_TOOLS, tool_choice="auto"
            )
            message = completion.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                agent_text = message.content or ""
                return self._finish_turn(user_text, agent_text, last_tool_name, tool_trace, started)

            for tool_call in message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")
                last_tool_name = name

                missing = _missing_required_args(name, args)
                arg_issue = f"missing required argument(s): {', '.join(missing)}" if missing else None
                self.tracer.log_tool_call(name, args, arg_issue=arg_issue)

                tool_started = time.time()
                try:
                    result = _dispatch_tool(self.tracer.call_id, name, args)
                except Exception as e:  # tool failures are a real signal, not a crash
                    result = {"error": str(e)}
                tool_latency = (time.time() - tool_started) * 1000
                tool_failed = isinstance(result, dict) and "error" in result
                self.tracer.log_tool_result(name, result, latency_ms=tool_latency, tool_failed=tool_failed)
                tool_trace.append(
                    {"name": name, "args": args, "result": result, "tool_failed": tool_failed, "arg_issue": arg_issue}
                )

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    }
                )

        # Safety valve: if the model won't stop calling tools, surface what happened.
        fallback = "Sorry, I'm having trouble finishing that — could you repeat what you need?"
        return self._finish_turn(user_text, fallback, last_tool_name, tool_trace, started)

    def _finish_turn(
        self,
        user_text: str,
        agent_text: str,
        last_tool_name: str | None,
        tool_trace: List[Dict[str, Any]],
        started: float,
    ) -> Dict[str, Any]:
        latency_ms = (time.time() - started) * 1000
        agent_event = self.tracer.log_agent_response(agent_text, latency_ms=latency_ms)

        # Tool failures and missing-required-args are facts we already know
        # for certain from the dispatch code — hand them to the judge as
        # verified ground truth instead of making it infer them from raw
        # text, and force drift for a missing-arg call regardless of what
        # the judge concludes (skipping required info gathering is always a
        # real problem, not a judgment call).
        tool_issue_lines: List[str] = []
        forced_drift_note: str | None = None
        for i, t in enumerate(tool_trace):
            if t["arg_issue"]:
                tool_issue_lines.append(f"- `{t['name']}` was called {t['arg_issue']}")
                forced_drift_note = forced_drift_note or (
                    f"Called `{t['name']}` {t['arg_issue']} instead of gathering it first"
                )
            if t["tool_failed"]:
                # A failure the agent retried and fixed within the SAME turn is
                # not an unresolved problem — say so explicitly, otherwise the
                # judge sees only the failure and wrongly calls the (actually
                # accurate, grounded-in-the-successful-retry) final reply a
                # hallucination.
                recovered = any(later["name"] == t["name"] and not later["tool_failed"] for later in tool_trace[i + 1 :])
                if recovered:
                    tool_issue_lines.append(
                        f"- `{t['name']}` failed once ({t['result'].get('error')}) but the agent retried it "
                        "later this same turn and it succeeded — treat the retry's result as the real outcome"
                    )
                else:
                    tool_issue_lines.append(f"- `{t['name']}` FAILED: {t['result'].get('error')}")
        tool_issue_summary = "\n".join(tool_issue_lines) or None

        # The judge call is a real network dependency (Gemini) with its own
        # failure modes (rate limits, transient 503s). Losing the score for
        # one turn is fine; losing the agent's actual reply because of it is
        # not — so a judge failure degrades to "unscored", not a dead turn.
        try:
            judge_result = self.tracer.judge_last_turn(
                agent_event,
                latest_user_text=user_text,
                latest_agent_text=agent_text,
                latest_tool_call=last_tool_name,
                tool_issue_summary=tool_issue_summary,
                forced_drift_note=forced_drift_note,
            )
        except Exception as e:
            log.warning("judge failed for call %s, turn %d: %s", self.tracer.call_id, self.tracer.turn_index, e)
            judge_result = None

        call = db.get_call(self.tracer.call_id)
        return {
            "event_id": agent_event.id,
            "agent_text": agent_text,
            "latency_ms": latency_ms,
            "tool_trace": tool_trace,
            "tool_issue_summary": tool_issue_summary,
            "flow_name": judge_result.flow_name if judge_result else None,  # which flow THIS turn matched, if any
            "stage_actual": judge_result.node_id if judge_result else None,
            "active_flow_name": self.tracer.active_flow.name if self.tracer.active_flow else None,  # overall engaged flow, persists across off-flow turns
            "drift_flag": judge_result.drift_flag if judge_result else False,
            "drift_note": judge_result.drift_note if judge_result else None,
            "caller_mood": judge_result.caller_mood if judge_result else None,
            "profanity_user": judge_result.profanity_user if judge_result else False,
            "profanity_agent": judge_result.profanity_agent if judge_result else False,
            "unscored": judge_result is None,
            "running_satisfaction": call["running_satisfaction"] if call else None,
            "drift_count": call["drift_count"] if call else None,
        }
