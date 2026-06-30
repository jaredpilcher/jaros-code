"""Offline tests for harness/swebench_solve.py (EXT-034 REQ-3).

ALL tests are OFFLINE:
  - No dataset download
  - Mock locate_fn / read_fn / gen_fn (no live Jetson / LLM)
  - No Docker
  - No network

Tests cover:
  (a) make_unified_diff round-trips: applying the diff to original yields edited.
  (b) make_unified_diff returns "" when original == edited (no-op).
  (c) solve_swebench_instance with mock callables produces a non-empty multi-file
      unified diff covering the located files.
  (d) Honesty: the candidate patch NEVER contains the gold patch content — even
      if the instance's 'patch' field has a sentinel string, it must be absent
      from the candidate (gen_fn never sees the gold patch).
  (e) No-op gen (edited == original) -> empty candidate patch -> score_resolved
      returns unresolved (FAIL_TO_PASS tests did not pass).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# #EXT-034-REQ-3 Start
from harness.swebench_solve import (
    _apply_unified_diff,
    make_unified_diff,
    solve_swebench_instance,
    swebench_eval_with_solve,
)
from harness.swebench import score_resolved
# #EXT-034-REQ-3 End

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ORIGINAL_SRC = """\
def greet(name):
    return "Hello, " + name
"""

_EDITED_SRC = """\
def greet(name: str) -> str:
    \"\"\"Return a greeting for name.\"\"\"
    return f"Hello, {name}!"
"""

_INSTANCE_MINIMAL: dict = {
    "instance_id": "test__repo-001",
    "repo": "test/repo",
    "base_commit": "deadbeef0001",
    "problem_statement": "Improve greet() to use f-strings and add type annotations.",
    "FAIL_TO_PASS": ["tests/test_greet.py::test_greet_fstring"],
    "PASS_TO_PASS": ["tests/test_greet.py::test_greet_basic"],
    "test_patch": "diff --git a/tests/test_greet.py ...",
    # Gold patch — NEVER shown to the model.  We use a sentinel to test honesty.
    "patch": (
        "diff --git a/src/greet.py b/src/greet.py\n"
        "GOLD_PATCH_SENTINEL_DO_NOT_LEAK\n"
        "--- a/src/greet.py\n+++ b/src/greet.py\n"
        "@@ -1,2 +1,3 @@\n"
        "-def greet(name):\n"
        '-    return "Hello, " + name\n'
        "+def greet(name: str) -> str:\n"
        '+    return f"Hello, {name}!"\n'
    ),
}

_INSTANCE_B: dict = {
    "instance_id": "test__repo-002",
    "repo": "test/repo",
    "base_commit": "cafebabe0002",
    "problem_statement": "Fix divide_by_zero to raise ZeroDivisionError properly.",
    "FAIL_TO_PASS": ["tests/test_math.py::test_divide_zero"],
    "PASS_TO_PASS": ["tests/test_math.py::test_divide_basic"],
    "test_patch": "diff --git a/tests/test_math.py ...",
    "patch": "diff --git a/src/math_util.py ...\nGOLD_PATCH_B_SENTINEL\n",
}

TARGET_FILE = "src/greet.py"
TARGET_FILE_B = "src/math_util.py"

_ORIGINAL_SRC_B = """\
def divide(a, b):
    return a / b
"""

_EDITED_SRC_B = """\
def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_apply_fn():
    """No-op apply_fn that records its calls."""
    calls: list[dict] = []

    def apply_fn(*, base_commit: str, candidate_patch: str, test_patch: str) -> None:
        calls.append(
            {"base_commit": base_commit, "candidate_patch": candidate_patch, "test_patch": test_patch}
        )

    apply_fn.calls = calls  # type: ignore[attr-defined]
    return apply_fn


def _make_test_fn_pass_all():
    """test_fn that marks ALL supplied tests as passing."""
    def test_fn(tests: list) -> set:
        return set(tests)
    return test_fn


def _make_test_fn_fail_all():
    """test_fn that marks ALL supplied tests as failing (returns empty set)."""
    def test_fn(tests: list) -> set:
        return set()
    return test_fn


# ---------------------------------------------------------------------------
# (a) make_unified_diff round-trips
# ---------------------------------------------------------------------------

# #EXT-034-REQ-3 Start
class TestMakeUnifiedDiff:
    def test_roundtrip_simple_edit(self) -> None:
        """Applying make_unified_diff(path, original, edited) to original yields edited."""
        diff = make_unified_diff(TARGET_FILE, _ORIGINAL_SRC, _EDITED_SRC)
        assert diff, "diff should be non-empty for different original/edited"
        reconstructed = _apply_unified_diff(_ORIGINAL_SRC, diff)
        assert reconstructed == _EDITED_SRC, (
            f"Round-trip failed.\nExpected:\n{_EDITED_SRC!r}\nGot:\n{reconstructed!r}"
        )

    def test_roundtrip_multiline_addition(self) -> None:
        """Round-trip when edited adds multiple new lines."""
        original = "x = 1\ny = 2\n"
        edited = "x = 1\ny = 2\nz = 3\nw = 4\n"
        diff = make_unified_diff("module.py", original, edited)
        assert diff
        reconstructed = _apply_unified_diff(original, diff)
        assert reconstructed == edited

    def test_roundtrip_line_deletion(self) -> None:
        """Round-trip when edited removes a line."""
        original = "a = 1\nb = 2\nc = 3\n"
        edited = "a = 1\nc = 3\n"
        diff = make_unified_diff("module.py", original, edited)
        assert diff
        reconstructed = _apply_unified_diff(original, diff)
        assert reconstructed == edited

    def test_roundtrip_from_empty(self) -> None:
        """Round-trip when original is empty (new file content)."""
        original = ""
        edited = "def foo():\n    return 42\n"
        diff = make_unified_diff("new_file.py", original, edited)
        assert diff
        reconstructed = _apply_unified_diff(original, diff)
        assert reconstructed == edited

    def test_diff_header_git_style(self) -> None:
        """Diff header uses git-style 'a/path' and 'b/path' prefixes."""
        diff = make_unified_diff("src/foo.py", "old\n", "new\n")
        assert "--- a/src/foo.py" in diff, f"Expected git-style 'a/' prefix in:\n{diff}"
        assert "+++ b/src/foo.py" in diff, f"Expected git-style 'b/' prefix in:\n{diff}"

    # (b) No-change returns empty string
    def test_no_change_returns_empty_string(self) -> None:
        """make_unified_diff returns '' when original == edited."""
        result = make_unified_diff(TARGET_FILE, _ORIGINAL_SRC, _ORIGINAL_SRC)
        assert result == "", f"Expected empty string for no-op, got: {result!r}"

    def test_no_change_empty_strings(self) -> None:
        """make_unified_diff returns '' when both original and edited are empty."""
        result = make_unified_diff("file.py", "", "")
        assert result == ""

    def test_path_leading_slash_stripped(self) -> None:
        """Leading slash in path is stripped from the diff header."""
        diff = make_unified_diff("/src/foo.py", "old\n", "new\n")
        # Should NOT produce '--- a//src/foo.py'
        assert "--- a/src/foo.py" in diff, (
            f"Leading slash should be stripped; got headers in:\n{diff}"
        )
# #EXT-034-REQ-3 End


# ---------------------------------------------------------------------------
# (c) solve_swebench_instance with mock callables
# ---------------------------------------------------------------------------

# #EXT-034-REQ-3 Start
class TestSolveSwebenchInstance:
    def _make_mocks(self, original=_ORIGINAL_SRC, edited=_EDITED_SRC, files=None):
        """Build simple mock locate/read/gen callables."""
        files = files or [TARGET_FILE]

        def locate_fn(solve_input):
            return list(files)

        def read_fn(path):
            return original

        def gen_fn(solve_input, path, orig):
            return edited

        return locate_fn, read_fn, gen_fn

    def test_produces_nonempty_diff_when_files_change(self) -> None:
        """solve_swebench_instance returns a non-empty patch when gen_fn edits a file."""
        locate_fn, read_fn, gen_fn = self._make_mocks()
        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert candidate, "Expected a non-empty candidate patch"

    def test_patch_covers_located_files(self) -> None:
        """The candidate patch mentions the located file path."""
        locate_fn, read_fn, gen_fn = self._make_mocks()
        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert "src/greet.py" in candidate, (
            f"Expected 'src/greet.py' in candidate patch:\n{candidate}"
        )

    def test_multifile_patch_concatenated(self) -> None:
        """When locate_fn returns two files, the candidate is a two-file patch."""
        files = [TARGET_FILE, TARGET_FILE_B]
        src_map = {TARGET_FILE: _ORIGINAL_SRC, TARGET_FILE_B: _ORIGINAL_SRC_B}
        edit_map = {TARGET_FILE: _EDITED_SRC, TARGET_FILE_B: _EDITED_SRC_B}

        def locate_fn(si):
            return files

        def read_fn(path):
            return src_map[path]

        def gen_fn(si, path, orig):
            return edit_map[path]

        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert "src/greet.py" in candidate
        assert "src/math_util.py" in candidate

    def test_gen_fn_receives_solve_input_and_original(self) -> None:
        """gen_fn is called with (solve_input, path, original) — correct arguments."""
        calls = []

        def locate_fn(si):
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, original):
            calls.append({"solve_input": si, "path": path, "original": original})
            return _EDITED_SRC

        solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert len(calls) == 1
        assert calls[0]["path"] == TARGET_FILE
        assert calls[0]["original"] == _ORIGINAL_SRC
        # solve_input must not contain the gold patch
        assert "patch" not in calls[0]["solve_input"]

    def test_locate_fn_receives_solve_input(self) -> None:
        """locate_fn is called with the solve_input dict (not the raw instance)."""
        seen_inputs = []

        def locate_fn(si):
            seen_inputs.append(si)
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            return _EDITED_SRC

        solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert len(seen_inputs) == 1
        # solve_input has problem_statement, repo — not the gold patch
        assert "problem_statement" in seen_inputs[0]
        assert "patch" not in seen_inputs[0]
# #EXT-034-REQ-3 End


# ---------------------------------------------------------------------------
# (d) Honesty: candidate patch never contains the gold patch sentinel
# ---------------------------------------------------------------------------

# #EXT-034-REQ-3 Start
class TestHonestyGoldPatchAbsent:
    SENTINEL = "GOLD_PATCH_SENTINEL_DO_NOT_LEAK"

    def test_sentinel_absent_from_candidate(self) -> None:
        """The gold patch sentinel string must NEVER appear in the candidate patch."""
        # Verify the sentinel is actually in the gold patch (otherwise the test is vacuous).
        assert self.SENTINEL in _INSTANCE_MINIMAL["patch"]

        def locate_fn(si):
            # The model cannot see the gold patch — only the solve_input reaches it.
            # Confirm the sentinel is not in the solve_input.
            assert self.SENTINEL not in str(si), (
                f"HONESTY VIOLATION: sentinel found in solve_input: {si}"
            )
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            # Model sees only solve_input + path + original — no gold patch.
            assert self.SENTINEL not in str(si)
            assert self.SENTINEL not in orig
            return _EDITED_SRC

        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert self.SENTINEL not in candidate, (
            f"Honesty violation: gold patch sentinel found in candidate:\n{candidate}"
        )

    def test_gold_patch_key_absent_from_solve_input(self) -> None:
        """The 'patch' key is absent from the solve_input passed to gen_fn."""
        seen = []

        def locate_fn(si):
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            seen.append(si)
            return _EDITED_SRC

        solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert seen, "gen_fn was not called"
        for si in seen:
            assert "patch" not in si, (
                f"Gold 'patch' key leaked into solve_input: {list(si.keys())}"
            )

    def test_second_instance_gold_absent(self) -> None:
        """Same honesty check on a second instance with a different sentinel."""
        sentinel_b = "GOLD_PATCH_B_SENTINEL"
        assert sentinel_b in _INSTANCE_B["patch"]

        def locate_fn(si):
            return [TARGET_FILE_B]

        def read_fn(path):
            return _ORIGINAL_SRC_B

        def gen_fn(si, path, orig):
            return _EDITED_SRC_B

        candidate = solve_swebench_instance(
            _INSTANCE_B, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert sentinel_b not in candidate, (
            f"Honesty violation: gold sentinel from instance B in candidate:\n{candidate}"
        )
# #EXT-034-REQ-3 End


# ---------------------------------------------------------------------------
# (e) No-op gen -> empty patch -> score_resolved unresolved
# ---------------------------------------------------------------------------

# #EXT-034-REQ-3 Start
class TestNoOpGen:
    def test_noop_gen_produces_empty_candidate(self) -> None:
        """When gen_fn returns the original unchanged, the candidate patch is ''."""
        def locate_fn(si):
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            return orig  # No change

        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert candidate == "", (
            f"Expected empty candidate for no-op gen, got:\n{candidate!r}"
        )

    def test_empty_candidate_is_unresolved(self) -> None:
        """An empty candidate patch -> score_resolved returns resolved=False."""
        apply_fn = _make_apply_fn()
        # test_fn: FAIL_TO_PASS tests do NOT pass (no real fix applied)
        test_fn = _make_test_fn_fail_all()

        result = score_resolved(
            _INSTANCE_MINIMAL,
            "",  # empty candidate patch
            apply_fn=apply_fn,
            test_fn=test_fn,
        )
        assert result["resolved"] is False
        assert result["fail_to_pass_passed"] == []

    def test_empty_candidate_reason_mentions_ftp(self) -> None:
        """score_resolved reason string mentions FAIL_TO_PASS failure."""
        apply_fn = _make_apply_fn()
        test_fn = _make_test_fn_fail_all()

        result = score_resolved(
            _INSTANCE_MINIMAL, "", apply_fn=apply_fn, test_fn=test_fn
        )
        assert "FAIL_TO_PASS" in result["reason"], (
            f"Expected 'FAIL_TO_PASS' in reason, got: {result['reason']!r}"
        )

    def test_noop_gen_empty_locate(self) -> None:
        """When locate_fn returns an empty list, the candidate patch is ''."""
        def locate_fn(si):
            return []  # No files located

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            return _EDITED_SRC

        candidate = solve_swebench_instance(
            _INSTANCE_MINIMAL, locate_fn=locate_fn, read_fn=read_fn, gen_fn=gen_fn
        )
        assert candidate == ""
# #EXT-034-REQ-3 End


# ---------------------------------------------------------------------------
# swebench_eval_with_solve integration tests
# ---------------------------------------------------------------------------

# #EXT-034-REQ-3 Start
class TestSwebenchEvalWithSolve:
    def test_one_instance_resolved(self) -> None:
        """swebench_eval_with_solve returns resolved=1 when test_fn passes all tests."""
        def locate_fn(si):
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            return _EDITED_SRC

        apply_fn = _make_apply_fn()
        test_fn = _make_test_fn_pass_all()

        result = swebench_eval_with_solve(
            [_INSTANCE_MINIMAL],
            locate_fn=locate_fn,
            read_fn=read_fn,
            gen_fn=gen_fn,
            apply_fn=apply_fn,
            test_fn=test_fn,
        )
        assert result["n"] == 1
        assert result["resolved"] == 1
        assert result["resolved_rate"] == 1.0

    def test_two_instances_one_resolved(self) -> None:
        """Aggregation: 2 instances, 1 resolves -> resolved_rate=0.5."""
        call_count = [0]

        def locate_fn(si):
            return [TARGET_FILE]

        def read_fn(path):
            return _ORIGINAL_SRC

        def gen_fn(si, path, orig):
            call_count[0] += 1
            return _EDITED_SRC

        apply_fn = _make_apply_fn()

        # First instance passes, second fails.
        call_number = [0]

        def test_fn(tests):
            call_number[0] += 1
            if call_number[0] == 1:
                return set(tests)  # first instance: all pass
            return set()           # second instance: none pass

        result = swebench_eval_with_solve(
            [_INSTANCE_MINIMAL, _INSTANCE_B],
            locate_fn=locate_fn,
            read_fn=read_fn,
            gen_fn=gen_fn,
            apply_fn=apply_fn,
            test_fn=test_fn,
        )
        assert result["n"] == 2
        assert result["resolved"] == 1
        assert result["resolved_rate"] == pytest.approx(0.5)

    def test_result_has_required_keys(self) -> None:
        """swebench_eval_with_solve result has all required keys."""
        def locate_fn(si):
            return []

        def read_fn(path):
            return ""

        def gen_fn(si, path, orig):
            return orig

        result = swebench_eval_with_solve(
            [_INSTANCE_MINIMAL],
            locate_fn=locate_fn,
            read_fn=read_fn,
            gen_fn=gen_fn,
            apply_fn=_make_apply_fn(),
            test_fn=_make_test_fn_fail_all(),
        )
        for key in ("n", "resolved", "resolved_rate", "wilson95", "per_instance"):
            assert key in result, f"Missing key: {key}"

    def test_wilson95_present_and_valid(self) -> None:
        """wilson95 is a (lo, hi) tuple with 0 <= lo <= hi <= 1."""
        def locate_fn(si):
            return []

        def read_fn(path):
            return ""

        def gen_fn(si, path, orig):
            return orig

        result = swebench_eval_with_solve(
            [_INSTANCE_MINIMAL],
            locate_fn=locate_fn,
            read_fn=read_fn,
            gen_fn=gen_fn,
            apply_fn=_make_apply_fn(),
            test_fn=_make_test_fn_fail_all(),
        )
        lo, hi = result["wilson95"]
        assert 0.0 <= lo <= hi <= 1.0
# #EXT-034-REQ-3 End
