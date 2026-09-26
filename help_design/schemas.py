"""Typed data shapes shared across signatures, modules, tools, and fixtures.

These are plain pydantic models. DSPy signatures use them directly as
InputField/OutputField types, which is what lets each module emit (and be
compiled against) structured objects instead of loose strings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Stage 0 — brief extraction
# ---------------------------------------------------------------------------


class ProjectBrief(BaseModel):
    space_type: str = Field(description="e.g. 'backyard', 'patio', 'front yard'")
    stated_goals: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(
        default_factory=list, description="Budget, size, must-haves explicitly stated"
    )
    missing_info: List[str] = Field(
        default_factory=list,
        description="Critical information not yet known that design work needs",
    )


# ---------------------------------------------------------------------------
# Stage 1 — live scene capture loop
# ---------------------------------------------------------------------------


CaptureMode = Literal["photo", "video"]
"""Which capture path the user picked at the start of the capture loop:
'photo' means single-shot uploads (an incomplete view gets another upload
request), 'video' means a live feed (an incomplete view gets a physical
camera-movement instruction). Which one is active is decided once, up
front, by a plain deterministic UI choice — not a DSPy module — but it
changes how FrameCompletenessChecker should phrase adjustment_instruction,
so it flows in as an input."""


class FrameFacts(BaseModel):
    """Mocked vision-tool output for a single frame. In the real system this
    would come from a CV/vision model; here it's a canned fixture dict."""

    frame_id: str
    visible_elements: List[str] = Field(default_factory=list)
    cutoff_edges: List[str] = Field(
        default_factory=list, description="Edges of the frame that cut off something, e.g. 'left', 'bottom'"
    )
    lighting: Optional[str] = None
    notes: Optional[str] = None


class CoverageHistory(BaseModel):
    """Accumulated state across the capture loop: every frame seen so far and
    every adjustment already requested, so the checker doesn't repeat itself
    or lose track of what's already been confirmed visible."""

    frames_seen: List[FrameFacts] = Field(default_factory=list)
    adjustments_requested: List[str] = Field(default_factory=list)


class FrameAssessment(BaseModel):
    is_complete: bool
    missing_elements: List[str] = Field(default_factory=list)
    adjustment_instruction: Optional[str] = Field(
        default=None, description="Single actionable instruction; only set when is_complete is False"
    )


# ---------------------------------------------------------------------------
# Stage 2 — scene understanding
# ---------------------------------------------------------------------------


class SceneSummary(BaseModel):
    style_tags: List[str] = Field(default_factory=list)
    key_features: List[str] = Field(default_factory=list)
    condition_notes: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 2.5 — task list identification + user editing
# ---------------------------------------------------------------------------


class Task(BaseModel):
    task_name: str = Field(description="Short human label, e.g. 'Decking Materials'")
    topic_area: str = Field(
        description="One of the supported grounding categories, e.g. 'materials', "
        "'furniture', 'plants', 'structures', 'lighting', 'irrigation', 'color', 'budget'"
    )
    rationale: Optional[str] = None


class TaskList(BaseModel):
    tasks: List[Task] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 3 — Q&A loop (now one inner loop per task in the TaskList)
# ---------------------------------------------------------------------------


class QAExchange(BaseModel):
    question: str
    topic: str
    chosen_answer: str
    backing_product_ids: List[str] = Field(default_factory=list)
    task_name: str = Field(
        description="Which Task (by task_name) this exchange belongs to"
    )


class NextQuestion(BaseModel):
    question_text: str
    topic: str


ToolName = Literal[
    "product_search",
    "price_range_lookup",
    "color_palette_search",
    "shipping_options_lookup",
    "none",
]
"""'none' is a legitimate choice, not a gap: some questions (a shipping
address) have nothing to ground — the user's own answer is the data."""

UIComponentType = Literal[
    "chip_select", "swatch_grid", "image_carousel", "slider", "color_picker", "text_input"
]


class ToolCallPlan(BaseModel):
    tool_name: ToolName
    tool_args: Dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    """A single mocked catalog item, as returned by product_search / friends."""

    product_id: str
    name: str
    category: str
    tags: List[str] = Field(default_factory=list)
    price: Optional[float] = None
    swatch_ref: Optional[str] = None


class DeliveryOption(BaseModel):
    """One shipping tier, as returned by shipping_options_lookup."""

    tier: Literal["standard", "expedited"]
    cost: float
    window: str = Field(description="e.g. '5-7 business days'")


class ToolResults(BaseModel):
    """Wrapper around whatever the dispatched mock tool returned, normalized
    enough for AnswerOptionComposer to reason over regardless of tool_name."""

    products: List[Product] = Field(default_factory=list)
    price_range: Optional[Dict[str, float]] = None
    palette: Optional[List[Dict[str, str]]] = None
    delivery_options: Optional[List[DeliveryOption]] = None


class UIOption(BaseModel):
    label: Optional[str] = Field(
        default=None, description="Omitted for widgets like slider that have no discrete label"
    )
    description: Optional[str] = None
    backing_product_id: Optional[str] = Field(
        default=None,
        description="A grounding key this option traces back to — a product id, "
        "a delivery tier ('standard'/'expedited'), or similar. Named for the "
        "common case; not literally a product for every widget.",
    )
    swatch_ref: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    default: Optional[float] = None


class UITask(BaseModel):
    component_type: UIComponentType
    prompt_text: str
    options: List[UIOption] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 4 — design synthesis
# ---------------------------------------------------------------------------


class Placement(BaseModel):
    product_id: str
    zone: str
    position_hint: str


class DesignProposal(BaseModel):
    concept_narrative: str
    layout_notes: str
    shopping_list: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    placements: List[Placement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5b — ground delivery details while the (non-DSPy) 3D render runs.
#
# An auto-appended "Shipping & Timing" task, not part of TaskList/TaskListEditor
# — it runs the same Q&A loop mechanics (QuestionPlanner -> TaskUIPlanner ->
# tool -> AnswerOptionComposer) as any other task, just system-triggered right
# after DesignSynthesizer instead of user-planned up front.
# ---------------------------------------------------------------------------


class CostLineItem(BaseModel):
    product_id: str
    label: str
    unit_price: float
    subtotal: float


class CostSummary(BaseModel):
    line_items: List[CostLineItem] = Field(default_factory=list)
    subtotal: float
    shipping_cost: float
    estimated_tax: float
    total: float
    delivery_window: str
    closing_note: str = Field(
        description="One short, warm line about when it'll arrive — read as a "
        "confident wrap-up, not a receipt dump"
    )
