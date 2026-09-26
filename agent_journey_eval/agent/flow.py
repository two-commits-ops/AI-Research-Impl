from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from agent.schemas import CallFlow

FLOWS_DIR = Path(__file__).resolve().parent.parent / "flows"
DEFAULT_FLOW_PATH = FLOWS_DIR / "shopping_agent_flow.yaml"


def load_flow(path: Path = DEFAULT_FLOW_PATH) -> CallFlow:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CallFlow.model_validate(raw)


def load_all_flows(directory: Path = FLOWS_DIR) -> Dict[str, CallFlow]:
    """Loads every reviewed flow (*.yaml, excluding *.draft.yaml) in a directory,
    keyed by flow name. Only one flow exists today, but the judge and tracer
    are written against this dict so a second flow drops in without code
    changes once this agent gains a genuinely different capability/intent."""
    flows: Dict[str, CallFlow] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.endswith(".draft.yaml"):
            continue
        flow = load_flow(path)
        flows[flow.name] = flow
    return flows
