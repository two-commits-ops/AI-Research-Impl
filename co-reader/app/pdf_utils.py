"""PDF text extraction and, for pages with no text at all, page rendering
so they can be handed to a vision model instead (see app/vision.py).
"""
import io

import pymupdf
from pypdf import PdfReader


def extract_pages(pdf_path: str) -> list[str]:
    """Return a list of plain-text strings, one per page. A page with no
    real text layer at all (scanned, or a pure picture-book page) comes
    back as an empty string here — app/vision.py is the fallback for those,
    not this function.
    """
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    return pages


def render_page_png(pdf_path: str, page_index: int, max_dim: int = 1024) -> bytes:
    """Rasterizes one page (0-indexed) to PNG bytes, scaled so its longer
    side is about `max_dim` px — plenty for a vision model to read both
    illustrations and any in-image text, without sending a huge payload.
    """
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_index]
        scale = max_dim / max(page.rect.width, page.rect.height)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        return pixmap.tobytes("png")
