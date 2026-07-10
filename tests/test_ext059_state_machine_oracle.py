"""EXT-059 REQ-7: offline tests for the deterministic state-machine / lifecycle oracle.

Every fixture here is a small, hand-written Python module written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib only. These tests
are pure execution-plane verification of a deterministic module and must never reach the Jetson.

Run in isolation: ``python -m pytest tests/test_ext059_state_machine_oracle.py -q``.
"""

# #EXT-059-REQ-7 Start
# TASK-5
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.state_machine_oracle import grade_state_machine, validate_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# A correctly-implemented order lifecycle: created -> paid -> shipped -> delivered, or
# created -> cancelled. Every action raises ValueError on an illegal transition and leaves state
# unchanged; `state` is a real Python `@property`.
CORRECT_ORDER = """
    class Order:
        _TRANSITIONS = {
            ("created", "pay"): "paid",
            ("paid", "ship"): "shipped",
            ("shipped", "deliver"): "delivered",
            ("created", "cancel"): "cancelled",
        }

        def __init__(self):
            self._state = "created"

        @property
        def state(self):
            return self._state

        def _transition(self, action):
            key = (self._state, action)
            if key not in self._TRANSITIONS:
                raise ValueError(f"illegal transition: {action} from {self._state}")
            self._state = self._TRANSITIONS[key]

        def pay(self):
            self._transition("pay")

        def ship(self):
            self._transition("ship")

        def deliver(self):
            self._transition("deliver")

        def cancel(self):
            self._transition("cancel")
"""

# The flagship honesty bug: `ship()` allows shipping from ANY state (no guard at all), so an
# unpaid order can be shipped. Every other action is implemented correctly.
BROKEN_SHIP_BEFORE_PAY_ORDER = """
    class Order:
        def __init__(self):
            self._state = "created"

        @property
        def state(self):
            return self._state

        def pay(self):
            if self._state != "created":
                raise ValueError("illegal transition: pay")
            self._state = "paid"

        def ship(self):
            # BUG: no guard at all -- ships from any state, including before payment.
            self._state = "shipped"

        def deliver(self):
            if self._state != "shipped":
                raise ValueError("illegal transition: deliver")
            self._state = "delivered"

        def cancel(self):
            if self._state != "created":
                raise ValueError("illegal transition: cancel")
            self._state = "cancelled"
"""

# Guards are all correct (illegal transitions ARE rejected), but `deliver()` has a bug: it forgets
# to actually move to "delivered" and leaves the order stuck on "shipped" instead.
WRONG_FINAL_STATE_ORDER = """
    class Order:
        def __init__(self):
            self._state = "created"

        @property
        def state(self):
            return self._state

        def pay(self):
            if self._state != "created":
                raise ValueError("illegal transition: pay")
            self._state = "paid"

        def ship(self):
            if self._state != "paid":
                raise ValueError("illegal transition: ship")
            self._state = "shipped"

        def deliver(self):
            if self._state != "shipped":
                raise ValueError("illegal transition: deliver")
            self._state = "shipped"  # BUG: should transition to "delivered"

        def cancel(self):
            if self._state != "created":
                raise ValueError("illegal transition: cancel")
            self._state = "cancelled"
"""

# A garbage fixture: raises at IMPORT time, before any entity could ever be constructed.
CRASHING_MODULE = """
    raise RuntimeError("boom -- this module is broken at import time")
"""

# ``states``/``transitions``/``drive``/``expect_final`` for the correct order lifecycle: attempt
# an illegal ship-before-pay FIRST (must be rejected), then walk the legal path to "delivered",
# then attempt an illegal cancel-after-delivered (must also be rejected).
ORDER_SPEC = {
    "states": ["created", "paid", "shipped", "delivered", "cancelled"],
    "initial": "created",
    "transitions": {
        "created:pay": "paid",
        "paid:ship": "shipped",
        "shipped:deliver": "delivered",
        "created:cancel": "cancelled",
    },
    "drive": [
        {"action": "ship", "expect": "reject"},
        {"action": "pay", "expect": "accept"},
        {"action": "ship", "expect": "accept"},
        {"action": "deliver", "expect": "accept"},
        {"action": "cancel", "expect": "reject"},
    ],
    "expect_final": "delivered",
}


def test_validate_spec_accepts_well_formed_order_spec():
    ok, note = validate_spec(ORDER_SPEC)
    assert ok, note


def test_validate_spec_rejects_malformed_specs():
    ok, note = validate_spec({"states": ["a"], "initial": "a"})  # missing transitions/drive/etc
    assert not ok
    assert note

    ok, note = validate_spec("not a dict")
    assert not ok

    bad = dict(ORDER_SPEC)
    bad["initial"] = "not_a_real_state"
    ok, note = validate_spec(bad)
    assert not ok
    assert "initial" in note


def test_correct_order_lifecycle_passes(tmp_path):
    _write(tmp_path, "order.py", CORRECT_ORDER)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec=ORDER_SPEC, python_exe=PY,
    )
    assert accepted, note
    assert "ok" in note.lower()


def test_ship_before_pay_bug_is_caught(tmp_path):
    """The flagship honesty test: a build that ALLOWS an illegal transition must be caught, not
    silently accepted just because the legal path also happens to work."""
    _write(tmp_path, "order.py", BROKEN_SHIP_BEFORE_PAY_ORDER)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec=ORDER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_wrong_final_state_is_caught(tmp_path):
    """Every guard is correct (illegal transitions ARE rejected), but a legal transition lands on
    the wrong actual state -- the state-machine oracle must catch this too, not just illegal-
    transition leakage."""
    _write(tmp_path, "order.py", WRONG_FINAL_STATE_ORDER)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec=ORDER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_never_raises_on_crashing_module(tmp_path):
    _write(tmp_path, "order.py", CRASHING_MODULE)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec=ORDER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_module(tmp_path):
    accepted, note = grade_state_machine(
        tmp_path, module="does_not_exist_at_all", entity="Order", spec=ORDER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_entity(tmp_path):
    _write(tmp_path, "order.py", CORRECT_ORDER)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="NoSuchClass", spec=ORDER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_malformed_spec(tmp_path):
    _write(tmp_path, "order.py", CORRECT_ORDER)

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec={"garbage": True}, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_inconsistent_spec(tmp_path):
    """A spec whose `drive` script disagrees with its own `transitions` table (declares 'accept'
    for a transition that isn't listed as legal) is caught BEFORE any subprocess is launched."""
    _write(tmp_path, "order.py", CORRECT_ORDER)

    inconsistent = dict(ORDER_SPEC)
    inconsistent["drive"] = [{"action": "deliver", "expect": "accept"}]  # illegal from "created"
    inconsistent["expect_final"] = "delivered"

    accepted, note = grade_state_machine(
        tmp_path, module="order", entity="Order", spec=inconsistent, python_exe=PY,
    )
    assert accepted is False
    assert "inconsistent" in note
# #EXT-059-REQ-7 End
