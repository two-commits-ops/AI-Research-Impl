"""Preprocessing, latency-first: a fast whole-document overview up front,
then per-page summaries generated lazily — prefetched just ahead of
wherever the listener actually is, never all up front. A 500-page PDF and
a 5-page one both reach the landing screen in about the same time.
"""
import threading

from app.store import Document
from app import brain

OVERVIEW_PROMPT = (
    "Here is the beginning of a document. Write a short, engaging spoken "
    "overview (100-150 words) of what it likely covers overall — plain "
    "prose, no bullet points, no headings, suitable to be read aloud before "
    "someone starts reading."
)

TERMS_PROMPT = (
    "Here is the beginning of a document. ONLY if this is a work of "
    "fiction (a novel, short story, screenplay, children's book, etc.) "
    "with named characters, list up to 8 of them — strictly named "
    "characters who act in the story, nothing else: no places, objects, "
    "organizations, paper/book titles, author names, or technical terms. "
    "A character can be a person OR a named animal/creature who talks and "
    "acts like one (very common in children's stories) — either counts. "
    "If this is not fiction, or is fiction with no named characters, "
    "there is nothing to list.\n\n"
    "For each character, give: their name; their gender as exactly one of "
    "male, female, or unknown (use unknown if the text never indicates "
    "it, or it genuinely doesn't apply); and a short (5-10 word) "
    "description of who they are, so the reader knows who's being renamed. "
    "Reply with ONE character per line, formatted exactly as:\n"
    "Name — gender — short description\n"
    "Nothing else — no numbering, no headings, no extra commentary. If "
    "there's nothing to list, reply with exactly: no character found"
)

_FIELD_SEPARATORS = (" — ", " – ", " - ", ": ")
_VALID_GENDERS = {"male", "female", "unknown"}


def _split_field(line: str) -> tuple[str, str]:
    for sep in _FIELD_SEPARATORS:
        if sep in line:
            head, rest = line.split(sep, 1)
            return head.strip(), rest.strip()
    return line.strip(), ""


def _parse_characters(raw: str) -> list[dict]:
    """Parses "Name — gender — short description" lines into
    [{"name", "gender", "description"}, ...]. Tolerant of which dash/colon
    style the model used, and of it dropping the gender field entirely
    (older prompt shape, or a model that just forgets) — falls back to
    "unknown" rather than misreading the description as a gender.
    """
    characters = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        name, rest = _split_field(line)
        gender, description = _split_field(rest)
        if gender.strip(".").lower() not in _VALID_GENDERS:
            # No real gender field present — what we split off as "gender"
            # was actually (the start of) the description.
            description = rest
            gender = "unknown"
        else:
            gender = gender.strip(".").lower()
        name, description = name.strip(), description.strip()
        if name:
            characters.append({"name": name, "gender": gender, "description": description})
    return characters


PAGE_SUMMARY_PROMPT = (
    "Summarize this page of a document in exactly one short sentence "
    "(max ~20 words). Just the sentence, no preamble."
)

# Keep just one lightweight page summary ahead.  Generating several model
# requests at once made the reader feel slower than doing no prefetching at
# all—especially when the optional cloud provider is rate-limited.
PREFETCH_AHEAD = 1


CONTEXT_PAGES = 10  # how many content-bearing pages to gather for character detection
_MAX_VISION_PAGES = 3  # describing an image page is much slower than reading text — cap it


def _gather_context_pages(doc: Document, max_pages: int = CONTEXT_PAGES) -> str:
    """Collects text from up to `max_pages` pages that actually have
    something on them — skipping genuinely blank ones — so character
    detection sees enough of the story to find names that don't show up
    on page 1 (a cover) or page 2 (a title page). Real extracted text is
    free to gather from every page in range; a page with none needs a
    vision call to describe its image, which is much slower, so that path
    is capped at a few pages regardless of `max_pages`.
    """
    chunks = []
    vision_used = 0
    for i in range(min(max_pages, len(doc.pages))):
        text = doc.pages[i]
        if not text.strip():
            if vision_used >= _MAX_VISION_PAGES:
                continue
            text = doc.page_content(i + 1)  # renders + describes + caches this page's image
            vision_used += 1
        if text.strip():
            chunks.append(text)
    return "\n\n".join(chunks)[:8000]


def quick_overview(doc: Document):
    """Two quick model calls over the opening content-bearing pages — the
    overview, and a scan for characters worth offering pronunciation/gender
    fixes for.

    Run in PARALLEL, not sequentially: measured back-to-back, these two
    calls took 27+ seconds combined (each ~13-14s) and kept the landing
    screen blocked that whole time for no reason — neither call depends on
    the other. In parallel the wait is roughly whichever one is slower,
    not their sum. The overview alone gates the landing screen; terms are
    filled in whenever they finish, even a beat later.
    """
    lead_text = _gather_context_pages(doc)

    def run_overview():
        try:
            doc.doc_summary = brain.simple_completion(OVERVIEW_PROMPT, lead_text)
        except Exception as exc:
            doc.doc_summary = f"(overview unavailable: {exc})"
        with doc.lock:
            doc.processing["status"] = "done"
        doc.save_meta()

    def run_terms():
        try:
            raw = brain.simple_completion(TERMS_PROMPT, lead_text)
            normalized = raw.strip().lower()
            # Be lenient about how "nothing to list" comes back — models
            # don't always echo the exact sentinel phrase.
            if not raw.strip() or "no character" in normalized or normalized == "none":
                doc.detected_terms = []
            else:
                doc.detected_terms = _parse_characters(raw)[:8]
        except Exception:
            doc.detected_terms = []
        finally:
            doc.terms_ready = True

    overview_thread = threading.Thread(target=run_overview, daemon=True)
    terms_thread = threading.Thread(target=run_terms, daemon=True)
    overview_thread.start()
    terms_thread.start()
    overview_thread.join()
    # Don't join terms_thread — the landing screen doesn't need to wait for
    # it; app/main.py's /summary response just reflects whatever's there.


def _summarize_one(doc: Document, idx: int):
    page_text = doc.page_content(idx + 1)
    if not page_text.strip():
        summary = "(blank page)"
    else:
        try:
            summary = brain.simple_completion(PAGE_SUMMARY_PROMPT, page_text[:3000])
        except Exception as exc:
            summary = f"(summary unavailable: {exc})"
    doc.page_summaries[idx] = summary
    with doc.lock:
        doc.summarizing.discard(idx)


def ensure_page_summary(doc: Document, page_number: int) -> str:
    """Synchronous, on-demand fallback: guarantees a summary exists even if
    prefetch hasn't reached this page yet (e.g. the model jumps far ahead).
    """
    idx = page_number - 1
    if not (0 <= idx < len(doc.pages)):
        return f"page {page_number} does not exist"
    if doc.page_summaries[idx] is not None:
        return doc.page_summaries[idx]
    _summarize_one(doc, idx)
    return doc.page_summaries[idx]


def prefetch_ahead(doc: Document, from_page: int, ahead: int = PREFETCH_AHEAD):
    """Fire-and-forget: kicks off background threads to summarize the next
    few not-yet-summarized pages. Safe to call on every page turn — pages
    already done or already in progress are skipped.
    """
    last = min(from_page - 1 + ahead, len(doc.pages) - 1)
    for idx in range(max(from_page - 1, 0), last + 1):
        with doc.lock:
            if doc.page_summaries[idx] is not None or idx in doc.summarizing:
                continue
            doc.summarizing.add(idx)
        threading.Thread(target=_summarize_one, args=(doc, idx), daemon=True).start()
