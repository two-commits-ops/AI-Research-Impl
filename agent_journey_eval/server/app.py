"""Local web app: a live voice call page (browser mic + speech recognition,
Groq-driven agent, TTS playback, live trajectory side panel over WebSocket)
plus a post-call graphical trajectory report and a call list."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from agent import tts
from agent.flow import load_all_flows
from agent.loop import ShoppingSession
from agent.tracer import start_call
from server import db

log = logging.getLogger("uvicorn.error")

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="agent_journey_eval")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Cache-busts every static asset reference on server restart — browsers cache
# /static/* independently of the page URL, so a hard-reload of the page alone
# doesn't pick up JS/CSS edits without this.
templates.env.globals["asset_version"] = str(int(time.time()))

# Three distinct intents this agent handles, each its own flow graph. Which
# one (if any) is actually engaged is decided per-call by the judge from the
# conversation itself — see agent/tracer.py — not fixed up front here.
FLOWS = load_all_flows()
FLOWS_JSON = {
    name: {
        "name": f.name,
        "display_name": f.display_name,
        "entry_description": f.entry_description,
        "stages": [s.model_dump() for s in f.stages],
    }
    for name, f in FLOWS.items()
}


def _flow_stage(flow_name: str | None, stage_id: str | None) -> Dict[str, Any] | None:
    if not flow_name or not stage_id:
        return None
    flow = FLOWS.get(flow_name)
    if not flow:
        return None
    stage = flow.get(stage_id)
    return stage.model_dump() if stage else None


@app.get("/")
def call_page(request: Request):
    return templates.TemplateResponse(request, "call.html", {"flows": FLOWS_JSON})


@app.get("/calls")
def calls_page(request: Request):
    return templates.TemplateResponse(request, "calls_list.html", {})


@app.get("/call/{call_id}")
def report_page(request: Request, call_id: str):
    return templates.TemplateResponse(request, "report.html", {"call_id": call_id})


@app.get("/api/calls")
def api_list_calls():
    return JSONResponse(db.list_calls())


@app.get("/api/calls/{call_id}")
def api_get_call(call_id: str):
    call = db.get_call(call_id)
    if not call:
        return JSONResponse({"error": "not found"}, status_code=404)
    events = db.get_trace_events(call_id)
    for e in events:
        if e.get("tool_args_json"):
            e["tool_args"] = json.loads(e["tool_args_json"])
        if e.get("tool_result_json"):
            e["tool_result"] = json.loads(e["tool_result_json"])
        if e.get("audio_path"):
            e["audio_url"] = f"/audio/{Path(e['audio_path']).relative_to(AUDIO_DIR)}"
    return JSONResponse({"call": call, "events": events, "flows": FLOWS_JSON})


@app.post("/api/calls/{call_id}/label")
async def api_set_label(call_id: str, request: Request):
    body = await request.json()
    db.set_user_label(call_id, int(body["score"]), body.get("comment", ""))
    return JSONResponse({"ok": True})


async def _synthesize_and_attach(event_id: str, call_id: str, text: str) -> str | None:
    """Best-effort TTS: on any failure (e.g. Groq TTS model terms not yet
    accepted), return None so the browser falls back to speechSynthesis."""
    try:
        audio_bytes = await asyncio.to_thread(tts.synthesize, text)
    except Exception as e:
        log.warning("TTS failed, falling back to browser voice: %s", e)
        return None
    call_dir = AUDIO_DIR / call_id
    call_dir.mkdir(parents=True, exist_ok=True)
    path = call_dir / f"{event_id}.mp3"
    path.write_bytes(audio_bytes)
    db.update_trace_event_audio(event_id, str(path))
    return f"/audio/{call_id}/{event_id}.mp3"


@app.websocket("/ws/call")
async def ws_call(websocket: WebSocket):
    await websocket.accept()
    tracer = start_call(FLOWS)
    session = ShoppingSession(tracer)

    await websocket.send_json({"type": "call_started", "call_id": tracer.call_id})

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg["type"] == "end_call":
                break

            if msg["type"] != "utterance" or not msg.get("text", "").strip():
                continue

            user_text = msg["text"].strip()
            await websocket.send_json({"type": "user_echo", "text": user_text})

            try:
                result = await asyncio.to_thread(session.run_turn, user_text)
            except Exception as e:
                log.exception("turn failed")
                await websocket.send_json({"type": "error", "message": str(e)})
                continue

            audio_url = await _synthesize_and_attach(result["event_id"], tracer.call_id, result["agent_text"])

            await websocket.send_json(
                {
                    "type": "agent_turn",
                    **result,
                    "audio_url": audio_url,
                    "stage": _flow_stage(result["flow_name"], result["stage_actual"]),
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        await asyncio.to_thread(tracer.end_call)
        try:
            await websocket.send_json({"type": "call_ended", "call_id": tracer.call_id})
        except Exception:
            pass
