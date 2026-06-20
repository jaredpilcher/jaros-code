"""Tiny single-purpose agent ``body-completer`` (EXT-002 / REQ-12).

For the IMPLEMENT regime (filling a stub): the model wastes most tokens copying the
signature+docstring back when it rewrites the whole file. This grain instead asks for
ONLY the function body and splices it after the given signature+docstring — measured at
~62% faster generation than whole-file at equal pass (and it solves *different* problems,
so as a cascade strategy it raises the union). Emits a complete file via code.write_file.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "body-completer"

_PROMPT = (
    "Complete this Python function. Output ONLY the function body — the indented "
    "statements that go after the signature and docstring. NO signature, NO docstring, "
    "NO markdown fences, NO explanation. Indent every line under the function.\n\n"
    "TASK: {instruction}\n{feedback}"
    "FUNCTION (keep this exactly, write the body that follows):\n{sig_doc}\n"
)

_STUB_LINE = re.compile(r"^\s*(pass|\.\.\.|raise\s+NotImplementedError.*)\s*$")


def signature_and_docstring(stub: str) -> str:
    """Drop the placeholder body (pass / ... / raise NotImplementedError) from the stub,
    leaving the signature + docstring the model should keep and build on."""
    lines = stub.rstrip("\n").split("\n")
    while lines and (_STUB_LINE.match(lines[-1]) or lines[-1].strip() == ""):
        lines.pop()
    return "\n".join(lines)


def splice(sig_doc: str, raw: str) -> str:
    """Combine the kept signature+docstring with the model's body. Robust to the model
    re-emitting the whole function or dropping indentation."""
    raw = re.sub(r"```[\w+-]*", "", raw).replace("```", "")
    stripped = raw.strip("\n")
    if stripped.lstrip().startswith("def "):   # model gave the whole function — use it
        return stripped + "\n"
    body_lines = []
    for ln in raw.split("\n"):
        if ln.strip() == "":
            body_lines.append("")
        elif ln.startswith((" ", "\t")):
            body_lines.append(ln)
        else:
            body_lines.append("    " + ln)     # force indentation under the function
    body = "\n".join(body_lines).rstrip("\n")
    if not body.strip():
        return ""                              # nothing usable
    return sig_doc + "\n" + body + "\n"


class BodyCompleterBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        stub = ctx.get("content", "")
        sig_doc = signature_and_docstring(stub)
        instruction = ctx.get("instruction", "")
        feedback = ctx.get("feedback", "")
        fb = f"Your previous attempt failed:\n{feedback}\n" if feedback else ""
        params = {}
        if "temperature" in ctx:
            params["temperature"] = ctx["temperature"]
        if "seed" in ctx:
            params["seed"] = ctx["seed"]
        reply = self._llm.complete(LlmRequest(
            prompt=_PROMPT.format(instruction=instruction, feedback=fb, sig_doc=sig_doc),
            params=params)).text
        content = splice(sig_doc, reply)
        if not content:
            return [create_decision(id=f"bc-{uuid.uuid4().hex}", source=NAME, type="advance",
                    payload={"events": ["start", "fail"], "note": "body-completer: empty body"})]
        return [create_decision(id=f"bc-{uuid.uuid4().hex}", source=NAME,
                type="code.write_file", payload={"path": ctx.get("path", ""), "content": content})]


def build(llm) -> BodyCompleterBoundary:
    return BodyCompleterBoundary(llm)
