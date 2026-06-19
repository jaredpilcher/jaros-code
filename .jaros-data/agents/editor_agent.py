"""Single-purpose agent ``editor`` (EXT-002 / REQ-1).

Given a file's content and an instruction, proposes ONE exact old->new edit and
emits a ``code.apply_patch`` Decision. Uses a delimited-block contract (not JSON)
because a 2B model produces it reliably. Emits inert data only — the deterministic
EXT-001 tool applies (and uniqueness-checks) the edit.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "editor"

_MAX_CONTENT = 6000  # keep the prompt within gemma2:2b's reliable window

_PROMPT = (
    "You are a precise code-editing tool. You are given a FILE and an INSTRUCTION.\n"
    "Output EXACTLY ONE edit as these two blocks and NOTHING else:\n"
    "<<<OLD\n"
    "(snippet copied character-for-character from the FILE; it must appear EXACTLY once)\n"
    "OLD>>>\n"
    "<<<NEW\n"
    "(the replacement text)\n"
    "NEW>>>\n"
    "Keep the edit as small as possible. Do not explain.\n\n"
    "INSTRUCTION: {instruction}\n\n"
    "FILE ({path}):\n{content}\n"
)

_OLD_RE = re.compile(r"<<<OLD\r?\n(.*?)\r?\nOLD>>>", re.S)
_NEW_RE = re.compile(r"<<<NEW\r?\n(.*?)\r?\nNEW>>>", re.S)


def parse_edit(text: str):
    """Extract (old, new) from the model output, or None if absent."""
    old = _OLD_RE.search(text)
    new = _NEW_RE.search(text)
    if not old or not new:
        return None
    return old.group(1), new.group(1)


class EditorBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        path = ctx.get("path", "")
        content = (ctx.get("content", "") or "")[:_MAX_CONTENT]
        instruction = ctx.get("instruction", "")

        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(
            instruction=instruction, path=path, content=content))).text
        parsed = parse_edit(reply)

        if parsed is None:
            # Honest failure: record it, never invent an action (Tenet 3).
            return [create_decision(
                id=f"edit-{uuid.uuid4().hex}",
                source=NAME,
                type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"editor: could not parse an edit from model output ({reply[:60]!r})"},
            )]

        old, new = parsed
        return [create_decision(
            id=f"edit-{uuid.uuid4().hex}",
            source=NAME,
            type="code.apply_patch",
            payload={"path": path, "old": old, "new": new},
        )]


def build(llm) -> EditorBoundary:
    return EditorBoundary(llm)
