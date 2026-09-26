#!/usr/bin/env python
"""One-time (or occasional) offline step: draft the ideal-path graph for the
shopping agent from its actual capabilities — its system prompt and its tool
schemas — rather than hand-writing the graph from scratch.

This writes a DRAFT file; it never overwrites the reviewed, live flow. Review
the draft, then copy what you want into flows/shopping_agent_flow.yaml.

    python -m scripts.derive_flow
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from dotenv import load_dotenv

load_dotenv()

from agent.judge import _generate  # reuses the same structured-output + retry plumbing as the turn judge
from agent.prompts import AGENT_SYSTEM_PROMPT
from agent.schemas import CallFlow
from agent.tools.mock_tools import MOCK_TOOL_SPECS
from agent.tools.product_search import PRODUCT_SEARCH_TOOL_SPEC

DRAFT_PATH = Path(__file__).resolve().parent.parent / "flows" / "shopping_agent_flow.draft.yaml"

DERIVE_PROMPT = """\
Given this voice agent's system prompt and its available tools, draft its ideal call-flow graph.

The graph should be the SMALLEST set of nodes that captures the real branch points implied by
the prompt and tools — not one node per sentence of the prompt. Each node needs: a stable snake_case
id, a short name, a one-sentence description, the expected_actor (who drives it forward), an
expected_tool if one is typically called there (else null), and a list of edges — each a
plain-language condition for when that transition legitimately fires, plus the target node id.

Include legitimate loops where the prompt/tools imply them (e.g. searching again after feedback,
or restarting the flow for a second item) as edges, not as separate linear stages. Only include
transitions that are actually plausible given the tools this agent has — don't invent a branch
for a capability it doesn't have.

Also give the flow a one-line entry_description: when does this flow apply at all (useful later
if multiple flows are loaded and one has to be chosen).

System prompt:
{system_prompt}

Available tools (name, description, parameters):
{tools_desc}
"""


def _tools_desc() -> str:
    specs = [PRODUCT_SEARCH_TOOL_SPEC, *MOCK_TOOL_SPECS]
    lines = []
    for spec in specs:
        fn = spec["function"]
        lines.append(f"- {fn['name']}: {fn['description']} — params: {json.dumps(fn['parameters']['properties'])}")
    return "\n".join(lines)


def main() -> None:
    prompt = DERIVE_PROMPT.format(system_prompt=AGENT_SYSTEM_PROMPT, tools_desc=_tools_desc())
    raw = _generate(prompt, "You design conversational call-flow graphs for voice agents.", CallFlow)
    flow = CallFlow.model_validate(raw)
    flow.name = flow.name or "shopping_agent_draft"

    DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DRAFT_PATH, "w") as f:
        yaml.dump(json.loads(flow.model_dump_json()), f, sort_keys=False, allow_unicode=True)

    print(f"Draft written to {DRAFT_PATH}")
    print("Review it, then merge what you want into flows/shopping_agent_flow.yaml — this never auto-promotes.")


if __name__ == "__main__":
    main()
