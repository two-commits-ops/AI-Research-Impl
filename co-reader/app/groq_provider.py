"""Fast reasoning via Groq's OpenAI-compatible API.

Groq's inference is dramatically faster than local Ollama or Gemini — it's
the fix for "the thinker feels slow." Reasoning only: Groq isn't used here
for narration audio (see app/audio.py — that stays Gemini/Kokoro).

Not exercised by local testing in this session — no key was available.
Wire it in, drop a real key in .env as GROQ_API_KEY, and try a narration +
a navigation command + a web-search question to confirm before relying on
it; app/brain.py falls back to Gemini/Ollama on any failure either way.
"""
import json

import requests

from app.config import GROQ_API_KEY

API_URL = "https://api.groq.com/openai/v1/chat/completions"
# OpenAI's open-weight model, served on Groq's hardware — chosen after
# `llama-3.3-70b-versatile` (the original pick) came back 404'd as
# retired; checked GET /openai/v1/models against a real key to find what's
# actually available now. gpt-oss is OpenAI's own tool-calling-trained
# family, which matters more here than raw size. If this is ever retired
# too, the same models-list call finds its replacement.
MODEL = "openai/gpt-oss-120b"


def _to_openai_tools(tool_defs: list[dict]) -> list[dict]:
    # Our tool_defs are already in this exact {"type":"function","function":
    # {...}} shape (it's what Ollama's API also uses) — Groq's is identical.
    return tool_defs


def _chat(messages: list[dict], tools: list[dict] | None) -> dict:
    payload = {"model": MODEL, "messages": messages, "temperature": 0.3}
    if tools:
        payload["tools"] = _to_openai_tools(tools)
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def run_with_tools(
    system_prompt: str,
    user_prompt: str,
    tool_defs: list[dict],
    tool_impls: dict,
    max_rounds: int = 4,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    for _ in range(max_rounds):
        message = _chat(messages, tool_defs)
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return (message.get("content") or "").strip()

        messages.append(message)
        for call in tool_calls:
            fn_name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = tool_impls[fn_name](**args) if fn_name in tool_impls else f"unknown tool: {fn_name}"
            except Exception as exc:
                result = f"tool error: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result) if not isinstance(result, str) else result,
                }
            )

    final = _chat(messages, None)
    return (final.get("content") or "").strip()


def simple_completion(system_prompt: str, user_prompt: str) -> str:
    message = _chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        None,
    )
    return (message.get("content") or "").strip()
