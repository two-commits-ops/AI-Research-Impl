"""dspy.Module wrappers around each Signature.

These are deliberately thin — one predictor each — so that compiling a module
means compiling exactly one instruction + its few-shot demos. No control flow
(looping, stage routing, tool dispatch) lives here; that's the orchestrator's
job, which is runtime and out of scope for this pass.

forward() returns the raw dspy.Prediction rather than unwrapping to a single
field. That's deliberate: metrics.py (and BootstrapFewShot/MIPROv2, which
call forward() directly during compiling) are written against the
signature's named output fields — e.g. `pred.brief`, `pred.next_question`,
`pred.is_task_done`. Unwrapping here would break that contract at compile
time even though it reads more conveniently at a call site. Callers who just
want one field can do `module(...).brief` themselves.
"""

import dspy

from help_design.schemas import (
    CaptureMode,
    CoverageHistory,
    DeliveryOption,
    DesignProposal,
    FrameFacts,
    Product,
    ProjectBrief,
    QAExchange,
    SceneSummary,
    Task,
    TaskList,
    ToolResults,
    UIComponentType,
)
from help_design.signatures import (
    AssessFrame,
    ComposeAnswerOptions,
    EditTaskList,
    ExtractBrief,
    IdentifyTasks,
    InterpretScene,
    PlanNextQuestion,
    PlanTaskUI,
    SynthesizeCostSummary,
    SynthesizeDesign,
)
from typing import List


class BriefExtractor(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(ExtractBrief)

    def forward(self, raw_query: str) -> dspy.Prediction:
        return self.predict(raw_query=raw_query)


class FrameCompletenessChecker(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(AssessFrame)

    def forward(
        self,
        brief: ProjectBrief,
        capture_mode: CaptureMode,
        current_frame: FrameFacts,
        coverage_history: CoverageHistory,
    ) -> dspy.Prediction:
        return self.predict(
            brief=brief,
            capture_mode=capture_mode,
            current_frame=current_frame,
            coverage_history=coverage_history,
        )


class SceneInterpreter(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(InterpretScene)

    def forward(
        self, brief: ProjectBrief, merged_frame_facts: List[FrameFacts]
    ) -> dspy.Prediction:
        return self.predict(brief=brief, merged_frame_facts=merged_frame_facts)


class TaskListPlanner(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(IdentifyTasks)

    def forward(self, brief: ProjectBrief, scene_summary: SceneSummary) -> dspy.Prediction:
        return self.predict(brief=brief, scene_summary=scene_summary)


class TaskListEditor(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(EditTaskList)

    def forward(
        self,
        brief: ProjectBrief,
        current_task_list: TaskList,
        supported_categories: List[str],
        user_edit_request: str,
    ) -> dspy.Prediction:
        return self.predict(
            brief=brief,
            current_task_list=current_task_list,
            supported_categories=supported_categories,
            user_edit_request=user_edit_request,
        )


class QuestionPlanner(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(PlanNextQuestion)

    def forward(
        self,
        brief: ProjectBrief,
        scene_summary: SceneSummary,
        current_task: Task,
        qa_history: List[QAExchange],
    ) -> dspy.Prediction:
        return self.predict(
            brief=brief,
            scene_summary=scene_summary,
            current_task=current_task,
            qa_history=qa_history,
        )


class TaskUIPlanner(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(PlanTaskUI)

    def forward(
        self,
        next_question,
        brief: ProjectBrief,
        scene_summary: SceneSummary,
    ) -> dspy.Prediction:
        return self.predict(
            next_question=next_question, brief=brief, scene_summary=scene_summary
        )


class AnswerOptionComposer(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(ComposeAnswerOptions)

    def forward(
        self,
        next_question,
        draft_options: List[str],
        tool_results: ToolResults,
        ui_component_type: UIComponentType,
    ) -> dspy.Prediction:
        return self.predict(
            next_question=next_question,
            draft_options=draft_options,
            tool_results=tool_results,
            ui_component_type=ui_component_type,
        )


class DesignSynthesizer(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(SynthesizeDesign)

    def forward(
        self,
        brief: ProjectBrief,
        scene_summary: SceneSummary,
        qa_history: List[QAExchange],
    ) -> dspy.Prediction:
        return self.predict(
            brief=brief, scene_summary=scene_summary, qa_history=qa_history
        )


class CostSynthesizer(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.ChainOfThought(SynthesizeCostSummary)

    def forward(
        self,
        design_proposal: DesignProposal,
        priced_items: List[Product],
        delivery_choice: DeliveryOption,
    ) -> dspy.Prediction:
        return self.predict(
            design_proposal=design_proposal,
            priced_items=priced_items,
            delivery_choice=delivery_choice,
        )


ALL_MODULES = {
    "brief_extractor": BriefExtractor,
    "frame_completeness_checker": FrameCompletenessChecker,
    "scene_interpreter": SceneInterpreter,
    "task_list_planner": TaskListPlanner,
    "task_list_editor": TaskListEditor,
    "question_planner": QuestionPlanner,
    "task_ui_planner": TaskUIPlanner,
    "answer_option_composer": AnswerOptionComposer,
    "design_synthesizer": DesignSynthesizer,
    "cost_synthesizer": CostSynthesizer,
}
