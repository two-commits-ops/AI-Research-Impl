"""Co-Reader — local FastAPI backend.

Run with: uvicorn app.main:app --port 8765
(see run.sh for the one-command version, which also makes sure Ollama is up)
"""
import hashlib
import json
import logging
import os
import random
import threading
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import pdf_utils, preprocess, narrator, replacements
from app import audio as tts
from app.store import Document, new_doc_id, register, get, ensure_data_dir, DATA_DIR

ensure_data_dir()

app = FastAPI(title="Co-Reader")
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html")) as f:
        return f.read()


def _doc_or_404(doc_id: str) -> Document:
    doc = get(doc_id)
    if doc is None:
        raise HTTPException(404, "unknown document")
    return doc


def _audio_dir(doc: Document) -> str:
    path = os.path.join(doc.dir, "audio")
    os.makedirs(path, exist_ok=True)
    return path


def _audio_url(doc_id: str, filename: str) -> str:
    return f"/api/audio/{doc_id}/{filename}"


class Replacement(BaseModel):
    find: str  # the character's originally-detected name
    replace: str = ""  # rename it's spoken as, if any (empty = keep the original name)
    gender: str = ""  # "male" or "female" to override pronouns; empty = leave as detected/written


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    doc_id = new_doc_id()
    doc_dir = os.path.join(DATA_DIR, doc_id)
    os.makedirs(doc_dir, exist_ok=True)
    pdf_path = os.path.join(doc_dir, "source.pdf")
    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    pages = pdf_utils.extract_pages(pdf_path)
    if not pages:
        raise HTTPException(400, "could not extract any text from this PDF")

    doc = Document(doc_id, pdf_path, pages)
    register(doc)

    # Fast path to the landing screen: one call over the first few pages,
    # not a per-page pass over the whole document.
    threading.Thread(target=preprocess.quick_overview, args=(doc,), daemon=True).start()
    # Deliberately NOT prefetching page 1's narration here. The listener
    # reviews detected characters and can rename any of them on the
    # landing screen before ever reaching the reader — prefetching this
    # early would generate (and pay for) audio using the ORIGINAL names,
    # which is then wasted the moment a rename is set. /touch starts the
    # real prefetch once the reader screen actually opens, by which point
    # any renames are already known and get baked in from the first call.
    return {"doc_id": doc_id, "num_pages": len(pages)}


@app.get("/api/{doc_id}/status")
def status(doc_id: str):
    doc = _doc_or_404(doc_id)
    with doc.lock:
        proc = dict(doc.processing)
    return proc


PREFETCH_PAGES_AHEAD = 2


def _prefetch_narration(
    doc: Document, doc_id: str, page: int, tone: str = tts.DEFAULT_TONE, req_replacements: list[dict] | None = None
):
    """Fire-and-forget: generate one page's narration + audio in the
    background, ahead of anyone pressing play. Cheap to call repeatedly —
    _narrate_and_cache is cached (per page, tone, AND active renames) and
    lock-serialized per page, so a page already done or already in
    progress is a near-instant no-op. Falls back to local Ollama/Kokoro
    automatically if the cloud provider is unavailable or rate-limited
    (see app/brain.py, app/audio.py).
    """
    def run():
        try:
            _narrate_and_cache(doc, doc_id, page, tone, req_replacements or [])
        except Exception:
            pass  # best-effort; a direct /narrate call will just try again

    threading.Thread(target=run, daemon=True).start()


def _prefetch_ahead(
    doc: Document, doc_id: str, from_page: int, tone: str, req_replacements: list[dict], ahead: int = PREFETCH_PAGES_AHEAD
):
    for p in range(from_page, min(from_page + ahead, len(doc.pages)) + 1):
        _prefetch_narration(doc, doc_id, p, tone, req_replacements)


@app.post("/api/{doc_id}/touch")
def touch(doc_id: str, page: int, tone: str = tts.DEFAULT_TONE, replacements_json: str = "[]"):
    """The frontend calls this whenever the visible page changes (passing
    whatever voice AND pronunciation renames are currently active): buffers
    this page and the next couple ahead of it in that exact voice+renames
    combination, so moving forward almost always finds audio already
    waiting instead of a fresh wait. This is also what makes page 1 fast
    the first time: it's the reader screen opening — after the listener
    has already reviewed and renamed characters on the landing screen —
    that starts prefetching, not the upload itself, so the very first
    buffered audio already has any renames baked in rather than needing to
    be redone.

    `replacements_json` is a JSON-encoded list of {find, replace} objects
    (kept as a plain string param rather than a body, since this is a
    simple fire-and-forget GET-shaped ping, not a form the caller waits on).
    """
    doc = _doc_or_404(doc_id)
    doc.reader_opened.set()
    try:
        req_replacements = json.loads(replacements_json)
    except (json.JSONDecodeError, TypeError):
        req_replacements = []
    _prefetch_ahead(doc, doc_id, page, tone, req_replacements)
    return {"ok": True}


@app.get("/api/{doc_id}/summary")
def summary(doc_id: str):
    doc = _doc_or_404(doc_id)
    if doc.doc_summary is None:
        return {"ready": False}
    return {
        "ready": True,
        "text": doc.doc_summary,
        "terms": doc.detected_terms,
        "terms_ready": doc.terms_ready,
    }


@app.get("/api/{doc_id}/summary/audio")
def summary_audio(doc_id: str, tone: str = tts.DEFAULT_TONE):
    doc = _doc_or_404(doc_id)
    if doc.doc_summary is None:
        raise HTTPException(409, "summary not ready yet")
    if tone not in doc.doc_summary_audio:
        filename = f"summary_{tone}.wav"
        try:
            tts.synthesize(doc.doc_summary, os.path.join(_audio_dir(doc), filename), tone=tone)
        except Exception as exc:
            logger.exception("Could not synthesize document overview")
            raise HTTPException(503, "Audio is unavailable right now. Please try again in a moment.") from exc
        doc.doc_summary_audio[tone] = filename
    return {"audio_url": _audio_url(doc_id, doc.doc_summary_audio[tone])}


@app.get("/api/{doc_id}/wrapup")
def wrapup(doc_id: str, tone: str = tts.DEFAULT_TONE):
    """Called once the listener reaches the last page: a short recap of
    what was actually covered, plus an invitation to ask something,
    revisit a page, or start a new document. Generated once per document,
    then cached — like the landing overview, just for the other end.
    """
    doc = _doc_or_404(doc_id)
    if doc.wrapup_text is None:
        try:
            doc.wrapup_text = narrator.wrap_up(doc)
        except Exception as exc:
            logger.exception("Could not generate wrap-up")
            raise HTTPException(503, "Could not put together a wrap-up right now.") from exc
    if tone not in doc.wrapup_audio:
        filename = f"wrapup_{tone}.wav"
        try:
            tts.synthesize(doc.wrapup_text, os.path.join(_audio_dir(doc), filename), tone=tone)
        except Exception as exc:
            logger.exception("Could not synthesize wrap-up")
            raise HTTPException(503, "Audio is unavailable right now. Please try again in a moment.") from exc
        doc.wrapup_audio[tone] = filename
    return {"text": doc.wrapup_text, "audio_url": _audio_url(doc_id, doc.wrapup_audio[tone])}


@app.get("/api/{doc_id}/pdf")
def pdf(doc_id: str):
    doc = _doc_or_404(doc_id)
    return FileResponse(doc.pdf_path, media_type="application/pdf")


@app.get("/api/audio/_filler/{filename}")
def filler_audio_file(filename: str):
    path = os.path.join(_FILLER_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "no such audio file")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/audio/{doc_id}/{filename}")
def audio_file(doc_id: str, filename: str):
    doc = _doc_or_404(doc_id)
    path = os.path.join(_audio_dir(doc), filename)
    if not os.path.exists(path):
        raise HTTPException(404, "no such audio file")
    return FileResponse(path, media_type="audio/wav")


class NarrateRequest(BaseModel):
    page: int
    tone: str = tts.DEFAULT_TONE
    replacements: list[Replacement] = []


def _replacements_key(req_replacements: list[dict]) -> str:
    """A stable, short cache-key fragment for a set of renames+genders —
    order and case shouldn't matter to whether two requests count as "the
    same" customization. "none" for the common case of nothing active.
    Gender is part of this fingerprint (not just the rename): it changes
    the model's own pronoun choice during generation, so it's a real
    dimension of "which text is this", not a cosmetic detail.
    """
    if not req_replacements:
        return "none"
    normalized = sorted(
        (r["find"].strip().lower(), r.get("replace", "").strip(), r.get("gender", "").strip().lower())
        for r in req_replacements
    )
    return hashlib.sha1(json.dumps(normalized).encode()).hexdigest()[:10]


def _gender_notes(req_replacements: list[dict]) -> list[dict]:
    return [
        {"name": r["find"], "gender": r["gender"]}
        for r in req_replacements
        if r.get("gender") in ("male", "female")
    ]


def _narrate_and_cache(doc: Document, doc_id: str, page: int, tone: str, req_replacements: list[dict]):
    """Shared by direct narration requests and the background prefetch —
    produces {text, segments: [{text, audio_url}], sources}.

    Locked per page so simultaneous calls (a prefetch and a direct click,
    or two prefetches) serialize instead of doing the LLM+TTS work twice.
    Both the TEXT and its audio are cached per (page, active renames AND
    genders) — genders affect the model's own generation, not just a
    post-hoc substitution, so a different gender setup is a genuinely
    different piece of narrated text, not the same text with a swap
    applied on top.
    """
    fingerprint = _replacements_key(req_replacements)
    text_key = f"{page}:{fingerprint}"

    with doc.page_lock(page):
        if text_key in doc.transcripts:
            raw_text = doc.transcripts[text_key]
            sources = doc.transcript_sources.get(text_key, [])
        else:
            raw_text, sources = narrator.narrate_page(doc, page, gender_notes=_gender_notes(req_replacements))
            doc.transcripts[text_key] = raw_text
            doc.transcript_sources[text_key] = sources

        text = replacements.apply(raw_text, req_replacements)

        audio_cache = doc.transcript_audio.setdefault(text_key, {})
        if tone not in audio_cache:
            prefix = f"page_{page}_{fingerprint}_{tone}"
            audio_cache[tone] = tts.synthesize_segments(text, _audio_dir(doc), prefix, tone=tone)
        segs = audio_cache[tone]

    segments = [{"text": s["text"], "audio_url": _audio_url(doc_id, s["filename"])} for s in segs]
    return {"page": page, "text": text, "segments": segments, "sources": sources}


@app.post("/api/{doc_id}/narrate")
def narrate(doc_id: str, req: NarrateRequest):
    doc = _doc_or_404(doc_id)
    page = req.page
    if not (1 <= page <= len(doc.pages)):
        raise HTTPException(400, "page out of range")

    req_replacements = [r.model_dump() for r in req.replacements]
    try:
        result = _narrate_and_cache(doc, doc_id, page, req.tone, req_replacements)
    except Exception as exc:
        logger.exception("Could not narrate page %s", page)
        raise HTTPException(503, "Could not create audio for this page. Please try again.") from exc

    return result


# Short, natural things a person says right before actually answering —
# played instantly while the real answer is still being generated, so a
# question gets an immediate, engaged response instead of dead air.
FILLER_PHRASES = [
    "Hmm, let me check.",
    "Good question — one sec.",
    "Let me take a look.",
    "Let's see here.",
    "One moment, let me look that up.",
]
_FILLER_DIR = os.path.join(DATA_DIR, "_filler")
_filler_cache: dict[str, list[str]] = {}


def _ensure_filler(tone: str) -> list[str]:
    os.makedirs(_FILLER_DIR, exist_ok=True)
    urls = _filler_cache.get(tone)
    if urls is None:
        urls = []
        for i, phrase in enumerate(FILLER_PHRASES):
            filename = f"{tone}_{i}.wav"
            path = os.path.join(_FILLER_DIR, filename)
            if not os.path.exists(path):
                try:
                    tts.synthesize(phrase, path, tone=tone)
                except Exception:
                    logger.exception("Could not pre-render filler phrase")
                    continue
            urls.append(f"/api/audio/_filler/{filename}")
        _filler_cache[tone] = urls
    return urls


@app.on_event("startup")
def _prewarm_default_filler():
    # Generate these once at boot, not on a viewer's first question — the
    # whole point is that it plays instantly.
    threading.Thread(target=_ensure_filler, args=(tts.DEFAULT_TONE,), daemon=True).start()


@app.get("/api/filler")
def filler(tone: str = tts.DEFAULT_TONE):
    urls = _ensure_filler(tone)
    if not urls:
        raise HTTPException(503, "no filler audio available")
    return {"audio_url": random.choice(urls)}


class AskRequest(BaseModel):
    page: int
    question: str
    tone: str = tts.DEFAULT_TONE
    replacements: list[Replacement] = []


@app.post("/api/{doc_id}/ask")
def ask(doc_id: str, req: AskRequest):
    doc = _doc_or_404(doc_id)
    if not (1 <= req.page <= len(doc.pages)):
        raise HTTPException(400, "page out of range")

    req_replacements = [r.model_dump() for r in req.replacements]
    try:
        answer, sources, navigate_to, go_home = narrator.answer_question(
            doc, req.page, req.question, gender_notes=_gender_notes(req_replacements)
        )
    except Exception as exc:
        logger.exception("Could not answer question about page %s", req.page)
        raise HTTPException(503, "Could not answer that right now. Please try again.") from exc
    answer = replacements.apply(answer, req_replacements)
    filename = f"ask_{uuid.uuid4().hex[:8]}.wav"
    try:
        tts.synthesize(answer, os.path.join(_audio_dir(doc), filename), tone=req.tone)
    except Exception as exc:
        logger.exception("Could not synthesize answer for page %s", req.page)
        raise HTTPException(503, "I found an answer but could not create its audio. Please try again.") from exc
    return {
        "answer": answer,
        "audio_url": _audio_url(doc_id, filename),
        "sources": sources,
        "navigate_to": navigate_to,
        "go_home": go_home,
    }
