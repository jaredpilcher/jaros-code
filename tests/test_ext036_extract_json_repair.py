"""EXT-036 TASK-43: robust `_extract_json` -- balanced-bracket extraction + bounded
repair for malformed model JSON (REQ-33).

MEASURED (plan-coherence gap-hunt, 2026-07-06): across 40 CREATION-suite builds (20
tasks x2 draws) the ONLY not-shipped failures were `todo-list-cli` on BOTH draws, note
"planner produced no parseable JSON plan". Repro: the plan's `"acceptance"` field is a
long prose string that on some gemma draws carries an UNESCAPED literal control
character (a raw newline) inside the JSON string value -- `_extract_json`
(`harness/system_builder.py`) did one greedy `opener.*closer` regex + a single
`json.loads` with NO repair attempt, so it returned `None` and the build never shipped.

This suite proves: (a) the exact measured shape is now fixed (was `None` under the OLD
logic, replicated here inline as an oracle, and now returns the correct dict); (b) a
balanced-bracket extraction avoids over-spanning into trailing prose containing a
stray closer; (c) already-valid JSON is parsed to the IDENTICAL object as the OLD
logic (byte-identical valid-path regression guard); (d) genuine garbage still returns
`None`, never raises; (e) a trailing-comma defect is repaired; (f) the new helpers
never raise on None/empty/malformed input.

OFFLINE -- no live model, no network.
"""

from __future__ import annotations

import json
import re

import pytest

from harness.system_builder import (
    _balanced_span,
    _extract_json,
    _repair_json_candidate,
    _strip_md_fences,
)


def _old_extract_json(raw: str, opener: str, closer: str):
    """Exact replica of the PRE-TASK-43 `_extract_json` implementation -- the oracle
    used to prove (1) the measured failure genuinely failed under the old logic and
    (2) the new implementation is byte-identical for every input the old logic already
    parsed successfully."""
    m = re.search(re.escape(opener) + r".*" + re.escape(closer), raw or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# (a) TRUE FIX: the MEASURED todo-list shape -- a plan-shaped JSON object whose
# "acceptance" string contains a raw, unescaped embedded newline.
# ---------------------------------------------------------------------------

BROKEN_ACCEPTANCE_PLAN = '''{
  "modules": [
    {"name": "todo.py", "responsibility": "manage todo items in memory",
     "exports": [{"name": "add_todo", "signature": "def add_todo(items, text):"}],
     "imports": []},
    {"name": "main.py", "responsibility": "cli entrypoint",
     "exports": [{"name": "main", "signature": "def main():"}],
     "imports": ["todo.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "Piping input echo -e \\"add hello
list
done 0\\" should add hello, list it, then mark it done"
}'''


def test_measured_todo_list_shape_was_broken_under_old_logic():
    # Confirms this is a GENUINE fix, not a pre-existing pass: the old greedy-match +
    # single json.loads logic could not parse this measured shape.
    assert _old_extract_json(BROKEN_ACCEPTANCE_PLAN, "{", "}") is None


def test_measured_todo_list_shape_now_parses():
    result = _extract_json(BROKEN_ACCEPTANCE_PLAN, "{", "}")
    assert isinstance(result, dict)
    assert result["entrypoint"] == "main.py"
    assert [m["name"] for m in result["modules"]] == ["todo.py", "main.py"]
    assert "add hello" in result["acceptance"]
    assert "done 0" in result["acceptance"]


# ---------------------------------------------------------------------------
# (b) BALANCED: an object followed by trailing prose containing a stray '}'.
# ---------------------------------------------------------------------------

TRAILING_PROSE_WITH_STRAY_CLOSER = (
    '{"a": 1, "b": 2} some trailing prose mentioning a stray closer: } and more text.'
)


def test_trailing_prose_with_stray_closer_old_logic_fails():
    # The old greedy-to-LAST-closer match over-spans into the trailing prose and its
    # own stray '}', producing unparseable text.
    assert _old_extract_json(TRAILING_PROSE_WITH_STRAY_CLOSER, "{", "}") is None


def test_trailing_prose_with_stray_closer_now_parses_balanced():
    result = _extract_json(TRAILING_PROSE_WITH_STRAY_CLOSER, "{", "}")
    assert result == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# (c) VALID UNCHANGED: several already-valid JSON payloads parse to the IDENTICAL
# object as the OLD code -- explicit regression guard.
# ---------------------------------------------------------------------------

VALID_PAYLOADS_OBJECT = [
    '{"a": 1, "b": "line1\\nline2", "c": [1, 2, 3]}',
    '{"nested": {"x": {"y": [1, {"z": true}]}}, "note": "has \\"quotes\\" inside"}',
    """```json
{"modules": [{"name": "a.py", "exports": [], "imports": []}], "entrypoint": "a.py", "acceptance": "ok"}
```""",
    '{"only": "one field"}',
]

VALID_PAYLOADS_ARRAY = [
    '[{"name": "check1", "code": "assert True"}, {"name": "check2", "code": "assert 1 == 1"}]',
    "[1, 2, 3, [4, 5], {\"k\": \"v\\nwith escaped newline\"}]",
    "[]",
]


@pytest.mark.parametrize("raw", VALID_PAYLOADS_OBJECT)
def test_valid_object_payloads_identical_to_old_logic(raw):
    old = _old_extract_json(raw, "{", "}")
    new = _extract_json(raw, "{", "}")
    assert old is not None, "test payload must itself be valid under the old logic"
    assert new == old


@pytest.mark.parametrize("raw", VALID_PAYLOADS_ARRAY)
def test_valid_array_payloads_identical_to_old_logic(raw):
    old = _old_extract_json(raw, "[", "]")
    new = _extract_json(raw, "[", "]")
    assert old is not None, "test payload must itself be valid under the old logic"
    assert new == old


# ---------------------------------------------------------------------------
# (d) GARBAGE: genuinely non-JSON input still returns None, never raises.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "this is not json at all, no braces here",
        "{ this is truncated and never closed",
        "",
        None,
        "just some prose. no brackets whatsoever.",
    ],
)
def test_garbage_input_returns_none(raw):
    assert _extract_json(raw, "{", "}") is None


def test_garbage_array_input_returns_none():
    assert _extract_json("no array markers present", "[", "]") is None


# ---------------------------------------------------------------------------
# (e) Trailing-comma-only defect is repaired.
# ---------------------------------------------------------------------------

TRAILING_COMMA_JSON = '{"a": 1, "b": [1, 2,], "c": 3,}'


def test_trailing_comma_old_logic_fails():
    assert _old_extract_json(TRAILING_COMMA_JSON, "{", "}") is None


def test_trailing_comma_now_repaired():
    result = _extract_json(TRAILING_COMMA_JSON, "{", "}")
    assert result == {"a": 1, "b": [1, 2], "c": 3}


# ---------------------------------------------------------------------------
# (f) The [",']' array mode (acceptance checks) still works end-to-end with a
# genuinely malformed array (embedded raw newline in a check's code string).
# ---------------------------------------------------------------------------

BROKEN_CHECKS_ARRAY = '''[
  {"name": "check_one", "code": "assert True"},
  {"name": "check_two", "code": "line one
line two
assert 1 == 1"}
]'''


def test_broken_checks_array_old_logic_fails():
    assert _old_extract_json(BROKEN_CHECKS_ARRAY, "[", "]") is None


def test_broken_checks_array_now_parses():
    result = _extract_json(BROKEN_CHECKS_ARRAY, "[", "]")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "check_one"
    assert "line one" in result[1]["code"]
    assert "assert 1 == 1" in result[1]["code"]


# ---------------------------------------------------------------------------
# Helper-level robustness: never raise on None/empty/malformed input.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [None, "", "no brackets here", "}{", "{unterminated"])
def test_balanced_span_never_raises(text):
    _balanced_span(text, "{", "}")  # must not raise


@pytest.mark.parametrize("text", [None, "", "not json", 12345])
def test_repair_json_candidate_never_raises(text):
    try:
        result = _repair_json_candidate(text)
    except TypeError:
        # Only acceptable for a non-string type; must never raise for str/None/"".
        assert not isinstance(text, (str, type(None)))
    else:
        if text:
            assert isinstance(result, str)


@pytest.mark.parametrize("raw", [None, "", "no fences here", "```\njust a fence\n```"])
def test_strip_md_fences_never_raises(raw):
    _strip_md_fences(raw)  # must not raise
