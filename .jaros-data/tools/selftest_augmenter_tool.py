"""Execution-plane tool ``code.augment_selftests`` (EXT-012 / REQ-13).

STRONGER-ORACLE self-test augmenter: given the target function name, its full
source/docstring text (the VISIBLE spec from the parent repo source — never
test_more.py), and the model's model-generated self-test code, this tool
deterministically appends doctest-derived assertions so the fix-loop has a
HARDER red-signal on wrong candidates.

HONESTY (non-negotiable, EXT-012 REQ-8 / Tenet 3):
  This tool reads ONLY the target function's visible docstring (taken from the
  parent source or the commit's source file — the same text the model sees).
  It NEVER reads, imports, or references ``test_more.py`` or any hidden oracle.
  The augmented self-tests remain SCAFFOLDING (the model's spec, strengthened by
  the publicly visible docstring examples); the hidden oracle (``task["redgreen"]``)
  is always and only used at the final scoring step, exactly as before.

Doctest parsing strategy:
  - Extract the docstring of the named function with ``ast`` + ``inspect.cleandoc``.
  - Find every ``>>> expr`` / ``>>> stmt`` line and the expected value on the
    *following* line (``... cont`` continuations are joined; a bare ``>>> `` line
    with no following value is skipped).
  - Convert ``>>> f(x)\nresult`` pairs to ``assert f(x) == result`` assertions
    where ``result`` is a non-blank, non-``>>> `` line.
  - Wrap in a named test function (``def test_docstring_examples__<name>():``).
  - If no docstring examples are found (new function or docstring-less), return
    the model's self-tests UNCHANGED (graceful no-op fallback).
  - Also add a trivial no-crash check: call the function with each unique
    positional-arg-set from the docstring examples inside a try/except and assert
    no exception was raised (property invariant: the function accepts the inputs).

Decision payload:
  name         (str, required)  — Python function name.
  source       (str, required)  — Full function/module source text containing the
                                   docstring.  This is the VISIBLE spec text (from
                                   the parent repo file or commit source), NEVER the
                                   hidden test file.
  self_tests   (str, required)  — Model-generated self-test code to augment.

Returns:
  {
    "tool":           "code.augment_selftests",
    "self_tests":     <str>,   # augmented test code (or unchanged if no examples)
    "augmented":      <bool>,  # True if doctest assertions were appended
    "examples_found": <int>,   # number of doctest example pairs parsed
  }

This tool is additive and purely deterministic: no LLM call, no network, no disk
write.  It is the execution-plane complement to the model's own self-test grain.
"""

from __future__ import annotations

import ast
import re
import textwrap

from jaros.core.decision_gate import ValidationResult

# #EXT-012-REQ-13 Start

NAME = "code.augment_selftests"


def _extract_docstring(source: str, name: str) -> str:
    """Parse *source* with ast and return the docstring of function *name*.

    Returns an empty string if not found or if the function has no docstring.
    HONESTY: *source* must be the VISIBLE function/module source; never the
    hidden oracle.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_docstring(node) or ""
    return ""


def _parse_doctest_examples(docstring: str) -> list[tuple[str, str]]:
    """Return a list of (expr, expected_repr) pairs from the docstring.

    Each pair comes from a consecutive ``>>> expr`` / value block.
    Multi-line expressions (``... cont``) are joined.  Pairs where the expected
    value line starts with ``>>> `` (a new example immediately follows) or is blank
    are skipped — we cannot infer the expected value in those cases.

    This parser is intentionally conservative: it only produces assertions it is
    certain are correct.  False positives (wrong assertions) hurt the fix-loop
    more than false negatives (missed assertions).
    """
    lines = docstring.splitlines()
    examples: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(">>> "):
            # Collect a (possibly multi-line) expression.
            expr_parts = [line[4:]]         # strip leading ">>> "
            i += 1
            while i < len(lines) and lines[i].strip().startswith("... "):
                expr_parts.append(lines[i].strip()[4:])
                i += 1
            expr = "\n".join(expr_parts).strip()
            # The next line (if it exists) is the expected value.
            if i < len(lines):
                val_line = lines[i].strip()
                if val_line and not val_line.startswith(">>> ") and not val_line.startswith("..."):
                    examples.append((expr, val_line))
                    i += 1
                    continue
            # No usable expected value — skip this example.
        else:
            i += 1
    return examples


def _build_augment_block(name: str, examples: list[tuple[str, str]]) -> str:
    """Build a pytest test function string that asserts the doctest examples.

    Each ``(expr, expected_repr)`` pair becomes::

        assert <expr> == <expected_repr>

    ``expr`` may reference the function by name (as written in the docstring);
    the generated test imports ``name`` from whatever the caller's test file
    already imports (the augmented block is appended to the model's tests, so the
    import is already present).

    A trivial no-crash guard wraps every expression in try/except to provide the
    second invariant (no exception on docstring inputs).
    """
    lines = [f"def test_docstring_examples__{name}():"]
    lines.append(f'    """Doctest-derived assertions for `{name}` (visible spec only)."""')
    for expr, expected in examples:
        # Indent multi-line expressions.
        expr_indented = textwrap.indent(expr, "    ").lstrip()
        # Emit a no-crash check and an equality assertion.
        lines.append(f"    try:")
        lines.append(f"        _result = {expr_indented}")
        lines.append(f"    except Exception as _e:")
        lines.append(f'        raise AssertionError(f"docstring example raised: {{_e}}") from _e')
        lines.append(f"    assert _result == {expected}, (")
        lines.append(f'        f"docstring example: {name}(...) expected {expected!r}, got {{_result!r}}"')
        lines.append(f"    )")
    return "\n".join(lines)


class SelftestAugmenterTool:
    NAME = "code.augment_selftests"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        name = payload.get("name")
        source = payload.get("source")
        self_tests = payload.get("self_tests")

        if not isinstance(name, str) or not name.strip():
            return ValidationResult.reject(
                "code.augment_selftests requires a non-empty 'name' string"
            )
        if not isinstance(source, str):
            return ValidationResult.reject(
                "code.augment_selftests requires 'source' to be a string"
            )
        if not isinstance(self_tests, str):
            return ValidationResult.reject(
                "code.augment_selftests requires 'self_tests' to be a string"
            )
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        name: str = payload["name"]
        source: str = payload["source"]
        self_tests: str = payload["self_tests"]

        # HONESTY: we only inspect the visible docstring from *source*.
        # The hidden oracle (test_more.py / task["redgreen"]) is never read here.
        docstring = _extract_docstring(source, name)
        if not docstring:
            # No docstring at all — fall back gracefully, tests unchanged.
            return {
                "tool": self.NAME,
                "self_tests": self_tests,
                "augmented": False,
                "examples_found": 0,
            }

        examples = _parse_doctest_examples(docstring)
        if not examples:
            # Docstring exists but has no parseable ">>> " examples — graceful no-op.
            return {
                "tool": self.NAME,
                "self_tests": self_tests,
                "augmented": False,
                "examples_found": 0,
            }

        augment_block = _build_augment_block(name, examples)
        augmented_tests = self_tests.rstrip() + "\n\n\n" + augment_block + "\n"

        return {
            "tool": self.NAME,
            "self_tests": augmented_tests,
            "augmented": True,
            "examples_found": len(examples),
        }

# #EXT-012-REQ-13 End
