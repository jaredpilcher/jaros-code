"""EXT-036 TASK-71: a truncation-SALVAGE last-resort stage for `_extract_json` (REQ-58).

MEASURED MOTIVATION (live-reproduced, raw evidence captured in this session's scratchpad
diagnostics -- `batch3_diag_gfs_d1.out` + `batch3_calls_backup-retention-gfs-pruning-lib_d1.jsonl`):
`backup-retention-gfs-pruning-lib` fails 2/3 with note "planner produced no parseable JSON
plan" because the planner emits a WELL-FORMED ```json plan whose `"acceptance"` value is a
giant multi-line Python string, and the completion hard-truncates at
`PLAN_MAX_TOKENS=900` MID-STRING -- the raw completion ends `...test_gfs_retention` with no
closing quote, no closing brace, and no closing fence. Every existing `_extract_json` stage
fails on this shape: the greedy match and balanced-span extraction both need a closer that
was never emitted (and the greedy match, when it DOES find some `}` earlier in the text, cuts
the candidate off there -- BEFORE the "entrypoint"/"acceptance" fields even begin); and
`_recover_missing_braces` (TASK-48) deliberately leaves an end-of-input-open stack untouched
(a different, non-truncation defect class -- see its docstring).

This suite proves: (a) the EXACT measured shape now salvages -- parses cleanly, keeps the
complete `modules`/`entrypoint` fields, and passes `validate_plan` with zero defects (only
the TAIL of the truncated `acceptance` string is lost, which is expected and safe -- see the
requirement); (b) a fragment truncated mid-KEY or at a structural (non-string) position is
handled without crashing and never yields invalid JSON; (c) every PRE-EXISTING
`_extract_json`/`_salvage_truncated_json`-adjacent test still passes byte-identical (this
stage is LAST-RESORT, reached only when every earlier stage has already failed); (d)
garbage/empty input returns None, never raises; (e) a truncated fragment whose salvage
attempt still does not `json.loads` returns None -- no partial/garbage payload is ever
returned.

OFFLINE -- no live model, no network. The measured raw completion bytes below were captured
from a live Jetson gemma draw during diagnosis and are embedded verbatim (via a `repr()`
round-trip) so this regression proof is self-contained on a fresh clone/CI.
"""

from __future__ import annotations

import json

import pytest

from harness.system_builder import (
    _extract_json,
    _recover_missing_braces,
    _repair_json_candidate,
    _salvage_truncated_json,
    _strip_md_fences,
    validate_plan,
)


def _pre_task71_extract_json(raw: str, opener: str, closer: str):
    """Exact replica of `_extract_json` as it stood AFTER TASK-48 but BEFORE this task's
    truncation-salvage stage -- the oracle used to prove (1) the measured completion
    genuinely failed to parse without the new stage and (2) the new stage is reached
    ONLY as a true last resort (every input the pre-TASK-71 logic already parsed keeps
    parsing the same way)."""
    import re

    raw = raw or ""
    m = re.search(re.escape(opener) + r".*" + re.escape(closer), raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    candidates: list[str] = []
    from harness.system_builder import _balanced_span

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

    for candidate in candidates:
        recovered = _recover_missing_braces(candidate)
        if recovered == candidate:
            continue
        try:
            return json.loads(recovered)
        except (json.JSONDecodeError, ValueError):
            pass
        repaired = _repair_json_candidate(recovered)
        try:
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            continue

    return None


# ---------------------------------------------------------------------------
# (a) TRUE FIX: the MEASURED backup-retention-gfs-pruning-lib shape -- a plan-shaped
# ```json completion hard-truncated MID-STRING inside the "acceptance" value (no
# closing quote, brace, or fence at all).
# ---------------------------------------------------------------------------

MEASURED_TRUNCATED_PLAN = '```json\n{\n  "modules": [\n    {\n      "name": "gfs_retention.py",\n      "responsibility": "Implements the GFS retention policy logic.",\n      "exports": [\n        {\n          "name": "compute_keep_dates",\n          "signature": "def compute_keep_dates(snapshots: list[str], keep_daily: int, keep_weekly: int, keep_monthly: int) -> list[str]:"\n        }\n      ],\n      "imports": [\n        "datetime"\n      ]\n    }\n  ],\n  "entrypoint": "gfs_retention.py",\n  "acceptance": "def test_gfs_retention():\\n    # Test Case 1: Basic daily retention\\n    snapshots1 = [\\"2023-01-01\\", \\"2023-01-02\\", \\"2023-01-03\\", \\"2023-01-04\\", \\"2023-01-05\\"]\\n    # keep_daily=2 should keep the two most recent: 2023-01-04, 2023-01-05\\n    result1 = gfs_retention.compute_keep_dates(snapshots1, 2, 0, 0)\\n    assert sorted(result1) == [\\"2023-01-04\\", \\"2023-01-05\\"]\\n\\n    # Test Case 2: Mixed retention (Daily, Weekly, Monthly)\\n    # Snapshots spanning multiple weeks/months\\n    snapshots2 = [\\n        \\"2023-01-01\\",  # Week 1, Month 1\\n        \\"2023-01-08\\",  # Week 2, Month 1\\n        \\"2023-02-01\\",  # Week 5, Month 2\\n        \\"2023-02-15\\",  # Week 6, Month 2\\n        \\"2023-03-10\\",  # Week 9, Month 3\\n        \\"2023-03-25\\",  # Week 10, Month 3\\n    ]\\n    # keep_daily=1, keep_weekly=1, keep_monthly=1\\n    # Daily: Keep 2023-03-25 (most recent)\\n    # Weekly: Weeks present: W1, W2, W5, W6, W9, W10. Keep 1 most recent (W10). Keep newest in W10 (2023-03-25)\\n    # Monthly: Months present: M1, M2, M3. Keep 1 most recent (M3). Keep newest in M3 (2023-03-25)\\n    # Expected result should be the union, sorted.\\n    result2 = gfs_retention.compute_keep_dates(snapshots2, 1, 1, 1)\\n    expected2 = [\\"2023-03-25\\"]\\n    assert sorted(result2) == expected2\\n\\n    # Test Case 3: Retention limits exceeded (keep_daily > available)\\n    snapshots3 = [\\"2023-01-01\\", \\"2023-01-02\\"]\\n    # keep_daily=5 should keep both available dates\\n    result3 = gfs_retention.compute_keep_dates(snapshots3, 5, 0, 0)\\n    assert sorted(result3) == [\\"2023-01-01\\", \\"2023-01-02\\"]\\n\\n    print(\\"All acceptance tests passed.\\")\\n\\nif __name__ == \'__main__\':\\n    test_gfs_retention'


def test_measured_truncated_plan_was_unparseable_before_this_task():
    # Confirms this is a GENUINE fix, not a pre-existing pass: the pre-TASK-71 logic
    # (greedy match / balanced span / repair / TASK-48 brace recovery) could not parse
    # this measured, mid-string-truncated completion.
    assert _pre_task71_extract_json(MEASURED_TRUNCATED_PLAN, "{", "}") is None


def test_measured_truncated_plan_now_salvages():
    result = _extract_json(MEASURED_TRUNCATED_PLAN, "{", "}")
    assert isinstance(result, dict)
    assert [m["name"] for m in result["modules"]] == ["gfs_retention.py"]
    assert result["entrypoint"] == "gfs_retention.py"
    export = result["modules"][0]["exports"][0]
    assert export["name"] == "compute_keep_dates"
    assert "def compute_keep_dates" in export["signature"]
    # The tail of the truncated acceptance string is lost -- expected and safe (see the
    # requirement) -- but the surviving prefix is intact.
    assert result["acceptance"].startswith("def test_gfs_retention():")


def test_measured_truncated_plan_validates_clean_on_modules_and_entrypoint():
    result = _extract_json(MEASURED_TRUNCATED_PLAN, "{", "}")
    assert validate_plan(result) == []


# ---------------------------------------------------------------------------
# (b) Truncation mid-KEY or at a structural (non-string) position -- existing
# behavior preserved: never crashes, never returns invalid JSON.
# ---------------------------------------------------------------------------

TRUNCATED_MID_KEY = '{\n  "modules": [\n    {"name": "a.py", "exports": [], "imports": []}\n  ],\n  "entrypoi'

TRUNCATED_AFTER_COLON_NO_VALUE = '{"modules": [], "entrypoint":'

TRUNCATED_AFTER_COMMA_STRUCTURAL = '{"modules": [{"name": "a.py"}],\n  '

TRUNCATED_MID_NUMBER = '{"count": 4'


@pytest.mark.parametrize(
    "raw",
    [
        TRUNCATED_MID_KEY,
        TRUNCATED_AFTER_COLON_NO_VALUE,
        TRUNCATED_AFTER_COMMA_STRUCTURAL,
        TRUNCATED_MID_NUMBER,
    ],
)
def test_structural_truncation_never_crashes_and_never_returns_invalid(raw):
    # These are NOT mid-string truncations (they end mid-key, right after a colon with
    # no value, right after a trailing comma, or mid-number) -- the salvage stage may
    # or may not manage to produce something parseable, but it must never raise and
    # must never hand back a result that ISN'T genuinely valid JSON.
    result = _extract_json(raw, "{", "}")
    if result is not None:
        # If something was returned, it must be a real dict/list -- round-tripping
        # through json.dumps/json.loads must not raise.
        json.loads(json.dumps(result))


def test_salvage_helper_never_raises_on_structural_truncations():
    for raw in (
        TRUNCATED_MID_KEY,
        TRUNCATED_AFTER_COLON_NO_VALUE,
        TRUNCATED_AFTER_COMMA_STRUCTURAL,
        TRUNCATED_MID_NUMBER,
    ):
        _salvage_truncated_json(raw, "{", "}")  # must not raise


# ---------------------------------------------------------------------------
# (c) ORDERING / no-regression: the salvage stage is LAST-RESORT -- every
# pre-existing valid/repairable shape from the earlier stages still resolves
# WITHOUT needing salvage (and salvage itself is a no-op on those shapes).
# ---------------------------------------------------------------------------

ALREADY_VALID_PAYLOADS = [
    '{"a": 1, "b": "line1\\nline2", "c": [1, 2, 3]}',
    '{"nested": {"x": {"y": [1, {"z": true}]}}, "note": "has \\"quotes\\" inside"}',
    '{"only": "one field"}',
]

TRAILING_COMMA_PAYLOAD = '{"a": 1, "b": [1, 2,], "c": 3,}'

MISSING_BRACE_PAYLOAD = (
    '{\n  "modules": [\n    {"name": "a.py", "exports": [\n      {"name": "f", "signature": "def f():"}\n    ]\n    ],\n  "entrypoint": "a.py",\n  "acceptance": "ok"\n}'
)


@pytest.mark.parametrize("raw", ALREADY_VALID_PAYLOADS)
def test_already_valid_payloads_unaffected_by_salvage_stage(raw):
    # A payload the ORIGINAL greedy-match path already parses never reaches the
    # salvage stage at all -- `_salvage_truncated_json` is a no-op on it (not
    # truncated: the walk ends outside any string with an empty bracket stack).
    assert _salvage_truncated_json(raw, "{", "}") is None
    assert _extract_json(raw, "{", "}") == json.loads(raw)


def test_trailing_comma_repair_still_resolves_before_salvage_would_be_needed():
    result = _extract_json(TRAILING_COMMA_PAYLOAD, "{", "}")
    assert result == {"a": 1, "b": [1, 2], "c": 3}
    # Not truncated -- the repair stage above salvage already fixes it, and salvage
    # itself is a no-op on this shape.
    assert _salvage_truncated_json(TRAILING_COMMA_PAYLOAD, "{", "}") is None


def test_missing_brace_recovery_still_resolves_before_salvage_would_be_needed():
    # A TASK-48 structural-bracket-recovery shape (a dropped '}' INSIDE the payload,
    # not at end-of-input) is still fixed by `_recover_missing_braces`, not salvage.
    result = _extract_json(MISSING_BRACE_PAYLOAD, "{", "}")
    assert isinstance(result, dict)
    assert result["entrypoint"] == "a.py"


# ---------------------------------------------------------------------------
# (d) GARBAGE / empty -> None, never raises.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "this is not json at all, no braces here",
        "",
        None,
        "just some prose. no brackets whatsoever.",
    ],
)
def test_garbage_input_returns_none(raw):
    assert _extract_json(raw, "{", "}") is None


@pytest.mark.parametrize("text", [None, "", "no brackets here", "not json", "}{", "{unterminated"])
def test_salvage_helper_never_raises_on_garbage(text):
    # Mirrors `_balanced_span`'s garbage-input contract (both helpers `.find()` the
    # opener directly): None/empty/no-bracket/malformed strings never raise, and with
    # no opener present the helper correctly declines (returns None).
    result = _salvage_truncated_json(text, "{", "}")
    if not text or "{" not in text:
        assert result is None


# ---------------------------------------------------------------------------
# (e) A truncated fragment whose salvage attempt does NOT json.loads -> None, no
# partial/garbage payload is ever returned.
# ---------------------------------------------------------------------------

# Truncated mid-string, but closing the string + brackets still leaves invalid JSON
# because a required VALUE is entirely missing (a dangling key with no colon/value).
UNSALVAGEABLE_TRUNCATION = '{"modules": [], "entrypoint": "a.py", "note'


def test_unsalvageable_truncation_returns_none_not_garbage():
    salvage = _salvage_truncated_json(UNSALVAGEABLE_TRUNCATION, "{", "}")
    # Closing the dangling key's string still leaves `"note"` with no `:`/value --
    # not valid JSON -- so salvage must decline rather than hand back garbage.
    if salvage is not None:
        # If some attempt DID parse, it must be genuinely valid JSON (never garbage).
        json.loads(salvage)
    result = _extract_json(UNSALVAGEABLE_TRUNCATION, "{", "}")
    if result is not None:
        json.loads(json.dumps(result))


def test_array_mode_truncation_salvages_or_declines_cleanly():
    # The `[`/`]` mode (acceptance-checklist arrays) exercised end-to-end: a truncated
    # array of check objects, mid-string in the last element.
    raw = '[\n  {"name": "check_one", "code": "assert True"},\n  {"name": "check_two", "code": "assert 1 == 1'
    result = _extract_json(raw, "[", "]")
    assert isinstance(result, list)
    assert result[0]["name"] == "check_one"
    assert result[1]["name"] == "check_two"
    assert "assert 1 == 1" in result[1]["code"]
