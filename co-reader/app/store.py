"""In-memory + on-disk state for uploaded documents.

Single-user local app: one process, simple dicts, good enough. Everything
also lands on disk under data/<doc_id>/ so it survives a server restart.
"""
import json
import os
import threading
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class Document:
    def __init__(self, doc_id: str, pdf_path: str, pages: list[str]):
        self.doc_id = doc_id
        self.pdf_path = pdf_path
        self.pages = pages
        self.page_summaries: list[str | None] = [None] * len(pages)
        self.summarizing: set[int] = set()  # page indices currently being summarized
        self.doc_summary: str | None = None
        self.detected_terms: list[dict] = []  # [{"name", "gender", "description"}, ...]
        # Character detection runs in parallel with the overview and isn't
        # awaited before the landing screen can show — it's frequently NOT
        # done yet at that moment. Without this flag, an empty list reads
        # as "no characters found" instead of "still looking", and the
        # frontend has no way to tell the two apart or know to check again.
        self.terms_ready = False
        self.doc_summary_audio: dict[str, str] = {}  # tone -> wav filename
        self.wrapup_text: str | None = None  # generated once, when the reader reaches the last page
        self.wrapup_audio: dict[str, str] = {}  # tone -> wav filename
        # Keyed by "{page}:{gender_key}", not just page — which character
        # genders are active changes the model's own word choice (pronouns),
        # not just a post-hoc text substitution, so it's a real cache
        # dimension: two different gender setups for the same page are two
        # different pieces of narrated text, not the same text with a swap
        # applied. See app/main.py's _cache_key.
        self.transcripts: dict[str, str] = {}
        self.transcript_sources: dict[str, list[dict]] = {}
        self.transcript_audio: dict[str, dict[str, str]] = {}  # cache_key -> {tone: wav filename}
        self.image_descriptions: dict[int, str] = {}  # page -> vision description, for image-only pages
        self.processing = {"status": "processing", "current": 0, "total": len(pages)}
        self.lock = threading.Lock()
        # Set as soon as the reader opens.  The optional landing overview may
        # finish, but it should not begin lower-priority follow-up work while
        # someone is already trying to read and listen.
        self.reader_opened = threading.Event()
        self._page_locks: dict[int, threading.Lock] = {}
        self._page_locks_lock = threading.Lock()

    def page_lock(self, page: int) -> threading.RLock:
        """One lock per page, created on demand, so simultaneous work on
        the same page does not duplicate an expensive generation.

        Reentrant (RLock), not a plain Lock: narrate_page's own text
        generation can call back into page_content for the SAME page (a
        scanned page with no text needs its image described first) while
        _narrate_and_cache is still holding this exact lock — a plain Lock
        would have the one thread block forever waiting on itself. This
        was a real, reproduced deadlock: any narrate() call on an
        image-only page hung indefinitely until this was an RLock.
        """
        with self._page_locks_lock:
            if page not in self._page_locks:
                self._page_locks[page] = threading.RLock()
            return self._page_locks[page]

    def page_content(self, page_number: int) -> str:
        """The text to actually use for this page — the real extracted
        text where there is any, otherwise a one-time vision description
        of the rendered page (cached after the first call). This is what
        every LLM call reads instead of `self.pages[...]` directly, so a
        scanned/picture-only page narrates something real instead of
        silently getting fed an empty string.
        """
        idx = page_number - 1
        if not (0 <= idx < len(self.pages)):
            return ""
        text = self.pages[idx]
        if text.strip():
            return text
        with self.page_lock(page_number):
            if page_number in self.image_descriptions:
                return self.image_descriptions[page_number]
            from app import pdf_utils, vision  # local: avoids a store<->pdf_utils/vision import cycle

            try:
                image_bytes = pdf_utils.render_page_png(self.pdf_path, idx)
                description = vision.describe_page_image(image_bytes)
            except Exception as exc:
                description = f"(could not read this page's image: {exc})"
            self.image_descriptions[page_number] = description
            return description

    @property
    def dir(self) -> str:
        return os.path.join(DATA_DIR, self.doc_id)

    def save_meta(self):
        meta = {
            "doc_id": self.doc_id,
            "num_pages": len(self.pages),
            "page_summaries": self.page_summaries,
            "doc_summary": self.doc_summary,
        }
        with open(os.path.join(self.dir, "meta.json"), "w") as f:
            json.dump(meta, f)


_DOCS: dict[str, Document] = {}


def new_doc_id() -> str:
    return uuid.uuid4().hex[:12]


def register(doc: Document):
    _DOCS[doc.doc_id] = doc


def get(doc_id: str) -> Document | None:
    return _DOCS.get(doc_id)


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
