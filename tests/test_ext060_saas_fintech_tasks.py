"""EXT-060 TASK-13/TASK-14: offline tests for two NEW real-systems CREATE tasks growing the
canonical scoreboard's SaaS + fintech vertical coverage (REQ-18, REQ-19):

- ``SUBSCRIPTION_LIFECYCLE_TASK`` (``oracle_kind="state_machine"``, ``cls="subscription"``): a SaaS
  billing subscription lifecycle, graded by the ALREADY-LANDED
  ``harness.state_machine_oracle.grade_state_machine`` dispatch (REQ-13's ``_grade_state_machine``,
  no new oracle code).
- ``WALLET_NO_OVERDRAW_TASK`` (``oracle_kind="conservation"``, ``cls="wallet"``): a fintech wallet
  balance that must never overdraw, graded by the ALREADY-LANDED
  ``harness.conservation_oracle.grade_conservation`` dispatch (REQ-15's ``_grade_conservation``, no
  new oracle code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python class written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_saas_fintech_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    REAL_SYSTEMS_TASKS,
    SUBSCRIPTION_LIFECYCLE_TASK,
    WALLET_NO_OVERDRAW_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-18 Start
# SUBSCRIPTION_LIFECYCLE_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_SUBSCRIPTION = """
    class Subscription:
        _TRANSITIONS = {
            ("trialing", "activate"): "active",
            ("active", "payment_failed"): "past_due",
            ("past_due", "recover"): "active",
            ("active", "cancel"): "canceled",
            ("past_due", "cancel"): "canceled",
            ("trialing", "lapse"): "expired",
        }

        def __init__(self):
            self._state = "trialing"

        @property
        def state(self):
            return self._state

        def _transition(self, action):
            key = (self._state, action)
            if key not in self._TRANSITIONS:
                raise ValueError(f"illegal transition: {action} from {self._state}")
            self._state = self._TRANSITIONS[key]

        def activate(self):
            self._transition("activate")

        def payment_failed(self):
            self._transition("payment_failed")

        def recover(self):
            self._transition("recover")

        def cancel(self):
            self._transition("cancel")

        def lapse(self):
            self._transition("lapse")
"""


def test_correct_subscription_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_subtest_") as tmp:
        root = Path(tmp)
        _write(root, "subscription.py", CORRECT_SUBSCRIPTION)
        accepted, note = grade_real_system_task(SUBSCRIPTION_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that allows an illegal transition (cancel() with no state guard at all) is
# rejected -- the honesty core the state_machine oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_SUBSCRIPTION_UNGUARDED_CANCEL = """
    class Subscription:
        _TRANSITIONS = {
            ("trialing", "activate"): "active",
            ("active", "payment_failed"): "past_due",
            ("past_due", "recover"): "active",
            ("trialing", "lapse"): "expired",
        }

        def __init__(self):
            self._state = "trialing"

        @property
        def state(self):
            return self._state

        def activate(self):
            key = (self._state, "activate")
            if key not in self._TRANSITIONS:
                raise ValueError("illegal")
            self._state = self._TRANSITIONS[key]

        def payment_failed(self):
            key = (self._state, "payment_failed")
            if key not in self._TRANSITIONS:
                raise ValueError("illegal")
            self._state = self._TRANSITIONS[key]

        def recover(self):
            key = (self._state, "recover")
            if key not in self._TRANSITIONS:
                raise ValueError("illegal")
            self._state = self._TRANSITIONS[key]

        def cancel(self):
            # BUG: no state guard at all -- cancel() is legal from ANY state, including
            # "trialing" (which must be rejected per the task's contract).
            self._state = "canceled"

        def lapse(self):
            key = (self._state, "lapse")
            if key not in self._TRANSITIONS:
                raise ValueError("illegal")
            self._state = self._TRANSITIONS[key]
"""


def test_broken_subscription_with_unguarded_cancel_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_subtest_") as tmp:
        root = Path(tmp)
        _write(root, "subscription.py", BROKEN_SUBSCRIPTION_UNGUARDED_CANCEL)
        accepted, note = grade_real_system_task(SUBSCRIPTION_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is False


def test_subscription_lifecycle_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SUBSCRIPTION_LIFECYCLE_TASK.sentence) is None
    assert SUBSCRIPTION_LIFECYCLE_TASK in REAL_SYSTEMS_TASKS
    assert SUBSCRIPTION_LIFECYCLE_TASK.oracle_kind == "state_machine"
    assert SUBSCRIPTION_LIFECYCLE_TASK.cls == "subscription"
    assert SUBSCRIPTION_LIFECYCLE_TASK.name == "subscription-lifecycle-state-machine"
# #EXT-060-REQ-18 End


# ================================================================================================
# #EXT-060-REQ-19 Start
# WALLET_NO_OVERDRAW_TASK ("conservation" oracle_kind)
# ================================================================================================

CORRECT_WALLET = """
    class Wallet:
        def __init__(self, initial_balance_cents):
            self._balance_cents = initial_balance_cents
            self._ledger_cents = 0

        def balance_cents(self):
            return self._balance_cents

        def ledger_cents(self):
            return self._ledger_cents

        def credit(self, cents):
            self._balance_cents += cents
            self._ledger_cents -= cents

        def debit(self, cents):
            if cents > self._balance_cents:
                raise ValueError(f"cannot debit {cents}: only {self._balance_cents} available")
            self._balance_cents -= cents
            self._ledger_cents += cents
"""


def test_correct_wallet_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_wallettest_") as tmp:
        root = Path(tmp)
        _write(root, "wallet.py", CORRECT_WALLET)
        accepted, note = grade_real_system_task(WALLET_NO_OVERDRAW_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that allows an overdraw (debit() with no balance guard) is rejected -- the
# honesty core the conservation oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_WALLET_ALLOWS_OVERDRAW = """
    class Wallet:
        def __init__(self, initial_balance_cents):
            self._balance_cents = initial_balance_cents
            self._ledger_cents = 0

        def balance_cents(self):
            return self._balance_cents

        def ledger_cents(self):
            return self._ledger_cents

        def credit(self, cents):
            self._balance_cents += cents
            self._ledger_cents -= cents

        def debit(self, cents):
            # BUG: never checks that cents <= balance_cents -- allows the balance to go negative
            # (an overdraw), instead of raising.
            self._balance_cents -= cents
            self._ledger_cents += cents
"""


def test_broken_wallet_that_allows_an_overdraw_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_wallettest_") as tmp:
        root = Path(tmp)
        _write(root, "wallet.py", BROKEN_WALLET_ALLOWS_OVERDRAW)
        accepted, note = grade_real_system_task(WALLET_NO_OVERDRAW_TASK, root, python_exe=PY)
        assert accepted is False


def test_wallet_no_overdraw_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(WALLET_NO_OVERDRAW_TASK.sentence) is None
    assert WALLET_NO_OVERDRAW_TASK in REAL_SYSTEMS_TASKS
    assert WALLET_NO_OVERDRAW_TASK.oracle_kind == "conservation"
    assert WALLET_NO_OVERDRAW_TASK.cls == "wallet"
    assert WALLET_NO_OVERDRAW_TASK.name == "wallet-no-overdraw"


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these two tasks (REQ-18 + REQ-19).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_two_new_tasks():
    assert len(REAL_SYSTEMS_TASKS) == 12
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "subscription-lifecycle-state-machine" in names
    assert "wallet-no-overdraw" in names
# #EXT-060-REQ-19 End
