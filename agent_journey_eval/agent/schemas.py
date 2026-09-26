"""Typed shapes shared across the agent loop, the tracer, the judge, and the dashboard."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ideal path ("expected call pattern") — a graph, not a line. A turn can stay
# on a node, follow one of its outgoing edges, or land off-graph entirely
# (which is not automatically drift — see JudgeResult below).
# ---------------------------------------------------------------------------


class Edge(BaseModel):
    condition: str = Field(description="Natural-language trigger, e.g. 'caller asks to see other options'")
    to: str = Field(description="Target stage id")


class Stage(BaseModel):
    id: str = Field(description="Short stable id, e.g. 'needs_discovery'")
    name: str
    description: str = Field(description="What happens in this stage, for the judge prompt")
    expected_actor: Literal["user", "agent"] = Field(
        description="Who is expected to drive this stage forward"
    )
    expected_tool: Optional[str] = Field(
        default=None, description="Tool name typically called during this stage, if any"
    )
    edges: List[Edge] = Field(
        default_factory=list, description="Valid transitions out of this stage"
    )


class CallFlow(BaseModel):
    name: str
    display_name: str = Field(default="", description="User-facing name — 'name' is an internal id (e.g. carries a _v1 suffix)")
    entry_description: str = Field(
        default="", description="One-liner for when this flow applies, used if multiple flows are loaded"
    )
    stages: List[Stage]

    def model_post_init(self, __context) -> None:
        if not self.display_name:
            self.display_name = self.name

    def index_of(self, stage_id: str) -> int:
        for i, s in enumerate(self.stages):
            if s.id == stage_id:
                return i
        return -1

    def get(self, stage_id: str) -> Optional[Stage]:
        return next((s for s in self.stages if s.id == stage_id), None)

    def is_valid_transition(self, from_id: Optional[str], to_id: str, max_hops: int = 10) -> bool:
        """True if to_id is a real node in this flow AND is either from_id
        itself (stayed put), reachable within max_hops of from_id's authored
        edges, or from_id is None (first turn / freshly (re-)entering this
        flow — any real node is a valid entry point, but it still has to be a
        real one). max_hops defaults generously (comfortably covering a full
        flow traversal) because a single conversational turn can legitimately
        chain together many real, tool-verified steps at once (e.g. pick an
        option -> check stock -> add to cart -> checkout -> close, all in one
        reply) — the actual gate against illegitimate skipping is the
        tool-usage check in tracer.py, not an arbitrary hop ceiling; this hop
        bound just keeps the BFS finite, it's not a business rule anymore.
        (e.g. the agent both searches AND presents results in one reply,
        which is needs_discovery -> product_search -> present_options)."""
        if self.get(to_id) is None:
            return False
        if from_id is None or from_id == to_id:
            return True
        frontier = {from_id}
        for _ in range(max_hops):
            next_frontier = set()
            for node_id in frontier:
                stage = self.get(node_id)
                if not stage:
                    continue
                for e in stage.edges:
                    if e.to == to_id:
                        return True
                    next_frontier.add(e.to)
            frontier = next_frontier
        return False

    def path_stages(self, from_id: Optional[str], to_id: str, max_hops: int = 10) -> List["Stage"]:
        """The stages actually passed through on a shortest valid path from
        from_id to to_id (inclusive of to_id), or [] if unreachable within
        max_hops. Used to check that every tool-requiring stage IMPLIED by a
        multi-hop move was actually invoked this turn — e.g. a turn landing
        on present_options via needs_discovery -> product_search -> present_options
        implies product_search ran, even though the turn didn't stop there."""
        to_stage = self.get(to_id)
        if to_stage is None:
            return []
        if from_id is None or from_id == to_id:
            return [to_stage]
        frontier = [(from_id, [])]
        visited = {from_id}
        for _ in range(max_hops):
            next_frontier = []
            for node_id, path in frontier:
                stage = self.get(node_id)
                if not stage:
                    continue
                for e in stage.edges:
                    new_path = path + [e.to]
                    if e.to == to_id:
                        return [s for s in (self.get(nid) for nid in new_path) if s]
                    if e.to not in visited:
                        visited.add(e.to)
                        next_frontier.append((e.to, new_path))
            frontier = next_frontier
        return []


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class Product(BaseModel):
    product_id: str
    name: str
    price: Optional[float] = None
    url: Optional[str] = None
    snippet: Optional[str] = None


class DeliveryOption(BaseModel):
    tier: Literal["standard", "expedited"]
    cost: float
    window: str


class CartItem(BaseModel):
    product_id: str
    name: str
    price: float
    quantity: int = 1


class CostSummary(BaseModel):
    line_items: List[CartItem]
    subtotal: float
    shipping_cost: float
    estimated_tax: float
    total: float
    delivery_window: str


# ---------------------------------------------------------------------------
# Trace events (mirrors the trace_events table)
# ---------------------------------------------------------------------------

Actor = Literal["user", "agent", "tool", "system"]
EventType = Literal[
    "transcript",
    "llm_response",
    "tool_call",
    "tool_result",
    "tts_start",
    "tts_end",
    "interruption",
    "flow_switch",
]
Mood = Literal["frustrated", "confused", "neutral", "satisfied", "urgent"]


class JudgeResult(BaseModel):
    """What the offline Gemini judge produces for a single turn. Three-way
    classification: on the active flow (flow_name/node_id set to it), on a
    DIFFERENT flow (flow_name set to that other flow — a genuine intent
    switch), or off every flow (both null) — which then splits into a fine
    tangent (drift_flag false) or real drift (drift_flag true)."""

    flow_name: Optional[str] = Field(
        default=None, description="Which flow this turn belongs to — the active one, a different "
        "known one (a switch), or null if it fits none"
    )
    node_id: Optional[str] = Field(
        default=None, description="Matched node id within flow_name, else None"
    )
    drift_flag: bool = Field(
        description="True only if something is actually wrong (hallucination, broken tool loop, "
        "non-response, wrong tool) — NOT simply true because on_path is False"
    )
    drift_note: Optional[str] = Field(
        default=None, description="Concrete description of what deviated and why, only set if drift_flag"
    )
    caller_mood: Mood
    profanity_user: bool = Field(default=False, description="Profanity/abuse in the caller's utterance")
    profanity_agent: bool = Field(default=False, description="Profanity/inappropriate content in the agent's reply")
    satisfaction_delta: float = Field(
        description="How much this turn should move the running satisfaction estimate, "
        "roughly in [-0.2, 0.2]"
    )


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    call_id: str
    turn_index: int
    ts: float = Field(default_factory=time.time)
    latency_ms: Optional[float] = None
    actor: Actor
    event_type: EventType
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    tool_failed: bool = Field(
        default=False, description="Set deterministically from tool_result — not inferred by the judge"
    )
    tool_arg_issue: Optional[str] = Field(
        default=None,
        description="Set deterministically if the call was missing a required argument — not inferred by the judge",
    )
    stage_expected: Optional[str] = None
    stage_actual: Optional[str] = None
    flow_name: Optional[str] = None
    drift_flag: bool = False
    drift_note: Optional[str] = None
    caller_mood: Optional[Mood] = None
    profanity_user: bool = False
    profanity_agent: bool = False


CallLabel = Literal["completed", "abandoned", "unresolved_drift", "general_only", "escalation_needed"]


class CallSummary(BaseModel):
    """End-of-call synthesis over the full trace — a holistic read, not just
    the running per-turn average."""

    label: CallLabel
    score: float = Field(description="Overall satisfaction estimate for the whole call, 0-1")
    reasoning: str = Field(description="2-4 sentences: what happened, and specifically where/why it went off path")
