"""Specialist agent ``dockerfile-editor`` (EXT-002 / REQ-7).

A specialist split from the broad rewriter (EXT-007/REQ-6): edits Dockerfiles with a
Docker-focused prompt (valid instructions, sensible layer order, no app code). Emits a
``code.write_file`` Decision. The loop's dispatcher routes Dockerfile targets here.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "dockerfile-editor"

_MAX_CONTENT = 6000

_PROMPT = (
    "You are a Dockerfile editor. Rewrite the ENTIRE Dockerfile with the instruction "
    "applied. Output the complete corrected Dockerfile between these sentinels and "
    "NOTHING else:\n"
    "<<<FILE\n...the full corrected Dockerfile...\nFILE>>>\n"
    "Rules: use valid Dockerfile instructions (FROM, WORKDIR, COPY, RUN, EXPOSE, CMD, ...); "
    "keep a sensible order; change only what the instruction requires; no application code. "
    "Do not explain.\n\n"
    "INSTRUCTION: {instruction}\n"
    "{feedback}"
    "\nCURRENT DOCKERFILE ({path}):\n{content}\n"
)

_FEEDBACK = "\nYour PREVIOUS attempt did not work. Failure output — fix the cause:\n{feedback}\n"
_FILE_RE = re.compile(r"<<<FILE\r?\n(.*?)\r?\nFILE>>>", re.S)
_FENCE_RE = re.compile(r"```(?:[\w+-]*\r?\n)?(.*?)```", re.S)


def parse_file(text: str):
    m = _FILE_RE.search(text) or _FENCE_RE.search(text)
    return m.group(1).rstrip("\n") if m else None


class DockerfileEditorBoundary:
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
                id=f"dock-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"dockerfile-editor: could not parse a Dockerfile ({reply[:60]!r})"})]
        if not new_content.endswith("\n"):
            new_content += "\n"
        return [create_decision(
            id=f"dock-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": path, "content": new_content})]


def build(llm) -> DockerfileEditorBoundary:
    return DockerfileEditorBoundary(llm)
