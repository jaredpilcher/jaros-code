"""Tiny single-purpose agent ``test-writer`` (EXT-008 / REQ-1).

A GENERATIVE-spine grain: given a natural-language intent and a target function
signature, emit pytest tests that pin down what "correct" means — the judgement Claude
Code makes when it writes a test before code. It does NOT implement anything; it only
turns intent into checkable assertions, then hands a ``code.write_file`` Decision to the
deterministic tool plane to persist them.

Plane placement (proven the hard way): asking Gemma 4 2B (`e2b`) to COMPUTE the expected output
of an example fails the same way the off-by-one did — it got `running_total([2,3])`
"== [1,3,6]", arithmetic it cannot do, producing impossible tests. So ground-truth
values are NOT computed by the model. ``extract_examples`` deterministically pulls the
literal `f(args) returns value` examples the user already stated in the intent and turns
them into assertions — zero model arithmetic. The model is only the fallback when the
intent states no explicit example. The hidden oracle still guards honesty: a hardcoded
`return [1,3,6]` passes the extracted example but fails the oracle's other cases.
"""

from __future__ import annotations

import ast
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "test-writer"

_CONNECTOR = re.compile(r"\s*(?:returns?|->|==|gives?|yields?|equals?|is|=)\s*", re.IGNORECASE)


def _match_call(text: str, open_idx: int) -> tuple[str | None, int]:
    """Balanced bracket scan from the '(' at ``open_idx``; return (args, end-after-')')."""
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i + 1
    return None, -1


def _coerce_literal(s: str) -> str | None:
    """Longest prefix of ``s`` that is a valid Python literal (list/dict/num/str)."""
    s = s.strip()
    for end in range(len(s), 0, -1):
        frag = s[:end].strip().rstrip(".").strip()
        if not frag:
            continue
        try:
            ast.literal_eval(frag)
            return frag
        except (ValueError, SyntaxError):
            continue
    return None


def extract_examples(intent: str, func: str) -> list[tuple[str, str]]:
    """Deterministically pull `func(args) <connector> value` examples the user STATED in
    the intent. No model arithmetic — the user's own examples are the ground truth."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(re.escape(func) + r"\s*\(", intent):
        open_idx = intent.index("(", m.start())
        args, end = _match_call(intent, open_idx)
        if args is None:
            continue
        conn = _CONNECTOR.match(intent, end)
        if not conn:
            continue
        lit = _coerce_literal(intent[conn.end():])
        if lit is None:
            continue
        call = f"{func}({args.strip()})"
        key = f"{call}=={lit}"
        if key not in seen:
            seen.add(key)
            out.append((call, lit))
    return out

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


def build_tests_from_examples(module: str, func: str, examples: list[tuple[str, str]]) -> str:
    """Render extracted (call, literal) examples into a runnable pytest module."""
    body = "\n".join(f"    assert {call} == {lit}" for call, lit in examples)
    return f"from {module} import {func}\n\n\ndef test_it():\n{body}\n"


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

        # Plane placement: prefer the user's own stated examples (deterministic, no
        # model arithmetic). Only fall back to the model if the intent states none.
        examples = extract_examples(intent, func)
        if examples:
            tests = build_tests_from_examples(module, func, examples)
            return [create_decision(
                id=f"tw-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
                payload={"path": test_path, "content": tests,
                         "note": f"test-writer: {len(examples)} example(s) extracted"})]

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
