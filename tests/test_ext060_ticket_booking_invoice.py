"""EXT-060 TASK-15/TASK-16/TASK-17: offline tests for THREE NEW real-systems CREATE tasks growing
the canonical scoreboard's roster into new verticals (REQ-20, REQ-21, REQ-22):

- ``TICKET_WORKFLOW_TASK`` (``oracle_kind="state_machine"``, ``cls="ticket"``): a support/helpdesk
  ticket workflow, graded by the ALREADY-LANDED
  ``harness.state_machine_oracle.grade_state_machine`` dispatch (REQ-13's ``_grade_state_machine``,
  no new oracle code).
- ``SEAT_BOOKING_TASK`` (``oracle_kind="conservation"``, ``cls="booking"``): an event/venue
  seat-booking system that must never double-book, graded by the ALREADY-LANDED
  ``harness.conservation_oracle.grade_conservation`` dispatch (REQ-15's ``_grade_conservation``, no
  new oracle code).
- ``INVOICE_AR_TASK`` (``oracle_kind="double_entry"``, ``cls="invoice"``): an accounts-receivable
  double-entry ledger, graded by the ALREADY-LANDED
  ``harness.double_entry_oracle.grade_double_entry`` dispatch (REQ-17's ``_grade_double_entry``, no
  new oracle code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python class written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_ticket_booking_invoice.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    INVOICE_AR_TASK,
    REAL_SYSTEMS_TASKS,
    SEAT_BOOKING_TASK,
    TICKET_WORKFLOW_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-20 Start
# TICKET_WORKFLOW_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_TICKET = """
    class Ticket:
        _TRANSITIONS = {
            ("open", "assign"): "assigned",
            ("assigned", "await_customer"): "pending_customer",
            ("pending_customer", "respond"): "assigned",
            ("assigned", "resolve"): "resolved",
            ("resolved", "close"): "closed",
            ("closed", "reopen"): "open",
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

        def assign(self):
            self._transition("assign")

        def await_customer(self):
            self._transition("await_customer")

        def respond(self):
            self._transition("respond")

        def resolve(self):
            self._transition("resolve")

        def close(self):
            self._transition("close")

        def reopen(self):
            self._transition("reopen")
"""


def test_correct_ticket_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_tickettest_") as tmp:
        root = Path(tmp)
        _write(root, "ticket.py", CORRECT_TICKET)
        accepted, note = grade_real_system_task(TICKET_WORKFLOW_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that allows illegal transitions (resolve()/reopen() with no state guard at all)
# is rejected -- the honesty core the state_machine oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_TICKET_UNGUARDED_RESOLVE_AND_REOPEN = """
    class Ticket:
        def __init__(self):
            self._state = "open"

        @property
        def state(self):
            return self._state

        def assign(self):
            self._state = "assigned"

        def await_customer(self):
            self._state = "pending_customer"

        def respond(self):
            self._state = "assigned"

        def resolve(self):
            # BUG: no state guard at all -- resolve() is legal from ANY state, including "open"
            # (which must be rejected per the task's contract).
            self._state = "resolved"

        def close(self):
            self._state = "closed"

        def reopen(self):
            # BUG: no state guard at all -- reopen() is legal from ANY state, including
            # "assigned" (which must be rejected per the task's contract).
            self._state = "open"
"""


def test_broken_ticket_with_unguarded_resolve_and_reopen_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_tickettest_") as tmp:
        root = Path(tmp)
        _write(root, "ticket.py", BROKEN_TICKET_UNGUARDED_RESOLVE_AND_REOPEN)
        accepted, note = grade_real_system_task(TICKET_WORKFLOW_TASK, root, python_exe=PY)
        assert accepted is False


def test_ticket_workflow_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(TICKET_WORKFLOW_TASK.sentence) is None
    assert TICKET_WORKFLOW_TASK in REAL_SYSTEMS_TASKS
    assert TICKET_WORKFLOW_TASK.oracle_kind == "state_machine"
    assert TICKET_WORKFLOW_TASK.cls == "ticket"
    assert TICKET_WORKFLOW_TASK.name == "support-ticket-workflow-state-machine"
# #EXT-060-REQ-20 End


# ================================================================================================
# #EXT-060-REQ-21 Start
# SEAT_BOOKING_TASK ("conservation" oracle_kind)
# ================================================================================================

CORRECT_SEAT_BOOKING = """
    class SeatBooking:
        def __init__(self, total_seats):
            self._available_seats = total_seats
            self._reserved_seats = 0

        def available_seats(self):
            return self._available_seats

        def reserved_seats(self):
            return self._reserved_seats

        def reserve(self, n):
            if n > self._available_seats:
                raise ValueError(f"cannot reserve {n}: only {self._available_seats} available")
            self._available_seats -= n
            self._reserved_seats += n

        def release(self, n):
            if n > self._reserved_seats:
                raise ValueError(f"cannot release {n}: only {self._reserved_seats} reserved")
            self._reserved_seats -= n
            self._available_seats += n
"""


def test_correct_seat_booking_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_bookingtest_") as tmp:
        root = Path(tmp)
        _write(root, "booking.py", CORRECT_SEAT_BOOKING)
        accepted, note = grade_real_system_task(SEAT_BOOKING_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that allows an overbooking (reserve() with no capacity guard) is rejected --
# the honesty core the conservation oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_SEAT_BOOKING_ALLOWS_OVERBOOK = """
    class SeatBooking:
        def __init__(self, total_seats):
            self._available_seats = total_seats
            self._reserved_seats = 0

        def available_seats(self):
            return self._available_seats

        def reserved_seats(self):
            return self._reserved_seats

        def reserve(self, n):
            # BUG: never checks that n <= available_seats -- allows overbooking (available_seats
            # to go negative) instead of raising.
            self._available_seats -= n
            self._reserved_seats += n

        def release(self, n):
            self._reserved_seats -= n
            self._available_seats += n
"""


def test_broken_seat_booking_that_allows_an_overbook_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_bookingtest_") as tmp:
        root = Path(tmp)
        _write(root, "booking.py", BROKEN_SEAT_BOOKING_ALLOWS_OVERBOOK)
        accepted, note = grade_real_system_task(SEAT_BOOKING_TASK, root, python_exe=PY)
        assert accepted is False


def test_seat_booking_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SEAT_BOOKING_TASK.sentence) is None
    assert SEAT_BOOKING_TASK in REAL_SYSTEMS_TASKS
    assert SEAT_BOOKING_TASK.oracle_kind == "conservation"
    assert SEAT_BOOKING_TASK.cls == "booking"
    assert SEAT_BOOKING_TASK.name == "seat-booking-no-double-book"
# #EXT-060-REQ-21 End


# ================================================================================================
# #EXT-060-REQ-22 Start
# INVOICE_AR_TASK ("double_entry" oracle_kind)
# ================================================================================================

CORRECT_INVOICING = """
    class Invoicing:
        def __init__(self):
            self._accounts_receivable = 0
            self._revenue = 0
            self._cash = 0

        def accounts_receivable(self):
            return self._accounts_receivable

        def revenue(self):
            return self._revenue

        def cash(self):
            return self._cash

        def post(self, legs):
            deltas = {"accounts_receivable": 0, "revenue": 0, "cash": 0}
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
            self._accounts_receivable += deltas["accounts_receivable"]
            self._revenue += deltas["revenue"]
            self._cash += deltas["cash"]
"""


def test_correct_invoicing_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_invoicetest_") as tmp:
        root = Path(tmp)
        _write(root, "invoicing.py", CORRECT_INVOICING)
        accepted, note = grade_real_system_task(INVOICE_AR_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that posts an unbalanced entry unconditionally is rejected -- the honesty core
# the double_entry oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_INVOICING_ACCEPTS_UNBALANCED = """
    class Invoicing:
        def __init__(self):
            self._accounts_receivable = 0
            self._revenue = 0
            self._cash = 0

        def accounts_receivable(self):
            return self._accounts_receivable

        def revenue(self):
            return self._revenue

        def cash(self):
            return self._cash

        def post(self, legs):
            # BUG: never checks that debits == credits -- posts every entry unconditionally,
            # including unbalanced ones (which would create or destroy money out of nowhere).
            for leg in legs:
                account = leg["account"]
                if "debit" in leg:
                    delta = leg["debit"]
                else:
                    delta = -leg["credit"]
                if account == "accounts_receivable":
                    self._accounts_receivable += delta
                elif account == "revenue":
                    self._revenue += delta
                else:
                    self._cash += delta
"""


def test_broken_invoicing_that_accepts_unbalanced_entries_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_invoicetest_") as tmp:
        root = Path(tmp)
        _write(root, "invoicing.py", BROKEN_INVOICING_ACCEPTS_UNBALANCED)
        accepted, note = grade_real_system_task(INVOICE_AR_TASK, root, python_exe=PY)
        assert accepted is False


def test_invoice_ar_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INVOICE_AR_TASK.sentence) is None
    assert INVOICE_AR_TASK in REAL_SYSTEMS_TASKS
    assert INVOICE_AR_TASK.oracle_kind == "double_entry"
    assert INVOICE_AR_TASK.cls == "invoice"
    assert INVOICE_AR_TASK.name == "invoice-accounts-receivable-ledger"
# #EXT-060-REQ-22 End


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these three tasks (REQ-20/21/22).
# (The total below reflects the roster's size as of REQ-24/25/26/27's later additions -- this
# test only asserts that THESE THREE names are present, not an exact historical count.)
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_three_new_tasks():
    assert len(REAL_SYSTEMS_TASKS) == 19
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "support-ticket-workflow-state-machine" in names
    assert "seat-booking-no-double-book" in names
    assert "invoice-accounts-receivable-ledger" in names
