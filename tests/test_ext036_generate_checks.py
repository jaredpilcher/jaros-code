"""EXT-036 TASK-41 (REQ-31): 7B-GENERATE acceptance checks -- the owner's extension of the
landed REQ-30 7B-review. Where `review_checks` (REQ-30) is BOUNDED by Gemma's own proposed
checks (it can only correct/drop what Gemma wrote), `generate_checks` writes acceptance
checks FROM SCRATCH -- unshackled from Gemma's hallucinations -- using ONLY the visible spec
+ built module sources (NO ORACLE LEAK, same honesty framing as REQ-30's `REVIEW_PROMPT`).

This file proves, OFFLINE (a fake/canned `generator_llm` stub, no live model, no network):
  (1) a well-formed multi-check response is parsed into the right number of runnable
      {name, code} dicts;
  (2) NO ORACLE LEAK: the prompt sent to the generator carries only the spec + module
      sources -- never any hidden/expected value that could only come from an oracle;
  (3) fenced markdown code (```python ... ```) is stripped correctly, and multiple fenced
      blocks are split into separate checks;
  (4) a generator that raises, or returns unparseable/non-asserting garbage, never crashes
      -- `generate_checks` always returns a list, `[]` at worst.
"""

from __future__ import annotations

from harness.acceptance_review import GENERATE_PROMPT, generate_checks


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


MODULES = {"main.py": "def add(a, b):\n    return a + b\n"}
SPEC = "A tiny helper module `main.py` exporting `add(a, b)` that returns a + b."

# A value that could ONLY appear in a hidden/expected-output oracle (never in spec or code) --
# used to prove the generator prompt never leaks such a thing.
ORACLE_ONLY_STRING = "__HIDDEN_ORACLE_EXPECTED_VALUE_42__"


TWO_CHECK_RESPONSE = (
    "```python\n"
    "# add returns the sum\n"
    "from main import add\n"
    "assert add(2, 3) == 5\n"
    "```\n"
    "```python\n"
    "# add is commutative\n"
    "from main import add\n"
    "assert add(3, 2) == add(2, 3)\n"
    "```\n"
)


class _TwoCheckGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp(TWO_CHECK_RESPONSE)


class _DropGenerator:
    def complete(self, request):
        return _Resp("DROP")


class _RaisingGenerator:
    def complete(self, request):
        raise RuntimeError("Jetson unreachable")


class _GarbageGenerator:
    """Returns prose with no runnable/asserting code at all."""

    def complete(self, request):
        return _Resp("I think the module looks correct and probably works as intended.")


class _SyntaxErrorGenerator:
    def complete(self, request):
        return _Resp("```python\ndef broken(:\n    pass\n```")


def test_generate_checks_parses_two_wellformed_checks():
    out = generate_checks(SPEC, MODULES, _TwoCheckGenerator())
    assert len(out) == 2
    for chk in out:
        assert set(chk.keys()) >= {"name", "code"}
        assert "assert" in chk["code"]
        assert "```" not in chk["code"]
    # each check's code is genuinely runnable (imports the real module, real assertion)
    joined = "\n".join(c["code"] for c in out)
    assert "from main import add" in joined
    assert "add(2, 3) == 5" in joined
    assert "add(3, 2) == add(2, 3)" in joined


def test_generate_checks_respects_max_checks_bound():
    out = generate_checks(SPEC, MODULES, _TwoCheckGenerator(), max_checks=1)
    assert len(out) == 1


def test_generate_checks_no_oracle_leak_prompt_carries_only_spec_and_code():
    """NO ORACLE LEAK (Tenet 3): the generator only ever sees spec + built module source --
    never a hidden/expected value. The prompt must contain the spec and code verbatim, and
    must NEVER contain a string that could only come from a hidden oracle."""
    generator = _TwoCheckGenerator()
    generate_checks(SPEC, MODULES, generator)
    assert len(generator.prompts) == 1
    prompt = generator.prompts[0]
    assert SPEC in prompt
    assert "def add(a, b)" in prompt
    assert ORACLE_ONLY_STRING not in prompt
    assert prompt == GENERATE_PROMPT.format(
        spec=SPEC[:1500], code="# main.py\n" + MODULES["main.py"], max_checks=4
    )


def test_generate_checks_strips_markdown_fences_and_splits_multiple_blocks():
    out = generate_checks(SPEC, MODULES, _TwoCheckGenerator())
    assert len(out) == 2
    names = {c["name"] for c in out}
    assert "add returns the sum" in names
    assert "add is commutative" in names
    for chk in out:
        assert not chk["code"].strip().startswith("```")
        assert not chk["code"].strip().endswith("```")


def test_generate_checks_whole_response_drop_returns_empty_list():
    assert generate_checks(SPEC, MODULES, _DropGenerator()) == []


def test_generate_checks_generator_raises_returns_empty_list():
    assert generate_checks(SPEC, MODULES, _RaisingGenerator()) == []


def test_generate_checks_unparseable_prose_returns_empty_list():
    assert generate_checks(SPEC, MODULES, _GarbageGenerator()) == []


def test_generate_checks_syntax_error_block_is_omitted_not_crashed():
    assert generate_checks(SPEC, MODULES, _SyntaxErrorGenerator()) == []


def test_generate_checks_never_raises_on_bad_input():
    assert generate_checks(SPEC, MODULES, _TwoCheckGenerator(), max_checks=0) is not None
    assert generate_checks(None, None, _TwoCheckGenerator()) is not None
    assert generate_checks(SPEC, None, _RaisingGenerator()) == []
    assert generate_checks("", {}, _DropGenerator()) == []
