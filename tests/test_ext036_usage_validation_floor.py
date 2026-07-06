"""EXT-036 TASK-39 (REQ-28): fixes a MEASURED FALSE-NEGATIVE sitting directly beneath REQ-27's
own floor.

MEASURED PROBLEM (2026-07-05): a best-of-k (k=5) attempt built a GENUINELY WORKING SQLite
notes CLI (physically verified: `add "T" "BODY"` persists, `list` shows it, all requirements
met, n_unmet=0), but `build_system`'s acceptance still reported `done=false` ("best attempt
passes 4/5 acceptance checks"). Root cause: `_minimum_acceptance`'s per-command probe
(`_no_crash_subprocess_check(..., [[cmd, "x"]])`) feeds exactly ONE guessed positional arg per
command -- it has no way to know a command's real arity. The winning app's `add` takes TWO
args (title + content); probed with only one (`add x`), it correctly prints its OWN
usage/argument-validation message ("Error: 'add' command requires a title and content.") at
rc=0 -- REQ-27's `_has_error_marker` correctly flags the bare "Error:"-prefixed line, so the
per-command check FAILS even though the app is genuinely working. Correct argument validation
was mis-classified as a runtime defect -- a false-negative under-claim of a working app, itself
a Tenet-3 defect.

THE FIX: `_is_usage_validation_message` (+ its generated-code mirror
`_USAGE_VALIDATION_HELPER_SRC`), a conservative vocabulary classifier, wired ONLY into the
per-command GUESSED-ARITY probe via `_no_crash_subprocess_check(..., allow_usage_validation=True)`
-- an error marker is excused ONLY when it is ALSO classified as usage/argument-validation
feedback. The arity-aware round-trip check and the unconditional traceback assertion stay
STRICT/unchanged, so a genuine runtime defect (REQ-27's own motivating case) is still caught.

This file runs the ACTUAL `_minimum_acceptance` + `_run_check`/`_run_check_verbose` machinery
against two synthetic on-disk CLIs -- the hard dual test the task calls for:
  1. TRUE-POSITIVE PRESERVED: a CLI whose `list` command (invoked correctly) prints a genuine
     runtime error at rc=0 -- must still FAIL.
  2. FALSE-NEGATIVE FIXED: a CLI whose `add` command, probed with a guessed single arg, prints
     its own usage/argument-validation message at rc=0, but whose real two-arg invocation
     genuinely persists to sqlite and round-trips through `list` -- must PASS in full.

OFFLINE -- no live model; no `llm` needed at all (only the deterministic minimum + real
subprocess runs against real on-disk fixture files).
"""

from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    _has_error_marker,
    _is_usage_validation_message,
    _minimum_acceptance,
    _run_check,
    _run_check_verbose,
)


# ============================================================================================
# (unit) _is_usage_validation_message
# ============================================================================================

def test_is_usage_validation_message_catches_the_measured_false_negative_phrasing():
    assert _is_usage_validation_message(
        "Error: 'add' command requires a title and content."
    ) is True


def test_is_usage_validation_message_catches_argparse_style_usage_vocabulary():
    assert _is_usage_validation_message(
        "usage: main.py [-h] {add,list} ...\n"
        "main.py: error: the following arguments are required: command\n"
    ) is True
    assert _is_usage_validation_message("too many arguments provided") is True
    assert _is_usage_validation_message("expected 2 arguments, got 1") is True
    assert _is_usage_validation_message("please provide a title") is True


def test_is_usage_validation_message_does_not_flag_the_req27_genuine_defect_text():
    # the EXACT graceful-error phrasing REQ-27 measured live -- a genuine runtime TypeError
    # caught and printed -- must NEVER be excused as usage validation, or REQ-27's own catch
    # would be silently defeated.
    text = ("An error occurred while listing notes: DatabaseManager.__init__() "
            "missing 1 required positional argument: 'db_path'")
    assert _is_usage_validation_message(text) is False


def test_is_usage_validation_message_does_not_flag_other_req27_genuine_defect_fixtures():
    assert _is_usage_validation_message("Error: no such table: notes") is False
    assert _is_usage_validation_message("Error: could not open the store") is False
    assert _is_usage_validation_message("Exception: boom") is False
    assert _is_usage_validation_message("Traceback (most recent call last):\n  ...\n") is False
    assert _is_usage_validation_message("note not found") is False
    assert _is_usage_validation_message("Server error rate: 0.02") is False


def test_is_usage_validation_message_never_raises_on_bad_input():
    assert _is_usage_validation_message(None) is False
    assert _is_usage_validation_message("") is False
    assert _is_usage_validation_message(123) is False


# ============================================================================================
# (hard dual test, end to end through the REAL _minimum_acceptance + _run_check machinery)
# ============================================================================================

# --- Fixture 1: TRUE-POSITIVE PRESERVED -- `list` (invoked correctly) is genuinely broken ---

BROKEN_LIST_SPEC = "A tiny notes viewer CLI in main.py: the 'list' command lists all notes."

BROKEN_LIST_MODS = [
    {"name": "main.py", "responsibility": "notes viewer", "imports": [],
     "exports": [{"name": "list_notes", "signature": "def list_notes():"}]},
]
BROKEN_LIST_PLAN = {"entrypoint": "main.py"}

# `list` genuinely fails every time it is invoked (a real backing-store defect) -- this is
# REQ-27's own motivating class, reproduced generically: the command runs (no traceback) but
# gracefully prints its own error at rc=0. Extra positional args (the per-command probe's
# guessed "x") are simply ignored by this dispatch, exactly like a hand-rolled `sys.argv`
# CLI that doesn't validate argument COUNT for a zero-arg command.
BROKEN_LIST_CLI = (
    "import sys\n\n"
    "def list_notes():\n"
    "    print('Error: no such table: notes')\n\n"
    "if __name__ == '__main__':\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'list':\n"
    "        list_notes()\n"
    "    else:\n"
    "        print('usage: main.py list')\n"
)


def test_true_positive_preserved_broken_list_still_fails_the_per_command_check(tmp_path):
    root = tmp_path / "broken_list_cli"
    root.mkdir()
    (root / "main.py").write_text(BROKEN_LIST_CLI, encoding="utf-8", newline="\n")

    checks = _minimum_acceptance(BROKEN_LIST_SPEC, BROKEN_LIST_MODS, BROKEN_LIST_PLAN)
    names = [c["name"] for c in checks]
    assert any("'list'" in n for n in names)

    results = {c["name"]: _run_check(root, c) for c in checks}

    list_check_name = next(n for n in names if "'list'" in n)
    ok, out = _run_check_verbose(
        root, next(c for c in checks if c["name"] == list_check_name)
    )
    assert ok is False, f"expected the 'list' per-command check to FAIL, got pass; output={out!r}"

    # REQ-27's genuine-defect catch is untouched by REQ-28's relaxation: the full composed
    # minimum-acceptance checklist must NOT be all-pass.
    assert not all(results.values()), results


# --- Fixture 2: FALSE-NEGATIVE FIXED -- `add` needs 2 args; guessed 1-arg probe correctly
# prints its OWN usage/argument-validation message at rc=0, but the real system genuinely
# round-trips through sqlite ------------------------------------------------------------------

ROUNDTRIP_SPEC = (
    "A tiny notes datastore CLI in main.py: the 'add' command adds a note (requires a "
    "title and content) and the 'list' command lists every note."
)

ROUNDTRIP_MODS = [
    {"name": "main.py", "responsibility": "notes datastore CLI: add/list over sqlite",
     "imports": [],
     "exports": [{"name": "add_note", "signature": "def add_note(title, content):"},
                 {"name": "list_notes", "signature": "def list_notes():"}]},
]
ROUNDTRIP_PLAN = {"entrypoint": "main.py"}

# GENUINELY WORKING: `add` takes TWO positional args and persists to a real sqlite database;
# `list` genuinely reads it back. Probed with only ONE guessed arg ("x"), `add` correctly
# reports its own arity requirement -- exactly the measured false-negative shape.
WORKING_TWO_ARG_ADD_CLI = (
    "import sqlite3\n"
    "import sys\n\n"
    "DB = 'notes.db'\n\n"
    "def _ensure_table(conn):\n"
    "    conn.execute('CREATE TABLE IF NOT EXISTS notes (title TEXT, content TEXT)')\n\n"
    "def add_note(title, content):\n"
    "    conn = sqlite3.connect(DB)\n"
    "    _ensure_table(conn)\n"
    "    conn.execute('INSERT INTO notes (title, content) VALUES (?, ?)', (title, content))\n"
    "    conn.commit()\n"
    "    conn.close()\n"
    "    print('added')\n\n"
    "def list_notes():\n"
    "    conn = sqlite3.connect(DB)\n"
    "    _ensure_table(conn)\n"
    "    for row in conn.execute('SELECT title, content FROM notes'):\n"
    "        print(row[0] + ' ' + row[1])\n"
    "    conn.close()\n\n"
    "if __name__ == '__main__':\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'add':\n"
    "        args = sys.argv[2:]\n"
    "        if len(args) < 2:\n"
    "            print(\"Error: 'add' command requires a title and content.\")\n"
    "        else:\n"
    "            add_note(args[0], args[1])\n"
    "    elif len(sys.argv) > 1 and sys.argv[1] == 'list':\n"
    "        list_notes()\n"
    "    else:\n"
    "        print('usage: main.py [add|list]')\n"
)


def test_false_negative_fixed_per_command_add_check_passes_on_a_genuinely_working_cli(tmp_path):
    root = tmp_path / "working_two_arg_add_cli"
    root.mkdir()
    (root / "main.py").write_text(WORKING_TWO_ARG_ADD_CLI, encoding="utf-8", newline="\n")

    checks = _minimum_acceptance(ROUNDTRIP_SPEC, ROUNDTRIP_MODS, ROUNDTRIP_PLAN)
    names = [c["name"] for c in checks]
    assert any("'add'" in n for n in names)
    assert any("'list'" in n for n in names)
    assert any("round-trip" in n for n in names)   # the add+list pair was derived

    add_check = next(c for c in checks if "'add'" in c["name"])
    ok, out = _run_check_verbose(root, add_check)
    assert ok is True, (
        f"the per-command 'add' check must PASS -- the guessed single-arg probe's own "
        f"usage-validation message must be excused, not graded as a runtime defect; "
        f"output={out!r}"
    )

    # the FULL composed minimum-acceptance checklist (smoke + usage/--help + per-command +
    # round-trip) is all-pass for this genuinely-working system -- no new false negative.
    results = {c["name"]: _run_check_verbose(root, c) for c in checks}
    failed = {name: out for name, (ok, out) in results.items() if not ok}
    assert not failed, f"expected every minimum-acceptance check to pass; failures: {failed!r}"


def test_working_add_probed_alone_still_reports_a_usage_validation_message_not_a_crash():
    # sanity/unit check on the exact measured phrasing this fixture emits when guessed-arity
    # under-supplies an argument -- confirms the fixture reproduces the measured shape.
    assert _is_usage_validation_message(
        "Error: 'add' command requires a title and content."
    ) is True
    assert _has_error_marker(
        "Error: 'add' command requires a title and content."
    ) is True   # REQ-27's marker still fires -- REQ-28 excuses it, doesn't blind REQ-27
