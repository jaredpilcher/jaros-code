"""Specialist agent ``config-editor`` (EXT-002 / REQ-6).

A specialist split off from the broad rewriter: edits CONFIG files (JSON / YAML /
INI / TOML) rather than code. Same delimited-block contract, but a config-focused
prompt (preserve structure, valid syntax, no code). Emits a ``code.write_file``
Decision. The first step of the specialized-agent swarm (EXT-007 / REQ-6).
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "config-editor"

_MAX_CONTENT = 6000

_PROMPT = (
    "You are a configuration-file editor (JSON / YAML / INI / TOML). Rewrite the ENTIRE "
    "config file with the instruction applied. Output the complete corrected file between "
    "these sentinels and NOTHING else:\n"
    "<<<FILE\n...the full corrected config...\nFILE>>>\n"
    "Rules: keep it syntactically valid for its format (close every brace/bracket/quote); "
    "change only what the instruction requires; it is config, not code. Do not explain.\n\n"
    "INSTRUCTION: {instruction}\n"
    "{feedback}"
    "\nCURRENT CONFIG ({path}):\n{content}\n"
)

_FEEDBACK = "\nYour PREVIOUS attempt did not work. Failure output — fix the cause:\n{feedback}\n"
_FILE_RE = re.compile(r"<<<FILE\r?\n(.*?)\r?\nFILE>>>", re.S)
_FENCE_RE = re.compile(r"```(?:[\w+-]*\r?\n)?(.*?)```", re.S)


def parse_file(text: str):
    m = _FILE_RE.search(text) or _FENCE_RE.search(text)
    return m.group(1).rstrip("\n") if m else None


class ConfigEditorBoundary:
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
                id=f"cfg-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"config-editor: could not parse a config ({reply[:60]!r})"})]
        if not new_content.endswith("\n"):
            new_content += "\n"
        return [create_decision(
            id=f"cfg-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": path, "content": new_content})]


def build(llm) -> ConfigEditorBoundary:
    return ConfigEditorBoundary(llm)
