"""Per-module compile metrics.

Where the spec calls for an "LLM-judge", these are implemented as cheap
deterministic proxies instead (word-overlap / structural checks) so the
compile step stays fast, offline-repeatable, and doesn't burn LM calls on
every candidate during bootstrapping. `make_llm_judge_metric` at the bottom
is a drop-in real judge you can swap into DESIGN_SYNTHESIZER_METRIC (or any
other module) once you want the higher-fidelity version.
"""

from __future__ import annotations

from typing import Iterable, List

import dspy


def _covered(gold_items: Iterable[str], pred_items: Iterable[str]) -> float:
    """Fraction of gold_items that show up (by keyword) somewhere in pred_items.
    Loose on purpose — these are generated phrases, not fixed vocabulary."""
    gold_items = list(gold_items)
    if not gold_items:
        return 1.0
    haystack = " ".join(pred_items).lower()
    covered = 0
    for item in gold_items:
        keywords = [w for w in item.lower().split() if len(w) > 3]
        if not keywords or any(k in haystack for k in keywords):
            covered += 1
    return covered / len(gold_items)


# ---------------------------------------------------------------------------
# Stage 0
# ---------------------------------------------------------------------------


def brief_extractor_metric(example, pred, trace=None) -> bool:
    gold, got = example.brief, pred.brief
    if got.space_type.strip().lower() != gold.space_type.strip().lower():
        return False
    goals_ok = _covered(gold.stated_goals, got.stated_goals) >= 0.4
    missing_ok = _covered(gold.missing_info, got.missing_info) >= 0.4
    return goals_ok and missing_ok


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------


_VIDEO_ADJUSTMENT_WORDS = ["pan", "tilt", "step", "move", "walk", "forward", "back", "closer", "further"]


def _phrasing_matches_capture_mode(instruction: str, capture_mode: str) -> bool:
    """A photo-mode instruction should ask for another upload; a video-mode
    one should describe a physical camera movement. Loose keyword check —
    enough to catch a mismatched mode, not a full phrasing rubric."""
    text = instruction.lower()
    if capture_mode == "photo":
        return "upload" in text or "photo" in text
    return any(w in text for w in _VIDEO_ADJUSTMENT_WORDS)


def frame_completeness_checker_metric(example, pred, trace=None) -> bool:
    gold, got = example.assessment, pred.assessment
    if got.is_complete != gold.is_complete:
        return False
    if gold.is_complete:
        return True
    missing_ok = _covered(gold.missing_elements, got.missing_elements) >= 0.5
    has_instruction = bool(got.adjustment_instruction and got.adjustment_instruction.strip())
    if not (missing_ok and has_instruction):
        return False
    return _phrasing_matches_capture_mode(got.adjustment_instruction, example.capture_mode)


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------


def scene_interpreter_metric(example, pred, trace=None) -> bool:
    facts_text = " ".join(
        " ".join(f.visible_elements) + " " + (f.notes or "")
        for f in example.merged_frame_facts
    ).lower()
    claims: List[str] = pred.summary.key_features + pred.summary.condition_notes
    if not claims:
        return False
    grounded = sum(
        1
        for c in claims
        if any(w in facts_text for w in c.lower().split() if len(w) > 3)
    )
    return (grounded / len(claims)) >= 0.5


# ---------------------------------------------------------------------------
# Stage 2.5 — task list identification + editing
# ---------------------------------------------------------------------------


def task_list_planner_metric(example, pred, trace=None) -> bool:
    got_tasks = pred.task_list.tasks
    if not (2 <= len(got_tasks) <= 7):
        return False
    gold_areas = {t.topic_area.lower() for t in example.task_list.tasks}
    got_areas = {t.topic_area.lower() for t in got_tasks}
    overlap = len(gold_areas & got_areas) / len(gold_areas) if gold_areas else 1.0
    return overlap >= 0.6


def task_list_editor_metric(example, pred, trace=None) -> bool:
    if pred.edit_result != example.edit_result:
        return False
    if not (pred.explanation and pred.explanation.strip()):
        return False
    gold_names = {t.task_name.lower() for t in example.updated_task_list.tasks}
    got_names = {t.task_name.lower() for t in pred.updated_task_list.tasks}
    if example.edit_result == "rejected":
        # rejected means the list must come back unchanged
        return got_names == gold_names
    return got_names == gold_names


# ---------------------------------------------------------------------------
# Stage 3 — now scoped per-task: is_done -> is_task_done, plus current_task
# ---------------------------------------------------------------------------


def question_planner_metric(example, pred, trace=None) -> bool:
    if example.is_task_done:
        return pred.is_task_done is True
    if pred.is_task_done:
        return False
    covered_topics = {qa.topic.lower() for qa in example.qa_history}
    if pred.next_question.topic.lower() in covered_topics:
        return False
    return pred.next_question.topic.lower() == example.next_question.topic.lower()


def task_ui_planner_metric(example, pred, trace=None) -> bool:
    tool_match = pred.tool_call_plan.tool_name == example.tool_call_plan.tool_name
    ui_match = pred.ui_component_type == example.ui_component_type
    if pred.ui_component_type == "text_input":
        options_ok = len(pred.draft_options) == 0
    else:
        options_ok = 2 <= len(pred.draft_options) <= 6
    return tool_match and ui_match and options_ok


def answer_option_composer_metric(example, pred, trace=None) -> bool:
    got, gold = pred.ui_task, example.ui_task
    valid_ids = {p.product_id for p in example.tool_results.products}
    valid_ids |= {d.tier for d in (example.tool_results.delivery_options or [])}
    got_ids = {o.backing_product_id for o in got.options if o.backing_product_id}

    if valid_ids:
        ungrounded = got_ids - valid_ids
        recall = len(got_ids & valid_ids) / len(valid_ids)
        return not ungrounded and recall >= 0.5

    # slider / color_picker / text_input: nothing groundable in play (a
    # delivery tier or product id) — just check shape parity
    return len(got.options) == len(gold.options) and got.component_type == gold.component_type


# ---------------------------------------------------------------------------
# Stage 4
# ---------------------------------------------------------------------------


def design_synthesizer_metric(example, pred, trace=None) -> bool:
    proposal = pred.proposal
    chosen_ids = {
        pid for qa in example.qa_history for pid in qa.backing_product_ids
    }
    placement_ids = {p.product_id for p in proposal.placements}
    covers_chosen = chosen_ids.issubset(placement_ids) if chosen_ids else True
    narrative_ok = len(proposal.concept_narrative.split()) >= 8
    has_next_steps = len(proposal.next_steps) >= 2
    has_shopping_list = len(proposal.shopping_list) >= 1
    return covers_chosen and narrative_ok and has_next_steps and has_shopping_list


# ---------------------------------------------------------------------------
# Stage 5b — cost + delivery grounding, run while the 3D render is working
# ---------------------------------------------------------------------------

TAX_RATE = 0.08  # kept in sync with SynthesizeCostSummary's instruction text
_CENTS = 0.01


def cost_synthesizer_metric(example, pred, trace=None) -> bool:
    got = pred.cost_summary
    priced_ids = {p.product_id for p in example.priced_items}

    line_item_ids = {li.product_id for li in got.line_items}
    if line_item_ids != priced_ids:
        return False

    expected_subtotal = round(sum(p.price for p in example.priced_items), 2)
    expected_tax = round(expected_subtotal * TAX_RATE, 2)
    expected_total = round(
        expected_subtotal + expected_tax + example.delivery_choice.cost, 2
    )

    arithmetic_ok = (
        abs(got.subtotal - expected_subtotal) < _CENTS
        and abs(got.estimated_tax - expected_tax) < _CENTS
        and abs(got.shipping_cost - example.delivery_choice.cost) < _CENTS
        and abs(got.total - expected_total) < _CENTS
    )
    if not arithmetic_ok:
        return False

    if got.delivery_window != example.delivery_choice.window:
        return False

    return bool(got.closing_note and got.closing_note.strip())


METRICS = {
    "brief_extractor": brief_extractor_metric,
    "frame_completeness_checker": frame_completeness_checker_metric,
    "scene_interpreter": scene_interpreter_metric,
    "task_list_planner": task_list_planner_metric,
    "task_list_editor": task_list_editor_metric,
    "question_planner": question_planner_metric,
    "task_ui_planner": task_ui_planner_metric,
    "answer_option_composer": answer_option_composer_metric,
    "design_synthesizer": design_synthesizer_metric,
    "cost_synthesizer": cost_synthesizer_metric,
}


# ---------------------------------------------------------------------------
# Optional: a real LLM-judge, for whenever the deterministic proxies above
# aren't enough (e.g. judging prose quality rather than structure).
# ---------------------------------------------------------------------------


class JudgeQuality(dspy.Signature):
    """Score how well the candidate output accomplishes the stated task, from
    1 (poor) to 5 (excellent). Return only the integer score."""

    task_description: str = dspy.InputField()
    candidate_output: str = dspy.InputField()
    score: int = dspy.OutputField()


def make_llm_judge_metric(task_description: str, min_score: int = 4, render=str):
    """Returns a metric(example, pred, trace) -> bool backed by an LM judge.
    `render` extracts the text to judge from `pred` (default: str(pred))."""
    judge = dspy.Predict(JudgeQuality)

    def metric(example, pred, trace=None) -> bool:
        result = judge(task_description=task_description, candidate_output=render(pred))
        return result.score >= min_score

    return metric
