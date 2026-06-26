"""Deterministic unit tests for EXT-013 / REQ-2 — Jaros-tool-based solve ops.

Tests that every solve op (write_artifact, run_tests, repair_syntax) routes through
Runtime.apply, producing a DecisionLog entry AND the expected tool effect.  No model
calls, no Jetson, no clone — all model interaction is stubbed out or avoided via the
parse-gate fast path (valid code never calls the LLM in repair_syntax).

Coverage targets (EXT-013 / REQ-2):
  - Artifacts written via code.write_file through Runtime.apply -> file on disk + log entry
  - Tests run via shell.exec through Runtime.apply -> exitCode dict + log entry
  - Repair invoked via code.repair through Runtime.apply -> returned content + log entry
  - Gate rejects a malformed Decision (no ungated host effect)
  - repair_syntax fast-path skips LLM when content already parses
"""

from __future__ import annotations

# #EXT-013-REQ-2 Start

import ast
import importlib
import os
import sys
import uuid
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so imports resolve regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ensure tools dir is importable for repair_tool (set_llm_factory).
_TOOLS_DIR = _REPO_ROOT / ".jaros-data" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(tmp_path: Path):
    """Build a Runtime that writes its state into *tmp_path* (isolated per test)."""
    from harness.coding_loop import Runtime  # noqa: PLC0415
    return Runtime(data_dir=tmp_path)


def _decision_types_logged(rt) -> list[str]:
    """Return the decision types recorded in rt's DecisionLog, in append order."""
    return [rec.decision.get("type") for rec in rt._dlog.read()]


# ---------------------------------------------------------------------------
# Stub-LLM helpers for repair tests that exercise the non-fast-path branch
# ---------------------------------------------------------------------------

class _StubCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubLlm:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, req):
        return _StubCompletion(self._reply)


# ---------------------------------------------------------------------------
# write_artifact tests
# ---------------------------------------------------------------------------

class TestWriteArtifact:

    def test_creates_file_on_disk(self, tmp_path):
        """write_artifact writes the content to the specified path."""
        from harness.jaros_solve_ops import write_artifact  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        target = str(tmp_path / "spec.txt")
        write_artifact(rt, target, "hello world", source="test")
        assert Path(target).read_text() == "hello world"

    def test_returns_tool_result_dict(self, tmp_path):
        """write_artifact returns the code.write_file tool's result dict."""
        from harness.jaros_solve_ops import write_artifact  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        target = str(tmp_path / "out.py")
        result = write_artifact(rt, target, "x = 1\n", source="test")
        assert isinstance(result, dict)
        assert result.get("applied") is True
        assert result.get("path") == target

    def test_produces_decision_log_entry(self, tmp_path):
        """write_artifact leaves a code.write_file entry in the DecisionLog."""
        from harness.jaros_solve_ops import write_artifact  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        target = str(tmp_path / "code.py")
        write_artifact(rt, target, "def f(): pass\n", source="test")
        logged = _decision_types_logged(rt)
        assert "code.write_file" in logged

    def test_gate_rejects_missing_content(self, tmp_path):
        """The gate must reject a code.write_file Decision with non-string content."""
        from jaros.core import create_decision  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        # content is None — gate should reject
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="code.write_file",
            payload={"path": str(tmp_path / "x.py"), "content": None},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)

    def test_gate_rejects_missing_path(self, tmp_path):
        """The gate must reject a code.write_file Decision with no 'path' key."""
        from jaros.core import create_decision  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="code.write_file",
            payload={"content": "x = 1"},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)


# ---------------------------------------------------------------------------
# run_tests tests
# ---------------------------------------------------------------------------

class TestRunTests:

    def test_exit_code_zero_on_success(self, tmp_path):
        """run_tests returns exitCode 0 for a command that succeeds."""
        from harness.jaros_solve_ops import run_tests  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        result = run_tests(rt, "python -c \"exit(0)\"", source="test")
        assert isinstance(result, dict)
        assert result.get("exitCode") == 0

    def test_exit_code_nonzero_on_failure(self, tmp_path):
        """run_tests returns non-zero exitCode for a failing command."""
        from harness.jaros_solve_ops import run_tests  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        result = run_tests(rt, "python -c \"exit(1)\"", source="test")
        assert result.get("exitCode") == 1

    def test_produces_decision_log_entry(self, tmp_path):
        """run_tests leaves a shell.exec entry in the DecisionLog."""
        from harness.jaros_solve_ops import run_tests  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        run_tests(rt, "python -c \"pass\"", source="test")
        logged = _decision_types_logged(rt)
        assert "shell.exec" in logged

    def test_stdout_captured(self, tmp_path):
        """run_tests captures stdout from the command."""
        from harness.jaros_solve_ops import run_tests  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        result = run_tests(rt, "python -c \"print('hello-from-test')\"", source="test")
        assert "hello-from-test" in result.get("stdout", "")

    def test_gate_rejects_network_command(self, tmp_path):
        """The gate must reject a shell.exec Decision with a denied network command."""
        from jaros.core import create_decision  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="shell.exec",
            payload={"command": "curl http://example.com"},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)


# ---------------------------------------------------------------------------
# repair_syntax tests
# ---------------------------------------------------------------------------

class TestRepairSyntax:

    def test_fast_path_valid_code_unchanged(self, tmp_path):
        """repair_syntax returns valid Python unchanged without calling the LLM."""
        from harness.jaros_solve_ops import repair_syntax  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        code = "def f(x):\n    return x + 1\n"
        result = repair_syntax(rt, code, source="test")
        assert result == code

    def test_fast_path_produces_decision_log_entry(self, tmp_path):
        """repair_syntax (fast-path) still logs a code.repair Decision."""
        from harness.jaros_solve_ops import repair_syntax  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        code = "def g():\n    return 42\n"
        repair_syntax(rt, code, source="test")
        logged = _decision_types_logged(rt)
        assert "code.repair" in logged

    def test_stub_llm_repairs_bad_indentation(self, tmp_path):
        """When code doesn't parse, repair_syntax calls the LLM and returns its output.

        Uses set_llm_factory to inject a stub LLM — avoids Jetson dependency.
        The stub returns syntactically valid Python so the gate accepts the repair.
        """
        import repair_tool  # noqa: PLC0415 -- loaded from .jaros-data/tools via sys.path
        from harness.jaros_solve_ops import repair_syntax  # noqa: PLC0415

        # Badly indented source (would raise IndentationError)
        broken = "def h():\nreturn 1\n"
        repaired_code = "def h():\n    return 1\n"

        stub = _StubLlm(repaired_code)
        repair_tool.set_llm_factory(lambda: stub)
        try:
            rt = _make_runtime(tmp_path)
            result = repair_syntax(rt, broken, source="test")
        finally:
            repair_tool.set_llm_factory(None)  # restore production path

        # Result should parse cleanly
        try:
            ast.parse(result)
            parsed_ok = True
        except SyntaxError:
            parsed_ok = False
        assert parsed_ok, f"repair_syntax did not return parseable code: {result!r}"

    def test_stub_llm_repair_logged(self, tmp_path):
        """A stub-LLM repair still records a code.repair Decision in the log."""
        import repair_tool  # noqa: PLC0415
        from harness.jaros_solve_ops import repair_syntax  # noqa: PLC0415

        broken = "def j():\nreturn 99\n"
        repaired_code = "def j():\n    return 99\n"

        stub = _StubLlm(repaired_code)
        repair_tool.set_llm_factory(lambda: stub)
        try:
            rt = _make_runtime(tmp_path)
            repair_syntax(rt, broken, source="test")
        finally:
            repair_tool.set_llm_factory(None)

        logged = _decision_types_logged(rt)
        assert "code.repair" in logged

    def test_gate_rejects_empty_content(self, tmp_path):
        """The gate must reject a code.repair Decision with empty content."""
        from jaros.core import create_decision  # noqa: PLC0415
        rt = _make_runtime(tmp_path)
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="code.repair",
            payload={"content": ""},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)


# ---------------------------------------------------------------------------
# Combined: multiple ops in a single Runtime share the same DecisionLog
# ---------------------------------------------------------------------------

class TestCombinedOps:

    def test_all_three_ops_log_entries(self, tmp_path):
        """All three ops applied via the same Runtime each log their Decision type."""
        from harness.jaros_solve_ops import (  # noqa: PLC0415
            write_artifact, run_tests, repair_syntax,
        )
        rt = _make_runtime(tmp_path)

        # 1) write
        target = str(tmp_path / "solution.py")
        write_artifact(rt, target, "def f():\n    return 0\n", source="test-combined")

        # 2) run tests (trivially passing)
        run_tests(rt, "python -c \"pass\"", source="test-combined")

        # 3) repair (fast-path — valid code, no LLM call needed)
        repair_syntax(rt, "def g():\n    return 1\n", source="test-combined")

        logged = _decision_types_logged(rt)
        assert "code.write_file" in logged
        assert "shell.exec" in logged
        assert "code.repair" in logged
        # All three decisions must appear — minimum 3 log entries
        assert len(logged) >= 3

# #EXT-013-REQ-2 End
