"""EXT-036 TASK-82 (REQ-67, task #165): fixes a MEASURED false-REJECT of a correct pure-LIBRARY
build.

MEASURED PROBLEM (`.jaros-data/rmed_accept_probe.py`, `running-median-lib`): for a spec that
explicitly declares an import-only, no-side-effect-on-import LIBRARY module (e.g.
`running_median.py`, "must not run anything, print anything, or have any side effect merely
from being imported"), `_minimum_acceptance` still derived a CLI-shaped round-trip check by
matching PROSE words as CLI subcommands -- `_derive_roundtrip_pair` matched "new" (from
"returns a NEW list") as an add-command and "list" (from "Python `list`") as a list-command,
then ran `python running_median.py new <sentinel>` / `... list` as if it were a real CLI. There
is no `__main__` dispatch (the spec forbids one), so both invocations produced NO output and the
round-trip check ("minimum: 'new'+'list' round-trip persists") genuinely FAILED -- even though
the code was correct and the independent EXT-060 import oracle passed it. This same sentence
shape covers 39 distinct library tasks in `harness/real_systems_suite.py`.

THE FIX: `_is_library_spec`, a deterministic (no model call), CONSERVATIVE classifier gating
the CLI-shaped derivations (`_extract_command_tokens` per-command loop,
`_derive_roundtrip_pair`, `_derive_kv_roundtrip`) inside `_minimum_acceptance` -- skipped
entirely for a detected library spec, while the always-on floor (`_smoke_checklist` + the
usage/`--help` no-crash check) stays. Byte-identical for every non-library (CLI) spec.

This file runs the ACTUAL `_minimum_acceptance` + `_run_check`/`_run_check_verbose` machinery
against real on-disk fixtures (a correct library module + two broken ones) -- OFFLINE, no live
model, no network, no Jetson call.
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    _is_library_spec,
    _minimum_acceptance,
    _run_check,
    _run_check_verbose,
)
from harness.real_systems_suite import RUNNING_MEDIAN_TASK


# ============================================================================================
# (unit) _is_library_spec
# ============================================================================================

def test_is_library_spec_true_for_the_real_running_median_sentence():
    assert _is_library_spec(RUNNING_MEDIAN_TASK.sentence) is True


def test_is_library_spec_true_for_a_synthetic_no_cli_no_side_effect_sentence():
    sentence = (
        "Write a Python module in a file named stats.py: it must not run anything, print "
        "anything, or have any side effect merely from being imported, using only the "
        "standard library, defining exactly one public function `summarize(values)`."
    )
    assert _is_library_spec(sentence) is True


def test_is_library_spec_false_for_a_cli_notes_app_sentence():
    sentence = (
        "Build a command-line notes app in main.py with add and list commands, reading "
        "arguments from argv, that prints the notes to standard output."
    )
    assert _is_library_spec(sentence) is False


def test_is_library_spec_false_for_a_sentence_naming_neither_signal():
    assert _is_library_spec("Compute the sum of two numbers.") is False


def test_is_library_spec_never_raises_on_bad_input():
    assert _is_library_spec(None) is False
    assert _is_library_spec("") is False
    assert _is_library_spec(123) is False
    assert _is_library_spec("   ") is False


# ============================================================================================
# (unit) _minimum_acceptance -- checklist SHAPE for a library vs. a CLI spec
# ============================================================================================

LIBRARY_MODS = [
    {"name": "running_median.py", "responsibility": "running median over a numeric stream",
     "imports": [],
     "exports": [{"name": "running_medians", "signature": "running_medians(stream)"}]},
]
LIBRARY_PLAN = {"entrypoint": "running_median.py"}


def _has_roundtrip_check(checks):
    return any(
        "round-trip" in c.get("name", "") or "round-trip" in c.get("code", "")
        for c in checks
    )


def _has_smoke_check(checks):
    return any(c.get("name") == "smoke: modules import and expose their API" for c in checks)


def test_minimum_acceptance_for_library_spec_has_no_cli_roundtrip_but_keeps_smoke():
    checks = _minimum_acceptance(RUNNING_MEDIAN_TASK.sentence, LIBRARY_MODS, LIBRARY_PLAN)
    assert _has_smoke_check(checks)
    assert not _has_roundtrip_check(checks)
    # the per-command CLI-shaped no-crash loop is also skipped for a library spec
    assert not any("command runs without crashing" in c.get("name", "") for c in checks)


CLI_SPEC = (
    "Build a command-line notes app in main.py: the add command adds a note and the list "
    "command lists every note, reading arguments from argv."
)
CLI_MODS = [
    {"name": "main.py", "responsibility": "notes CLI", "imports": [],
     "exports": [{"name": "add_note", "signature": "def add_note(text):"},
                 {"name": "list_notes", "signature": "def list_notes():"}]},
]
CLI_PLAN = {"entrypoint": "main.py"}


def test_minimum_acceptance_for_cli_spec_still_has_the_roundtrip_check_unchanged():
    checks = _minimum_acceptance(CLI_SPEC, CLI_MODS, CLI_PLAN)
    assert _has_smoke_check(checks)
    assert _has_roundtrip_check(checks)
    assert any("command runs without crashing" in c.get("name", "") for c in checks)


# ============================================================================================
# (end to end) real on-disk fixtures through the ACTUAL _minimum_acceptance + _run_check
# ============================================================================================

# A known-correct running_medians implementation (verified by hand, mirrors the reference
# computation recorded in `harness/real_systems_suite.py` next to RUNNING_MEDIAN_TASK):
#   running_medians([5, 15, 1, 3]) -> [5, 10.0, 5, 4.0]
#   running_medians([2, 4])        -> [2, 3.0]
#   running_medians([7])           -> [7]
CORRECT_RUNNING_MEDIAN_SRC = (
    "def running_medians(stream):\n"
    "    result = []\n"
    "    prefix = []\n"
    "    for x in stream:\n"
    "        prefix.append(x)\n"
    "        sp = sorted(prefix)\n"
    "        n = len(sp)\n"
    "        if n % 2 == 1:\n"
    "            result.append(sp[n // 2])\n"
    "        else:\n"
    "            result.append((sp[n // 2 - 1] + sp[n // 2]) / 2)\n"
    "    return result\n"
)

# A regression fixture reproducing this exact bug CLASS generically: an import-only library
# whose free-standing public function returns a NEW list and whose spec text happens to use
# the words "new" and "list" in prose -- this used to false-fail the round-trip check.
GENERIC_LIBRARY_SPEC = (
    "Write a single-file Python module (never a script -- it must not run anything, print "
    "anything, or have any side effect merely from being imported) in a file named stats.py, "
    "using only the standard library, defining exactly one public function `double_all(values)` "
    "for a data pipeline. `values` is a Python `list` of numbers. The function returns a NEW "
    "Python `list` of the same length, where each element is twice the corresponding input "
    "element. `values` itself must never be mutated."
)
GENERIC_LIBRARY_MODS = [
    {"name": "stats.py", "responsibility": "doubles every element of a list", "imports": [],
     "exports": [{"name": "double_all", "signature": "double_all(values)"}]},
]
GENERIC_LIBRARY_PLAN = {"entrypoint": "stats.py"}
CORRECT_DOUBLE_ALL_SRC = (
    "def double_all(values):\n"
    "    return [v * 2 for v in values]\n"
)


def test_real_running_median_sentence_extracted_new_and_list_as_bogus_roundtrip_words():
    # sanity: confirm the SPEC really does contain the two prose words that used to be
    # mis-picked as CLI subcommands, so the regression this task fixes is genuinely exercised.
    assert " new " in RUNNING_MEDIAN_TASK.sentence.lower().replace("\n", " ")
    assert "list" in RUNNING_MEDIAN_TASK.sentence.lower()


def test_correct_library_module_now_passes_the_library_minimum_checklist(tmp_path):
    root = tmp_path / "correct_running_median"
    root.mkdir()
    (root / "running_median.py").write_text(
        CORRECT_RUNNING_MEDIAN_SRC, encoding="utf-8", newline="\n"
    )

    checks = _minimum_acceptance(RUNNING_MEDIAN_TASK.sentence, LIBRARY_MODS, LIBRARY_PLAN)
    assert not _has_roundtrip_check(checks)  # the bogus check must not even be derived

    results = {c["name"]: _run_check_verbose(root, c) for c in checks}
    failed = {name: out for name, (ok, out) in results.items() if not ok}
    assert not failed, f"expected every library minimum-acceptance check to pass; failures: {failed!r}"


def test_correct_generic_library_with_new_and_list_prose_now_passes(tmp_path):
    # the exact bug CLASS (not sqlite/lru-specific): a spec that uses "new"/"list" in prose
    # while declaring an import-only library must not false-fail the round-trip check that
    # used to be derived from those words.
    root = tmp_path / "correct_generic_library"
    root.mkdir()
    (root / "stats.py").write_text(CORRECT_DOUBLE_ALL_SRC, encoding="utf-8", newline="\n")

    checks = _minimum_acceptance(GENERIC_LIBRARY_SPEC, GENERIC_LIBRARY_MODS, GENERIC_LIBRARY_PLAN)
    assert not _has_roundtrip_check(checks)

    results = {c["name"]: _run_check_verbose(root, c) for c in checks}
    failed = {name: out for name, (ok, out) in results.items() if not ok}
    assert not failed, f"expected every library minimum-acceptance check to pass; failures: {failed!r}"


def test_false_done_safety_broken_library_missing_export_still_fails(tmp_path):
    # a library module that never defines the declared export must still fail the
    # always-kept smoke check -- the guard can only skip false-FAILING checks, never a
    # genuine defect the smoke floor already catches.
    root = tmp_path / "broken_missing_export"
    root.mkdir()
    (root / "running_median.py").write_text(
        "def some_other_function():\n    return None\n", encoding="utf-8", newline="\n"
    )

    checks = _minimum_acceptance(RUNNING_MEDIAN_TASK.sentence, LIBRARY_MODS, LIBRARY_PLAN)
    results = {c["name"]: _run_check(root, c) for c in checks}
    smoke_name = "smoke: modules import and expose their API"
    assert smoke_name in results
    assert results[smoke_name] is False
    assert not all(results.values())


def test_false_done_safety_broken_library_raising_on_import_still_fails(tmp_path):
    # a library module that raises merely from being imported must still fail the smoke
    # check -- proving the guard never manufactures a pass for a genuinely broken library.
    root = tmp_path / "broken_raises_on_import"
    root.mkdir()
    (root / "running_median.py").write_text(
        "raise RuntimeError('boom at import time')\n\n"
        "def running_medians(stream):\n"
        "    return list(stream)\n",
        encoding="utf-8", newline="\n",
    )

    checks = _minimum_acceptance(RUNNING_MEDIAN_TASK.sentence, LIBRARY_MODS, LIBRARY_PLAN)
    results = {c["name"]: _run_check(root, c) for c in checks}
    smoke_name = "smoke: modules import and expose their API"
    assert smoke_name in results
    assert results[smoke_name] is False
    assert not all(results.values())
