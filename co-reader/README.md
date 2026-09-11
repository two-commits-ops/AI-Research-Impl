# Co-Reader

A local Mac app that reads PDFs aloud, page by page, like someone reading a
book to you. Ask it questions mid-read, jump around by voice, and tell it
how to pronounce or gender each character before you start — all running
on your machine, no API keys or accounts required.

## Requirements

- **macOS on Apple Silicon** (M1 or later) — the local narration voice
  (Kokoro-82M via `mlx-audio`) uses Apple's MLX framework.
- **Python 3.10+**
- **~4 GB free disk** for model weights (Kokoro TTS + Ollama's `qwen2.5:7b`),
  downloaded once on first run.
- **[Ollama](https://ollama.com)**, for the local reasoning model. Optional
  if you configure a cloud provider instead (see below).
- A Chromium-based browser (Chrome or Edge) if you want voice input — it's
  the only engine that supports the Web Speech API this app uses for the
  mic button. Everything else works in any modern browser.
- Optional, for image-only/scanned PDFs: an Ollama vision model
  (`ollama pull qwen2.5vl:3b`) or a `GEMINI_API_KEY` (see below).

No API keys are required for normal use — everything above runs fully
offline once the models are downloaded.

## Setup

```bash
brew install ollama
brew services start ollama
ollama pull qwen2.5:7b

python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run it

```bash
./run.sh
```

Then open **http://localhost:8765**. First narration call downloads
Kokoro's TTS weights (cached under `~/.cache/huggingface`) — a one-time,
roughly one-minute wait.

## What it does

1. **Upload a PDF.** Text is extracted page by page. Pages with no
   extractable text (scanned pages, picture books) are handled by
   describing the rendered image with a vision model instead — nothing
   is silently skipped.
2. **Quick overview.** A single model call over the opening content-bearing
   pages produces a short spoken summary — this doesn't wait for the whole
   document, so a 500-page PDF reaches the landing screen about as fast as
   a 5-page one.
3. **Character setup, before you start reading.** For fiction, the app
   detects named characters (people or animal characters, common in
   children's books) up front and lets you:
   - **Rename** any character, for pronunciation.
   - **Set their gender** (male / female / unknown), so pronouns come out
     correct. This is a generation-time instruction to the model, not a
     find-and-replace — "he"/"she" are too short and common to safely
     substitute as plain text.
4. **Reading.** The main area always shows the actual PDF page, forward or
   back, so you can read along visually no matter what's playing.
   - One button narrates (or stops) the current page. Narration reads the
     content the way a person reads aloud to someone — not a page-by-page
     description ("this page shows...").
   - Auto-advance moves to the next page and keeps narrating, so listening
     is continuous rather than one page at a time.
   - **Ask a question** any time — by typing, or with the mic button — and
     narration pauses for the answer, then resumes where it left off.
   - **Voice navigation** ("go to the next page", "take me home") is
     recognized by an LLM tool-call check, not keyword matching, so it
     understands varied phrasing.
   - A tone picker (warm / calm / bright / deep / classic) changes the
     narrating voice.
   - Any rename or gender fix made on the landing screen applies to every
     future narration and answer — edit it any time and it takes effect on
     the next thing you hear, not retroactively.
5. **Wrap-up.** Reaching the last page generates a short spoken close-out.
6. **Tools, used silently.** The model can call `get_page_summary(n)`,
   `load_page(n)`, `move_page(n)`, `go_home()`, or `web_search(query)` —
   you see only the result (with real source links when it searched), not
   the mechanics.

**Context model:** each narration or question call sees only the current
page's content, plus whatever it explicitly fetches with a tool call.
Nothing accumulates turn over turn.

## Architecture

```
Browser (PDF.js + vanilla JS, no build step)
   │
FastAPI backend (app/main.py)
   ├── preprocess.py   — landing overview + character/gender detection + page summaries
   ├── narrator.py     — narration / Q&A "brain" (tool calling: page nav, search)
   ├── vision.py        — describes image-only pages for models with no text to read
   ├── tools.py        — get_page_summary, load_page, move_page, go_home, web_search
   ├── replacements.py — character renames + gender overrides
   └── tts.py          — Kokoro-82M via mlx-audio (native Apple Silicon)
```

## Model choices

**Reasoning brain: local `qwen2.5:7b` via Ollama by default**, chosen after
benchmarking it against `qwen3:8b` and `llama3-groq-tool-use:8b` on
tool-selection accuracy (when to search the web vs. jump pages vs. answer
directly) — it scored highest of the three. Optional cloud fallbacks, in
priority order: **Groq** (`GROQ_API_KEY`, fastest — recommended if local
inference feels slow) → **Gemini** (`GEMINI_API_KEY`) → local Ollama.

**Narration voice: Kokoro-82M (Apache 2.0) via `mlx-audio`**, running
natively on Apple Silicon. If `GEMINI_API_KEY` is set, Gemini's TTS is used
instead (independent of which reasoning provider is active).

**Image-only pages: Gemini vision (if `GEMINI_API_KEY` is set) → local
Ollama `qwen2.5vl:3b` → a clear "no vision model available" message.**

## Optional: cloud providers

Add either key to a `.env` file at the project root — nothing else to
configure, `app/config.py` picks it up automatically:

```
GROQ_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
```

- **`GROQ_API_KEY`** — routes reasoning (narration, Q&A, navigation) through
  Groq instead of Ollama/Gemini. Much faster than local inference; doesn't
  affect which TTS engine is used.
- **`GEMINI_API_KEY`** — routes reasoning (if Groq isn't set) and narration
  audio through Gemini. Useful for hosting without a local GPU. Note:
  Gemini's free tier is capped at 5 requests/minute for text and 10/day
  for TTS — fine for trying it out, tight for continuous use. Provider
  failures fall back to local Ollama/Kokoro automatically where possible.

Never required — the app is fully functional with no keys set.

## Known limitations

- **Web search** uses DuckDuckGo's keyless HTML search, not Google — a
  genuine Google Search API needs a paid key, which conflicts with this
  project's no-required-keys goal. Answers that used it show real source
  links.
- **Tool-calling judgment isn't perfectly consistent** for any ~7-8B local
  model — it occasionally answers from its own knowledge instead of
  calling `web_search` when it should. The tool plumbing itself is
  reliable; this is a model judgment call, not a bug.
- **In-memory document state**: restarting the server forgets uploaded
  documents (files remain on disk under `data/`, but aren't reloaded
  automatically).
- **Single voice loaded at a time**: changing tone mid-document applies to
  the next thing generated, not audio already playing.

## Project layout

```
app/                  backend + static frontend (FastAPI, vanilla JS)
sample_pdfs/          three original children's stories for trying it out
requirements.txt      pinned Python dependencies
run.sh                starts the server (isolates the venv from other Python envs)
```
