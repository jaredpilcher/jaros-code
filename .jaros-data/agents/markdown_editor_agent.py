"""Specialist agent ``markdown-editor`` (EXT-002 / REQ-8).

A specialist split from the broad rewriter (EXT-007/REQ-6): edits Markdown documents
with a docs-focused prompt (valid Markdown, preserve structure, no code logic),
emitting a ``code.write_file`` Decision. The dispatcher routes .md/.markdown targets here.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "markdown-editor"

_MAX_CONTENT = 6000

_PROMPT = (
    "You are a Markdown editor. Rewrite the ENTIRE Markdown document with the instruction "
    "applied. Output the complete corrected document between these sentinels and NOTHING "
    "else:\n"
    "<<<FILE\n...the full corrected Markdown...\nFILE>>>\n"
    "Rules: valid Markdown (headings with #, lists with - , links [text](url)); keep the "
    "structure; change only what the instruction requires; it is documentation, not code. "
    "Do not explain.\n\n"
    "INSTRUCTION: {instruction}\n"
    "{feedback}"
    "\nCURRENT DOCUMENT ({path}):\n{content}\n"
)

_FEEDBACK = "\nYour PREVIOUS attempt did not work. Failure output — fix the cause:\n{feedback}\n"
_FILE_RE = re.compile(r"<<<FILE\r?\n(.*?)\r?\nFILE>>>", re.S)
_FENCE_RE = re.compile(r"```(?:[\w+-]*\r?\n)?(.*?)```", re.S)


def parse_file(text: str):
    m = _FILE_RE.search(text) or _FENCE_RE.search(text)
    return m.group(1).rstrip("\n") if m else None


class MarkdownEditorBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        path = ctx.get("path", "")
        content = (ctx.get("content", "") or "")[:_MAX_CONTENT]
        instruction = ctx.get("instruction", "")
        fb = (ctx.get("feedback", "") or "")[:1500]
        feedback = _FEEDBACK.format(feedback=fb) if fb.strip() else ""
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
                id=f"md-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"markdown-editor: could not parse a document ({reply[:60]!r})"})]
        if not new_content.endswith("\n"):
            new_content += "\n"
        return [create_decision(
            id=f"md-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": path, "content": new_content})]


def build(llm) -> MarkdownEditorBoundary:
    return MarkdownEditorBoundary(llm)
