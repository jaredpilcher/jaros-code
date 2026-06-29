"""Offline tests for harness/r1_adapt.py — EXT-021 REQ-3.

All tests are OFFLINE: the _LLM singleton in r1_adapt is monkeypatched with a
fake that returns predefined text.  No live Jetson, no real LLM calls.

Coverage
--------
(a) <think>...</think> block is stripped AND the fenced code extracted / def found.
(b) No <think> tags: prose before code + trailing explanation after — only def returned.
(c) Multiple fenced blocks: the LAST (final answer) block is taken, not the first.
(d) Unclosed <think> (model ran out of tokens) — r1_code does not crash.
(e) code_gen_for({"prompts": "r1-reasoning"}) returns the r1 code-gen callable.
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

import harness.r1_adapt as ra


# ---------------------------------------------------------------------------
# Fake LLM helpers (mirrors test_qwen_adapt.py pattern)
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal response object with a .text attribute."""
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Fake LLM that returns a predefined response and records the last request."""
    def __init__(self, response: str) -> None:
        self._response = response
        self.last_request: Any = None

    def complete(self, request: Any) -> _FakeResponse:
        self.last_request = request
        return _FakeResponse(self._response)


# ---------------------------------------------------------------------------
# (a) <think>...</think> stripping + fenced block extraction + def location
# ---------------------------------------------------------------------------

class TestThinkBlockStripping:
    def test_strips_think_block_and_extracts_def(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code strips <think>...</think> and extracts def from the fenced block."""
        response = (
            "<think>let me reason about this step by step...</think>\n"
            "```python\n"
            "def f(x):\n"
            "    return x\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        assert "```" not in result
        assert "<think>" not in result
        assert result.startswith("def f")
        ast.parse(result)

    def test_think_block_content_does_not_appear_in_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reasoning content inside <think>...</think> is absent from the result."""
        response = (
            "<think>My internal reasoning process...</think>\n"
            "```python\n"
            "def compute(n):\n"
            "    return n * 2\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Double n.", "compute")
        assert "My internal reasoning" not in result
        assert "def compute" in result

    def test_think_block_multiline_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multi-line <think>...</think> is fully stripped (DOTALL)."""
        response = (
            "<think>\n"
            "Line one of reasoning.\n"
            "Line two of reasoning.\n"
            "</think>\n"
            "```python\n"
            "def g(a, b):\n"
            "    return a + b\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Add a and b.", "g")
        assert "<think>" not in result
        assert "</think>" not in result
        assert "def g" in result
        ast.parse(result)


# ---------------------------------------------------------------------------
# (b) No <think> tags: prose before code + trailing explanation
# ---------------------------------------------------------------------------

class TestNoThinkTagsProseAndTrailingText:
    def test_prose_before_and_after_code_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code extracts def f and drops leading prose and trailing explanation."""
        response = (
            "Here is the code:\n"
            "```python\n"
            "def f(x): return x\n"
            "```\n"
            "This works because we return x directly."
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        assert "Here is the code" not in result
        assert "This works" not in result
        assert "def f" in result

    def test_result_starts_with_def_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without <think> tags the extracted function still starts with def {name}."""
        response = (
            "Sure, here you go:\n"
            "```python\n"
            "def square(n):\n"
            "    return n * n\n"
            "```\n"
            "That's the implementation."
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Square n.", "square")
        assert result.startswith("def square")
        ast.parse(result)


# ---------------------------------------------------------------------------
# (c) Multiple fenced blocks → take the LAST (final answer)
# ---------------------------------------------------------------------------

class TestMultipleFencedBlocksTakesLast:
    def test_two_blocks_takes_second(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When there are two fenced blocks, the LAST one is the answer."""
        response = (
            "Intermediate attempt:\n"
            "```python\n"
            "def f(x): return 0\n"
            "```\n"
            "But actually:\n"
            "```python\n"
            "def f(x): return x\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        assert "return x" in result
        assert "return 0" not in result

    def test_three_blocks_takes_third(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When there are three fenced blocks, the LAST (third) is taken."""
        response = (
            "First:\n```python\ndef f(): return 1\n```\n"
            "Second:\n```python\ndef f(): return 2\n```\n"
            "Final:\n```python\ndef f(): return 3\n```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Implement f.", "f")
        assert "return 3" in result
        assert "return 1" not in result
        assert "return 2" not in result

    def test_think_block_with_intermediate_then_final(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Think block may contain code snippets; only the final fenced block is used."""
        response = (
            "<think>\n"
            "Let me try: ```python\ndef f(x): return 0\n```\n"
            "No, that's wrong.\n"
            "</think>\n"
            "```python\n"
            "def f(x):\n"
            "    return x\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        # After stripping <think>, only the post-think fenced block remains
        assert "return x" in result
        assert "return 0" not in result


# ---------------------------------------------------------------------------
# (d) Unclosed <think> (model ran out of tokens) — must not crash
# ---------------------------------------------------------------------------

class TestUnclosedThinkDoesNotCrash:
    def test_unclosed_think_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unclosed <think> (no </think>) does not crash r1_code."""
        response = "<think>I'm thinking about how to implement this function..."
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        assert isinstance(result, str)

    def test_unclosed_think_content_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Content after an unclosed <think> is stripped (dropped to end-of-string)."""
        response = "<think>reasoning that never ends"
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Return x.", "f")
        assert "<think>" not in result

    def test_unclosed_think_then_code_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even a response that starts with unclosed <think> then has no code doesn't raise."""
        response = "<think>let me think\ndef f(x):\n    return x"
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        # Should not raise
        result = ra.r1_code("Return x.", "f")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# (e) code_gen_for({"prompts": "r1-reasoning"}) returns the r1 callable
# ---------------------------------------------------------------------------

class TestCodeGenForR1:
    def test_r1_adaptation_dict_returns_r1_callable(self) -> None:
        """code_gen_for({"prompts": "r1-reasoning"}) returns the r1 code-gen callable."""
        from harness.adaptation import code_gen_for, _r1_reasoning_code_gen
        fn = code_gen_for({"prompts": "r1-reasoning"})
        assert fn is _r1_reasoning_code_gen, (
            f"Expected _r1_reasoning_code_gen, got {fn!r}"
        )

    def test_r1_string_label_returns_r1_callable(self) -> None:
        """code_gen_for('r1-reasoning') returns the r1 code-gen callable."""
        from harness.adaptation import code_gen_for, _r1_reasoning_code_gen
        fn = code_gen_for("r1-reasoning")
        assert fn is _r1_reasoning_code_gen

    def test_r1_callable_in_registry(self) -> None:
        """ADAPTATION_REGISTRY has an 'r1-reasoning' entry."""
        from harness.adaptation import ADAPTATION_REGISTRY, _r1_reasoning_code_gen
        assert "r1-reasoning" in ADAPTATION_REGISTRY
        assert ADAPTATION_REGISTRY["r1-reasoning"] is _r1_reasoning_code_gen

    def test_r1_callable_is_callable(self) -> None:
        """The r1 code-gen entry is a callable."""
        from harness.adaptation import ADAPTATION_REGISTRY
        fn = ADAPTATION_REGISTRY.get("r1-reasoning")
        assert callable(fn)

    def test_r1_callable_invokes_r1_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_r1_reasoning_code_gen delegates to r1_code (functional round-trip)."""
        from harness.adaptation import _r1_reasoning_code_gen
        response = "```python\ndef h(x):\n    return x + 1\n```"
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = _r1_reasoning_code_gen("Increment x.", "h")
        assert "def h" in result
        assert "return x + 1" in result


# ---------------------------------------------------------------------------
# Additional robustness / LLM params checks
# ---------------------------------------------------------------------------

class TestR1AdaptRobustness:
    def test_max_tokens_is_large(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code passes max_tokens >= 3500 to the LLM (reasoning needs room)."""
        captured: list[dict] = []

        class _CaptureLlm:
            def complete(self, req: Any) -> _FakeResponse:
                captured.append(dict(req.params))
                return _FakeResponse("```python\ndef f(): pass\n```")

        monkeypatch.setattr(ra, "_LLM", _CaptureLlm())
        ra.r1_code("Implement f.", "f")
        assert captured
        assert captured[0].get("max_tokens", 0) >= 3500

    def test_temperature_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code passes temperature=0.0 (deterministic) to the LLM."""
        captured: list[dict] = []

        class _CaptureLlm:
            def complete(self, req: Any) -> _FakeResponse:
                captured.append(dict(req.params))
                return _FakeResponse("```python\ndef f(): pass\n```")

        monkeypatch.setattr(ra, "_LLM", _CaptureLlm())
        ra.r1_code("Implement f.", "f")
        assert captured
        assert captured[0].get("temperature") == 0.0

    def test_empty_response_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty LLM response does not crash r1_code."""
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(""))
        result = ra.r1_code("Implement f.", "f")
        assert isinstance(result, str)

    def test_garbage_response_no_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Completely garbled LLM output does not crash r1_code."""
        monkeypatch.setattr(ra, "_LLM", _FakeLlm("!@#$%^&*(){}[]<>|"))
        result = ra.r1_code("Implement f.", "f")
        assert isinstance(result, str)

    def test_result_parseable_for_clean_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A clean R1-style response produces ast-parseable output."""
        response = (
            "<think>Let me think step by step.</think>\n"
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```"
        )
        monkeypatch.setattr(ra, "_LLM", _FakeLlm(response))
        result = ra.r1_code("Add a and b.", "add")
        ast.parse(result)
        assert "def add" in result

    def test_context_included_in_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code embeds the context block in the prompt when non-empty."""
        captured_prompts: list[str] = []

        class _CaptureLlm:
            def complete(self, req: Any) -> _FakeResponse:
                captured_prompts.append(req.prompt)
                return _FakeResponse("```python\ndef fn(x): return x\n```")

        monkeypatch.setattr(ra, "_LLM", _CaptureLlm())
        ra.r1_code("Implement fn.", "fn", context="def fn(x):\n    pass")
        assert captured_prompts
        assert "def fn(x):" in captured_prompts[0]

    def test_function_name_in_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """r1_code includes the backtick-quoted function name in the prompt."""
        captured_prompts: list[str] = []

        class _CaptureLlm:
            def complete(self, req: Any) -> _FakeResponse:
                captured_prompts.append(req.prompt)
                return _FakeResponse("```python\ndef my_fn(): pass\n```")

        monkeypatch.setattr(ra, "_LLM", _CaptureLlm())
        ra.r1_code("Implement my_fn.", "my_fn")
        assert captured_prompts
        assert "`my_fn`" in captured_prompts[0]
