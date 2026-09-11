"""Tiny .env loader (no extra dependency) + provider selection.

Local-first by default. Add keys to a `.env` file at the project root (or
real environment variables) to switch providers — no other code change
needed:

- GROQ_API_KEY: fast reasoning. Groq's inference is dramatically faster
  than either local Ollama or Gemini, which matters most for the
  small back-and-forth calls (navigation checks, tool loops). Used for
  the reasoning brain only — Groq isn't a TTS provider here.
- GEMINI_API_KEY: reasoning (if Groq isn't set) + narration audio (Gemini's
  native TTS). Useful for hosting without a local GPU.

Priority for reasoning: Groq > Gemini > local Ollama. Audio always prefers
Gemini TTS over local Kokoro when GEMINI_API_KEY is set, regardless of
which reasoning provider is active — the two are independent.
"""
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


def _load_dotenv():
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
USE_GEMINI = bool(GEMINI_API_KEY)  # governs audio (Gemini TTS) independent of reasoning provider
USE_GROQ = bool(GROQ_API_KEY)  # governs reasoning only
