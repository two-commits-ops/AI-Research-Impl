"""Thin client around the local Ollama server, with a small tool-calling loop.

Nothing here ever leaves the machine: it only talks to http://localhost:11434,
which is Ollama serving locally-downloaded model weights.
"""
import base64
import json
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """One raw call to Ollama's chat endpoint. Returns the response message dict."""
    payload = {"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.3}}
    if tools:
        payload["tools"] = tools
    resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["message"]


def run_with_tools(
    system_prompt: str,
    user_prompt: str,
    tools: list[dict],
    tool_impls: dict,
    max_rounds: int = 4,
) -> str:
    """Runs a small agent loop: the model may call tools (silently, server-side)
    before producing its final text answer. Returns just the final text.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(max_rounds):
        message = chat(messages, tools=tools)
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            return (message.get("content") or "").strip()

        # The assistant asked to call one or more tools — execute them locally
        # and feed the results back, then let it continue.
        messages.append(message)
        for call in tool_calls:
            fn = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            try:
                result = tool_impls[fn](**args)
            except Exception as exc:  # keep the loop alive even if a tool fails
                result = f"tool error: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result) if not isinstance(result, str) else result,
                }
            )

    # Ran out of rounds — ask once more for a final answer with no tools offered.
    final = chat(messages, tools=None)
    return (final.get("content") or "").strip()


def describe_image(image_bytes: bytes, prompt: str, model: str) -> str:
    """One-shot vision call to a local Ollama vision model (e.g.
    qwen2.5vl) — separate from `chat`'s text MODEL constant since a vision
    model is a different weight class, pulled separately.
    """
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(image_bytes).decode()]}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json()["message"].get("content") or "").strip()


def simple_completion(system_prompt: str, user_prompt: str) -> str:
    """Plain, tool-free call — used for the batch preprocessing pass."""
    message = chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return (message.get("content") or "").strip()
