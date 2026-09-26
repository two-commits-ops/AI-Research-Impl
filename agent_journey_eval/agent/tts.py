"""Groq TTS for the agent's spoken replies. Raises on failure (e.g. the model's
terms not yet accepted in the Groq console) — callers should catch this and
fall back to the browser's own speechSynthesis rather than blocking the call."""

from __future__ import annotations

import os

from groq import Groq

_MODEL = "canopylabs/orpheus-v1-english"
_VOICE = "autumn"
_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def synthesize(text: str) -> bytes:
    response = _get_client().audio.speech.create(
        model=_MODEL, voice=_VOICE, input=text, response_format="mp3"
    )
    return response.read() if hasattr(response, "read") else response.content
