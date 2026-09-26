"""Offline compile entrypoint.

Builds the per-module trainsets from fixtures, runs the chosen optimizer for
each module against its metric, and saves the resulting compiled state to
help_design/compiled/<module_name>.json.

No server, no runtime orchestrator, no real search/vision/render backend is
touched here — this only produces compiled DSPy programs for later use.

Usage:
    export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, or set HELP_DESIGN_MODEL
    python -m help_design.compile
"""

from __future__ import annotations

import os

import dspy

from help_design.fixtures.trainsets import build_all_trainsets
from help_design.metrics import METRICS
from help_design.modules import ALL_MODULES

COMPILED_DIR = os.path.join(os.path.dirname(__file__), "compiled")

# Per the offline-compile plan in docs/dspy-design-studio-spec.md section 5:
# language-heavy, high-leverage modules get MIPROv2 (joint instruction +
# few-shot optimization); the rest get BootstrapFewShot as a cheap baseline.
OPTIMIZER_CHOICE = {
    "brief_extractor": "bootstrap",
    "frame_completeness_checker": "bootstrap",
    "scene_interpreter": "bootstrap",
    "task_list_planner": "bootstrap",
    "task_list_editor": "bootstrap",
    "question_planner": "mipro",
    "task_ui_planner": "bootstrap",
    "answer_option_composer": "mipro",
    "design_synthesizer": "mipro",
    "cost_synthesizer": "bootstrap",
}


def configure_lm() -> dspy.LM:
    """Reads HELP_DESIGN_MODEL, else picks a cheap default based on whichever
    API key is set. Raises loudly if neither is configured — compiling
    always needs a real LM, even though every tool in the pipeline is mocked."""
    model = os.environ.get("HELP_DESIGN_MODEL")
    if not model:
        if os.environ.get("ANTHROPIC_API_KEY"):
            model = "anthropic/claude-3-5-haiku-latest"
        elif os.environ.get("OPENAI_API_KEY"):
            model = "openai/gpt-4o-mini"
        else:
            raise RuntimeError(
                "No LM configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
                "or set HELP_DESIGN_MODEL to a dspy.LM model string."
            )
    lm = dspy.LM(model)
    dspy.settings.configure(lm=lm)
    return lm


def compile_module(name: str, trainset: list, metric) -> dspy.Module:
    module = ALL_MODULES[name]()
    strategy = OPTIMIZER_CHOICE[name]

    if strategy == "bootstrap":
        optimizer = dspy.teleprompt.BootstrapFewShot(
            metric=metric,
            max_bootstrapped_demos=4,
            max_labeled_demos=min(16, len(trainset)),
        )
        return optimizer.compile(module, trainset=trainset)

    # mipro — fixture trainsets are tiny, so run it in its cheapest mode and
    # reuse trainset as valset; swap in a real held-out valset once the
    # trainset in fixtures/sessions.py grows past a handful of sessions.
    optimizer = dspy.teleprompt.MIPROv2(metric=metric, auto="light")
    return optimizer.compile(
        module,
        trainset=trainset,
        valset=trainset,
        minibatch=False,
        requires_permission_to_run=False,
    )


def main() -> None:
    configure_lm()
    os.makedirs(COMPILED_DIR, exist_ok=True)

    trainsets = build_all_trainsets()

    for name in ALL_MODULES:
        examples = trainsets[name]
        strategy = OPTIMIZER_CHOICE[name]
        print(f"[compile] {name}: {len(examples)} examples, optimizer={strategy}")

        compiled = compile_module(name, examples, METRICS[name])

        out_path = os.path.join(COMPILED_DIR, f"{name}.json")
        compiled.save(out_path)
        print(f"[compile] {name} -> {out_path}")


if __name__ == "__main__":
    main()
