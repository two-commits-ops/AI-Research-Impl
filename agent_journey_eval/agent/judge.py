"""Offline drift/mood/satisfaction scoring, one Gemini call per turn, plus the
end-of-call summary pass. Runs off the live-conversation hot path (Groq drives
the actual call) so a slower or rate-limited judge call never adds latency to
the agent's replies."""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

from google import genai
from google.genai import errors as genai_errors

from agent.prompts import CALL_SUMMARY_SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT
from agent.schemas import CallFlow, CallSummary, JudgeResult

_MODEL = "gemini-3.1-flash-lite"  # separate free-tier quota bucket from gemini-3.6-flash, which needs billing enabled to be usable at all
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set — see .env.example")
        _client = genai.Client(api_key=api_key)
    return _client


def _generate(prompt: str, system: str, schema) -> dict:
    client = _get_client()
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config={
                    "system_instruction": system,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            return json.loads(response.text)
        except genai_errors.ServerError as e:
            last_error = e
            time.sleep(1.5 * (attempt + 1))  # transient 503s happen; not worth failing a whole turn over
    raise last_error


def evaluate_turn(
    active_flow: Optional[CallFlow],
    other_flows: Dict[str, CallFlow],
    current_node_id: Optional[str],
    history_summary: str,
    latest_user_text: Optional[str],
    latest_agent_text: Optional[str],
    latest_tool_call: Optional[str],
    tool_issue_summary: Optional[str] = None,
) -> JudgeResult:
    if active_flow is None:
        active_desc = "(none — no flow has been engaged by this call yet)"
        edges_desc = "(no active flow)"
        all_nodes_desc = "(no active flow)"
        valid_ids_desc = "(no active flow — if you pick a flow_name below, node_id must be one of THAT flow's exact ids)"
    else:
        current = active_flow.get(current_node_id) if current_node_id else None
        active_desc = f"{active_flow.name} ({active_flow.entry_description})"
        edges_desc = (
            "\n".join(f"- {e.condition!r} -> {e.to}" for e in current.edges)
            if current and current.edges
            else "(none — this is a terminal node or no node is active yet)"
        )
        all_nodes_desc = "\n".join(f"- {s.id}: {s.name} — {s.description}" for s in active_flow.stages)
        valid_ids_desc = ", ".join(s.id for s in active_flow.stages)

    other_flows_desc = (
        "\n".join(
            f"- {name}: {f.entry_description} (its exact node ids: {', '.join(s.id for s in f.stages)})"
            for name, f in other_flows.items()
        )
        if other_flows
        else "(none — this is the only flow this agent has)"
    )

    prompt = f"""Active flow: {active_desc}

Current node: {current_node_id or "(none — call just started or last turn was off this flow)"}
Valid edges from the current node:
{edges_desc}

All nodes in the active flow, for reference:
{all_nodes_desc}

IMPORTANT: node_id must be copied EXACTLY from this list — never invent, paraphrase, or
summarize a node id. Valid ids for the active flow: {valid_ids_desc}

Other flows this agent can handle (for detecting a genuine change of intent):
{other_flows_desc}

Conversation so far (most recent last):
{history_summary}

Latest turn:
- caller said: {latest_user_text!r}
- agent said: {latest_agent_text!r}
- tool called: {latest_tool_call!r}

Verified facts about this turn's tool calls (checked programmatically — trust these completely,
they are not something you need to re-derive from the raw text above):
{tool_issue_summary or "(no tool issues detected)"}

Grade this latest turn."""

    return JudgeResult.model_validate(_generate(prompt, JUDGE_SYSTEM_PROMPT, JudgeResult))


def summarize_call(flow_name: str, trace_summary: str) -> CallSummary:
    prompt = f"""Flow: {flow_name}

Full call trace:
{trace_summary}

Write the final summary."""
    return CallSummary.model_validate(_generate(prompt, CALL_SUMMARY_SYSTEM_PROMPT, CallSummary))
