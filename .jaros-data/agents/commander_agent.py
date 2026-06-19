"""Single-purpose agent ``commander`` (EXT-002 / REQ-2).

Given a task, proposes exactly ONE shell command and emits a ``shell.exec``
Decision. Used to run builds and tests. Inert data only; the deterministic
EXT-001 tool runs the command, bounded and timed.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "commander"

_PROMPT = (
    "You decide ONE shell command to accomplish the task. "
    "Output ONLY the command on a single line: no explanation, no markdown, no backticks.\n\n"
    "TASK: {task}\n"
)


def parse_command(text: str) -> str:
    """Pull a single command line out of the model output."""
    for raw in text.splitlines():
        line = raw.strip().strip("`").strip()
        if line.lower().startswith(("here", "command:", "```")):
            line = line.split(":", 1)[-1].strip().strip("`").strip()
        if line:
            return line
    return ""


class CommanderBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        task = ctx.get("task", str(context))
        cwd = ctx.get("cwd")
        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(task=task))).text
        command = parse_command(reply)

        if not command:
            return [create_decision(
                id=f"cmd-{uuid.uuid4().hex}",
                source=NAME,
                type="advance",
                payload={"events": ["start", "fail"],
                         "note": "commander: model produced no command"},
            )]

        payload = {"command": command}
        if cwd:
            payload["cwd"] = cwd
        return [create_decision(
            id=f"cmd-{uuid.uuid4().hex}",
            source=NAME,
            type="shell.exec",
            payload=payload,
        )]


def build(llm) -> CommanderBoundary:
    return CommanderBoundary(llm)
