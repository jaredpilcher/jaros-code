"""EXT-059 TASK-2: exact-stdout / exit-code / empty-output check variants (REQ-2).

OFFLINE -- no live model, no network. These are pure deterministic checks over small inline stub
Python programs, run through the SAME ``_run_single_check`` seam ``run_creation_suite`` already
uses for every check kind, proving the new ``exact_stdout``/``expect_rc``/``empty_output`` dict-
shaped variants DISCRIMINATE (a correct stub passes, a wrong one honestly fails) without altering
the existing substring-contains 3-tuple behavior at all (regression proof at the bottom).
"""

from __future__ import annotations

import sys
from pathlib import Path

from harness.system_suite import (
    CreationTask,
    _run_check_variant,
    _run_single_check,
    run_creation_suite,
)

# --- stub programs -----------------------------------------------------------------------------

_EXACT_STDOUT_GOOD_CODE = (
    "if __name__ == '__main__':\n"
    "    print('hello')\n"
)

_EXACT_STDOUT_EXTRA_CODE = (
    "if __name__ == '__main__':\n"
    "    print('hello')\n"
    "    print('extra')\n"
)

_RC2_CODE = (
    "import sys\n"
    "if __name__ == '__main__':\n"
    "    sys.exit(2)\n"
)

_RC0_CODE = (
    "if __name__ == '__main__':\n"
    "    pass\n"
)

_EMPTY_OUTPUT_CODE = (
    "if __name__ == '__main__':\n"
    "    pass\n"
)

_NONEMPTY_OUTPUT_CODE = (
    "if __name__ == '__main__':\n"
    "    print('unexpected')\n"
)

_SUBSTRING_SUM_CLI_CODE = (
    "import sys\n"
    "def main():\n"
    "    line = sys.stdin.readline()\n"
    "    print(sum(int(x) for x in line.split()))\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


def _write_entry(root: Path, code: str) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(code, encoding="utf-8")
    return {"entrypoint": "main.py"}


# --- exact_stdout ---------------------------------------------------------------------------

def test_exact_stdout_passes_on_exact_match(tmp_path):
    plan = _write_entry(tmp_path, _EXACT_STDOUT_GOOD_CODE)
    check = {"kind": "exact_stdout", "argv": [], "stdin": None, "expected": "hello\n"}
    assert _run_single_check(check, tmp_path, plan, sys.executable) is True


def test_exact_stdout_fails_on_extra_output():
    """A stub emitting extra output beyond the expected exact stdout FAILS -- discriminates,
    unlike a substring-contains check which would still pass."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext059_") as tmp:
        root = Path(tmp)
        plan = _write_entry(root, _EXACT_STDOUT_EXTRA_CODE)
        check = {"kind": "exact_stdout", "argv": [], "stdin": None, "expected": "hello\n"}
        assert _run_single_check(check, root, plan, sys.executable) is False

        passed, message = _run_check_variant(check, root, plan, sys.executable)
        assert passed is False
        assert "mismatch" in message
        assert "hello" in message


# --- expect_rc -------------------------------------------------------------------------------

def test_expect_rc_passes_when_matching(tmp_path):
    plan = _write_entry(tmp_path, _RC2_CODE)
    check = {"kind": "expect_rc", "argv": [], "stdin": None, "rc": 2}
    assert _run_single_check(check, tmp_path, plan, sys.executable) is True


def test_expect_rc_fails_when_process_exits_zero():
    """A stub exiting 0 FAILS an `expect_rc: 2` check -- the class of bug the old oracle
    (which only ever asserted rc==0 implicitly) could never catch."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext059_") as tmp:
        root = Path(tmp)
        plan = _write_entry(root, _RC0_CODE)
        check = {"kind": "expect_rc", "argv": [], "stdin": None, "rc": 2}
        assert _run_single_check(check, root, plan, sys.executable) is False

        passed, message = _run_check_variant(check, root, plan, sys.executable)
        assert passed is False
        assert "mismatch" in message


# --- empty_output ----------------------------------------------------------------------------

def test_empty_output_passes_on_no_stdout(tmp_path):
    plan = _write_entry(tmp_path, _EMPTY_OUTPUT_CODE)
    check = {"kind": "empty_output", "argv": [], "stdin": None}
    assert _run_single_check(check, tmp_path, plan, sys.executable) is True


def test_empty_output_fails_when_anything_printed():
    """A stub printing anything at all FAILS an `empty_output` check."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext059_") as tmp:
        root = Path(tmp)
        plan = _write_entry(root, _NONEMPTY_OUTPUT_CODE)
        check = {"kind": "empty_output", "argv": [], "stdin": None}
        assert _run_single_check(check, root, plan, sys.executable) is False

        passed, message = _run_check_variant(check, root, plan, sys.executable)
        assert passed is False
        assert "mismatch" in message


# --- unresolvable entrypoint / unknown kind never fabricate a pass -------------------------

def test_no_entrypoint_is_honest_false(tmp_path):
    check = {"kind": "empty_output", "argv": [], "stdin": None}
    assert _run_single_check(check, tmp_path, {"entrypoint": "nope.py"}, sys.executable) is False


def test_unknown_kind_is_honest_false(tmp_path):
    plan = _write_entry(tmp_path, _EMPTY_OUTPUT_CODE)
    check = {"kind": "not_a_real_kind", "argv": [], "stdin": None}
    assert _run_single_check(check, tmp_path, plan, sys.executable) is False


# --- regression: a prior substring-contains check still passes UNCHANGED -------------------

def test_prior_substring_contains_check_still_passes_unchanged(tmp_path):
    plan = _write_entry(tmp_path, _SUBSTRING_SUM_CLI_CODE)
    check = ([], "1 2 3\n", "6")   # the existing (argv, stdin, expected_substring) 3-tuple shape
    assert _run_single_check(check, tmp_path, plan, sys.executable) is True


# --- full run_creation_suite integration: new kinds dispatch through the SAME seam ----------

def test_run_creation_suite_accepts_task_using_new_check_kinds():
    def build_fn(sentence, root):
        _write_entry(root, _EXACT_STDOUT_GOOD_CODE)
        return {"modules": {}, "shipped": True, "done": True, "unmet": [],
                "plan": {"entrypoint": "main.py"}, "note": "DONE"}

    task = CreationTask(
        name="exact-stdout-task", cls="cli-tool", tier="easy",
        sentence="a CLI that prints hello",
        checks=[
            {"kind": "exact_stdout", "argv": [], "stdin": None, "expected": "hello\n"},
            {"kind": "expect_rc", "argv": [], "stdin": None, "rc": 0},
        ],
    )
    result = run_creation_suite(build_fn, tasks=[task])
    rec = result["results"][0]
    assert rec["accepted"] is True
    assert rec["n_checks_passed"] == 2
    assert rec["n_checks"] == 2


def test_run_creation_suite_rejects_task_when_new_check_kind_fails():
    def build_fn(sentence, root):
        _write_entry(root, _EXACT_STDOUT_EXTRA_CODE)
        return {"modules": {}, "shipped": True, "done": True, "unmet": [],
                "plan": {"entrypoint": "main.py"}, "note": "DONE"}

    task = CreationTask(
        name="exact-stdout-task-extra", cls="cli-tool", tier="easy",
        sentence="a CLI that prints hello plus unwanted extra output",
        checks=[
            {"kind": "exact_stdout", "argv": [], "stdin": None, "expected": "hello\n"},
        ],
    )
    result = run_creation_suite(build_fn, tasks=[task])
    rec = result["results"][0]
    assert rec["accepted"] is False
    assert rec["n_checks_passed"] == 0
