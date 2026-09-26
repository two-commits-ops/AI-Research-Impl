"""Turns fixtures/sessions.py into per-module dspy.Example trainsets.

This is the only file that converts the hand-authored session dicts into
actual pydantic objects and dspy.Examples — one function per module, plus
`build_all_trainsets()` for compile.py to pull from in one call.
"""

from __future__ import annotations

from typing import Dict, List

import dspy

from help_design.fixtures.catalog import SUPPORTED_CATEGORIES
from help_design.fixtures.sessions import (
    SESSIONS,
    STANDALONE_BRIEF_QUERIES,
    TASK_EDIT_EXAMPLES,
)
from help_design.schemas import (
    CostSummary,
    CoverageHistory,
    DesignProposal,
    FrameAssessment,
    NextQuestion,
    ProjectBrief,
    QAExchange,
    SceneSummary,
    Task,
    TaskList,
    ToolCallPlan,
    UIOption,
    UITask,
)
from help_design.tools.mock_tools import (
    dispatch_tool_call,
    get_priced_products,
    shipping_options_lookup,
    vision_scene_tool,
)

SLIDER_STEP_DEFAULT = 500.0
TAX_RATE = 0.08  # kept in sync with SynthesizeCostSummary's instruction text

FULFILLMENT_TASK = {"task_name": "Shipping & Timing", "topic_area": "logistics"}
"""Auto-appended by the orchestrator once DesignSynthesizer finishes — not
part of any session's task_list, since it's system-triggered rather than
user-planned. Defined once here so every function that needs to treat it
like a normal task (QuestionPlanner training) uses the same Task shape."""


def _exchanges_to_history(exchanges: List[dict]) -> List[QAExchange]:
    return [
        QAExchange(
            question=exch["question_text"],
            topic=exch["topic"],
            chosen_answer=exch["chosen_answer"],
            backing_product_ids=[exch["chosen_product_id"]] if exch["chosen_product_id"] else [],
            task_name=exch["task_name"],
        )
        for exch in exchanges
    ]


def _qa_history_upto(session: dict, upto_index: int) -> List[QAExchange]:
    """QAExchange history accumulated from the *main* task exchanges
    [0, upto_index) — QuestionPlanner sees the full cross-task history, not
    just the current task's own slice, so it doesn't re-ask something an
    earlier task already established (e.g. budget). Deliberately excludes
    logistics_exchanges: those don't exist yet until DesignSynthesizer (and
    everything upstream of it) has already finished."""
    return _exchanges_to_history(session["qa_exchanges"][:upto_index])


def build_brief_extractor_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        examples.append(
            dspy.Example(
                raw_query=session["raw_query"],
                brief=ProjectBrief(**session["brief"]),
            ).with_inputs("raw_query")
        )
    for row in STANDALONE_BRIEF_QUERIES:
        examples.append(
            dspy.Example(
                raw_query=row["raw_query"],
                brief=ProjectBrief(**row["brief"]),
            ).with_inputs("raw_query")
        )
    return examples


def build_frame_completeness_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        brief = ProjectBrief(**session["brief"])
        capture_mode = session["capture_mode"]
        frames_seen = []
        adjustments_requested = []
        for frame_row in session["frame_sequence"]:
            current_frame = vision_scene_tool(frame_row["frame_id"])
            coverage_history = CoverageHistory(
                frames_seen=list(frames_seen),
                adjustments_requested=list(adjustments_requested),
            )
            assessment = FrameAssessment(
                is_complete=frame_row["gold_is_complete"],
                missing_elements=frame_row["gold_missing_elements"],
                adjustment_instruction=frame_row["gold_adjustment_instruction"],
            )
            examples.append(
                dspy.Example(
                    brief=brief,
                    capture_mode=capture_mode,
                    current_frame=current_frame,
                    coverage_history=coverage_history,
                    assessment=assessment,
                ).with_inputs("brief", "capture_mode", "current_frame", "coverage_history")
            )
            # roll state forward for the next frame in this session
            frames_seen.append(current_frame)
            if frame_row["gold_adjustment_instruction"]:
                adjustments_requested.append(frame_row["gold_adjustment_instruction"])
    return examples


def build_scene_interpreter_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        merged_frame_facts = [
            vision_scene_tool(row["frame_id"]) for row in session["frame_sequence"]
        ]
        examples.append(
            dspy.Example(
                brief=ProjectBrief(**session["brief"]),
                merged_frame_facts=merged_frame_facts,
                summary=SceneSummary(**session["scene_summary"]),
            ).with_inputs("brief", "merged_frame_facts")
        )
    return examples


def build_task_list_planner_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        examples.append(
            dspy.Example(
                brief=ProjectBrief(**session["brief"]),
                scene_summary=SceneSummary(**session["scene_summary"]),
                task_list=TaskList(tasks=[Task(**t) for t in session["task_list"]]),
            ).with_inputs("brief", "scene_summary")
        )
    return examples


def build_task_list_editor_examples() -> List[dspy.Example]:
    examples = []
    for row in TASK_EDIT_EXAMPLES:
        examples.append(
            dspy.Example(
                brief=ProjectBrief(**row["brief"]),
                current_task_list=TaskList(
                    tasks=[Task(**t) for t in row["current_task_list"]]
                ),
                supported_categories=list(SUPPORTED_CATEGORIES),
                user_edit_request=row["user_edit_request"],
                edit_result=row["edit_result"],
                updated_task_list=TaskList(
                    tasks=[Task(**t) for t in row["updated_task_list"]]
                ),
                explanation=row["explanation"],
            ).with_inputs(
                "brief", "current_task_list", "supported_categories", "user_edit_request"
            )
        )
    return examples


def _task_qa_examples(
    brief: ProjectBrief,
    scene_summary: SceneSummary,
    current_task: Task,
    task_exchanges: List[dict],
    history_before_task: List[QAExchange],
) -> List[dspy.Example]:
    """Shared by both the main task_list loop and the auto-appended
    fulfillment task below — same is_task_done=False*/True mechanics either
    way, since QuestionPlanner doesn't distinguish where a task came from."""
    examples = []
    history = list(history_before_task)
    for exch in task_exchanges:
        examples.append(
            dspy.Example(
                brief=brief,
                scene_summary=scene_summary,
                current_task=current_task,
                qa_history=list(history),
                next_question=NextQuestion(
                    question_text=exch["question_text"], topic=exch["topic"]
                ),
                is_task_done=False,
            ).with_inputs("brief", "scene_summary", "current_task", "qa_history")
        )
        history.append(_exchanges_to_history([exch])[0])
    # terminal example: this task's own exchanges are now exhausted
    examples.append(
        dspy.Example(
            brief=brief,
            scene_summary=scene_summary,
            current_task=current_task,
            qa_history=list(history),
            next_question=NextQuestion(question_text="", topic=""),
            is_task_done=True,
        ).with_inputs("brief", "scene_summary", "current_task", "qa_history")
    )
    return examples


def build_question_planner_examples() -> List[dspy.Example]:
    """One inner Q&A loop per task — every task in the session's task_list,
    plus one more for the auto-appended "Shipping & Timing" fulfillment task,
    which runs after all of them with the *full* main-task history already
    behind it."""
    examples = []
    for session in SESSIONS:
        brief = ProjectBrief(**session["brief"])
        scene_summary = SceneSummary(**session["scene_summary"])
        exchanges = session["qa_exchanges"]

        for task_row in session["task_list"]:
            task_exchanges = [e for e in exchanges if e["task_name"] == task_row["task_name"]]
            history_index = exchanges.index(task_exchanges[0])
            examples.extend(
                _task_qa_examples(
                    brief,
                    scene_summary,
                    Task(**task_row),
                    task_exchanges,
                    _qa_history_upto(session, history_index),
                )
            )

        examples.extend(
            _task_qa_examples(
                brief,
                scene_summary,
                Task(**FULFILLMENT_TASK),
                session["logistics_exchanges"],
                _qa_history_upto(session, len(exchanges)),  # all main tasks done
            )
        )
    return examples


def build_task_ui_planner_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        brief = ProjectBrief(**session["brief"])
        scene_summary = SceneSummary(**session["scene_summary"])
        for exch in session["qa_exchanges"] + session["logistics_exchanges"]:
            examples.append(
                dspy.Example(
                    next_question=NextQuestion(
                        question_text=exch["question_text"], topic=exch["topic"]
                    ),
                    brief=brief,
                    scene_summary=scene_summary,
                    draft_options=exch["draft_options"],
                    tool_call_plan=ToolCallPlan(**exch["tool_call_plan"]),
                    ui_component_type=exch["ui_component_type"],
                ).with_inputs("next_question", "brief", "scene_summary")
            )
    return examples


def _gold_ui_task(exch: dict) -> UITask:
    tool_results = dispatch_tool_call(ToolCallPlan(**exch["tool_call_plan"]))
    component_type = exch["ui_component_type"]

    if component_type == "text_input":
        # Nothing to reconcile — the user's own answer is the data.
        options = []
    elif tool_results.delivery_options:
        options = [
            UIOption(
                label=opt.tier.title(),
                description=f"{opt.window} · ${opt.cost:.0f} shipping",
                backing_product_id=opt.tier,
            )
            for opt in tool_results.delivery_options
        ]
    elif component_type in ("swatch_grid", "image_carousel", "chip_select"):
        options = [
            UIOption(
                label=p.name,
                description=f"{p.category} · {', '.join(p.tags)}",
                backing_product_id=p.product_id,
                swatch_ref=p.swatch_ref,
            )
            for p in tool_results.products
        ]
    elif component_type == "slider":
        pr = tool_results.price_range or {}
        options = [
            UIOption(
                min=pr.get("min"),
                max=pr.get("max"),
                step=SLIDER_STEP_DEFAULT,
                default=pr.get("typical"),
            )
        ]
    elif component_type == "color_picker":
        options = [
            UIOption(label=swatch["name"], description=swatch["hex"])
            for swatch in (tool_results.palette or [])
        ]
    else:
        options = []

    return UITask(
        component_type=component_type,
        prompt_text=exch["question_text"],
        options=options,
    )


def build_answer_option_composer_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        for exch in session["qa_exchanges"] + session["logistics_exchanges"]:
            tool_results = dispatch_tool_call(ToolCallPlan(**exch["tool_call_plan"]))
            examples.append(
                dspy.Example(
                    next_question=NextQuestion(
                        question_text=exch["question_text"], topic=exch["topic"]
                    ),
                    draft_options=exch["draft_options"],
                    tool_results=tool_results,
                    ui_component_type=exch["ui_component_type"],
                    ui_task=_gold_ui_task(exch),
                ).with_inputs(
                    "next_question", "draft_options", "tool_results", "ui_component_type"
                )
            )
    return examples


def build_design_synthesizer_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        n = len(session["qa_exchanges"])
        examples.append(
            dspy.Example(
                brief=ProjectBrief(**session["brief"]),
                scene_summary=SceneSummary(**session["scene_summary"]),
                qa_history=_qa_history_upto(session, n),
                proposal=DesignProposal(**session["design_proposal"]),
            ).with_inputs("brief", "scene_summary", "qa_history")
        )
    return examples


def _gold_cost_summary(priced_items, delivery_choice) -> dict:
    """Same arithmetic the SynthesizeCostSummary metric independently
    recomputes — kept here once so gold examples and the metric can't drift
    apart from each other by accident."""
    line_items = [
        {
            "product_id": p.product_id,
            "label": p.name,
            "unit_price": p.price,
            "subtotal": p.price,
        }
        for p in priced_items
    ]
    subtotal = round(sum(p.price for p in priced_items), 2)
    estimated_tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + estimated_tax + delivery_choice.cost, 2)
    return {
        "line_items": line_items,
        "subtotal": subtotal,
        "shipping_cost": delivery_choice.cost,
        "estimated_tax": estimated_tax,
        "total": total,
        "delivery_window": delivery_choice.window,
        "closing_note": f"Everything should arrive within {delivery_choice.window}.",
    }


def build_cost_synthesizer_examples() -> List[dspy.Example]:
    examples = []
    for session in SESSIONS:
        proposal = DesignProposal(**session["design_proposal"])
        product_ids = [p["product_id"] for p in session["design_proposal"]["placements"]]
        priced_items = get_priced_products(product_ids)

        location = session["logistics"]["shipping_location"]
        tier = session["logistics"]["delivery_tier"]
        options = shipping_options_lookup(location, product_ids)
        delivery_choice = next(o for o in options if o.tier == tier)

        examples.append(
            dspy.Example(
                design_proposal=proposal,
                priced_items=priced_items,
                delivery_choice=delivery_choice,
                cost_summary=CostSummary(**_gold_cost_summary(priced_items, delivery_choice)),
            ).with_inputs("design_proposal", "priced_items", "delivery_choice")
        )
    return examples


def build_all_trainsets() -> Dict[str, List[dspy.Example]]:
    return {
        "brief_extractor": build_brief_extractor_examples(),
        "frame_completeness_checker": build_frame_completeness_examples(),
        "scene_interpreter": build_scene_interpreter_examples(),
        "task_list_planner": build_task_list_planner_examples(),
        "task_list_editor": build_task_list_editor_examples(),
        "question_planner": build_question_planner_examples(),
        "task_ui_planner": build_task_ui_planner_examples(),
        "answer_option_composer": build_answer_option_composer_examples(),
        "design_synthesizer": build_design_synthesizer_examples(),
        "cost_synthesizer": build_cost_synthesizer_examples(),
    }
