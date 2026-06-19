"""Single-purpose agent ``orchestrator`` (EXT-004 / REQ-4).

The top-level router: given a user's natural-language request, it decides WHICH action
(and thus which downstream agents/tools) should serve it, emitting an inert routing
Decision. The model decides *what* the user wants; the deterministic CLI decides *how*
to carry it out (dispatching to the matching specialist/tool). Tiny, fixed output —
the regime where gemma2:2b is reliable.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "orchestrator"

ACTIONS = ("fix", "find", "grep", "run", "read", "list", "symbols", "status", "help")

_PROMPT = (
    "You route a developer's request to ONE action. Choose exactly one action from this "
    "list and give its argument. Output EXACTLY two lines and nothing else:\n"
    "ACTION: <one of: fix | find | run | read | list | symbols | status | help>\n"
    "ARG: <the file path, search term, or command — or empty>\n\n"
    "Guide: editing/fixing a file = fix; locating code = find; running a command/tests = run; "
    "showing a file = read; listing a directory = list; a file's functions = symbols.\n\n"
    "REQUEST: {request}\n"
)

_ACTION_RE = re.compile(r"ACTION:\s*([a-zA-Z]+)", re.I)
_ARG_RE = re.compile(r"ARG:\s*(.*)", re.I)


def parse_route(text: str):
    a = _ACTION_RE.search(text)
    g = _ARG_RE.search(text)
    action = (a.group(1).lower() if a else "")
    if action not in ACTIONS:
        # tolerate the model just naming the action somewhere
        for cand in ACTIONS:
            if re.search(rf"\b{cand}\b", text.lower()):
                action = cand
                break
        else:
            action = "help"
    arg = (g.group(1).strip() if g else "").strip().strip("`'\"")
    return action, arg


class OrchestratorBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        request = ctx.get("request", str(context))
        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(request=request))).text
        action, arg = parse_route(reply)
        return [create_decision(
            id=f"orch-{uuid.uuid4().hex}", source=NAME, type="advance",
            payload={"events": ["start", "complete"], "action": action, "arg": arg,
                     "note": f"orchestrator: route -> {action} {arg}".strip()})]


def build(llm) -> OrchestratorBoundary:
    return OrchestratorBoundary(llm)
