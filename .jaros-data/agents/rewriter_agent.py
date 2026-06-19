"""Single-purpose agent ``rewriter`` (EXT-002 / REQ-4).

Rewrites an ENTIRE (small) file with an instruction applied, emitting a
``code.write_file`` Decision. This is the 2B-reliable counterpart to ``editor``:
gemma2:2b reproduces a whole small file with a fix far more reliably than it
produces an exact OLD/NEW snippet pair. Inert data only.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "rewriter"

_MAX_CONTENT = 6000

_PROMPT = (
    "You are a code-fixing tool. Rewrite the ENTIRE file with the instruction applied.\n"
    "Output the complete corrected file between these sentinels and NOTHING else:\n"
    "<<<FILE\n"
    "...the full corrected file contents...\n"
    "FILE>>>\n"
    "Write valid, syntactically-correct code. Close every quote and bracket. "
    "Keep everything that is correct; change only what the instruction requires. Do not explain.\n\n"
    "INSTRUCTION: {instruction}\n"
    "{feedback}"
    "\nCURRENT FILE ({path}):\n{content}\n"
)

_FEEDBACK = (
    "\nYour PREVIOUS attempt did not work. Here is the failure output — fix the cause:\n"
    "{feedback}\n"
)

_FILE_RE = re.compile(r"<<<FILE\r?\n(.*?)\r?\nFILE>>>", re.S)
_FENCE_RE = re.compile(r"```(?:[\w+-]*\r?\n)?(.*?)```", re.S)


def parse_file(text: str):
    """Extract the rewritten file content: sentinel first, then a code fence."""
    m = _FILE_RE.search(text)
    if m:
        return m.group(1)
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).rstrip("\n")
    return None


class RewriterBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        path = ctx.get("path", "")
        content = (ctx.get("content", "") or "")[:_MAX_CONTENT]
        instruction = ctx.get("instruction", "")
        feedback_text = (ctx.get("feedback", "") or "")[:1500]
        feedback = _FEEDBACK.format(feedback=feedback_text) if feedback_text.strip() else ""

        # Optional sampling controls: the loop escalates temperature on retries so a
        # deterministically-wrong first answer can be escaped (still local gemma2:2b).
        params = {}
        if "temperature" in ctx:
            params["temperature"] = ctx["temperature"]
        if "seed" in ctx:
            params["seed"] = ctx["seed"]

        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(
            instruction=instruction, path=path, content=content, feedback=feedback),
            params=params)).text
        new_content = parse_file(reply)

        if new_content is None or not new_content.strip():
            return [create_decision(
                id=f"rw-{uuid.uuid4().hex}",
                source=NAME,
                type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"rewriter: could not parse a file from model output ({reply[:60]!r})"},
            )]

        if not new_content.endswith("\n"):
            new_content += "\n"
        return [create_decision(
            id=f"rw-{uuid.uuid4().hex}",
            source=NAME,
            type="code.write_file",
            payload={"path": path, "content": new_content},
        )]


def build(llm) -> RewriterBoundary:
    return RewriterBoundary(llm)
