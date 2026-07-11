"""EXT-060 TASK-39/TASK-40/TASK-41/TASK-42: offline tests for FOUR NEW real-systems CREATE tasks
spread across the LANDED oracles (state-machine/conservation/double-entry/import) (REQ-44/45/46/47):

- ``JOB_QUEUE_LIFECYCLE_TASK`` (``oracle_kind="state_machine"``, ``cls="jobs"``): a background-job
  processor's queued/running/succeeded/failed/retrying/dead lifecycle, graded by the ALREADY-LANDED
  ``harness.state_machine_oracle.grade_state_machine`` dispatch (REQ-13's ``_grade_state_machine``,
  no new oracle code).
- ``SEAT_HOLD_TASK`` (``oracle_kind="conservation"``, ``cls="ticketing"``): an event seat
  hold/confirm/release workflow (three-quantity available/held/sold mirror bookkeeping), graded by
  the SAME ALREADY-LANDED ``conservation`` dispatch (REQ-15's ``_grade_conservation``, no new
  oracle code).
- ``INVOICE_AR_AGING_TASK`` (``oracle_kind="double_entry"``, ``cls="fintech"``): an
  accounts-receivable ledger modeling MULTIPLE PARTIAL payments applied against one invoice, graded
  by the SAME ALREADY-LANDED ``double_entry`` dispatch (REQ-17's ``_grade_double_entry``, no new
  oracle code).
- ``CHECK_DIGIT_TASK`` (``oracle_kind="import"``, ``cls="validation"``): a Luhn/ISBN-13/EAN-13
  check-digit validator library, graded by the SAME ALREADY-LANDED ``import`` dispatch (REQ-3's
  ``_grade_import``, no new oracle code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_atlas_batch4_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.conservation_oracle import validate_spec as validate_conservation_spec
from harness.double_entry_oracle import validate_spec as validate_double_entry_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    CHECK_DIGIT_TASK,
    INVOICE_AR_AGING_TASK,
    JOB_QUEUE_LIFECYCLE_TASK,
    REAL_SYSTEMS_TASKS,
    SEAT_HOLD_TASK,
    grade_real_system_task,
)
from harness.state_machine_oracle import validate_spec as validate_state_machine_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-44 Start
# JOB_QUEUE_LIFECYCLE_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_JOB_LIFECYCLE = """
    class Job:
        _TRANSITIONS = {
            ("queued", "start"): "running",
            ("retrying", "start"): "running",
            ("running", "succeed"): "succeeded",
            ("running", "fail"): "failed",
            ("failed", "retry"): "retrying",
            ("queued", "kill"): "dead",
            ("running", "kill"): "dead",
            ("failed", "kill"): "dead",
            ("retrying", "kill"): "dead",
        }

        def __init__(self):
            self._state = "queued"

        @property
        def state(self):
            return self._state

        def _transition(self, action):
            key = (self._state, action)
            if key not in self._TRANSITIONS:
                raise ValueError(f"illegal transition: {action} from {self._state}")
            self._state = self._TRANSITIONS[key]

        def start(self):
            self._transition("start")

        def succeed(self):
            self._transition("succeed")

        def fail(self):
            self._transition("fail")

        def retry(self):
            self._transition("retry")

        def kill(self):
            self._transition("kill")
"""


def test_correct_job_lifecycle_passes_the_state_machine_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_jobtest_") as tmp:
        root = Path(tmp)
        _write(root, "job.py", CORRECT_JOB_LIFECYCLE)
        accepted, note = grade_real_system_task(JOB_QUEUE_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `succeed()` (and every other action) fires unconditionally from ANY state -- an illegal
# transition (succeed-from-"queued") is silently allowed instead of raising.
# ------------------------------------------------------------------------------------------------

BROKEN_JOB_LIFECYCLE_ALLOWS_ILLEGAL_TRANSITION = """
    class Job:
        def __init__(self):
            self._state = "queued"

        @property
        def state(self):
            return self._state

        def start(self):
            self._state = "running"

        def succeed(self):
            # BUG: never checks the current state -- allows succeed() even from "queued".
            self._state = "succeeded"

        def fail(self):
            self._state = "failed"

        def retry(self):
            self._state = "retrying"

        def kill(self):
            self._state = "dead"
"""


def test_broken_job_lifecycle_allows_illegal_transition_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_jobtest_") as tmp:
        root = Path(tmp)
        _write(root, "job.py", BROKEN_JOB_LIFECYCLE_ALLOWS_ILLEGAL_TRANSITION)
        accepted, note = grade_real_system_task(JOB_QUEUE_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is False


def test_job_lifecycle_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(JOB_QUEUE_LIFECYCLE_TASK.sentence) is None
    assert JOB_QUEUE_LIFECYCLE_TASK in REAL_SYSTEMS_TASKS
    assert JOB_QUEUE_LIFECYCLE_TASK.oracle_kind == "state_machine"
    assert JOB_QUEUE_LIFECYCLE_TASK.cls == "jobs"
    assert JOB_QUEUE_LIFECYCLE_TASK.name == "background-job-lifecycle-state-machine"
    assert JOB_QUEUE_LIFECYCLE_TASK.oracle_spec["module"] == "job"
    spec = JOB_QUEUE_LIFECYCLE_TASK.oracle_spec["spec"]
    ok, note = validate_state_machine_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert {"action": "succeed", "expect": "reject"} in drive
    assert {"action": "retry", "expect": "reject"} in drive
    assert sum(1 for op in drive if op["expect"] == "reject") == 2
# #EXT-060-REQ-44 End


# ================================================================================================
# #EXT-060-REQ-45 Start
# SEAT_HOLD_TASK ("conservation" oracle_kind)
# ================================================================================================

CORRECT_SEAT_HOLD = """
    class SeatHold:
        def __init__(self, total_seats):
            self._available = total_seats
            self._held = 0
            self._sold = 0

        def available(self):
            return self._available

        def held(self):
            return self._held

        def sold(self):
            return self._sold

        def hold(self, n):
            if n > self._available:
                raise ValueError(f"cannot hold {n}: only {self._available} available")
            self._available -= n
            self._held += n

        def confirm(self, n):
            if n > self._held:
                raise ValueError(f"cannot confirm {n}: only {self._held} held")
            self._held -= n
            self._sold += n

        def release(self, n):
            if n > self._held:
                raise ValueError(f"cannot release {n}: only {self._held} held")
            self._held -= n
            self._available += n
"""


def test_correct_seat_hold_passes_the_conservation_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_seathold_") as tmp:
        root = Path(tmp)
        _write(root, "seat_hold.py", CORRECT_SEAT_HOLD)
        accepted, note = grade_real_system_task(SEAT_HOLD_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `hold()` never checks `available` -- an over-hold (holding beyond what is available) is
# silently allowed instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_SEAT_HOLD_ALLOWS_OVER_HOLD = """
    class SeatHold:
        def __init__(self, total_seats):
            self._available = total_seats
            self._held = 0
            self._sold = 0

        def available(self):
            return self._available

        def held(self):
            return self._held

        def sold(self):
            return self._sold

        def hold(self, n):
            # BUG: never checks `available` -- allows an over-hold beyond current inventory.
            self._available -= n
            self._held += n

        def confirm(self, n):
            if n > self._held:
                raise ValueError(f"cannot confirm {n}: only {self._held} held")
            self._held -= n
            self._sold += n

        def release(self, n):
            self._held -= n
            self._available += n
"""


def test_broken_seat_hold_allows_over_hold_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_seathold_") as tmp:
        root = Path(tmp)
        _write(root, "seat_hold.py", BROKEN_SEAT_HOLD_ALLOWS_OVER_HOLD)
        accepted, note = grade_real_system_task(SEAT_HOLD_TASK, root, python_exe=PY)
        assert accepted is False


def test_seat_hold_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SEAT_HOLD_TASK.sentence) is None
    assert SEAT_HOLD_TASK in REAL_SYSTEMS_TASKS
    assert SEAT_HOLD_TASK.oracle_kind == "conservation"
    assert SEAT_HOLD_TASK.cls == "ticketing"
    assert SEAT_HOLD_TASK.name == "event-seat-hold-conservation"
    assert SEAT_HOLD_TASK.oracle_spec["module"] == "seat_hold"
    spec = SEAT_HOLD_TASK.oracle_spec["spec"]
    ok, note = validate_conservation_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 2
    assert spec["expect_final"] == {"available": 50, "held": 0, "sold": 50}
# #EXT-060-REQ-45 End


# ================================================================================================
# #EXT-060-REQ-46 Start
# INVOICE_AR_AGING_TASK ("double_entry" oracle_kind)
# ================================================================================================

CORRECT_AR_PAYMENT_APPLICATION = """
    class ARPaymentLedger:
        def __init__(self):
            self._balances = {"accounts_receivable": 0, "revenue": 0, "cash": 0}

        def accounts_receivable(self):
            return self._balances["accounts_receivable"]

        def revenue(self):
            return self._balances["revenue"]

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


def test_correct_ar_payment_application_passes_the_double_entry_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_artest_") as tmp:
        root = Path(tmp)
        _write(root, "ar_payment_application.py", CORRECT_AR_PAYMENT_APPLICATION)
        accepted, note = grade_real_system_task(INVOICE_AR_AGING_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `post()` never checks that debits equal credits -- an unbalanced posting is silently
# applied instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_AR_PAYMENT_APPLICATION_ACCEPTS_UNBALANCED = """
    class ARPaymentLedger:
        def __init__(self):
            self._balances = {"accounts_receivable": 0, "revenue": 0, "cash": 0}

        def accounts_receivable(self):
            return self._balances["accounts_receivable"]

        def revenue(self):
            return self._balances["revenue"]

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


def test_broken_ar_payment_application_accepts_unbalanced_posting_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_artest_") as tmp:
        root = Path(tmp)
        _write(root, "ar_payment_application.py", BROKEN_AR_PAYMENT_APPLICATION_ACCEPTS_UNBALANCED)
        accepted, note = grade_real_system_task(INVOICE_AR_AGING_TASK, root, python_exe=PY)
        assert accepted is False


def test_invoice_ar_aging_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INVOICE_AR_AGING_TASK.sentence) is None
    assert INVOICE_AR_AGING_TASK in REAL_SYSTEMS_TASKS
    assert INVOICE_AR_AGING_TASK.oracle_kind == "double_entry"
    assert INVOICE_AR_AGING_TASK.cls == "fintech"
    assert INVOICE_AR_AGING_TASK.name == "accounts-receivable-payment-application-ledger"
    assert INVOICE_AR_AGING_TASK.oracle_spec["module"] == "ar_payment_application"
    spec = INVOICE_AR_AGING_TASK.oracle_spec["spec"]
    ok, note = validate_double_entry_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 1
    assert spec["expect_final"] == {
        "accounts_receivable": 0, "revenue": -100000, "cash": 100000,
    }
# #EXT-060-REQ-46 End


# ================================================================================================
# #EXT-060-REQ-47 Start
# CHECK_DIGIT_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_CHECK_DIGITS = """
    def luhn_valid(number):
        if not isinstance(number, str) or not number.isdigit() or len(number) < 2:
            return False
        total = 0
        digits = [int(c) for c in number]
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0


    def _weighted13(s):
        if not isinstance(s, str) or not s.isdigit() or len(s) != 13:
            return None
        total = 0
        for i, ch in enumerate(s):
            weight = 1 if i % 2 == 0 else 3
            total += int(ch) * weight
        return total


    def isbn13_valid(s):
        total = _weighted13(s)
        return total is not None and total % 10 == 0


    def ean13_valid(s):
        total = _weighted13(s)
        return total is not None and total % 10 == 0
"""


def test_correct_check_digits_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_cdtest_") as tmp:
        root = Path(tmp)
        _write(root, "check_digits.py", CORRECT_CHECK_DIGITS)
        accepted, note = grade_real_system_task(CHECK_DIGIT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `luhn_valid` never implements the doubling/checksum algorithm -- it only checks the
# input's FORMAT (all digits, at least 2 of them), so it wrongly ACCEPTS a numerically-invalid
# Luhn number.
# ------------------------------------------------------------------------------------------------

BROKEN_CHECK_DIGITS_ACCEPTS_BAD_LUHN = """
    def luhn_valid(number):
        # BUG: never implements the actual doubling/checksum algorithm -- just checks the
        # format, so it wrongly ACCEPTS a numerically-invalid Luhn number.
        return isinstance(number, str) and number.isdigit() and len(number) >= 2


    def _weighted13(s):
        if not isinstance(s, str) or not s.isdigit() or len(s) != 13:
            return None
        total = 0
        for i, ch in enumerate(s):
            weight = 1 if i % 2 == 0 else 3
            total += int(ch) * weight
        return total


    def isbn13_valid(s):
        total = _weighted13(s)
        return total is not None and total % 10 == 0


    def ean13_valid(s):
        total = _weighted13(s)
        return total is not None and total % 10 == 0
"""


def test_broken_check_digits_accepts_bad_luhn_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_cdtest_") as tmp:
        root = Path(tmp)
        _write(root, "check_digits.py", BROKEN_CHECK_DIGITS_ACCEPTS_BAD_LUHN)
        accepted, note = grade_real_system_task(CHECK_DIGIT_TASK, root, python_exe=PY)
        assert accepted is False


def test_check_digit_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(CHECK_DIGIT_TASK.sentence) is None
    assert CHECK_DIGIT_TASK in REAL_SYSTEMS_TASKS
    assert CHECK_DIGIT_TASK.oracle_kind == "import"
    assert CHECK_DIGIT_TASK.cls == "validation"
    assert CHECK_DIGIT_TASK.name == "check-digit-validator-lib"
    assert CHECK_DIGIT_TASK.oracle_spec["module"] == "check_digits"
    checks = CHECK_DIGIT_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "luhn_good", "expected": True} in checks
    assert {"kind": "returns_equals", "call_id": "luhn_bad", "expected": False} in checks
    assert {"kind": "returns_equals", "call_id": "isbn13_good", "expected": True} in checks
    assert {"kind": "returns_equals", "call_id": "isbn13_bad", "expected": False} in checks
    assert {"kind": "returns_equals", "call_id": "ean13_good", "expected": True} in checks
    assert {"kind": "returns_equals", "call_id": "ean13_bad", "expected": False} in checks
# #EXT-060-REQ-47 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_atlas_wave7_tasks.py's own
# guard exactly), MINUS the bare token "queue": ``JOB_QUEUE_LIFECYCLE_TASK.sentence`` legitimately
# contains the required literal job-lifecycle state name `"queued"` (an ordinary status adjective,
# pinned by this REQ's own spec), which is a substring of "queue" -- but that is PROVABLY SAFE
# against the real leaf classifier: `harness.adt_oracle._KEYWORDS`/`_METHOD_TOKENS` never lists the
# bare token "queue" at all (only the FULL PHRASES "fifo"/"first-in-first-out" and "priority
# queue"/"priority-queue", neither of which "queued" or this task's "background-job processor"
# framing ever forms) -- confirmed directly below by asserting `leaf_for_spec` is still `None` for
# every task, not just by the literal substring scan.
# ------------------------------------------------------------------------------------------------

def test_no_new_batch4_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("expire", "expiry", "expiration", "cache", "ttl", "stack",
              "ring buffer", "ring-buffer", "circular buffer", "circular-buffer", "memoize",
              "fifo", "priority queue", "priority-queue")
    for task in (JOB_QUEUE_LIFECYCLE_TASK, SEAT_HOLD_TASK, INVOICE_AR_AGING_TASK, CHECK_DIGIT_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_batch4_task_has_a_leaf_fingerprint():
    for task in (JOB_QUEUE_LIFECYCLE_TASK, SEAT_HOLD_TASK, INVOICE_AR_AGING_TASK, CHECK_DIGIT_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-44..47),
# spread one-per-oracle-kind across every LANDED non-fs/non-cli-exact/non-service/non-agent/
# non-clock oracle (state_machine/conservation/double_entry/import).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_batch4_tasks():
    # bumped 30 -> 34 -> 38 -> 42 -> 46: this module's own REQ-44/45/46/47 add four more CREATE
    # tasks, then REQ-48..51 (tests/test_ext060_wave8_import_tasks.py) added four more, then
    # REQ-52..55 (tests/test_ext060_batch5_tasks.py) added four more, then REQ-56..59
    # (tests/test_ext060_batch6_tasks.py) added four more.
    assert len(REAL_SYSTEMS_TASKS) == 46
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "background-job-lifecycle-state-machine" in names
    assert "event-seat-hold-conservation" in names
    assert "accounts-receivable-payment-application-ledger" in names
    assert "check-digit-validator-lib" in names
    oracle_kinds = {
        "background-job-lifecycle-state-machine": "state_machine",
        "event-seat-hold-conservation": "conservation",
        "accounts-receivable-payment-application-ledger": "double_entry",
        "check-digit-validator-lib": "import",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
