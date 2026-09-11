"""Fallback for pages with no extractable text at all — scanned picture
books, cover pages, anything that's really just an image. Renders the page
and asks a vision-capable model to describe/narrate what's on it, instead
of silently feeding an empty string into everything downstream (which is
exactly what "completely failed" on an image-only PDF).

Provider priority: Gemini (if GEMINI_API_KEY is set — real vision, already
wired for text) > a local Ollama vision model (if pulled) > a clear "can't
read this page" message. Groq's text models here have no vision support at
all, so this is a genuinely separate path from app/brain.py, not another
fallback rung on the same chain.
"""
import requests

from app import config, ollama_client, gemini_provider

# Small, pulled separately from the text model — vision models are a
# different weight class, and not everyone needs one loaded.
LOCAL_VISION_MODEL = "qwen2.5vl:3b"

DESCRIBE_PROMPT = (
    "This is one page of a document with no machine-readable text — likely "
    "a scanned or picture-book page. These are working notes for another "
    "writer, NOT the final text a listener will hear — write them as plain "
    "factual statements of what's in the scene (characters, action, "
    "setting) plus the exact wording of any text that appears in the "
    "image itself (titles, speech, captions), transcribed directly. Do "
    "NOT frame this as 'the image shows' or 'we see' or narrate it as if "
    "speaking to someone — just state the facts plainly, 2-4 sentences. "
    "If the page is genuinely blank, just say so briefly."
)


def _local_model_available() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        names = [m["name"] for m in resp.json().get("models", [])]
        return any(n.startswith(LOCAL_VISION_MODEL.split(":")[0]) for n in names)
    except Exception:
        return False


def describe_page_image(image_bytes: bytes) -> str:
    if config.GEMINI_API_KEY:
        try:
            return gemini_provider.describe_image(image_bytes, DESCRIBE_PROMPT)
        except Exception:
            pass  # fall through to local vision below
    if _local_model_available():
        try:
            return ollama_client.describe_image(image_bytes, DESCRIBE_PROMPT, model=LOCAL_VISION_MODEL)
        except Exception:
            pass
    return (
        "This page has no readable text, and no vision-capable model is "
        "available to describe its image — add a GEMINI_API_KEY to .env, "
        f"or run `ollama pull {LOCAL_VISION_MODEL}` for local image support."
    )
