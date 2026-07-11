"""EXT-060 TASK-55/TASK-56/TASK-57/TASK-58: offline tests for FOUR NEW real-systems CREATE tasks
("batch-7", picked for ORACLE-KIND DIVERSITY -- the roster had grown heavy on
``oracle_kind="import"`` reusable-library tasks -- so this batch has exactly ONE task per
NON-import oracle kind, across four verticals, all reusing an ALREADY-LANDED oracle (NO new oracle
code) (REQ-60/61/62/63):

- ``ELEVATOR_DISPATCH_TASK`` (``oracle_kind="state_machine"``, ``cls="embedded"``): a single
  elevator car's idle/moving_up/moving_down/doors_open dispatch lifecycle, graded by the
  ALREADY-LANDED ``harness.state_machine_oracle.grade_state_machine`` dispatch (REQ-13's
  ``_grade_state_machine``, no new oracle code).
- ``HOTEL_ROOM_INVENTORY_TASK`` (``oracle_kind="conservation"``, ``cls="hospitality"``): a hotel
  property's available/reserved/occupied room bookkeeping through a
  reserve/check-in/check-out/cancel workflow, graded by the SAME ALREADY-LANDED ``conservation``
  dispatch (REQ-15's ``_grade_conservation``, no new oracle code).
- ``PAYROLL_RUN_TASK`` (``oracle_kind="double_entry"``, ``cls="payroll"``): a payroll run posting
  gross wages/withheld tax/net pay plus a later tax remittance, graded by the SAME ALREADY-LANDED
  ``double_entry`` dispatch (REQ-17's ``_grade_double_entry``, no new oracle code).
- ``TOKEN_BUCKET_RATE_LIMITER_TASK`` (``oracle_kind="clock"``, ``cls="infra"``): a token-bucket API
  rate limiter whose bucket refills continuously with injected elapsed time, graded by the SAME
  ALREADY-LANDED ``clock`` dispatch (REQ-28's ``_grade_clock``, no new oracle code).

Every hand-verified vector/delta/timeline value was independently recomputed (a standalone scratch
Python walk of the exact same transition table / conservation deltas / debit-credit legs / refill
formula each task's sentence pins) BEFORE being written into the task's ``oracle_spec`` -- see each
task's own definition in ``harness/real_systems_suite.py`` for the recompute notes.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_batch7_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.clock_oracle import validate_spec as validate_clock_spec
from harness.conservation_oracle import validate_spec as validate_conservation_spec
from harness.double_entry_oracle import validate_spec as validate_double_entry_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    ELEVATOR_DISPATCH_TASK,
    HOTEL_ROOM_INVENTORY_TASK,
    PAYROLL_RUN_TASK,
    REAL_SYSTEMS_TASKS,
    TOKEN_BUCKET_RATE_LIMITER_TASK,
    grade_real_system_task,
)
from harness.state_machine_oracle import validate_spec as validate_state_machine_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-60 Start
# ELEVATOR_DISPATCH_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_ELEVATOR_DISPATCH = """
    class ElevatorController:
        _TRANSITIONS = {
            ("idle", "call_up"): "moving_up",
            ("idle", "call_down"): "moving_down",
            ("moving_up", "arrive"): "doors_open",
            ("moving_down", "arrive"): "doors_open",
            ("idle", "open"): "doors_open",
            ("doors_open", "close"): "idle",
        }

        def __init__(self):
            self._state = "idle"

        @property
        def state(self):
            return self._state

        def _transition(self, action):
            key = (self._state, action)
            if key not in self._TRANSITIONS:
                raise ValueError(f"illegal transition: {action} from {self._state}")
            self._state = self._TRANSITIONS[key]

        def call_up(self):
            self._transition("call_up")

        def call_down(self):
            self._transition("call_down")

        def arrive(self):
            self._transition("arrive")

        def open(self):
            self._transition("open")

        def close(self):
            self._transition("close")
"""


def test_correct_elevator_dispatch_passes_the_state_machine_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_elevatortest_") as tmp:
        root = Path(tmp)
        _write(root, "elevator_dispatch.py", CORRECT_ELEVATOR_DISPATCH)
        accepted, note = grade_real_system_task(ELEVATOR_DISPATCH_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `open()` never checks the current state -- it opens the doors even while the car is
# mid-travel (moving_up/moving_down), which must be rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_ELEVATOR_DISPATCH_OPENS_DOORS_WHILE_MOVING = """
    class ElevatorController:
        def __init__(self):
            self._state = "idle"

        @property
        def state(self):
            return self._state

        def call_up(self):
            self._state = "moving_up"

        def call_down(self):
            self._state = "moving_down"

        def arrive(self):
            self._state = "doors_open"

        def open(self):
            # BUG: never checks current state -- allows opening doors mid-travel.
            self._state = "doors_open"

        def close(self):
            self._state = "idle"
"""


def test_broken_elevator_dispatch_opens_doors_while_moving_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_elevatortest_") as tmp:
        root = Path(tmp)
        _write(root, "elevator_dispatch.py",
               BROKEN_ELEVATOR_DISPATCH_OPENS_DOORS_WHILE_MOVING)
        accepted, note = grade_real_system_task(ELEVATOR_DISPATCH_TASK, root, python_exe=PY)
        assert accepted is False


def test_elevator_dispatch_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(ELEVATOR_DISPATCH_TASK.sentence) is None
    assert ELEVATOR_DISPATCH_TASK in REAL_SYSTEMS_TASKS
    assert ELEVATOR_DISPATCH_TASK.oracle_kind == "state_machine"
    assert ELEVATOR_DISPATCH_TASK.cls == "embedded"
    assert ELEVATOR_DISPATCH_TASK.name == "elevator-dispatch-state-machine"
    assert ELEVATOR_DISPATCH_TASK.oracle_spec["module"] == "elevator_dispatch"
    spec = ELEVATOR_DISPATCH_TASK.oracle_spec["spec"]
    ok, note = validate_state_machine_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    # the three REQUIRED illegal cases (open-from-moving, call_up-from-doors_open,
    # arrive-from-idle) are all present.
    assert {"action": "arrive", "expect": "reject"} in drive
    assert {"action": "open", "expect": "reject"} in drive
    assert {"action": "call_up", "expect": "reject"} in drive
    assert sum(1 for op in drive if op["expect"] == "reject") == 4
    assert spec["expect_final"] == "idle"
# #EXT-060-REQ-60 End


# ================================================================================================
# #EXT-060-REQ-61 Start
# HOTEL_ROOM_INVENTORY_TASK ("conservation" oracle_kind)
# ================================================================================================

CORRECT_HOTEL_ROOM_INVENTORY = """
    class RoomInventory:
        def __init__(self, total_rooms):
            self._available = total_rooms
            self._reserved = 0
            self._occupied = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def occupied(self):
            return self._occupied

        def reserve(self, n):
            if n > self._available:
                raise ValueError(f"cannot reserve {n}: only {self._available} available")
            self._available -= n
            self._reserved += n

        def check_in(self, n):
            if n > self._reserved:
                raise ValueError(f"cannot check in {n}: only {self._reserved} reserved")
            self._reserved -= n
            self._occupied += n

        def check_out(self, n):
            self._occupied -= n
            self._available += n

        def cancel(self, n):
            self._reserved -= n
            self._available += n
"""


def test_correct_hotel_room_inventory_passes_the_conservation_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_hoteltest_") as tmp:
        root = Path(tmp)
        _write(root, "hotel_room_inventory.py", CORRECT_HOTEL_ROOM_INVENTORY)
        accepted, note = grade_real_system_task(HOTEL_ROOM_INVENTORY_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `reserve()` never checks `available` -- an over-reserve (reserving beyond what is
# available) is silently allowed instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_HOTEL_ROOM_INVENTORY_ALLOWS_OVER_RESERVE = """
    class RoomInventory:
        def __init__(self, total_rooms):
            self._available = total_rooms
            self._reserved = 0
            self._occupied = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def occupied(self):
            return self._occupied

        def reserve(self, n):
            # BUG: never checks `available` -- allows an over-reserve beyond current inventory.
            self._available -= n
            self._reserved += n

        def check_in(self, n):
            if n > self._reserved:
                raise ValueError(f"cannot check in {n}: only {self._reserved} reserved")
            self._reserved -= n
            self._occupied += n

        def check_out(self, n):
            self._occupied -= n
            self._available += n

        def cancel(self, n):
            self._reserved -= n
            self._available += n
"""


def test_broken_hotel_room_inventory_allows_over_reserve_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_hoteltest_") as tmp:
        root = Path(tmp)
        _write(root, "hotel_room_inventory.py",
               BROKEN_HOTEL_ROOM_INVENTORY_ALLOWS_OVER_RESERVE)
        accepted, note = grade_real_system_task(HOTEL_ROOM_INVENTORY_TASK, root, python_exe=PY)
        assert accepted is False


def test_hotel_room_inventory_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(HOTEL_ROOM_INVENTORY_TASK.sentence) is None
    assert HOTEL_ROOM_INVENTORY_TASK in REAL_SYSTEMS_TASKS
    assert HOTEL_ROOM_INVENTORY_TASK.oracle_kind == "conservation"
    assert HOTEL_ROOM_INVENTORY_TASK.cls == "hospitality"
    assert HOTEL_ROOM_INVENTORY_TASK.name == "hotel-room-inventory-conservation"
    assert HOTEL_ROOM_INVENTORY_TASK.oracle_spec["module"] == "hotel_room_inventory"
    spec = HOTEL_ROOM_INVENTORY_TASK.oracle_spec["spec"]
    ok, note = validate_conservation_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 2
    assert spec["expect_final"] == {"available": 75, "reserved": 5, "occupied": 20}
# #EXT-060-REQ-61 End


# ================================================================================================
# #EXT-060-REQ-62 Start
# PAYROLL_RUN_TASK ("double_entry" oracle_kind)
# ================================================================================================

CORRECT_PAYROLL_RUN = """
    class PayrollLedger:
        def __init__(self):
            self._balances = {"wage_expense": 0, "tax_payable": 0, "cash": 0}

        def wage_expense(self):
            return self._balances["wage_expense"]

        def tax_payable(self):
            return self._balances["tax_payable"]

        def cash(self):
            return self._balances["cash"]

        def post(self, legs):
            total_debit = sum(leg["debit"] for leg in legs if "debit" in leg)
            total_credit = sum(leg["credit"] for leg in legs if "credit" in leg)
            if total_debit != total_credit:
                raise ValueError("unbalanced posting")
            for leg in legs:
                if "debit" in leg:
                    self._balances[leg["account"]] += leg["debit"]
                else:
                    self._balances[leg["account"]] -= leg["credit"]
"""


def test_correct_payroll_run_passes_the_double_entry_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_payrolltest_") as tmp:
        root = Path(tmp)
        _write(root, "payroll_ledger.py", CORRECT_PAYROLL_RUN)
        accepted, note = grade_real_system_task(PAYROLL_RUN_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `post()` never checks that debits equal credits -- an unbalanced posting is silently
# applied instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_PAYROLL_RUN_ACCEPTS_UNBALANCED = """
    class PayrollLedger:
        def __init__(self):
            self._balances = {"wage_expense": 0, "tax_payable": 0, "cash": 0}

        def wage_expense(self):
            return self._balances["wage_expense"]

        def tax_payable(self):
            return self._balances["tax_payable"]

        def cash(self):
            return self._balances["cash"]

        def post(self, legs):
            # BUG: never checks debits == credits -- posts unbalanced entries too.
            for leg in legs:
                if "debit" in leg:
                    self._balances[leg["account"]] += leg["debit"]
                else:
                    self._balances[leg["account"]] -= leg["credit"]
"""


def test_broken_payroll_run_accepts_unbalanced_posting_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_payrolltest_") as tmp:
        root = Path(tmp)
        _write(root, "payroll_ledger.py", BROKEN_PAYROLL_RUN_ACCEPTS_UNBALANCED)
        accepted, note = grade_real_system_task(PAYROLL_RUN_TASK, root, python_exe=PY)
        assert accepted is False


def test_payroll_run_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(PAYROLL_RUN_TASK.sentence) is None
    assert PAYROLL_RUN_TASK in REAL_SYSTEMS_TASKS
    assert PAYROLL_RUN_TASK.oracle_kind == "double_entry"
    assert PAYROLL_RUN_TASK.cls == "payroll"
    assert PAYROLL_RUN_TASK.name == "payroll-run-double-entry-ledger"
    assert PAYROLL_RUN_TASK.oracle_spec["module"] == "payroll_ledger"
    spec = PAYROLL_RUN_TASK.oracle_spec["spec"]
    ok, note = validate_double_entry_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 1
    assert spec["expect_final"] == {
        "wage_expense": 1100000, "tax_payable": 0, "cash": -1100000,
    }
# #EXT-060-REQ-62 End


# ================================================================================================
# #EXT-060-REQ-63 Start
# TOKEN_BUCKET_RATE_LIMITER_TASK ("clock" oracle_kind)
# ================================================================================================

CORRECT_TOKEN_BUCKET = """
    class TokenBucket:
        def __init__(self, capacity, refill_rate, now_fn):
            self._capacity = capacity
            self._refill_rate = refill_rate
            self._now_fn = now_fn
            self._tokens = capacity
            self._last_refill = now_fn()

        def allow(self):
            now = self._now_fn()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False
"""


def test_correct_token_bucket_passes_the_clock_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_buckettest_") as tmp:
        root = Path(tmp)
        _write(root, "rate_limiter.py", CORRECT_TOKEN_BUCKET)
        accepted, note = grade_real_system_task(TOKEN_BUCKET_RATE_LIMITER_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses the REAL wall clock (`time.time()`) instead of the injected `now_fn` -- the driver
# never sleeps, so two calls declared 98 simulated seconds apart execute within real milliseconds
# of each other and the bucket never actually refills.
# ------------------------------------------------------------------------------------------------

BROKEN_TOKEN_BUCKET_USES_REAL_CLOCK = """
    import time

    class TokenBucket:
        def __init__(self, capacity, refill_rate, now_fn):
            self._capacity = capacity
            self._refill_rate = refill_rate
            self._now_fn = now_fn
            self._tokens = capacity
            self._last_refill = time.time()

        def allow(self):
            # BUG: uses the REAL wall clock instead of the injected now_fn.
            now = time.time()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False
"""


def test_broken_token_bucket_uses_real_clock_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_buckettest_") as tmp:
        root = Path(tmp)
        _write(root, "rate_limiter.py", BROKEN_TOKEN_BUCKET_USES_REAL_CLOCK)
        accepted, note = grade_real_system_task(TOKEN_BUCKET_RATE_LIMITER_TASK, root, python_exe=PY)
        assert accepted is False


def test_token_bucket_rate_limiter_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(TOKEN_BUCKET_RATE_LIMITER_TASK.sentence) is None
    assert TOKEN_BUCKET_RATE_LIMITER_TASK in REAL_SYSTEMS_TASKS
    assert TOKEN_BUCKET_RATE_LIMITER_TASK.oracle_kind == "clock"
    assert TOKEN_BUCKET_RATE_LIMITER_TASK.cls == "infra"
    assert TOKEN_BUCKET_RATE_LIMITER_TASK.name == "api-rate-limit-token-bucket-lib"
    assert TOKEN_BUCKET_RATE_LIMITER_TASK.oracle_spec["module"] == "rate_limiter"
    spec = TOKEN_BUCKET_RATE_LIMITER_TASK.oracle_spec["spec"]
    ok, note = validate_clock_spec(spec)
    assert ok is True, note
    timeline = spec["timeline"]
    assert sum(1 for step in timeline if step["expect"] == {"returns": True}) == 12
    assert sum(1 for step in timeline if step["expect"] == {"returns": False}) == 3
    # the sentence pins the now_fn contract explicitly.
    assert "now_fn" in TOKEN_BUCKET_RATE_LIMITER_TASK.sentence
    assert "zero-argument callable" in TOKEN_BUCKET_RATE_LIMITER_TASK.sentence
# #EXT-060-REQ-63 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_batch6_tasks.py's own
# guard exactly).
# ------------------------------------------------------------------------------------------------

def test_no_new_batch7_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("lru", "least recently used", "priority queue", "priority-queue", "min-heap",
              "max-heap", "heapq", "ttl", "time-to-live", "time to live", "expire", "expiry",
              "expiration", "fifo", "first-in-first-out", "first in first out", "ring buffer",
              "ring-buffer", "circular buffer", "circular-buffer", "memoize", "cache", "stack",
              "queue", "hold", "buffer")
    for task in (ELEVATOR_DISPATCH_TASK, HOTEL_ROOM_INVENTORY_TASK, PAYROLL_RUN_TASK,
                 TOKEN_BUCKET_RATE_LIMITER_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_batch7_task_has_a_leaf_fingerprint():
    for task in (ELEVATOR_DISPATCH_TASK, HOTEL_ROOM_INVENTORY_TASK, PAYROLL_RUN_TASK,
                 TOKEN_BUCKET_RATE_LIMITER_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


def test_batch7_tasks_cover_all_four_non_import_oracle_kinds_exactly_once():
    tasks = (ELEVATOR_DISPATCH_TASK, HOTEL_ROOM_INVENTORY_TASK, PAYROLL_RUN_TASK,
             TOKEN_BUCKET_RATE_LIMITER_TASK)
    kinds = {t.oracle_kind for t in tasks}
    assert kinds == {"state_machine", "conservation", "double_entry", "clock"}
    assert len(tasks) == 4
    verticals = {t.cls for t in tasks}
    assert len(verticals) == 4


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-60..63),
# one per non-import oracle kind, in four new verticals.
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_batch7_tasks():
    # bumped 46 -> 50: this module's own REQ-60/61/62/63 add four more CREATE tasks (then
    # REQ-64..67 in tests/test_ext060_batch8_tasks.py bumped it again, 50 -> 54).
    assert len(REAL_SYSTEMS_TASKS) == 54
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "elevator-dispatch-state-machine" in names
    assert "hotel-room-inventory-conservation" in names
    assert "payroll-run-double-entry-ledger" in names
    assert "api-rate-limit-token-bucket-lib" in names
    oracle_kinds = {
        "elevator-dispatch-state-machine": "state_machine",
        "hotel-room-inventory-conservation": "conservation",
        "payroll-run-double-entry-ledger": "double_entry",
        "api-rate-limit-token-bucket-lib": "clock",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
