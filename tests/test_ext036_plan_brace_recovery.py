"""EXT-036 TASK-48: structural-bracket recovery stage for `_extract_json` -- a dropped
`}`/`]` closer inside a nested container (REQ-33 extension).

MEASURED (originally captured in the gitignored runtime artifact
`.jaros-data/artifacts/todo_rawplan.log`, embedded verbatim below so this regression
proof is self-contained on a fresh clone/CI -- see `MEASURED_MALFORMED_PLAN`): gemma's
`todo-list-cli` plan embeds a whole multi-line Python class body as an export
"signature" JSON string and DROPS the `}` that closes the export object before the `]`
ending `exports` -- `json.loads` fails ("Expecting ',' delimiter") because
`_extract_json`'s existing greedy-match / `_balanced_span` / `_repair_json_candidate`
stages (TASK-43, REQ-33) only escape control characters and drop trailing commas, never
insert an OMITTED structural closer. `plan=None` -> 0 files build (class scores 0/3).
The same defect class also kills `kv-store-ttl` on qwen.

This suite proves: (a) the exact MEASURED plan bytes now parse into a plan dict with
the export signature string intact (was unparseable before this task -- proven with an
inline oracle replicating the pre-TASK-48 candidate-gathering logic); (b) several
already-valid JSON payloads (including nested arrays-of-objects and strings literally
containing `{ } [ ] ,`) pass through `_recover_missing_braces` BYTE-IDENTICAL and
`_extract_json` returns the SAME result as before; (c) an end-of-input-truncated payload
is left unchanged BY `_recover_missing_braces` ITSELF (never fabricated -- that stays
this helper's explicit non-goal, unchanged); (d) the helper never raises on bad input.

UPDATED (TASK-71, REQ-58): `_recover_missing_braces` still deliberately leaves
end-of-input truncation untouched (proven below, unchanged), but `_extract_json` as a
WHOLE no longer returns `None` on that shape -- its new last-resort truncation-salvage
stage (`harness/system_builder.py::_salvage_truncated_json`) now closes the dangling
structure and salvages a parseable result. See `tests/test_ext036_truncation_salvage.py`
for that stage's dedicated coverage; `test_truncated_payload_extract_json_still_none`
below is updated accordingly (renamed) to assert the new, superseding behavior rather
than pin the old one.

OFFLINE -- no live model, no network, no filesystem dependency on runtime state.
"""

from __future__ import annotations

import json
import re

import pytest

from harness.system_builder import (
    _balanced_span,
    _extract_json,
    _recover_missing_braces,
    _repair_json_candidate,
    _strip_md_fences,
)

# The exact fenced JSON body captured from a LIVE gemma draw building `todo-list-cli`
# (source: the gitignored `.jaros-data/artifacts/todo_rawplan.log` runtime artifact).
# Embedded verbatim, byte-for-byte (via a `repr()` round-trip of the original file
# bytes), so this regression proof does not depend on gitignored runtime state that
# would be absent on a fresh clone/CI.
MEASURED_MALFORMED_PLAN = '```json\n{\n  "modules": [\n    {\n      "name": "data_manager.py",\n      "responsibility": "Manages the in-memory list of items and handles state modifications.",\n      "exports": [\n        {\n          "name": "DataManager",\n          "signature": "class DataManager:\\n    def __init__(self):\\n        self.items = []\\n\\n    def add(self, text: str) -> str:\\n        self.items.append(text)\\n        return f\\"added {text}\\"\\n\\n    def list_items(self) -> list[str]:\\n        output = []\\n        for i, item in enumerate(self.items):\\n            output.append(f\\"{i}) {item}\\")\\n\\n    def mark_done(self, index: int) -> str:\\n        if 0 <= index < len(self.items):\\n            # In this simple model, we just print the message, actual state change is omitted as per spec simplicity\\n            return f\\"marked done {index}\\"\\n        return \\"Error: Index out of bounds\\"\\n\\n    def get_all_items(self) -> list[str]:\\n        return self.items"\n      ],\n      "imports": []\n    }\n  ],\n  "entrypoint": "main.py",\n  "acceptance": "Running `python main.py` and piping the input \\"add A\\\\nlist\\\\ndone 0\\\\n\\" to the script should result in the output \\"added A\\\\n(0) A\\\\nmarked done 0\\"."\n}\n```\n'


def _pre_task48_extract_json(raw: str, opener: str, closer: str):
    """Exact replica of `_extract_json` as it stood AFTER TASK-43 but BEFORE this task's
    `_recover_missing_braces` stage -- the oracle used to prove (1) the captured artifact
    genuinely failed to parse without the new recovery stage and (2) every already-valid
    payload the pre-TASK-48 logic already parsed is returned byte-identically by the new
    code (the explicit regression guard)."""
    raw = raw or ""
    m = re.search(re.escape(opener) + r".*" + re.escape(closer), raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    candidates: list[str] = []
    text = _strip_md_fences(raw)
    balanced = _balanced_span(text, opener, closer)
    if balanced is not None:
        start_idx = text.find(opener)
        tail = text[start_idx + len(balanced):].strip() if start_idx != -1 else ""
        if not tail or not tail.startswith(opener):
            candidates.append(balanced)
    if text != raw:
        m2 = re.search(re.escape(opener) + r".*" + re.escape(closer), text, re.DOTALL)
        if m2 and m2.group(0) not in candidates:
            candidates.append(m2.group(0))
    if m and m.group(0) not in candidates:
        candidates.append(m.group(0))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

    for candidate in candidates:
        repaired = _repair_json_candidate(candidate)
        if repaired == candidate:
            continue
        try:
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            continue

    return None


# ---------------------------------------------------------------------------
# (a) TRUE FIX: the exact MEASURED todo-list-cli plan bytes (embedded above).
# ---------------------------------------------------------------------------


def test_measured_plan_constant_shape():
    # Sanity on the embedded fixture itself -- fence-wrapped, non-trivial in size, and
    # recognizably the measured shape (not an empty/placeholder string).
    assert MEASURED_MALFORMED_PLAN.startswith("```json")
    assert MEASURED_MALFORMED_PLAN.rstrip().endswith("```")
    assert '"data_manager.py"' in MEASURED_MALFORMED_PLAN
    assert len(MEASURED_MALFORMED_PLAN) > 500


def test_measured_artifact_was_unparseable_before_task48():
    assert _pre_task48_extract_json(MEASURED_MALFORMED_PLAN, "{", "}") is None


def test_measured_artifact_now_parses_into_plan_dict():
    result = _extract_json(MEASURED_MALFORMED_PLAN, "{", "}")
    assert isinstance(result, dict)
    assert "modules" in result
    modules = result["modules"]
    assert isinstance(modules, list) and len(modules) == 1
    module = modules[0]
    assert module["name"] == "data_manager.py"
    exports = module["exports"]
    assert isinstance(exports, list) and len(exports) == 1
    export = exports[0]
    assert export["name"] == "DataManager"
    # The embedded Python class body must be preserved INTACT -- nothing fabricated,
    # nothing truncated.
    signature = export["signature"]
    assert "class DataManager:" in signature
    assert "def add(self, text: str) -> str:" in signature
    assert "def get_all_items(self) -> list[str]:" in signature
    assert signature.strip().endswith("return self.items")
    assert result["entrypoint"] == "main.py"


# ---------------------------------------------------------------------------
# (b) VALID UNCHANGED: `_recover_missing_braces` is a byte-identical no-op on
# already-valid JSON, and `_extract_json` returns the identical result as before.
# ---------------------------------------------------------------------------

VALID_SAMPLES = [
    # Plain flat object.
    '{"a": 1, "b": 2, "c": 3}',
    # Nested arrays-of-objects.
    '{"items": [{"id": 1, "tags": ["x", "y"]}, {"id": 2, "tags": []}], "count": 2}',
    # A string value literally containing every structural bracket character + comma.
    '{"note": "braces { } and brackets [ ] and a comma , all inside a string", "ok": true}',
    # Deep nesting mixing both bracket families.
    '{"a": {"b": [{"c": {"d": [1, 2, {"e": "f"}]}}]}}',
    # An array-mode payload (acceptance-checks shape) with an embedded bracket-y string.
    '[{"name": "check_one", "code": "assert [1,2] == [1,2]"}, {"name": "check_two", "code": "assert {1:2} == {1:2}"}]',
    # Escaped quotes + escaped backslash immediately before a closer, to exercise the
    # backslash-escape-aware string scan right at a boundary.
    '{"path": "C:\\\\Users\\\\x", "quote": "she said \\"hi\\""}',
]


@pytest.mark.parametrize("sample", VALID_SAMPLES)
def test_recover_missing_braces_is_byte_identical_on_valid_json(sample):
    recovered = _recover_missing_braces(sample)
    assert recovered == sample
    assert recovered is sample  # no reconstruction at all when nothing changed


@pytest.mark.parametrize("sample", VALID_SAMPLES)
def test_extract_json_unchanged_on_valid_json(sample):
    opener, closer = ("[", "]") if sample.lstrip().startswith("[") else ("{", "}")
    old = _pre_task48_extract_json(sample, opener, closer)
    new = _extract_json(sample, opener, closer)
    assert old is not None, "sample must already be valid under the pre-TASK-48 logic"
    assert new == old
    assert new == json.loads(sample)


# ---------------------------------------------------------------------------
# (c) END-OF-INPUT TRUNCATION is a DIFFERENT class from what `_recover_missing_braces`
# handles -- that helper never fabricates/recovers it (still true, unchanged). TASK-71
# added a DIFFERENT, later stage inside `_extract_json` (`_salvage_truncated_json`)
# that DOES handle exactly this class -- see the module docstring's "UPDATED" note and
# `tests/test_ext036_truncation_salvage.py`.
# ---------------------------------------------------------------------------

TRUNCATED_PAYLOADS = [
    '{"a": 1, "b": [1, 2, 3',
    '{"modules": [{"name": "a.py", "exports": [{"name": "Foo"',
    '{"a": {"b": {"c": 1',
]


@pytest.mark.parametrize("raw", TRUNCATED_PAYLOADS)
def test_truncated_payload_left_unchanged_by_recover(raw):
    assert _recover_missing_braces(raw) == raw


@pytest.mark.parametrize("raw", TRUNCATED_PAYLOADS)
def test_truncated_payload_now_salvaged_by_extract_json(raw):
    # TASK-71: `_extract_json` as a whole no longer gives up on end-of-input
    # truncation -- its new last-resort salvage stage closes the dangling
    # string/brackets and returns a genuinely parseable result.
    result = _extract_json(raw, "{", "}")
    assert result is not None
    assert result == json.loads(json.dumps(result))


# ---------------------------------------------------------------------------
# (d) The MISSING-CLOSER defect class, isolated: a minimal repro of the same shape
# as the measured artifact (an object closer dropped before an array closer).
# ---------------------------------------------------------------------------

MISSING_BRACE_MINIMAL = (
    '{"modules": [{"name": "a.py", "exports": ['
    '{"name": "Foo", "signature": "class Foo:\\n    def bar(self): pass"}'
    '], "imports": []}], "entrypoint": "a.py", "acceptance": "ok"}'
)
# Drop the '}' that closes the export object, right before the ']' ending "exports".
MISSING_BRACE_BROKEN = MISSING_BRACE_MINIMAL.replace(
    '"}], "imports"', '"], "imports"'
)


def test_minimal_missing_brace_repro_is_broken_json():
    with pytest.raises(json.JSONDecodeError):
        json.loads(MISSING_BRACE_BROKEN)


def test_minimal_missing_brace_repro_unparseable_before_task48():
    assert _pre_task48_extract_json(MISSING_BRACE_BROKEN, "{", "}") is None


def test_minimal_missing_brace_repro_recovered_and_parses():
    recovered = _recover_missing_braces(MISSING_BRACE_BROKEN)
    assert recovered != MISSING_BRACE_BROKEN
    parsed = json.loads(recovered)
    assert parsed["modules"][0]["exports"][0]["name"] == "Foo"

    result = _extract_json(MISSING_BRACE_BROKEN, "{", "}")
    assert isinstance(result, dict)
    assert result["modules"][0]["exports"][0]["name"] == "Foo"
    assert result == parsed


# ---------------------------------------------------------------------------
# Helper-level robustness: never raise on bad/missing input.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", [None, "", "no brackets here", "}{", "{unterminated", "]][[", "{}"]
)
def test_recover_missing_braces_never_raises(text):
    _recover_missing_braces(text)  # must not raise


def test_recover_missing_braces_empty_and_none_are_falsy_passthrough():
    assert _recover_missing_braces(None) is None
    assert _recover_missing_braces("") == ""
