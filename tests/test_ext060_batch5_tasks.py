"""EXT-060 TASK-47/TASK-48/TASK-49/TASK-50: offline tests for FOUR NEW real-systems CREATE tasks
("batch-5"), spread across THREE ALREADY-LANDED oracles (import/state_machine/conservation -- NO new
oracle code) and FOUR distinct verticals (REQ-52/53/54/55):

- ``LOAN_AMORTIZATION_TASK`` (``oracle_kind="import"``, ``cls="fintech"``): a fixed-payment loan
  amortization schedule library, integer-cents throughout, graded by the ALREADY-LANDED
  ``harness.import_driver.drive_import`` dispatch (REQ-3's ``_grade_import``, no new oracle code).
- ``RUNNING_MEDIAN_TASK`` (``oracle_kind="import"``, ``cls="analytics"``): a running-median-over-a-
  stream library, graded by the SAME ALREADY-LANDED ``import`` dispatch.
- ``INCIDENT_ESCALATION_TASK`` (``oracle_kind="state_machine"``, ``cls="devops"``): an on-call
  incident's open/acknowledged/investigating/resolved/closed lifecycle (with a two-source-state
  ``reopen()``), graded by the ALREADY-LANDED ``harness.state_machine_oracle.grade_state_machine``
  dispatch (REQ-13's ``_grade_state_machine``, no new oracle code).
- ``WAREHOUSE_STOCK_RESERVATION_TASK`` (``oracle_kind="conservation"``, ``cls="logistics"``): a
  warehouse SKU's on_hand/reserved/shipped reservation/ship workflow, graded by the ALREADY-LANDED
  ``harness.conservation_oracle.grade_conservation`` dispatch (REQ-15's ``_grade_conservation``, no
  new oracle code).

Every hand-verified vector was independently recomputed (a standalone scratch Python walk of the
exact same formula/bookkeeping each task's sentence pins) BEFORE being written into the task's
``oracle_spec`` -- see each task's own definition in ``harness/real_systems_suite.py`` for the
recompute notes.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_batch5_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.conservation_oracle import validate_spec as validate_conservation_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    INCIDENT_ESCALATION_TASK,
    LOAN_AMORTIZATION_TASK,
    REAL_SYSTEMS_TASKS,
    RUNNING_MEDIAN_TASK,
    WAREHOUSE_STOCK_RESERVATION_TASK,
    grade_real_system_task,
)
from harness.state_machine_oracle import validate_spec as validate_state_machine_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-52 Start
# LOAN_AMORTIZATION_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_LOAN_AMORTIZATION = """
    def schedule(principal, annual_rate, n_months):
        r = annual_rate / 12
        M = round(principal * r / (1 - (1 + r) ** -n_months))
        balance = principal
        rows = []
        for i in range(n_months):
            interest = round(balance * r)
            if i == n_months - 1:
                principal_paid = balance
                pay = interest + principal_paid
            else:
                principal_paid = M - interest
                pay = M
            balance -= principal_paid
            rows.append({
                "payment": pay, "interest": interest,
                "principal": principal_paid, "balance": balance,
            })
        return rows
"""


def test_correct_loan_amortization_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_loantest_") as tmp:
        root = Path(tmp)
        _write(root, "loan_amortization.py", CORRECT_LOAN_AMORTIZATION)
        accepted, note = grade_real_system_task(LOAN_AMORTIZATION_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: never special-cases the final month -- the level payment `M` is reused for every month
# including the last, so rounding residue is never absorbed and the final balance lands on `-1`
# cent instead of exactly `0` (the "forgets to zero the final rounding residue" bug).
# ------------------------------------------------------------------------------------------------

BROKEN_LOAN_AMORTIZATION_NEVER_ZEROES_FINAL_BALANCE = """
    def schedule(principal, annual_rate, n_months):
        r = annual_rate / 12
        M = round(principal * r / (1 - (1 + r) ** -n_months))
        balance = principal
        rows = []
        for i in range(n_months):
            # BUG: no final-month override -- the level payment M is reused for every month, so
            # rounding residue accumulates instead of being absorbed into the last payment.
            interest = round(balance * r)
            principal_paid = M - interest
            balance -= principal_paid
            rows.append({
                "payment": M, "interest": interest,
                "principal": principal_paid, "balance": balance,
            })
        return rows
"""


def test_broken_loan_amortization_never_zeroes_final_balance_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_loantest_") as tmp:
        root = Path(tmp)
        _write(root, "loan_amortization.py", BROKEN_LOAN_AMORTIZATION_NEVER_ZEROES_FINAL_BALANCE)
        accepted, note = grade_real_system_task(LOAN_AMORTIZATION_TASK, root, python_exe=PY)
        assert accepted is False


def test_loan_amortization_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(LOAN_AMORTIZATION_TASK.sentence) is None
    assert LOAN_AMORTIZATION_TASK in REAL_SYSTEMS_TASKS
    assert LOAN_AMORTIZATION_TASK.oracle_kind == "import"
    assert LOAN_AMORTIZATION_TASK.cls == "fintech"
    assert LOAN_AMORTIZATION_TASK.name == "loan-amortization-schedule-lib"
    assert LOAN_AMORTIZATION_TASK.oracle_spec["module"] == "loan_amortization"
    checks = LOAN_AMORTIZATION_TASK.oracle_spec["checks"]
    assert {
        "kind": "returns_equals", "call_id": "schedule_single_month",
        "expected": [{"payment": 1212, "interest": 12, "principal": 1200, "balance": 0}],
    } in checks
    assert {
        "kind": "returns_equals", "call_id": "schedule_three_month",
        "expected": [
            {"payment": 40803, "interest": 1200, "principal": 39603, "balance": 80397},
            {"payment": 40803, "interest": 804, "principal": 39999, "balance": 40398},
            {"payment": 40802, "interest": 404, "principal": 40398, "balance": 0},
        ],
    } in checks
# #EXT-060-REQ-52 End


# ================================================================================================
# #EXT-060-REQ-53 Start
# RUNNING_MEDIAN_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_RUNNING_MEDIAN = """
    import bisect

    def running_medians(stream):
        sorted_vals = []
        out = []
        for x in stream:
            bisect.insort(sorted_vals, x)
            n = len(sorted_vals)
            if n % 2 == 1:
                out.append(sorted_vals[n // 2])
            else:
                out.append((sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2)
        return out
"""


def test_correct_running_median_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_medtest_") as tmp:
        root = Path(tmp)
        _write(root, "running_median.py", CORRECT_RUNNING_MEDIAN)
        accepted, note = grade_real_system_task(RUNNING_MEDIAN_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: returns the running MEAN instead of the running median.
# ------------------------------------------------------------------------------------------------

BROKEN_RUNNING_MEDIAN_RETURNS_MEAN = """
    def running_medians(stream):
        # BUG: returns the running MEAN instead of the running median.
        out = []
        total = 0
        for i, x in enumerate(stream, start=1):
            total += x
            out.append(total / i)
        return out
"""


def test_broken_running_median_returns_mean_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_medtest_") as tmp:
        root = Path(tmp)
        _write(root, "running_median.py", BROKEN_RUNNING_MEDIAN_RETURNS_MEAN)
        accepted, note = grade_real_system_task(RUNNING_MEDIAN_TASK, root, python_exe=PY)
        assert accepted is False


def test_running_median_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(RUNNING_MEDIAN_TASK.sentence) is None
    assert RUNNING_MEDIAN_TASK in REAL_SYSTEMS_TASKS
    assert RUNNING_MEDIAN_TASK.oracle_kind == "import"
    assert RUNNING_MEDIAN_TASK.cls == "analytics"
    assert RUNNING_MEDIAN_TASK.name == "running-median-lib"
    assert RUNNING_MEDIAN_TASK.oracle_spec["module"] == "running_median"
    checks = RUNNING_MEDIAN_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "medians_mixed_lengths",
            "expected": [5, 10.0, 5, 4.0]} in checks
    assert {"kind": "returns_equals", "call_id": "medians_two_element",
            "expected": [2, 3.0]} in checks
    assert {"kind": "returns_equals", "call_id": "medians_single_element",
            "expected": [7]} in checks
# #EXT-060-REQ-53 End


# ================================================================================================
# #EXT-060-REQ-54 Start
# INCIDENT_ESCALATION_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_INCIDENT_ESCALATION = """
    class Incident:
        _TRANSITIONS = {
            ("open", "acknowledge"): "acknowledged",
            ("acknowledged", "investigate"): "investigating",
            ("investigating", "resolve"): "resolved",
            ("resolved", "close"): "closed",
            ("resolved", "reopen"): "investigating",
            ("closed", "reopen"): "investigating",
        }

        def __init__(self):
            self._state = "open"

        @property
        def state(self):
            return self._state

        def _transition(self, action):
            key = (self._state, action)
            if key not in self._TRANSITIONS:
                raise ValueError(f"illegal transition: {action} from {self._state}")
            self._state = self._TRANSITIONS[key]

        def acknowledge(self):
            self._transition("acknowledge")

        def investigate(self):
            self._transition("investigate")

        def resolve(self):
            self._transition("resolve")

        def close(self):
            self._transition("close")

        def reopen(self):
            self._transition("reopen")
"""


def test_correct_incident_escalation_passes_the_state_machine_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_incidenttest_") as tmp:
        root = Path(tmp)
        _write(root, "incident_escalation.py", CORRECT_INCIDENT_ESCALATION)
        accepted, note = grade_real_system_task(INCIDENT_ESCALATION_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: every action fires unconditionally from ANY state -- an illegal transition (resolving an
# incident straight from "open") is silently allowed instead of raising.
# ------------------------------------------------------------------------------------------------

BROKEN_INCIDENT_ESCALATION_ALLOWS_ILLEGAL_TRANSITION = """
    class Incident:
        def __init__(self):
            self._state = "open"

        @property
        def state(self):
            return self._state

        def acknowledge(self):
            self._state = "acknowledged"

        def investigate(self):
            self._state = "investigating"

        def resolve(self):
            # BUG: never checks the current state -- allows resolve() even from "open".
            self._state = "resolved"

        def close(self):
            self._state = "closed"

        def reopen(self):
            self._state = "investigating"
"""


def test_broken_incident_escalation_allows_illegal_transition_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_incidenttest_") as tmp:
        root = Path(tmp)
        _write(root, "incident_escalation.py",
               BROKEN_INCIDENT_ESCALATION_ALLOWS_ILLEGAL_TRANSITION)
        accepted, note = grade_real_system_task(INCIDENT_ESCALATION_TASK, root, python_exe=PY)
        assert accepted is False


def test_incident_escalation_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INCIDENT_ESCALATION_TASK.sentence) is None
    assert INCIDENT_ESCALATION_TASK in REAL_SYSTEMS_TASKS
    assert INCIDENT_ESCALATION_TASK.oracle_kind == "state_machine"
    assert INCIDENT_ESCALATION_TASK.cls == "devops"
    assert INCIDENT_ESCALATION_TASK.name == "incident-escalation-state-machine"
    assert INCIDENT_ESCALATION_TASK.oracle_spec["module"] == "incident_escalation"
    spec = INCIDENT_ESCALATION_TASK.oracle_spec["spec"]
    ok, note = validate_state_machine_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert {"action": "resolve", "expect": "reject"} in drive
    assert {"action": "close", "expect": "reject"} in drive
    assert {"action": "acknowledge", "expect": "reject"} in drive
    assert sum(1 for op in drive if op["expect"] == "reject") == 3
    assert spec["expect_final"] == "closed"
# #EXT-060-REQ-54 End


# ================================================================================================
# #EXT-060-REQ-55 Start
# WAREHOUSE_STOCK_RESERVATION_TASK ("conservation" oracle_kind)
# ================================================================================================

CORRECT_WAREHOUSE_STOCK_RESERVATION = """
    class StockReservation:
        def __init__(self, total_units):
            self._on_hand = total_units
            self._reserved = 0
            self._shipped = 0

        def on_hand(self):
            return self._on_hand

        def reserved(self):
            return self._reserved

        def shipped(self):
            return self._shipped

        def reserve(self, n):
            if n > self._on_hand:
                raise ValueError(f"cannot reserve {n}: only {self._on_hand} on hand")
            self._on_hand -= n
            self._reserved += n

        def unreserve(self, n):
            if n > self._reserved:
                raise ValueError(f"cannot unreserve {n}: only {self._reserved} reserved")
            self._reserved -= n
            self._on_hand += n

        def ship(self, n):
            if n > self._reserved:
                raise ValueError(f"cannot ship {n}: only {self._reserved} reserved")
            self._reserved -= n
            self._shipped += n
"""


def test_correct_warehouse_stock_reservation_passes_the_conservation_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_whtest_") as tmp:
        root = Path(tmp)
        _write(root, "warehouse_stock_reservation.py", CORRECT_WAREHOUSE_STOCK_RESERVATION)
        accepted, note = grade_real_system_task(WAREHOUSE_STOCK_RESERVATION_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `reserve()` never checks `on_hand` -- an over-reserve (beyond current stock) is silently
# allowed instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_WAREHOUSE_STOCK_RESERVATION_ALLOWS_OVER_RESERVE = """
    class StockReservation:
        def __init__(self, total_units):
            self._on_hand = total_units
            self._reserved = 0
            self._shipped = 0

        def on_hand(self):
            return self._on_hand

        def reserved(self):
            return self._reserved

        def shipped(self):
            return self._shipped

        def reserve(self, n):
            # BUG: never checks `on_hand` -- allows an over-reserve beyond current stock.
            self._on_hand -= n
            self._reserved += n

        def unreserve(self, n):
            self._reserved -= n
            self._on_hand += n

        def ship(self, n):
            if n > self._reserved:
                raise ValueError(f"cannot ship {n}: only {self._reserved} reserved")
            self._reserved -= n
            self._shipped += n
"""


def test_broken_warehouse_stock_reservation_allows_over_reserve_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_whtest_") as tmp:
        root = Path(tmp)
        _write(root, "warehouse_stock_reservation.py",
               BROKEN_WAREHOUSE_STOCK_RESERVATION_ALLOWS_OVER_RESERVE)
        accepted, note = grade_real_system_task(WAREHOUSE_STOCK_RESERVATION_TASK, root, python_exe=PY)
        assert accepted is False


def test_warehouse_stock_reservation_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(WAREHOUSE_STOCK_RESERVATION_TASK.sentence) is None
    assert WAREHOUSE_STOCK_RESERVATION_TASK in REAL_SYSTEMS_TASKS
    assert WAREHOUSE_STOCK_RESERVATION_TASK.oracle_kind == "conservation"
    assert WAREHOUSE_STOCK_RESERVATION_TASK.cls == "logistics"
    assert WAREHOUSE_STOCK_RESERVATION_TASK.name == "warehouse-stock-reservation-conservation"
    assert WAREHOUSE_STOCK_RESERVATION_TASK.oracle_spec["module"] == "warehouse_stock_reservation"
    spec = WAREHOUSE_STOCK_RESERVATION_TASK.oracle_spec["spec"]
    ok, note = validate_conservation_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 2
    assert spec["expect_final"] == {"on_hand": 50, "reserved": 0, "shipped": 50}
# #EXT-060-REQ-55 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_atlas_batch4_tasks.py's own
# guard exactly).
# ------------------------------------------------------------------------------------------------

def test_no_new_batch5_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("lru", "least recently used", "priority queue", "priority-queue", "min-heap",
              "max-heap", "heapq", "ttl", "time-to-live", "time to live", "expire", "expiry",
              "expiration", "fifo", "first-in-first-out", "first in first out", "ring buffer",
              "ring-buffer", "circular buffer", "circular-buffer", "memoize", "cache", "stack",
              "queue", "hold", "buffer")
    for task in (LOAN_AMORTIZATION_TASK, RUNNING_MEDIAN_TASK, INCIDENT_ESCALATION_TASK,
                 WAREHOUSE_STOCK_RESERVATION_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_batch5_task_has_a_leaf_fingerprint():
    for task in (LOAN_AMORTIZATION_TASK, RUNNING_MEDIAN_TASK, INCIDENT_ESCALATION_TASK,
                 WAREHOUSE_STOCK_RESERVATION_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-52..55),
# spread across THREE already-landed oracles (import/state_machine/conservation) in four distinct
# verticals.
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_batch5_tasks():
    # bumped 38 -> 42 -> 46 -> 50: this module's own REQ-52/53/54/55 add four more CREATE tasks,
    # then REQ-56..59 (tests/test_ext060_batch6_tasks.py) added four more, then REQ-60..63
    # (tests/test_ext060_batch7_tasks.py) added four more.
    assert len(REAL_SYSTEMS_TASKS) == 50
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "loan-amortization-schedule-lib" in names
    assert "running-median-lib" in names
    assert "incident-escalation-state-machine" in names
    assert "warehouse-stock-reservation-conservation" in names
    oracle_kinds = {
        "loan-amortization-schedule-lib": "import",
        "running-median-lib": "import",
        "incident-escalation-state-machine": "state_machine",
        "warehouse-stock-reservation-conservation": "conservation",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
