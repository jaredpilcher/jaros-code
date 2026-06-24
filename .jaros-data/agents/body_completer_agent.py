"""Tiny single-purpose agent ``body-completer`` (EXT-002 / REQ-12).

For the IMPLEMENT regime (filling a stub): the model wastes most tokens copying the
signature+docstring back when it rewrites the whole file. This grain instead asks for
ONLY the function body and splices it after the given signature+docstring — measured at
~62% faster generation than whole-file at equal pass (and it solves *different* problems,
so as a cascade strategy it raises the union). Emits a complete file via code.write_file.
"""

from __future__ import annotations

import ast
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "body-completer"

_PROMPT = (
    "Complete this Python function. Output ONLY the function body — the indented "
    "statements that go after the signature and docstring. NO signature, NO docstring, "
    "NO markdown fences, NO explanation. Indent every line under the function.\n\n"
    "{edge}TASK: {instruction}\n{feedback}"
    "FUNCTION (keep this exactly, write the body that follows):\n{sig_doc}\n"
)

# Generic edge-case scaffolding (no-ceiling pursuit, 2026-06-23): the diagnosed HumanEval failures
# were ALL edge-case fall-throughs (function returns None on empty input). This is a generic coding
# concern, not benchmark-specific. Gated for held-out A/B measurement; promoted to default only if it
# lifts a held-out slice.
_EDGECASE = (
    "Handle EVERY input the docstring implies, including edge cases — empty string/list, zero, "
    "negative, single-element, and boundary values. Make sure every code path returns the correct "
    "value; never fall through to an implicit None.\n\n"
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


_REPAIR = (
    "This Python code fails to import (IndentationError). Re-indent it to VALID Python: every "
    "statement inside an if/for/while/def block must be indented 4 MORE spaces than the line that "
    "opens it, and code after a block dedents back out. Keep the logic identical. Output ONLY the "
    "corrected code, no markdown:\n\n{code}"
)


def _parses(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def repair_indentation(llm, content: str, *, seed: int = 0) -> str:
    """Parse-gated syntax-repair: the 2B often emits correct LOGIC with broken indentation (a flat /
    mis-nested body -> IndentationError -> the module won't even import). When the spliced output
    doesn't parse, ask the model to re-indent ITS OWN code (logic preserved, not regenerated). The
    parse-check is a deterministic gate. HELD-OUT deterministic pass@1: 0-50 33->38, 50-100 31->38
    (+12/100 = +12%). It was the dominant pass@1 failure mode (~60%), a harness gap not a model limit."""
    if not content or _parses(content):
        return content
    reply = llm.complete(LlmRequest(prompt=_REPAIR.format(code=content),
                                    params={"temperature": 0.0, "seed": seed})).text
    src = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    # Drop any prose BEFORE the first code line, but KEEP leading imports/decorators/class — cutting
    # to the first `def` would strip the stub's `from typing import List` / `import math` and cause a
    # NameError (the dominant post-repair failure before this fix).
    m = re.search(r"^\s*(?:from |import |@|class |def )", src, re.M)
    fixed = (src[m.start():] if m else src).rstrip() + "\n"
    return fixed if _parses(fixed) else content


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
        import os
        # TRIED + REVERTED (default OFF). It looked +6% on best-of-6, but that metric is NOISE
        # (run-to-run swings of 35/40 vs 49/50). On DETERMINISTIC pass@1-greedy (the honest metric):
        # baseline 34/50 -> edge 28/50 = -6 (helped 2, hurt 8) — the extra instruction distracts more
        # than it helps. Kept gated for reference; enable only with JCODE_EDGECASE_PROMPT=1.
        # LESSON: measure mechanism A/Bs on deterministic pass@1, never noisy best-of-6.
        edge = _EDGECASE if os.environ.get("JCODE_EDGECASE_PROMPT") == "1" else ""
        params = {}
        if "temperature" in ctx:
            params["temperature"] = ctx["temperature"]
        if "seed" in ctx:
            params["seed"] = ctx["seed"]
        reply = self._llm.complete(LlmRequest(
            prompt=_PROMPT.format(edge=edge, instruction=instruction, feedback=fb, sig_doc=sig_doc),
            params=params)).text
        content = splice(sig_doc, reply)
        if not content:
            return [create_decision(id=f"bc-{uuid.uuid4().hex}", source=NAME, type="advance",
                    payload={"events": ["start", "fail"], "note": "body-completer: empty body"})]
        content = repair_indentation(self._llm, content, seed=ctx.get("seed", 0))
        return [create_decision(id=f"bc-{uuid.uuid4().hex}", source=NAME,
                type="code.write_file", payload={"path": ctx.get("path", ""), "content": content})]


def build(llm) -> BodyCompleterBoundary:
    return BodyCompleterBoundary(llm)
