"""User-defined term/pronunciation substitutions, applied to narration text
right before it's spoken (and shown) — e.g. swapping a mispronounced name
for a phonetic spelling, or a dense acronym for something more listenable.

Deliberately applied AFTER the model writes its answer, never fed into the
model's own reasoning — so it can't distort tool-calling or comprehension,
only the final wording.
"""
import re


def apply(text: str, replacements: list[dict]) -> str:
    """`replacements` is a list of {"find": str, "replace": str}. Case-insensitive,
    applied in order. An entry with no `replace` (or the same as `find`)
    means no rename was actually requested for that character — this list
    also carries gender-only entries (see app/narrator.py's
    _gender_instruction for how those are handled instead), so an empty
    `replace` must mean "skip", never "delete this name from the text".
    """
    if not replacements:
        return text
    for r in replacements:
        find = (r.get("find") or "").strip()
        replace = (r.get("replace") or "").strip()
        if not find or not replace or replace.lower() == find.lower():
            continue
        pattern = re.compile(re.escape(find), re.IGNORECASE)
        text = pattern.sub(replace, text)
    return text
