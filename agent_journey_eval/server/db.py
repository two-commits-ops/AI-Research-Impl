"""SQLite storage for calls + trace_events. One file on disk, no server process."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from agent.schemas import TraceEvent

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trajectories.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    audio_path TEXT,
    goal_reached INTEGER DEFAULT 0,
    running_satisfaction REAL DEFAULT 0.5,
    drift_count INTEGER DEFAULT 0,
    user_label_score INTEGER,
    user_label_comment TEXT,
    signals_json TEXT,
    final_label TEXT,
    final_score REAL,
    final_reasoning TEXT,
    active_flow_name TEXT,
    tool_failure_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trace_events (
    id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES calls(id),
    turn_index INTEGER NOT NULL,
    ts REAL NOT NULL,
    latency_ms REAL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    tool_args_json TEXT,
    tool_result_json TEXT,
    tool_failed INTEGER DEFAULT 0,
    tool_arg_issue TEXT,
    stage_expected TEXT,
    stage_actual TEXT,
    flow_name TEXT,
    drift_flag INTEGER DEFAULT 0,
    drift_note TEXT,
    caller_mood TEXT,
    audio_path TEXT,
    satisfaction_after REAL,
    profanity_user INTEGER DEFAULT 0,
    profanity_agent INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trace_events_call ON trace_events(call_id);
"""


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def create_call(db_path: Path = DEFAULT_DB_PATH) -> str:
    call_id = uuid.uuid4().hex[:12]
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO calls (id, started_at, status) VALUES (?, ?, 'in_progress')",
            (call_id, time.time()),
        )
    return call_id


def end_call(call_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE calls SET ended_at = ?, status = 'ended' WHERE id = ?",
            (time.time(), call_id),
        )


def set_user_label(call_id: str, score: int, comment: str = "", db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE calls SET user_label_score = ?, user_label_comment = ? WHERE id = ?",
            (score, comment, call_id),
        )


def update_call_signals(
    call_id: str,
    running_satisfaction: Optional[float] = None,
    drift_count_increment: int = 0,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with connect(db_path) as conn:
        if running_satisfaction is not None:
            conn.execute(
                "UPDATE calls SET running_satisfaction = ? WHERE id = ?",
                (running_satisfaction, call_id),
            )
        if drift_count_increment:
            conn.execute(
                "UPDATE calls SET drift_count = drift_count + ? WHERE id = ?",
                (drift_count_increment, call_id),
            )


def increment_tool_failure_count(call_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE calls SET tool_failure_count = tool_failure_count + 1 WHERE id = ?", (call_id,))


def insert_trace_event(event: TraceEvent, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trace_events (
                id, call_id, turn_index, ts, latency_ms, actor, event_type, content,
                tool_name, tool_args_json, tool_result_json, tool_failed, tool_arg_issue,
                stage_expected, stage_actual, flow_name, drift_flag, drift_note, caller_mood
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.call_id,
                event.turn_index,
                event.ts,
                event.latency_ms,
                event.actor,
                event.event_type,
                event.content,
                event.tool_name,
                json.dumps(event.tool_args) if event.tool_args is not None else None,
                json.dumps(event.tool_result) if event.tool_result is not None else None,
                int(event.tool_failed),
                event.tool_arg_issue,
                event.stage_expected,
                event.stage_actual,
                event.flow_name,
                int(event.drift_flag),
                event.drift_note,
                event.caller_mood,
            ),
        )


def update_trace_event_audio(event_id: str, audio_path: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE trace_events SET audio_path = ? WHERE id = ?", (audio_path, event_id))


def update_trace_event_judge(
    event_id: str,
    stage_actual: Optional[str],
    flow_name: Optional[str],
    drift_flag: bool,
    drift_note: Optional[str],
    caller_mood: str,
    satisfaction_after: float,
    profanity_user: bool = False,
    profanity_agent: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE trace_events
            SET stage_actual = ?, flow_name = ?, drift_flag = ?, drift_note = ?, caller_mood = ?, satisfaction_after = ?,
                profanity_user = ?, profanity_agent = ?
            WHERE id = ?
            """,
            (
                stage_actual,
                flow_name,
                int(drift_flag),
                drift_note,
                caller_mood,
                satisfaction_after,
                int(profanity_user),
                int(profanity_agent),
                event_id,
            ),
        )


def update_call_active_flow(call_id: str, flow_name: Optional[str], db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE calls SET active_flow_name = ? WHERE id = ?", (flow_name, call_id))


def set_call_summary(call_id: str, label: str, score: float, reasoning: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE calls SET final_label = ?, final_score = ?, final_reasoning = ? WHERE id = ?",
            (label, score, reasoning, call_id),
        )


def list_calls(db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM calls ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_call(call_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        return dict(row) if row else None


def get_trace_events(call_id: str, db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM trace_events WHERE call_id = ? ORDER BY turn_index, ts", (call_id,)
        ).fetchall()
        return [dict(r) for r in rows]
