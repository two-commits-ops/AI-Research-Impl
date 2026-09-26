"""DSPy Signatures for every module in the Help Design pipeline.

Each Signature's docstring IS the instruction text the LM is compiled against —
kept verbatim from the design spec (docs/dspy-design-studio-spec.md) so the two
stay in sync. Field `desc=` strings are secondary hints, not the instruction.
"""

import dspy

from help_design.schemas import (
    CaptureMode,
    CostSummary,
    CoverageHistory,
    DeliveryOption,
    DesignProposal,
    FrameAssessment,
    FrameFacts,
    NextQuestion,
    Product,
    ProjectBrief,
    QAExchange,
    SceneSummary,
    Task,
    TaskList,
    ToolCallPlan,
    ToolResults,
    UIComponentType,
    UITask,
)
from typing import List, Literal


# ---------------------------------------------------------------------------
# Stage 0
# ---------------------------------------------------------------------------


class ExtractBrief(dspy.Signature):
    """You are a design intake assistant. Read the user's free-form request and
    extract a structured project brief. Identify the space type, any stated
    goals or style hints, explicit constraints (budget, size, must-haves), and
    list what critical information is still missing before design work can
    begin. Do not invent details not present in the query."""

    raw_query: str = dspy.InputField(desc="The user's free-form initial request")
    brief: ProjectBrief = dspy.OutputField()


# ---------------------------------------------------------------------------
# Stage 1 — capture loop
#
# Which capture_mode is active (photo upload vs. live video) is decided once,
# up front, by a plain deterministic UI choice ("upload a photo, or turn on
# video?") — not a DSPy module. It flows into AssessFrame because it changes
# how an incomplete view should be asked to be fixed.
# ---------------------------------------------------------------------------


class AssessFrame(dspy.Signature):
    """You are reviewing a frame of the user's space to decide if it captures
    enough to design from - the frame may be a live camera frame or an
    uploaded photo, given by capture_mode. Given facts extracted from the
    current frame, what's already been seen in earlier frames this session,
    and what this specific project needs visible (boundaries, ground plane,
    the features relevant to the stated goal), decide whether the view is
    complete. If not, name exactly what's missing and give one clear,
    actionable instruction phrased for the actual capture mode: for
    capture_mode="video", a physical camera movement - "step back about 5
    feet", "pan right to bring the fence line into frame", "tilt down to
    show the ground near the patio"; for capture_mode="photo", a request for
    another upload - "please upload another photo that also shows the left
    side of the yard". Never ask for more than one adjustment at a time.
    Only mark complete when nothing critical to the brief is cut off,
    occluded, or ambiguous."""

    brief: ProjectBrief = dspy.InputField()
    capture_mode: CaptureMode = dspy.InputField()
    current_frame: FrameFacts = dspy.InputField()
    coverage_history: CoverageHistory = dspy.InputField(
        desc="Every frame seen so far this session and every adjustment already requested"
    )
    assessment: FrameAssessment = dspy.OutputField()


# ---------------------------------------------------------------------------
# Stage 2 — scene understanding
# ---------------------------------------------------------------------------


class InterpretScene(dspy.Signature):
    """Given structured facts extracted from a photo/video of the user's space
    and the project brief, produce a design-relevant summary: current style
    tags, notable existing features, condition issues worth addressing, and
    design opportunities. Ground every claim in the provided facts; never
    mention anything not listed."""

    brief: ProjectBrief = dspy.InputField()
    merged_frame_facts: List[FrameFacts] = dspy.InputField(
        desc="Facts merged across every frame collected during the capture loop"
    )
    summary: SceneSummary = dspy.OutputField()


# ---------------------------------------------------------------------------
# Stage 2.5 — task list identification + user editing
# ---------------------------------------------------------------------------


class IdentifyTasks(dspy.Signature):
    """Given the project brief and scene understanding, break the design work
    into a short list of concrete decision areas ("tasks") the homeowner
    needs to make choices about - e.g. furniture, planting, materials,
    lighting, structures. Each task represents one coherent area of related
    decisions, not a single question - a task will itself generate multiple
    questions later. Keep the list focused: typically 3-6 tasks for a
    single-space project. Order tasks sensibly (structural/material
    decisions before furniture/decor), since the user completes them one at
    a time and can edit this list before starting."""

    brief: ProjectBrief = dspy.InputField()
    scene_summary: SceneSummary = dspy.InputField()
    task_list: TaskList = dspy.OutputField()


class EditTaskList(dspy.Signature):
    """The user wants to change the task list you proposed for their design
    project. Given their free-form edit request, the current task list, and
    the categories this system can actually ground with real options,
    decide how to apply it: add, remove, rename, or reorder a task. Only
    add a task if it maps to one of the supported categories - if the
    request doesn't correspond to anything groundable, decline it and say
    why in one sentence, returning the task list unchanged. Never silently
    ignore a request; always state whether it was accepted or rejected."""

    brief: ProjectBrief = dspy.InputField()
    current_task_list: TaskList = dspy.InputField()
    supported_categories: List[str] = dspy.InputField(
        desc="Categories this system can ground via mocked tools, e.g. "
        "'materials', 'furniture', 'plants', 'structures', 'lighting', "
        "'irrigation', 'color', 'budget'"
    )
    user_edit_request: str = dspy.InputField()
    edit_result: Literal["accepted", "rejected"] = dspy.OutputField()
    updated_task_list: TaskList = dspy.OutputField()
    explanation: str = dspy.OutputField(
        desc="One sentence; especially important when rejected"
    )


# ---------------------------------------------------------------------------
# Stage 3 — Q&A loop (one inner loop per task in the TaskList)
# ---------------------------------------------------------------------------


class PlanNextQuestion(dspy.Signature):
    """You are guiding a homeowner through backyard redesign discovery, one
    task at a time. You are currently working on current_task. Given what's
    known so far - including anything already established in this task or
    in earlier completed tasks - decide the single most valuable next
    question for THIS task specifically. Never repeat a topic already
    covered, whether in this task or an earlier one. If this task's key
    decisions are sufficiently covered, set is_task_done=true instead of
    asking another question; the orchestrator will then move to the next
    task in the list."""

    brief: ProjectBrief = dspy.InputField()
    scene_summary: SceneSummary = dspy.InputField()
    current_task: Task = dspy.InputField()
    qa_history: List[QAExchange] = dspy.InputField(
        desc="Full history across all tasks completed so far this session, not just this task"
    )
    next_question: NextQuestion = dspy.OutputField(
        desc="Ignored when is_task_done is True"
    )
    is_task_done: bool = dspy.OutputField()


class PlanTaskUI(dspy.Signature):
    """Given the question about to be asked, do three things. First, sketch
    3-5 plausible answer options from general knowledge alone, before any
    grounding data exists - this is a draft, used only to shape the tool
    query, never shown to the user on its own; leave it empty for an
    open-ended question where there's nothing to sketch (see text_input
    below). Second, decide which backend tool would ground this question in
    real, available options, and what query/filters to call it with (e.g.
    product_search for materials/furniture/plants, price_range_lookup for
    budget-shaped questions, color_palette_search for palette questions,
    shipping_options_lookup for delivery-speed questions). Use
    tool_name="none" when the question has nothing to ground - the user's
    own answer is the data, like a shipping address. Third, pick the UI
    component that matches how a person naturally makes this choice:
    chip_select for a short categorical pick, swatch_grid for
    material/texture/color choices, image_carousel for style or furniture
    choices, slider for a continuous range like budget or size, text_input
    for an open-ended answer like an address. Match the widget to the
    choice, not to convenience."""

    next_question: NextQuestion = dspy.InputField()
    brief: ProjectBrief = dspy.InputField()
    scene_summary: SceneSummary = dspy.InputField()
    draft_options: List[str] = dspy.OutputField()
    tool_call_plan: ToolCallPlan = dspy.OutputField()
    ui_component_type: UIComponentType = dspy.OutputField()


class ComposeAnswerOptions(dspy.Signature):
    """Reconcile the draft options against the real tool results now
    available. Drop any draft option with no backing item in the results, and
    add real options the draft missed. Shape every surviving option to fit
    the component: chip_select / image_carousel need a label, one-line
    description, and a backing id (a product, a delivery tier, or similar);
    swatch_grid needs a label, a swatch reference id, and a backing product
    id; slider needs min, max, step, and a suggested default drawn from the
    results; text_input needs no options at all - just carry the prompt
    through as-is, since the user's own answer is the data. Never emit an
    option that doesn't trace to a real item in the tool results."""

    next_question: NextQuestion = dspy.InputField()
    draft_options: List[str] = dspy.InputField()
    tool_results: ToolResults = dspy.InputField()
    ui_component_type: UIComponentType = dspy.InputField()
    ui_task: UITask = dspy.OutputField()


# ---------------------------------------------------------------------------
# Stage 4 — design synthesis
# ---------------------------------------------------------------------------


class SynthesizeDesign(dspy.Signature):
    """Synthesize everything learned - the brief, the scene, and every answer
    the user selected - into a cohesive design proposal. Reference the
    specific grounded products chosen along the way. Write it like a
    designer's pitch: a short concept narrative, layout notes tied to actual
    scene features, a shopping list of the grounded items, and 2-3 next
    steps. Also emit a structured placements list (product id, zone, position
    hint) for every chosen item that has a physical location in the scene -
    this is consumed by the rendering tool, not read by the user, so keep it
    terse and literal rather than prose."""

    brief: ProjectBrief = dspy.InputField()
    scene_summary: SceneSummary = dspy.InputField()
    qa_history: List[QAExchange] = dspy.InputField()
    proposal: DesignProposal = dspy.OutputField()


# ---------------------------------------------------------------------------
# Stage 5b — ground delivery details while the (non-DSPy) 3D render runs.
#
# The "Shipping & Timing" task itself (delivery-speed + shipping-address
# questions) runs through the existing PlanNextQuestion / PlanTaskUI /
# ComposeAnswerOptions loop like any other task — no new signature needed
# there. This is the one genuinely new module: turning the grounded shopping
# list, the chosen delivery tier, and real unit prices into a final tally.
# ---------------------------------------------------------------------------


class SynthesizeCostSummary(dspy.Signature):
    """Given every priced shopping-list item and the delivery tier the user
    picked, assemble a clear final cost summary. List every item with its
    price, sum them into a subtotal, estimate tax at 8% of the subtotal, add
    the shipping cost from the chosen delivery tier, and total everything -
    the arithmetic must be exact, this isn't the place to round loosely.
    Report the delivery window from the chosen tier. Close with one short,
    warm line about when it'll arrive. This is the last thing shown before
    the 3D render finishes, so it should read as a confident wrap-up, not a
    receipt dump."""

    design_proposal: DesignProposal = dspy.InputField()
    priced_items: List[Product] = dspy.InputField(
        desc="Every shopping-list item, with its real unit price"
    )
    delivery_choice: DeliveryOption = dspy.InputField(
        desc="The shipping tier the user picked, with its real cost and window"
    )
    cost_summary: CostSummary = dspy.OutputField()
