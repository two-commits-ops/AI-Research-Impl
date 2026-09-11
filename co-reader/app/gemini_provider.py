"""Optional cloud provider: Gemini for both the reasoning brain (function
calling + Gemini's own built-in Google Search grounding — no DuckDuckGo
scraping needed) and narration audio (Gemini's native TTS).

Only active when GEMINI_API_KEY is set (see app/config.py). Not exercised
by local testing in this session — no key was available to validate
against a live response. Wire it in, drop a real key in .env, and try a
narration + a "what's the weather" question to confirm before relying on
it; the local Ollama+Kokoro path is the one that's actually been tested.
"""
import os

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

_client = None

TEXT_MODEL = "gemini-3.6-flash"
TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Gemini's prebuilt TTS voices, curated the same way Kokoro's were.
TONES = {
    "warm": "Kore",
    "calm": "Charon",
    "bright": "Puck",
    "deep": "Fenrir",
    "classic": "Orus",
}
DEFAULT_TONE = "warm"

# Natural-language style prompts — Gemini's TTS is steerable by instruction,
# unlike a fixed voice id, so "tone" also shapes delivery, not just timbre.
STYLE_HINTS = {
    "warm": "Say this warmly and patiently, like a favorite teacher explaining something to a student they like.",
    "calm": "Say this slowly and calmly, like a quiet, reassuring narrator.",
    "bright": "Say this with light energy and enthusiasm, like an engaging presenter.",
    "deep": "Say this in a deep, measured, documentary-narrator voice.",
    "classic": "Say this in a clear, neutral, classic audiobook-narrator voice.",
}


def _get_client():
    global _client
    if _client is None:
        # attempts=1: fail on the first 429/5xx instead of the SDK's default
        # exponential-backoff retries. On a rate-limited free-tier key those
        # retries added many extra seconds per call before app/brain.py's
        # own fallback to local Ollama/Kokoro ever got a chance to run —
        # better to fall back immediately than wait through a retry that's
        # very likely to fail again anyway.
        http_options = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        _client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_options)
    return _client


def _to_gemini_function_declarations(tool_defs: list[dict]) -> list[types.FunctionDeclaration]:
    decls = []
    for t in tool_defs:
        fn = t["function"]
        decls.append(
            types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters_json_schema=fn.get("parameters", {}),
            )
        )
    return decls


def run_with_tools(
    system_prompt: str,
    user_prompt: str,
    tool_defs: list[dict],
    tool_impls: dict,
    max_rounds: int = 4,
) -> str:
    """Same contract as ollama_client.run_with_tools: a small manual agent
    loop over our own tools (get_page_summary / load_page / web_search /
    move_page). Gemini's built-in Google Search grounding tool was tried
    and dropped — it needs a billing-enabled tier and 429'd on a free-tier
    key even in isolation; our own web_search tool works everywhere.
    """
    client = _get_client()
    function_decls = _to_gemini_function_declarations(tool_defs)
    # Deliberately NOT using Gemini's built-in google_search tool here: it
    # requires a billing-enabled tier and returned 429 RESOURCE_EXHAUSTED
    # on a free-tier key in testing, even standing alone. Our own
    # web_search (DuckDuckGo, in tool_defs/tool_impls already) works on any
    # key and gives the same real-URL citations.
    tools = [types.Tool(function_declarations=function_decls)]

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]
    config = types.GenerateContentConfig(system_instruction=system_prompt, tools=tools)

    for _ in range(max_rounds):
        response = client.models.generate_content(model=TEXT_MODEL, contents=contents, config=config)
        candidate = response.candidates[0]
        function_calls = [p.function_call for p in candidate.content.parts if p.function_call]

        if not function_calls:
            return (response.text or "").strip()

        contents.append(candidate.content)
        response_parts = []
        for call in function_calls:
            fn = tool_impls.get(call.name)
            try:
                result = fn(**dict(call.args)) if fn else f"unknown tool: {call.name}"
            except Exception as exc:
                result = f"tool error: {exc}"
            if not isinstance(result, dict):
                result = {"result": result}
            response_parts.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=response_parts))

    final = client.models.generate_content(model=TEXT_MODEL, contents=contents)
    return (final.text or "").strip()


def simple_completion(system_prompt: str, user_prompt: str) -> str:
    client = _get_client()
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return (response.text or "").strip()


def describe_image(image_bytes: bytes, prompt: str) -> str:
    """Vision call for pages with no extractable text (scanned/picture-book
    pages) — see app/vision.py, the only caller. Gemini's models are
    natively multimodal, so this is the same generate_content call as
    simple_completion with an image Part added, not a separate API.
    """
    client = _get_client()
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/png"), prompt],
    )
    return (response.text or "").strip()


def synthesize(text: str, out_path: str, tone: str = DEFAULT_TONE) -> None:
    """Writes narration audio for `text` via Gemini's native TTS."""
    client = _get_client()
    voice = TONES.get(tone, TONES[DEFAULT_TONE])
    style = STYLE_HINTS.get(tone, STYLE_HINTS[DEFAULT_TONE])

    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=f"{style}\n\n{text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
            ),
        ),
    )
    audio_bytes = response.candidates[0].content.parts[0].inline_data.data
    # Gemini TTS returns raw 24kHz 16-bit PCM — wrap it as a playable WAV.
    import wave

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(audio_bytes)


def synthesize_segments(text: str, out_dir: str, prefix: str, tone: str = DEFAULT_TONE) -> list[dict]:
    """One call for the whole page, not one per sentence.

    Unlike Kokoro, Gemini's TTS is steerable by instruction (the style hint
    above) and paces itself — and a free-tier key is capped at 5
    requests/minute, so five sentence-level calls per page would burn the
    entire per-minute budget on a single page. A single segment plays back
    identically to the frontend either way.
    """
    filename = f"{prefix}_0.wav"
    synthesize(text, os.path.join(out_dir, filename), tone=tone)
    return [{"text": text, "filename": filename}]
