"""Tiny single-purpose agent ``test-writer`` (EXT-008 / REQ-1).

A GENERATIVE-spine grain: given a natural-language intent and a target function
signature, emit pytest tests that pin down what "correct" means — the judgement Claude
Code makes when it writes a test before code. It does NOT implement anything; it only
turns intent into checkable assertions, then hands a ``code.write_file`` Decision to the
deterministic tool plane to persist them.

This is the honest hard part: the quality of these tests (vs. a held-out oracle the
agent never sees) measures whether the system understood the user's intent.
"""

from __future__ import annotations

import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "test-writer"

_PROMPT = (
    "Write pytest tests that check a Python function meets this description.\n"
    "Output ONLY Python code: import the function, then ONE function `def test_it():` "
    "containing several `assert` statements covering normal and edge cases. No prose, "
    "no markdown fences, no explanation.\n\n"
    "DESCRIPTION:\n{intent}\n\n"
    "The function lives in module `{module}` and its signature is: {signature}\n"
    "Import it with: from {module} import {func}\n\n"
    "Tests:"
)


def parse_tests(text: str, module: str, func: str) -> str:
    """Pull runnable test code out of the model reply; guarantee the import + a test fn."""
    text = re.sub(r"```[\w+-]*", "", text).replace("```", "").strip()
    # Drop any leading chatter before the first plausible code line.
    lines = text.split("\n")
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith(("from ", "import ", "def test")):
            start = i
            break
    code = "\n".join(lines[start:]).strip()
    if f"from {module} import" not in code and f"import {module}" not in code:
        code = f"from {module} import {func}\n\n\n{code}"
    if "def test" not in code:
        return ""  # no actual test produced
    return code + "\n"


class TestWriterBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = ctx.get("intent", "")
        module = ctx.get("module", "")
        func = ctx.get("func", module)
        signature = ctx.get("signature", f"def {func}(...)")
        test_path = ctx.get("test_path", f"test_{module}.py")
        params = {"seed": ctx["seed"]} if "seed" in ctx else {}
        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(
            intent=intent, module=module, func=func, signature=signature),
            params=params)).text
        tests = parse_tests(reply, module, func)
        if not tests:
            return [create_decision(
                id=f"tw-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"], "note": "test-writer: no tests produced"})]
        return [create_decision(
            id=f"tw-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": test_path, "content": tests})]


def build(llm) -> TestWriterBoundary:
    return TestWriterBoundary(llm)
