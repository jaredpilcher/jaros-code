"""Single-purpose agent ``test-reader`` (EXT-002 / REQ-3).

Reads captured test/command output and judges PASS or FAIL, emitting an ``advance``
Decision whose events drive the job to DONE or FAILED. The model's verdict drives
the outcome; the deterministic executor performs the state transition. Defaults
safely to FAIL when the verdict is ambiguous.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "test-reader"

_MAX_OUTPUT = 4000

_PROMPT = (
    "You are judging whether a test/command run succeeded. "
    "Reply with ONLY one word: PASS if it clearly succeeded, or FAIL otherwise.\n\n"
    "OUTPUT:\n{output}\n"
)


def verdict_is_pass(text: str) -> bool:
    """Parse the model's one-word verdict; default to FAIL when ambiguous."""
    u = text.strip().upper()
    first = u.split()[0].strip(".,!:'\"") if u.split() else ""
    if first == "PASS":
        return True
    if "PASS" in u and "FAIL" not in u:
        return True
    return False


class TestReaderBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        output = (ctx.get("output", "") if isinstance(ctx, dict) else str(context))[:_MAX_OUTPUT]
        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(output=output))).text
        passed = verdict_is_pass(reply)
        return [create_decision(
            id=f"verdict-{uuid.uuid4().hex}",
            source=NAME,
            type="advance",
            payload={
                "events": ["start", "complete"] if passed else ["start", "fail"],
                "verdict": "pass" if passed else "fail",
                "note": f"test-reader: {reply.strip()[:60]}",
            },
        )]


def build(llm) -> TestReaderBoundary:
    return TestReaderBoundary(llm)
