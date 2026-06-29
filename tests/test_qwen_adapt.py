"""Offline tests for harness/qwen_adapt.py — EXT-021 REQ-4/REQ-5.

All tests are OFFLINE: the _LLM singleton is monkeypatched with a fake that
returns predefined Python code.  No live Jetson, no real LLM calls.

Acceptance criteria covered
----------------------------
(a) qwen_code builds a DIRECT instruct prompt containing the function name,
    the task spec, and "Output ONLY the function definition ... no markdown".
(b) qwen_code strips ```python ... ``` fences from the LLM response.
(c) qwen_code returns parseable Python code (ast.parse succeeds).
(d) qwen_code includes the context block in the prompt when non-empty.
(e) qwen_code locates the function definition even when the response has prose
    before the def.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import harness.qwen_adapt as qa


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal response object with a .text attribute (mirrors LlmResponse)."""
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Fake LLM that returns a predefined response and records the last prompt."""
    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    def complete(self, request: Any) -> _FakeResponse:
        self.prompts.append(request.prompt)
        return _FakeResponse(self._response)


# ---------------------------------------------------------------------------
# Tests: prompt structure
# ---------------------------------------------------------------------------

def test_prompt_contains_function_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code wraps the function name in backtick-quoting in the prompt."""
    fake = _FakeLlm("def foo(x):\n    return x + 1\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    qa.qwen_code("Add 1 to x.", "foo")

    assert len(fake.prompts) == 1
    assert "`foo`" in fake.prompts[0]


def test_prompt_contains_task_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code embeds the task spec (task_or_spec) verbatim in the prompt."""
    fake = _FakeLlm("def bar():\n    return 42\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    spec = "Return the number 42 unconditionally."
    qa.qwen_code(spec, "bar")

    assert spec in fake.prompts[0]


def test_prompt_has_output_only_directive(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code includes 'Output ONLY the function definition' and 'no markdown'."""
    fake = _FakeLlm("def baz():\n    pass\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    qa.qwen_code("Implement baz.", "baz")

    prompt = fake.prompts[0]
    assert "Output ONLY the function definition" in prompt
    assert "no markdown" in prompt


def test_prompt_includes_nonempty_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code includes the context block when it is non-empty."""
    fake = _FakeLlm("def fn(x):\n    return x\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    context = "Current source:\ndef fn(x):\n    pass\n"
    qa.qwen_code("Implement fn.", "fn", context=context)

    assert "Current source:" in fake.prompts[0]


def test_prompt_omits_empty_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code does NOT add an empty context block to the prompt."""
    fake = _FakeLlm("def fn():\n    pass\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    qa.qwen_code("Implement fn.", "fn", context="")

    # Prompt should not have stray blank context section — the word 'context'
    # itself need not be absent, but the prompt should be clean.
    prompt = fake.prompts[0]
    # The two consecutive \n\n\n (from empty ctx_block inserted) would be a sign.
    # Simpler: prompt does NOT contain the empty-string context.
    assert "  \n" not in prompt   # no trailing-whitespace-only line from empty block


# ---------------------------------------------------------------------------
# Tests: fence stripping
# ---------------------------------------------------------------------------

def test_strips_python_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code strips ```python ... ``` fences (qwen's default output style)."""
    fake = _FakeLlm("```python\ndef add(a, b):\n    return a + b\n```")
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Implement add.", "add")

    assert "```" not in result
    assert "def add" in result


def test_strips_plain_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code strips plain ``` fences without a language specifier."""
    fake = _FakeLlm("```\ndef sub(a, b):\n    return a - b\n```")
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Implement sub.", "sub")

    assert "```" not in result
    assert "def sub" in result


# ---------------------------------------------------------------------------
# Tests: parseable output
# ---------------------------------------------------------------------------

def test_result_is_parseable_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code output can be parsed by ast.parse (no broken indentation)."""
    fake = _FakeLlm("```python\ndef count(items):\n    return len(items)\n```")
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Count items.", "count")

    ast.parse(result)   # raises SyntaxError on failure


def test_result_is_parseable_with_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """A multi-line function body also parses cleanly."""
    code = (
        "```python\n"
        "def greet(name):\n"
        "    if not name:\n"
        "        return 'Hello!'\n"
        "    return f'Hello, {name}!'\n"
        "```"
    )
    fake = _FakeLlm(code)
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Greet by name.", "greet")

    ast.parse(result)
    assert "def greet" in result


# ---------------------------------------------------------------------------
# Tests: function-def extraction
# ---------------------------------------------------------------------------

def test_locates_def_after_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code extracts the def block even when prose precedes it."""
    # qwen sometimes outputs a brief explanation before the code
    fake = _FakeLlm(
        "Here is my implementation:\n\ndef my_sum(nums):\n    return sum(nums)\n"
    )
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Sum nums.", "my_sum")

    assert result.startswith("def my_sum")
    ast.parse(result)


def test_result_starts_with_def(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code result starts with 'def {name}' when the model returns a clean function."""
    fake = _FakeLlm("def square(n):\n    return n * n\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    result = qa.qwen_code("Square n.", "square")

    assert result.lstrip().startswith("def square")


# ---------------------------------------------------------------------------
# Tests: temperature and max_tokens passed to the LLM
# ---------------------------------------------------------------------------

def test_temperature_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """qwen_code passes temperature=0.0 (deterministic) to the LLM."""
    fake = _FakeLlm("def f():\n    pass\n")
    monkeypatch.setattr(qa, "_LLM", fake)

    # Intercept the LlmRequest to check params
    captured_params: list[dict] = []

    class _CaptureLlm:
        def complete(self, req: Any) -> _FakeResponse:
            captured_params.append(dict(req.params))
            return _FakeResponse("def f():\n    pass\n")

    monkeypatch.setattr(qa, "_LLM", _CaptureLlm())

    qa.qwen_code("Implement f.", "f")

    assert captured_params
    assert captured_params[0].get("temperature") == 0.0
