"""The "auto hook": every event of a call funnels through here and lands in
SQLite. Deliberately framework-agnostic (no Pipecat import) — in Phase 3 a
Pipecat FrameProcessor wraps these same calls instead of this being rewritten.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent.judge import evaluate_turn, summarize_call
from agent.schemas import CallFlow, JudgeResult, TraceEvent
from server import db

log = logging.getLogger(__name__)


class TrajectoryTracer:
    def __init__(self, call_id: str, available_flows: Dict[str, CallFlow], db_path: Path = db.DEFAULT_DB_PATH):
        self.call_id = call_id
        self.available_flows = available_flows
        self.db_path = db_path
        self.turn_index = 0
        # No flow is engaged until the conversation actually gives evidence of
        # one — this is the "pull in a tree based on the conversation" state.
        self.active_flow: Optional[CallFlow] = None
        self.current_node_id: Optional[str] = None
        self._history: list[str] = []
        # Tools called anywhere earlier in THIS call, successfully. Used so a
        # turn that just re-references already-fetched results (e.g. product
        # info already established a couple turns back) isn't wrongly forced
        # into drift for "not calling the tool this turn" — only a tool that
        # was NEVER actually called this whole call is treated as fabricated.
        self.tools_called_ever: set = set()

    def _insert(self, **kwargs) -> TraceEvent:
        event = TraceEvent(call_id=self.call_id, turn_index=self.turn_index, **kwargs)
        db.insert_trace_event(event, self.db_path)
        return event

    def log_user_turn(self, text: str) -> TraceEvent:
        self.turn_index += 1
        event = self._insert(actor="user", event_type="transcript", content=text)
        self._history.append(f"caller: {text}")
        return event

    def log_agent_response(self, text: str, latency_ms: Optional[float] = None) -> TraceEvent:
        event = self._insert(
            actor="agent", event_type="llm_response", content=text, latency_ms=latency_ms
        )
        self._history.append(f"agent: {text}")
        return event

    def log_tool_call(self, tool_name: str, tool_args: Dict[str, Any], arg_issue: Optional[str] = None) -> TraceEvent:
        event = self._insert(
            actor="tool", event_type="tool_call", tool_name=tool_name, tool_args=tool_args, tool_arg_issue=arg_issue
        )
        self._history.append(
            f"[tool_call] {tool_name}({tool_args})" + (f" — WARNING: {arg_issue}" if arg_issue else "")
        )
        return event

    def log_tool_result(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        latency_ms: Optional[float] = None,
        tool_failed: bool = False,
    ) -> TraceEvent:
        event = self._insert(
            actor="tool",
            event_type="tool_result",
            tool_name=tool_name,
            tool_result=tool_result,
            latency_ms=latency_ms,
            tool_failed=tool_failed,
        )
        self._history.append(f"[tool_result] {tool_name} -> {tool_result}")
        if tool_failed:
            db.increment_tool_failure_count(self.call_id, self.db_path)
        else:
            self.tools_called_ever.add(tool_name)
        return event

    def judge_last_turn(
        self,
        event_to_update: TraceEvent,
        latest_user_text: Optional[str],
        latest_agent_text: Optional[str],
        latest_tool_call: Optional[str],
        tool_issue_summary: Optional[str] = None,
        forced_drift_note: Optional[str] = None,
    ) -> JudgeResult:
        old_flow_name = self.active_flow.name if self.active_flow else None
        old_flow_display = self.active_flow.display_name if self.active_flow else None
        other_flows = {name: f for name, f in self.available_flows.items() if name != old_flow_name}

        history_summary = "\n".join(self._history[-12:])
        result = evaluate_turn(
            self.active_flow, other_flows, self.current_node_id, history_summary,
            latest_user_text, latest_agent_text, latest_tool_call, tool_issue_summary,
        )

        # A missing required argument is a certainty, not a judgment call —
        # force it regardless of what the judge concluded on its own.
        if forced_drift_note:
            result.drift_flag = True
            result.drift_note = forced_drift_note

        switched = False
        if result.flow_name and result.flow_name != old_flow_name:
            new_flow = self.available_flows.get(result.flow_name)
            if new_flow is None:
                # Referenced a flow that doesn't exist — that's drift, not a switch.
                result.drift_flag = True
                result.drift_note = result.drift_note or f"The conversation referenced {result.flow_name!r}, which isn't a flow this agent has"
                result.flow_name = None
                result.node_id = None
            else:
                switched = old_flow_name is not None  # None -> something is first engagement, not a "switch"
                self.active_flow = new_flow
                self.current_node_id = None  # entering fresh
                if result.node_id is not None and new_flow.get(result.node_id) is None:
                    # Flow name was real, but the judge invented a node id that
                    # isn't actually in that flow's graph — keep the flow
                    # engaged (that part was legitimate) but don't accept a
                    # made-up position; next turn starts from "no node yet".
                    result.node_id = None
        elif result.flow_name and self.active_flow is not None:
            # Continuing the active flow — verify the graph actually authorizes this move.
            if result.node_id is not None and not self.active_flow.is_valid_transition(self.current_node_id, result.node_id):
                result.drift_flag = True
                current_stage = self.active_flow.get(self.current_node_id) if self.current_node_id else None
                target_stage = self.active_flow.get(result.node_id)
                from_name = current_stage.name if current_stage else "the start"
                to_name = target_stage.name if target_stage else result.node_id
                result.drift_note = result.drift_note or (
                    f"The conversation jumped from {from_name!r} to {to_name!r} without going through "
                    "the steps expected in between"
                )
                result.flow_name = None
                result.node_id = None

        # A stage claiming a tool-driven action (e.g. product_search) is only
        # legitimate if that tool was ACTUALLY called at some point — checked
        # against everything called anywhere in the call so far (not just
        # this turn), so a turn that just re-references results a real call
        # already fetched a few turns back isn't wrongly forced into drift.
        # Checked against every stage implied by a multi-hop move, not just
        # the one landed on, since a turn can pass through product_search on
        # its way to present_options without ever stopping there.
        if result.node_id is not None and self.active_flow is not None:
            path = self.active_flow.path_stages(self.current_node_id, result.node_id)
            missing = [s for s in path if s.expected_tool and s.expected_tool not in self.tools_called_ever]
            if missing:
                result.drift_flag = True
                names = ", ".join(f"{s.name!r} (needs `{s.expected_tool}`)" for s in missing)
                note = f"Reached {names} without that tool ever being called this call — the response may not be grounded in real data"
                result.drift_note = f"{result.drift_note} {note}" if result.drift_note else note

        if switched:
            self._insert(
                actor="system",
                event_type="flow_switch",
                content=f"Switched from {old_flow_display or old_flow_name} to {self.active_flow.display_name}",
            )
            db.update_call_active_flow(self.call_id, result.flow_name, self.db_path)
        elif result.flow_name and old_flow_name is None:
            db.update_call_active_flow(self.call_id, result.flow_name, self.db_path)

        call = db.get_call(self.call_id, self.db_path)
        current_sat = call["running_satisfaction"] if call else 0.5
        new_sat = max(0.0, min(1.0, current_sat + result.satisfaction_delta))

        db.update_trace_event_judge(
            event_to_update.id,
            result.node_id,
            result.flow_name,
            result.drift_flag,
            result.drift_note,
            result.caller_mood,
            new_sat,
            result.profanity_user,
            result.profanity_agent,
            self.db_path,
        )

        db.update_call_signals(
            self.call_id,
            running_satisfaction=new_sat,
            drift_count_increment=1 if result.drift_flag else 0,
            db_path=self.db_path,
        )

        if result.node_id is not None:
            self.current_node_id = result.node_id
        return result

    def end_call(self) -> None:
        db.end_call(self.call_id, self.db_path)
        try:
            self._write_call_summary()
        except Exception as e:
            log.warning("call summary failed for %s: %s", self.call_id, e)

    def _write_call_summary(self) -> None:
        events = db.get_trace_events(self.call_id, self.db_path)
        lines = []
        for e in events:
            if e["event_type"] == "transcript":
                lines.append(f"[turn {e['turn_index']}] caller: {e['content']}")
            elif e["event_type"] == "flow_switch":
                lines.append(f"[turn {e['turn_index']}] {e['content']}")
            elif e["event_type"] == "llm_response":
                where = f"{e.get('flow_name')}/{e.get('stage_actual')}" if e.get("stage_actual") else "off-graph"
                flags = []
                if e.get("drift_flag"):
                    flags.append(f"DRIFT: {e.get('drift_note')}")
                if e.get("profanity_user"):
                    flags.append("profanity(caller)")
                if e.get("profanity_agent"):
                    flags.append("profanity(agent)")
                flag_str = f" [{'; '.join(flags)}]" if flags else ""
                lines.append(
                    f"[turn {e['turn_index']}] agent (node={where}, mood={e.get('caller_mood')}, "
                    f"satisfaction={e.get('satisfaction_after')}): {e['content']}{flag_str}"
                )
            elif e["event_type"] in ("tool_call", "tool_result"):
                lines.append(f"[turn {e['turn_index']}] {e['event_type']} {e['tool_name']}")
        trace_summary = "\n".join(lines)
        if not trace_summary.strip():
            return

        active_name = self.active_flow.name if self.active_flow else "none"
        summary = summarize_call(active_name, trace_summary)
        db.set_call_summary(self.call_id, summary.label, summary.score, summary.reasoning, self.db_path)


def start_call(available_flows: Dict[str, CallFlow], db_path: Path = db.DEFAULT_DB_PATH) -> TrajectoryTracer:
    db.init_db(db_path)
    call_id = db.create_call(db_path)
    return TrajectoryTracer(call_id, available_flows, db_path)
