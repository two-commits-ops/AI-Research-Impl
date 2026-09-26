# Agent Journey Eval

A text-mode voice-shopping agent (Groq LLM + tool calling) paired with an
automatic conversation-trajectory tracer: every turn is checked against a
graph of expected call flows, tool calls are verified deterministically
(never trusted from the model's own claims), and an LLM judge scores drift,
caller mood, and satisfaction — all viewable in a local dashboard.

## What it does

- **The agent** handles four kinds of requests — buying a product, checking
  an existing order, planning/designing a space, and finding a store — using
  a handful of mocked commerce tools (search, inventory, cart, shipping,
  checkout) so it runs fully offline with no external API billing.
- **The tracer** ("auto hook") logs every transcript turn, tool call, and
  tool result to SQLite as the call happens.
- **Deterministic checks** catch tool failures and missing required
  arguments in code, not by asking an LLM to notice them.
- **An offline judge** (Gemini) scores each turn against a hand-authored
  call-flow graph per skill, classifying genuine drift (profanity, an
  out-of-scope request, a mishandled tool failure, an ungrounded skip past a
  tool-driven step) versus a harmless tangent, and tracks caller mood and a
  running satisfaction score.
- **A local dashboard** renders the call as a swimlane diagram — one lane
  per skill the agent supports, plus general/off-track lanes — with every
  tool-verified step plotted individually, click-through detail per step
  (including the full path taken to reach it), a mood timeline, and an
  end-of-call satisfaction label.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, GEMINI_API_KEY
```

All commerce tools, including product search, are mocked — no billing or
extra API keys required beyond Groq (the agent) and Gemini (the judge).

## Run a call

```bash
python -m scripts.run_text_call
```

Have a full conversation, then try a deliberate detour (e.g. ask about a
return policy mid-purchase) to see it get classified as a harmless tangent
rather than drift. Or start the dashboard and use the browser-based call
page instead:

```bash
uvicorn server.app:app --reload --port 8420
```

Then open `http://localhost:8420` for a live call, or `/calls` for past
calls and their trajectory diagrams.

## Layout

```
agent/
  prompts.py         agent + judge system prompts
  schemas.py          pydantic models: Stage/CallFlow, Product, TraceEvent, JudgeResult
  loop.py             Groq LLM + tool-calling turn loop, deterministic arg/failure checks
  tracer.py           the "auto hook" — every event funnels through here into SQLite
  judge.py            Gemini call: drift/mood/satisfaction per turn
  flow.py             loads flows/*.yaml, graph reachability helpers
  tools/
    product_search.py   deterministic mocked search
    mock_tools.py        inventory, cart, shipping, checkout
flows/
  *.yaml              one hand-authored call-flow graph per skill
server/
  app.py              FastAPI dashboard + live call WebSocket
  db.py               SQLite schema + helpers (calls, trace_events)
  static/, templates/ live call page + post-call trajectory report
scripts/
  run_text_call.py    terminal harness for a text-mode call
```
