"""Provider dispatch for narration audio: Kokoro (local, default) or
Gemini's native TTS (when GEMINI_API_KEY is set). See app/brain.py for the
same pattern, including the rate-limit fallback, on the reasoning side.
"""
from google.genai.errors import APIError

from app import config, gemini_provider

DEFAULT_TONE = "warm"
TONES = gemini_provider.TONES if config.USE_GEMINI else None


def _local_tts():
    """Load the Apple-Silicon TTS backend only when it is actually needed.

    A Gemini-configured reader should still be able to start when the local
    MLX runtime is unavailable; it only needs MLX if Gemini fails and we
    attempt the local fallback.
    """
    from app import tts
    return tts


if TONES is None:
    TONES = _local_tts().TONES


def synthesize(text: str, out_path: str, tone: str = DEFAULT_TONE) -> None:
    if config.USE_GEMINI:
        try:
            return gemini_provider.synthesize(text, out_path, tone)
        except APIError:
            pass  # any Gemini-side failure — fall back to local Kokoro below
    return _local_tts().synthesize(text, out_path, tone)


def synthesize_segments(text: str, out_dir: str, prefix: str, tone: str = DEFAULT_TONE) -> list[dict]:
    if config.USE_GEMINI:
        try:
            return gemini_provider.synthesize_segments(text, out_dir, prefix, tone)
        except APIError:
            pass
    return _local_tts().synthesize_segments(text, out_dir, prefix, tone)
