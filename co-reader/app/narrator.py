"""The narration/answering "brain".

Today this is Ollama (Qwen2.5-7B) with real tool calling. The interface is
deliberately narrow (two functions returning plain text) so the engine can
be swapped for a native audio model later without touching the rest of the
app — see README.md.

Context model: each call gets ONLY the current page's text as ground truth.
Anything else comes through a tool call (get_page_summary / load_page /
web_search), never by accumulating prior pages into the prompt.
"""
from app.store import Document
from app import brain, tools

WRAPUP_PROMPT = (
    "The listener has just finished the last page of this document. Here "
    "are one-line notes on what each page covered, in order. Write a "
    "short, warm spoken wrap-up (80-130 words): recap what was actually "
    "covered (not a generic 'we covered a lot'), then invite them to ask "
    "a question about anything, revisit a page, or upload a new document "
    "to keep going. Plain spoken prose, no bullet points, no headings."
)

NARRATE_SYSTEM = (
    "You are Co-Reader, reading this document aloud to someone in one "
    "continuous sitting — like a person reading a book to a friend, not a "
    "machine describing a page. You are given the full content of the "
    "CURRENT point in the reading only. If you genuinely need something "
    "from elsewhere, call get_page_summary or load_page — but most of the "
    "time you won't.\n\n"
    "Deliver the actual content directly and continuously, in your own "
    "words — for a story, tell it the way a storyteller does; for "
    "anything else, explain it the way a good teacher would, with a "
    "relatable analogy where it helps. Either way, write the way people "
    "actually speak — contractions, natural rhythm — and never just "
    "compress the source into a denser paragraph.\n\n"
    "NEVER break the illusion of a continuous read-aloud: don't say "
    "things like 'this page shows', 'in this image', 'we see', 'I see', "
    "'looking at this', or anything else that describes you looking at a "
    "page or picture rather than just telling the reader what happens. "
    "Never mention tools, page numbers, or that you are an AI. 2-4 "
    "sentences total, closing on one short, natural beat — not a labeled "
    "'takeaway'.\n\n"
    "If you're given a one-line note on what came just before, let it "
    "inform a natural continuation — a light connective phrase if it "
    "genuinely helps the flow (varied, never the same one twice), or "
    "simply continuing straight into the content if a transition would "
    "feel forced. Skip it entirely on the very first page."
)

ASK_SYSTEM = (
    "You are Co-Reader: a good teacher, not a machine. The listener is "
    "currently on a given page of a document (shown below) and just asked "
    "you something, possibly interrupting the narration to do so. Answer "
    "the way a teacher answers a student mid-lecture — warm, direct, in "
    "your own words, natural spoken rhythm — not a formal or robotic "
    "recitation. If the answer needs a different "
    "page, prefer load_page over get_page_summary whenever the question "
    "asks what a page/chapter actually says (not just what it's about) — "
    "get_page_summary is for quick gist-checks only. If the question involves anything "
    "current, time-sensitive, or not knowable from training data alone "
    "(recent events, current facts, specific real-world details), you MUST "
    "call web_search rather than guessing or saying you don't have access — "
    "you do have a working web_search tool, so use it. Answer directly and "
    "conversationally, as if speaking aloud — at most three sentences unless "
    "the listener explicitly asks for more depth. Never mention tools or page indexes."
)

PAGE_CONTEXT_LIMIT = 4500

# Kept deliberately separate from ASK_SYSTEM: testing showed qwen2.5:7b
# reliably calls move_page when it's the ONLY tool-decision in the prompt,
# but stops calling it once load_page/get_page_summary/web_search guidance
# is added alongside it (100% -> 0%, reproduced repeatedly). So navigation
# intent is checked first, on its own, before falling through to the
# regular question-answering tools.
NAVIGATE_SYSTEM = (
    "The listener may be giving a spoken NAVIGATION command rather than "
    "asking a question. Two kinds:\n"
    "1) Moving within this document ('next page', 'go back', 'move 1 page "
    "back', 'go forward two pages', 'skip ahead two', 'go to page 12', "
    "'take me to the end') -> call move_page with the resolved target "
    "page number, worked out from the current/total page numbers given "
    "below (e.g. 'move 1 page back' from page 5 = target 4).\n"
    "2) Leaving this document entirely ('go home', 'start over', 'upload "
    "a new document', 'let's read something else') -> call go_home. "
    "'back to the start/beginning' ALONE (no mention of a new document) "
    "means move_page to page 1, not go_home.\n"
    "If this is a question instead, don't call anything and just reply "
    "with exactly: not navigation"
)


def _gender_instruction(gender_notes: list[dict] | None) -> str:
    """A short block telling the model which pronouns to use for which
    characters. This has to shape the model's OWN word choice during
    generation — pronouns aren't a literal string that a post-hoc find/
    replace over the finished text could safely swap (unlike a character's
    NAME, "he"/"she"/"his"/"her" are far too common and short to substitute
    without corrupting unrelated words), so gender is handled here, at
    prompt time, not in app/replacements.py.
    """
    notes = [n for n in (gender_notes or []) if n.get("gender") in ("male", "female")]
    if not notes:
        return ""
    pronouns = {"male": "he/him/his", "female": "she/her/hers"}
    lines = "\n".join(f"- {n['name']}: refer to them as {pronouns[n['gender']]}" for n in notes)
    return f"\n\nCharacter pronoun notes (follow these exactly):\n{lines}"


def narrate_page(doc: Document, page_number: int, gender_notes: list[dict] | None = None) -> tuple[str, list[dict]]:
    page_text = doc.page_content(page_number)
    tool_defs = tools.make_tool_defs()
    sources: list[dict] = []
    tool_impls = tools.build_tool_impls(doc, sources_sink=sources)
    user_prompt = f"Current page ({page_number} of {len(doc.pages)}):\n\n{page_text[:PAGE_CONTEXT_LIMIT]}"
    # A one-line note on the previous page, if it's already cached — this
    # is the ONLY thing carried forward between pages (never the full
    # prior text), just enough for a transition that actually connects to
    # what came before instead of a generic "moving on". Skipped rather
    # than generated on the spot, so narration never waits on it.
    if page_number > 1:
        prev_summary = doc.page_summaries[page_number - 2]
        if prev_summary:
            user_prompt += f"\n\nWhat the previous page covered: {prev_summary}"
    user_prompt += _gender_instruction(gender_notes)
    text = brain.run_with_tools(NARRATE_SYSTEM, user_prompt, tool_defs, tool_impls)
    return text, sources


def _check_navigation(doc: Document, page_number: int, question: str) -> tuple[int | None, bool]:
    navigate: list[int] = []
    home: list[bool] = []
    tool_impls = {
        "move_page": lambda target_page: tools.move_page(doc, target_page, navigate),
        "go_home": lambda: tools.go_home(home),
    }
    user_prompt = f"Current page ({page_number} of {len(doc.pages)}).\n\nListener said: {question}"
    brain.run_with_tools(
        NAVIGATE_SYSTEM, user_prompt, [tools.MOVE_PAGE_TOOL, tools.GO_HOME_TOOL], tool_impls, max_rounds=1
    )
    return (navigate[-1] if navigate else None), bool(home)


def answer_question(
    doc: Document, page_number: int, question: str, gender_notes: list[dict] | None = None
) -> tuple[str, list[dict], int | None, bool]:
    # No regex gate here on purpose: real navigation phrasing can be
    # anything ("move 1 page back", "hop forward a couple", "take me to
    # where the introduction was"), so a keyword heuristic will always
    # miss real commands. The model decides, every time — this is a
    # second, cheap, single-tool call (see NAVIGATE_SYSTEM's docstring for
    # why it's kept separate from ASK_SYSTEM's own tools), fast enough on
    # Groq that it's not worth trading reliability for.
    navigate_to, go_home = _check_navigation(doc, page_number, question)
    if go_home:
        return "Sure, heading back home.", [], None, True
    if navigate_to is not None:
        return "Sure, heading there.", [], navigate_to, False

    page_text = doc.page_content(page_number)
    tool_defs = tools.make_tool_defs()
    sources: list[dict] = []
    tool_impls = tools.build_tool_impls(doc, sources_sink=sources)
    user_prompt = (
        f"Current page ({page_number} of {len(doc.pages)}):\n\n{page_text[:PAGE_CONTEXT_LIMIT]}\n\n"
        f"Listener said: {question}"
    )
    user_prompt += _gender_instruction(gender_notes)
    text = brain.run_with_tools(ASK_SYSTEM, user_prompt, tool_defs, tool_impls)
    return text, sources, None, False


def wrap_up(doc: Document) -> str:
    notes = "\n".join(
        f"Page {i + 1}: {s}" for i, s in enumerate(doc.page_summaries) if s
    )
    if not notes:
        notes = "(no page notes available — the listener moved quickly)"
    return brain.simple_completion(WRAPUP_PROMPT, notes)
