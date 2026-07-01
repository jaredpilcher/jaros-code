"""End-to-end Runtime coverage for EXT-001 / REQ-13 -- code.search_replace.

Exercises the tool through the REAL Jaros two-plane path (inert Decision ->
Runtime.apply -> gate -> executor -> deterministic tool effect + DecisionLog
entry), not just as an isolated unit (see tests/test_ext001_search_replace.py
for the offline unit tests of the tool itself). Mirrors the pattern in
tests/test_ext013_jaros_ops.py: Runtime(data_dir=tmp_path) auto-loads the
custom tools directory (harness.coding_loop.Runtime.__init__ calls
load_custom_tools(TOOLS_DIR)), so no extra fixture is needed beyond building
the Runtime.

Coverage targets (EXT-001 / REQ-13, end-to-end):
  - (a) EXACT tier edit applied via Runtime.apply -> file on disk + log entry
  - (b) RESILIENT (rstrip-drift) tier edit applied via Runtime.apply
  - (c) An unmatchable edit (no tier matches) surfaces a RuntimeError from
        Runtime.apply, never a silent no-op
  - (d) The gate rejects a payload missing search/replace before any file write
"""

from __future__ import annotations

# #EXT-001-REQ-13 Start

import sys
import uuid
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so imports resolve regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/test_ext013_jaros_ops.py)
# ---------------------------------------------------------------------------

def _make_runtime(tmp_path: Path):
    """Build a Runtime that writes its state into *tmp_path* (isolated per test).

    Runtime.__init__ calls load_custom_tools(TOOLS_DIR), which registers
    code.search_replace (among the other .jaros-data/tools/*.py tools) with
    the gate and executor -- the same mechanism test_ext013_jaros_ops.py
    relies on, so no separate fixture is required here.
    """
    from harness.coding_loop import Runtime  # noqa: PLC0415
    return Runtime(data_dir=tmp_path)


def _decision_types_logged(rt) -> list[str]:
    """Return the decision types recorded in rt's DecisionLog, in append order."""
    return [rec.decision.get("type") for rec in rt._dlog.read()]


def _apply_search_replace(rt, path: str, search: str, replace: str):
    from jaros.core import create_decision  # noqa: PLC0415
    decision = create_decision(
        id=f"sr-{uuid.uuid4().hex}",
        source="test",
        type="code.search_replace",
        payload={"path": path, "search": search, "replace": replace},
    )
    return rt.apply(decision)


# ---------------------------------------------------------------------------
# (a) EXACT tier -- end-to-end through the Runtime
# ---------------------------------------------------------------------------

class TestExactTierE2E:

    def test_applies_exact_edit_on_disk(self, tmp_path):
        """An exact search block is replaced on disk via Runtime.apply."""
        target = tmp_path / "module.py"
        target.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

        rt = _make_runtime(tmp_path)
        result = _apply_search_replace(
            rt, str(target),
            "    return 'hello'",
            "    return 'goodbye'",
        )
        assert result.get("applied") is True

        contents = target.read_text(encoding="utf-8")
        assert "return 'goodbye'" in contents
        assert "return 'hello'" not in contents

    def test_produces_decision_log_entry(self, tmp_path):
        """A successful exact-tier edit leaves a code.search_replace entry in the log."""
        target = tmp_path / "module.py"
        target.write_text("x = 1\n", encoding="utf-8")

        rt = _make_runtime(tmp_path)
        _apply_search_replace(rt, str(target), "x = 1", "x = 2")

        logged = _decision_types_logged(rt)
        assert "code.search_replace" in logged


# ---------------------------------------------------------------------------
# (b) RESILIENT (rstrip-drift) tier -- end-to-end through the Runtime
# ---------------------------------------------------------------------------

class TestResilientTierE2E:

    def test_applies_rstrip_drift_edit_on_disk(self, tmp_path):
        """A search block with trailing-whitespace drift vs the file still applies."""
        target = tmp_path / "module.py"
        # File line has no trailing whitespace...
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        rt = _make_runtime(tmp_path)
        # ...but the model's search block has trailing spaces on that line.
        result = _apply_search_replace(
            rt, str(target),
            "    return a + b   \n",
            "    return a + b + 1\n",
        )
        assert result.get("applied") is True
        assert result.get("matchedBy") == "rstrip"

        contents = target.read_text(encoding="utf-8")
        assert "return a + b + 1" in contents
        assert "return a + b\n" not in contents

    def test_produces_decision_log_entry(self, tmp_path):
        """A successful rstrip-tier edit also leaves a code.search_replace entry."""
        target = tmp_path / "module.py"
        target.write_text("value = 10\n", encoding="utf-8")

        rt = _make_runtime(tmp_path)
        _apply_search_replace(rt, str(target), "value = 10   \n", "value = 20\n")

        logged = _decision_types_logged(rt)
        assert "code.search_replace" in logged


# ---------------------------------------------------------------------------
# (c) Unmatchable edit -- Runtime.apply must raise, never a silent no-op
# ---------------------------------------------------------------------------

class TestUnmatchableEditE2E:

    def test_apply_raises_when_no_tier_matches(self, tmp_path):
        """A search block absent from the file (even under the resilient tiers)
        must cause Runtime.apply to raise -- never a silent no-op."""
        target = tmp_path / "module.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")

        rt = _make_runtime(tmp_path)
        with pytest.raises(RuntimeError, match="no search/replace tier matched"):
            _apply_search_replace(
                rt, str(target),
                "this text does not appear anywhere in the file",
                "replacement",
            )

        # No silent no-op: file on disk must be unchanged.
        assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"


# ---------------------------------------------------------------------------
# (d) Gate rejection -- missing search/replace rejected before any file write
# ---------------------------------------------------------------------------

class TestGateRejectionE2E:

    def test_gate_rejects_missing_search_and_replace(self, tmp_path):
        """The gate must reject a code.search_replace Decision missing 'search'/'replace'."""
        from jaros.core import create_decision  # noqa: PLC0415

        target = tmp_path / "module.py"
        original = "def f():\n    return 1\n"
        target.write_text(original, encoding="utf-8")

        rt = _make_runtime(tmp_path)
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="code.search_replace",
            payload={"path": str(target)},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)

        # No ungated host effect: the file is untouched, and nothing was logged.
        assert target.read_text(encoding="utf-8") == original
        assert "code.search_replace" not in _decision_types_logged(rt)

    def test_gate_rejects_missing_path(self, tmp_path):
        """The gate must reject a code.search_replace Decision with no 'path' key."""
        from jaros.core import create_decision  # noqa: PLC0415

        rt = _make_runtime(tmp_path)
        decision = create_decision(
            id=f"bad-{uuid.uuid4().hex}",
            source="test",
            type="code.search_replace",
            payload={"search": "a", "replace": "b"},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)

        assert "code.search_replace" not in _decision_types_logged(rt)

# #EXT-001-REQ-13 End
