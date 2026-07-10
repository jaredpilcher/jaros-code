"""EXT-060 TASK-12: offline tests for the first FINTECH-LEDGER-shaped task (`oracle_kind=
"double_entry"`, REQ-17) on the canonical real-systems scoreboard.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every "ledger" module here is a small,
hand-written stdlib Python class written to a temp directory and driven against
`harness.double_entry_oracle`'s own deterministic import-and-drive machinery (exactly what
`grade_real_system_task` itself wires for `oracle_kind="double_entry"`) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_double_entry_task.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    DOUBLE_ENTRY_LEDGER_TASK,
    REAL_SYSTEMS_TASKS,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-17 Start
# (a) a CORRECT Ledger fixture passes DOUBLE_ENTRY_LEDGER_TASK's oracle
# ================================================================================================

CORRECT_LEDGER = """
    class Ledger:
        def __init__(self):
            self._cash = 0
            self._revenue = 0
            self._expense = 0

        def cash(self):
            return self._cash

        def revenue(self):
            return self._revenue

        def expense(self):
            return self._expense

        def post(self, legs):
            deltas = {"cash": 0, "revenue": 0, "expense": 0}
            for leg in legs:
                account = leg["account"]
                if "debit" in leg:
                    deltas[account] += leg["debit"]
                else:
                    deltas[account] -= leg["credit"]
            total_debit = sum(leg.get("debit", 0) for leg in legs)
            total_credit = sum(leg.get("credit", 0) for leg in legs)
            if total_debit != total_credit:
                raise ValueError("unbalanced entry")
            self._cash += deltas["cash"]
            self._revenue += deltas["revenue"]
            self._expense += deltas["expense"]
"""


def test_correct_ledger_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_ledgertest_") as tmp:
        root = Path(tmp)
        _write(root, "ledger.py", CORRECT_LEDGER)
        accepted, note = grade_real_system_task(DOUBLE_ENTRY_LEDGER_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# (b) a BROKEN fixture (posts an unbalanced entry instead of rejecting it) is rejected
# ------------------------------------------------------------------------------------------------

BROKEN_LEDGER_ACCEPTS_UNBALANCED = """
    class Ledger:
        def __init__(self):
            self._cash = 0
            self._revenue = 0
            self._expense = 0

        def cash(self):
            return self._cash

        def revenue(self):
            return self._revenue

        def expense(self):
            return self._expense

        def post(self, legs):
            # BUG: never checks that debits == credits -- posts every entry unconditionally,
            # including unbalanced ones (which would create or destroy money out of nowhere).
            for leg in legs:
                account = leg["account"]
                if "debit" in leg:
                    delta = leg["debit"]
                else:
                    delta = -leg["credit"]
                if account == "cash":
                    self._cash += delta
                elif account == "revenue":
                    self._revenue += delta
                else:
                    self._expense += delta
"""


def test_broken_ledger_that_accepts_unbalanced_entries_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_ledgertest_") as tmp:
        root = Path(tmp)
        _write(root, "ledger.py", BROKEN_LEDGER_ACCEPTS_UNBALANCED)
        accepted, note = grade_real_system_task(DOUBLE_ENTRY_LEDGER_TASK, root, python_exe=PY)
        assert accepted is False


# ------------------------------------------------------------------------------------------------
# (c) leaves-OFF + roster membership
# ------------------------------------------------------------------------------------------------

def test_double_entry_ledger_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(DOUBLE_ENTRY_LEDGER_TASK.sentence) is None
    assert DOUBLE_ENTRY_LEDGER_TASK in REAL_SYSTEMS_TASKS
    assert DOUBLE_ENTRY_LEDGER_TASK.oracle_kind == "double_entry"
    assert DOUBLE_ENTRY_LEDGER_TASK.cls == "ledger"
# #EXT-060-REQ-17 End
