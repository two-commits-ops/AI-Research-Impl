"""Tool implementations the narration/answer model can call.

get_page_summary / load_page implement the "replace, not accumulate" context
model: the model normally only sees the current page, and reaches for these
when it needs something else. web_search is the one tool call that leaves
the machine (a plain web request, no account, no API key).
"""
import requests
from bs4 import BeautifulSoup


def make_tool_defs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_page_summary",
                "description": "Get a short (1-2 sentence) summary of any page in the document, by page number. Cheap — use this instead of load_page when you just need the gist.",
                "parameters": {
                    "type": "object",
                    "properties": {"page_number": {"type": "integer"}},
                    "required": ["page_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_page",
                "description": "Load the full text of a specific page in the document, by page number. Use this when you need the actual detail from a page other than the current one.",
                "parameters": {
                    "type": "object",
                    "properties": {"page_number": {"type": "integer"}},
                    "required": ["page_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for something not in the document — definitions, current facts, background context. Returns a few short results.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
    ]


def get_page_summary(doc, page_number: int) -> str:
    from app import preprocess  # local import: preprocess also imports nothing from here

    idx = page_number - 1
    if not (0 <= idx < len(doc.pages)):
        return f"page {page_number} does not exist (document has {len(doc.pages)} pages)"
    # Page summaries are created only when a question actually needs them.
    return preprocess.ensure_page_summary(doc, page_number)


def load_page(doc, page_number: int) -> str:
    if 0 <= page_number - 1 < len(doc.pages):
        return doc.page_content(page_number)
    return f"page {page_number} does not exist (document has {len(doc.pages)} pages)"


def _clean_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML results wrap real URLs behind /l/?uddg=<encoded>.
    Unwrap that so the model (and the user) get the actual destination link.
    """
    if href.startswith("//duckduckgo.com/l/") or href.startswith("/l/"):
        from urllib.parse import urlparse, parse_qs, unquote

        qs = parse_qs(urlparse(href).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


def web_search(query: str, max_results: int = 4, sink: list | None = None) -> list[dict]:
    """Keyless web search via DuckDuckGo's HTML endpoint. Each result includes
    the real weblink so the model can cite it and the UI can show it.

    Note: this is a stand-in for "Google search" — genuine Google search
    requires a paid Custom Search API key, which conflicts with the
    no-API-keys goal of this project. DuckDuckGo's HTML search needs no
    key and serves the same purpose for the model.

    `sink`, if given, also collects {title, url} for every result actually
    used this turn — main.py reads it back to show sources under the answer.
    """
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__a")
            snippet_el = result.select_one(".result__snippet")
            if not title_el:
                continue
            url = _clean_ddg_redirect(title_el.get("href", ""))
            item = {
                "title": title_el.get_text(strip=True),
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                "url": url,
            }
            results.append(item)
            if sink is not None:
                sink.append({"title": item["title"], "url": url})
        return results or [{"title": "no results", "snippet": "", "url": ""}]
    except Exception as exc:
        return [{"title": "search failed", "snippet": str(exc), "url": ""}]


MOVE_PAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "move_page",
        "description": (
            "Navigate to a different page, for a spoken navigation command "
            "(e.g. 'next page', 'go back', 'skip ahead two', 'back to the "
            "start', 'go to the last page', 'jump to page 12'). Compute the "
            "absolute target page yourself from the current page and total "
            "page count given in the prompt, then call this with that "
            "number. Only for explicit navigation requests — not for "
            "questions about content."
        ),
        "parameters": {
            "type": "object",
            "properties": {"target_page": {"type": "integer"}},
            "required": ["target_page"],
        },
    },
}


def move_page(doc, target_page: int, navigate_sink: list) -> str:
    clamped = max(1, min(target_page, len(doc.pages)))
    navigate_sink.append(clamped)
    return f"navigated to page {clamped}"


GO_HOME_TOOL = {
    "type": "function",
    "function": {
        "name": "go_home",
        "description": (
            "Leave this document entirely and return to the upload screen "
            "to start over with a new PDF — for commands like 'go home', "
            "'start over', 'upload a new document', 'let's read something "
            "else', 'take me back to the beginning' when it's clear they "
            "mean leaving this document, not turning to its first page "
            "(use move_page for that instead — 'go to the start/beginning' "
            "on its own, with no mention of a new document, means page 1)."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def go_home(home_sink: list) -> str:
    home_sink.append(True)
    return "returning to the upload screen"


def build_tool_impls(
    doc,
    sources_sink: list | None = None,
    navigate_sink: list | None = None,
    home_sink: list | None = None,
) -> dict:
    impls = {
        "get_page_summary": lambda page_number: get_page_summary(doc, page_number),
        "load_page": lambda page_number: load_page(doc, page_number),
        "web_search": lambda query: web_search(query, sink=sources_sink),
    }
    if navigate_sink is not None:
        impls["move_page"] = lambda target_page: move_page(doc, target_page, navigate_sink)
    if home_sink is not None:
        impls["go_home"] = lambda: go_home(home_sink)
    return impls
