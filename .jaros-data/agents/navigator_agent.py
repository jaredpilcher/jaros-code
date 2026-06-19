"""Single-purpose agent ``navigator`` (EXT-002 / REQ-5).

Given a task, decides ONE search term likely to appear in the relevant code and
emits an ``fs.grep`` Decision — a genuine agent->tool wiring: the agent reasons
about *what* to look for; the deterministic fs.grep tool does the searching. Used to
locate where to make a change in a multi-file project.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "navigator"

_PROMPT = (
    "You locate where a change must be made. Given the TASK, output ONE search term "
    "(a function name, class name, or distinctive keyword) likely to appear in the "
    "relevant source file. Output ONLY the term: no explanation, no quotes, no markdown.\n\n"
    "TASK: {task}\n"
)


def parse_term(text: str) -> str:
    for raw in text.splitlines():
        term = raw.strip().strip("`'\"").strip()
        if term and not term.lower().startswith(("here", "search", "the term")):
            return term.split()[0] if " " in term else term
    return ""


class NavigatorBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        task = ctx.get("task", str(context))
        root = ctx.get("path", ".")
        term = parse_term(self._llm.complete(LlmRequest(prompt=_PROMPT.format(task=task))).text)
        if not term:
            return [create_decision(
                id=f"nav-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"], "note": "navigator: no search term produced"})]
        return [create_decision(
            id=f"nav-{uuid.uuid4().hex}", source=NAME, type="fs.grep",
            payload={"pattern": term, "path": root})]


def build(llm) -> NavigatorBoundary:
    return NavigatorBoundary(llm)
