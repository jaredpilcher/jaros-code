"""EXT-059 REQ-1: offline tests for the deterministic filesystem acceptance oracle.

Every fixture here is a small, hand-written Python script written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib ``pathlib`` only.
These tests are pure execution-plane verification of a deterministic module and must never reach
the Jetson.
"""

# #EXT-059-REQ-1 Start
# TASK-1
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.fs_oracle import FsCheckResult, run_and_inspect, seed_tree

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# A "correct" build: writes ONLY out/result.txt with the exact expected bytes. Uses write_bytes
# (not write_text) deliberately -- Windows text-mode writes translate "\n" to "\r\n", which would
# make an "exact bytes" comparison platform-dependent for reasons that have nothing to do with the
# oracle itself.
CORRECT_STUB = """
    from pathlib import Path

    def main():
        Path("out").mkdir(parents=True, exist_ok=True)
        Path("out/result.txt").write_bytes(b"HELLO\\n")
        print("Saved!")  # stdout is never trusted by the oracle -- this alone proves nothing

    if __name__ == "__main__":
        main()
"""

# A no-op build: prints a success message but touches the filesystem not at all.
NOOP_STUB = """
    def main():
        print("Saved!")

    if __name__ == "__main__":
        main()
"""

# Writes to the right path but with the WRONG bytes.
WRONG_BYTES_STUB = """
    from pathlib import Path

    def main():
        Path("out").mkdir(parents=True, exist_ok=True)
        Path("out/result.txt").write_bytes(b"wrong content\\n")
        print("Saved!")

    if __name__ == "__main__":
        main()
"""

# Writes the right BYTES but to the WRONG path/filename.
WRONG_PATHS_STUB = """
    from pathlib import Path

    def main():
        Path("out").mkdir(parents=True, exist_ok=True)
        Path("out/wrong_name.txt").write_bytes(b"HELLO\\n")
        print("Saved!")

    if __name__ == "__main__":
        main()
"""

# Reads a seeded input file and writes its uppercased content to the expected output path --
# proves seed_tree() + run_and_inspect() compose end-to-end (seed -> drive -> independently verify).
UPPERCASE_STUB = """
    from pathlib import Path

    def main():
        text = Path("input.txt").read_text(encoding="utf-8")
        Path("out").mkdir(parents=True, exist_ok=True)
        Path("out/result.txt").write_text(text.upper(), encoding="utf-8")

    if __name__ == "__main__":
        main()
"""

SLEEPY_STUB = """
    import time
    time.sleep(5)
"""

# The standard post-condition set exercised by the pass/fail stub matrix below: an exact file
# exists with exact bytes, its containing directory has exactly that one member, and a file that
# should never be created stays absent.
STANDARD_CHECKS = [
    {"kind": "path_exists", "path": "out/result.txt"},
    {"kind": "file_bytes_equal", "path": "out/result.txt", "bytes": "HELLO\n"},
    {"kind": "dir_members_equal", "path": "out", "members": ["result.txt"]},
    {"kind": "path_absent", "path": "out/temp.txt"},
]


# --------------------------------------------------------------------------------------------
# The load-bearing pass/fail matrix -- a correct stub passes every check; each specific wrong
# stub fails exactly the post-condition(s) it should.
# --------------------------------------------------------------------------------------------

def test_correct_stub_passes_every_post_condition(tmp_path):
    _write(tmp_path, "main.py", CORRECT_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], STANDARD_CHECKS, python_exe=PY)
    assert isinstance(result, FsCheckResult)
    assert result.ok is True
    assert result.failures == []
    assert result.checks_passed == len(STANDARD_CHECKS)


def test_noop_stub_fails_path_exists_and_bytes_and_membership(tmp_path):
    _write(tmp_path, "main.py", NOOP_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], STANDARD_CHECKS, python_exe=PY)
    assert result.ok is False
    joined = " | ".join(result.failures).lower()
    assert "path_exists" in joined
    assert "file_bytes_equal" in joined
    assert "dir_members_equal" in joined
    # the file/dir were never created, so the negative path_absent check still honestly passes
    assert "path_absent" not in joined


def test_wrong_bytes_stub_fails_only_file_bytes_equal(tmp_path):
    _write(tmp_path, "main.py", WRONG_BYTES_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], STANDARD_CHECKS, python_exe=PY)
    assert result.ok is False
    joined = " | ".join(result.failures).lower()
    assert "file_bytes_equal" in joined
    assert "path_exists" not in joined       # the file DOES exist at the right path
    assert "dir_members_equal" not in joined  # membership (just result.txt) is still correct


def test_wrong_paths_stub_fails_exists_and_membership(tmp_path):
    _write(tmp_path, "main.py", WRONG_PATHS_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], STANDARD_CHECKS, python_exe=PY)
    assert result.ok is False
    joined = " | ".join(result.failures).lower()
    assert "path_exists" in joined
    assert "dir_members_equal" in joined
    assert "wrong_name.txt" in joined or "result.txt" in joined


# --------------------------------------------------------------------------------------------
# seed_tree -- materializes a declarative input tree, independently verified via plain pathlib
# --------------------------------------------------------------------------------------------

def test_seed_tree_materializes_files_and_implied_subdirs(tmp_path):
    ok, note = seed_tree(tmp_path, [
        {"path": "a.txt", "bytes": "top level"},
        {"path": "nested/b.txt", "bytes": b"raw bytes"},
        {"path": "nested/deeper/c.txt", "bytes": "deep"},
    ])
    assert ok is True, note
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "top level"
    assert (tmp_path / "nested" / "b.txt").read_bytes() == b"raw bytes"
    assert (tmp_path / "nested" / "deeper" / "c.txt").read_text(encoding="utf-8") == "deep"


def test_seed_tree_rejects_escaping_and_absolute_paths(tmp_path):
    ok, note = seed_tree(tmp_path, [{"path": "../escape.txt", "bytes": "x"}])
    assert ok is False
    assert "unsafe" in note.lower() or "escap" in note.lower()

    ok2, note2 = seed_tree(tmp_path, [{"path": "/etc/passwd", "bytes": "x"}])
    assert ok2 is False

    ok3, note3 = seed_tree(tmp_path, [{"path": "C:/evil.txt", "bytes": "x"}])
    assert ok3 is False


def test_seed_tree_never_raises_on_malformed_spec(tmp_path):
    assert seed_tree(tmp_path, None)[0] is False
    assert seed_tree(tmp_path, "not-a-list")[0] is False
    assert seed_tree(tmp_path, [{"no_path_key": True}])[0] is False
    assert seed_tree(tmp_path, [{"path": "a.txt", "bytes": 12345}])[0] is False
    assert seed_tree(object(), [{"path": "a.txt", "bytes": "x"}])[0] is False


# --------------------------------------------------------------------------------------------
# seed_tree() + run_and_inspect() end-to-end (seed -> drive built system -> independently verify)
# --------------------------------------------------------------------------------------------

def test_seed_then_drive_then_independently_verify(tmp_path):
    seeded_ok, note = seed_tree(tmp_path, [{"path": "input.txt", "bytes": "hello world"}])
    assert seeded_ok is True, note
    _write(tmp_path, "main.py", UPPERCASE_STUB)

    result = run_and_inspect(
        tmp_path, "main.py", [],
        [
            {"kind": "path_exists", "path": "out/result.txt"},
            {"kind": "file_bytes_equal", "path": "out/result.txt", "bytes": "HELLO WORLD"},
        ],
        python_exe=PY,
    )
    assert result.ok is True
    assert result.failures == []


# --------------------------------------------------------------------------------------------
# Never-raises discipline + timeout/process-tree teardown
# --------------------------------------------------------------------------------------------

def test_run_and_inspect_never_raises_on_missing_entrypoint(tmp_path):
    result = run_and_inspect(tmp_path, "does_not_exist.py", [], STANDARD_CHECKS, python_exe=PY)
    assert result.ok is False
    assert "entrypoint" in result.note.lower()


def test_run_and_inspect_never_raises_on_invalid_root():
    result = run_and_inspect(object(), "main.py", [], STANDARD_CHECKS, python_exe=PY)
    assert result.ok is False

    result2 = run_and_inspect("/this/path/does/not/exist/at/all", "main.py", [], STANDARD_CHECKS,
                               python_exe=PY)
    assert result2.ok is False


def test_run_and_inspect_never_raises_on_no_checks(tmp_path):
    _write(tmp_path, "main.py", CORRECT_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], [], python_exe=PY)
    assert result.ok is False
    assert "checks" in result.note.lower()


def test_run_and_inspect_reports_unknown_check_kind_as_a_failure(tmp_path):
    _write(tmp_path, "main.py", CORRECT_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], [{"kind": "bogus", "path": "out"}],
                              python_exe=PY)
    assert result.ok is False
    assert "unknown check kind" in " | ".join(result.failures).lower()


def test_run_and_inspect_times_out_and_kills_the_process_tree(tmp_path):
    _write(tmp_path, "main.py", SLEEPY_STUB)
    result = run_and_inspect(tmp_path, "main.py", [], [{"kind": "path_absent", "path": "x.txt"}],
                              timeout=0.5, python_exe=PY)
    assert result.ok is False
    assert "timed out" in result.note.lower()
# #EXT-059-REQ-1 End
