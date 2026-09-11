"""Provider dispatch for the reasoning brain: Groq (fastest, if
GROQ_API_KEY is set) > Gemini (if GEMINI_API_KEY is set) > local Ollama.
See app/config.py. Everything else in the app calls this module, never
groq_provider/gemini_provider/ollama_client directly, so the rest of the
codebase doesn't know or care which one is active.

Falls back down the chain on any provider failure rather than failing the
request outright — tested against a real Gemini free-tier key, which caps
at 5 requests/minute for gemini-3.6-flash and 10/day for its TTS model.
Groq's own failure modes haven't been tested against a real key yet.
"""
import requests
from google.genai.errors import APIError

from app import config, ollama_client, gemini_provider, groq_provider

if config.USE_GROQ:
    MODEL_NAME = groq_provider.MODEL
elif config.USE_GEMINI:
    MODEL_NAME = gemini_provider.TEXT_MODEL
else:
    MODEL_NAME = ollama_client.MODEL


def run_with_tools(system_prompt, user_prompt, tool_defs, tool_impls, max_rounds=4):
    if config.USE_GROQ:
        try:
            return groq_provider.run_with_tools(system_prompt, user_prompt, tool_defs, tool_impls, max_rounds)
        except requests.RequestException:
            pass  # any Groq-side failure — fall through below
    if config.USE_GEMINI:
        try:
            return gemini_provider.run_with_tools(system_prompt, user_prompt, tool_defs, tool_impls, max_rounds)
        except APIError:
            pass  # any Gemini-side failure (rate limit, 500, etc.) — fall back below
    return ollama_client.run_with_tools(system_prompt, user_prompt, tool_defs, tool_impls, max_rounds)


def simple_completion(system_prompt: str, user_prompt: str) -> str:
    if config.USE_GROQ:
        try:
            return groq_provider.simple_completion(system_prompt, user_prompt)
        except requests.RequestException:
            pass
    if config.USE_GEMINI:
        try:
            return gemini_provider.simple_completion(system_prompt, user_prompt)
        except APIError:
            pass
    return ollama_client.simple_completion(system_prompt, user_prompt)
