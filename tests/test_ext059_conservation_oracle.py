"""EXT-059 REQ-8: offline tests for the deterministic conservation / no-oversell invariant oracle.

Every fixture here is a small, hand-written Python module written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib only. These tests
are pure execution-plane verification of a deterministic module and must never reach the Jetson.

Run in isolation: ``python -m pytest tests/test_ext059_conservation_oracle.py -q``.
"""

# #EXT-059-REQ-8 Start
# TASK-6
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.conservation_oracle import grade_conservation, validate_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# A correctly-implemented single-SKU inventory reservation: `reserve(qty)` moves units from
# `available` to `reserved`, refusing (ValueError) a reservation that would exceed what's
# available; `release(qty)` moves reserved units back to available. Units are never lost/created.
CORRECT_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def reserve(self, qty):
            if qty > self._available:
                raise ValueError(f"cannot reserve {qty}: only {self._available} available")
            self._available -= qty
            self._reserved += qty

        def release(self, qty):
            if qty > self._reserved:
                raise ValueError(f"cannot release {qty}: only {self._reserved} reserved")
            self._reserved -= qty
            self._available += qty
"""

# The flagship honesty bug: `reserve()` has NO guard at all -- it happily reserves more units than
# are available, driving `available` negative (an oversell). `release()` is correct.
BROKEN_OVERSELL_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def reserve(self, qty):
            # BUG: no guard at all -- oversells past available stock.
            self._available -= qty
            self._reserved += qty

        def release(self, qty):
            if qty > self._reserved:
                raise ValueError(f"cannot release {qty}: only {self._reserved} reserved")
            self._reserved -= qty
            self._available += qty
"""

# The oversell guard is correct, but `reserve()` forgets to credit `reserved` -- units silently
# vanish from the system (available drops, but nothing shows up as reserved).
BROKEN_LOSES_UNITS_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def reserve(self, qty):
            if qty > self._available:
                raise ValueError(f"cannot reserve {qty}: only {self._available} available")
            self._available -= qty
            # BUG: forgets `self._reserved += qty` -- units are lost, not conserved.

        def release(self, qty):
            if qty > self._reserved:
                raise ValueError(f"cannot release {qty}: only {self._reserved} reserved")
            self._reserved -= qty
            self._available += qty
"""

# Every guard and delta is correct, but `release()` has an off-by-double bug: it credits twice the
# requested quantity back to `available` -- units are silently CREATED out of nowhere.
BROKEN_CREATES_UNITS_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def reserve(self, qty):
            if qty > self._available:
                raise ValueError(f"cannot reserve {qty}: only {self._available} available")
            self._available -= qty
            self._reserved += qty

        def release(self, qty):
            if qty > self._reserved:
                raise ValueError(f"cannot release {qty}: only {self._reserved} reserved")
            self._reserved -= qty
            self._available += qty * 2  # BUG: creates units out of nowhere
"""

# Guards and per-op deltas are all correct, but the constructor starts `reserved` at a nonzero
# value it shouldn't -- the whole script still runs "legally" but lands on the wrong final
# quantities (never matches expect_final).
WRONG_FINAL_QUANTITIES_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock - 5  # BUG: silently pre-reserves 5 units
            self._reserved = 5

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def reserve(self, qty):
            if qty > self._available:
                raise ValueError(f"cannot reserve {qty}: only {self._available} available")
            self._available -= qty
            self._reserved += qty

        def release(self, qty):
            if qty > self._reserved:
                raise ValueError(f"cannot release {qty}: only {self._reserved} reserved")
            self._reserved -= qty
            self._available += qty
"""

# A garbage fixture: raises at IMPORT time, before any entity could ever be constructed.
CRASHING_MODULE = """
    raise RuntimeError("boom -- this module is broken at import time")
"""

# `quantities`/`initial`/`drive`/`expect_final` for a 100-unit SKU: attempt an illegal oversell
# FIRST (reserve 150 of 100 -- must be rejected), then reserve 30 (legal), then release 10 (legal),
# landing on available=80, reserved=20.
INVENTORY_SPEC = {
    "quantities": ["available", "reserved"],
    "initial": {"available": 100, "reserved": 0},
    "construct_args": [100],
    "drive": [
        {"action": "reserve", "args": [150], "expect": "reject"},
        {"action": "reserve", "args": [30], "expect": "accept",
         "deltas": {"available": -30, "reserved": 30}},
        {"action": "release", "args": [10], "expect": "accept",
         "deltas": {"available": 10, "reserved": -10}},
    ],
    "expect_final": {"available": 80, "reserved": 20},
}


def test_validate_spec_accepts_well_formed_inventory_spec():
    ok, note = validate_spec(INVENTORY_SPEC)
    assert ok, note


def test_validate_spec_rejects_malformed_specs():
    ok, note = validate_spec({"quantities": ["available"]})  # missing initial/drive/expect_final
    assert not ok
    assert note

    ok, note = validate_spec("not a dict")
    assert not ok

    bad = dict(INVENTORY_SPEC)
    bad["initial"] = {"available": 100}  # missing 'reserved' key
    ok, note = validate_spec(bad)
    assert not ok
    assert "initial" in note


def test_validate_spec_rejects_non_conserving_deltas():
    """The conservation law itself is enforced structurally: an accept op whose deltas don't sum
    to zero describes a spec that would create or destroy units -- caught before anything drives."""
    bad = dict(INVENTORY_SPEC)
    bad["drive"] = [
        {"action": "reserve", "args": [30], "expect": "accept",
         "deltas": {"available": -30, "reserved": 25}},  # sums to -5, not 0
    ]
    bad["expect_final"] = {"available": 70, "reserved": 25}
    ok, note = validate_spec(bad)
    assert not ok
    assert "conserve" in note.lower()


def test_validate_spec_rejects_deltas_on_reject_op():
    bad = dict(INVENTORY_SPEC)
    bad["drive"] = [
        {"action": "reserve", "args": [150], "expect": "reject", "deltas": {"available": 0, "reserved": 0}},
    ]
    ok, note = validate_spec(bad)
    assert not ok
    assert "deltas" in note.lower()


def test_correct_inventory_passes(tmp_path):
    _write(tmp_path, "inventory.py", CORRECT_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert accepted, note
    assert "ok" in note.lower()


def test_oversell_bug_is_caught(tmp_path):
    """The flagship honesty test: a build that ALLOWS overselling past available stock must be
    caught, not silently accepted just because the legal path also happens to work."""
    _write(tmp_path, "inventory.py", BROKEN_OVERSELL_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_silently_loses_units_bug_is_caught(tmp_path):
    """Oversell guards are all correct, but a legal op silently loses units (available drops
    without a matching credit to reserved) -- the conservation oracle must catch this too, not
    just outright oversell leakage."""
    _write(tmp_path, "inventory.py", BROKEN_LOSES_UNITS_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_silently_creates_units_bug_is_caught(tmp_path):
    """A legal op silently CREATES units (double-credits available on release) -- conservation
    violations in either direction (loss or creation) must be caught."""
    _write(tmp_path, "inventory.py", BROKEN_CREATES_UNITS_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_wrong_final_quantities_is_caught(tmp_path):
    """Every guard and per-op delta is correct, but a bug elsewhere (a bad initial state) means
    the whole script still lands on the wrong final quantities -- must be caught independently."""
    _write(tmp_path, "inventory.py", WRONG_FINAL_QUANTITIES_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_never_raises_on_crashing_module(tmp_path):
    _write(tmp_path, "inventory.py", CRASHING_MODULE)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_module(tmp_path):
    accepted, note = grade_conservation(
        tmp_path, module="does_not_exist_at_all", entity="Inventory", spec=INVENTORY_SPEC,
        python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_entity(tmp_path):
    _write(tmp_path, "inventory.py", CORRECT_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="NoSuchClass", spec=INVENTORY_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_malformed_spec(tmp_path):
    _write(tmp_path, "inventory.py", CORRECT_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec={"garbage": True}, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_inconsistent_spec(tmp_path):
    """A spec whose `drive` script's declared deltas disagree with its own `expect_final` is
    caught BEFORE any subprocess is launched."""
    _write(tmp_path, "inventory.py", CORRECT_INVENTORY)

    inconsistent = dict(INVENTORY_SPEC)
    inconsistent["drive"] = [
        {"action": "reserve", "args": [30], "expect": "accept",
         "deltas": {"available": -30, "reserved": 30}},
    ]
    inconsistent["expect_final"] = {"available": 999, "reserved": 999}  # disagrees with the shadow

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=inconsistent, python_exe=PY,
    )
    assert accepted is False
    assert "inconsistency" in note


def test_never_raises_on_garbage_spec_type(tmp_path):
    _write(tmp_path, "inventory.py", CORRECT_INVENTORY)

    accepted, note = grade_conservation(
        tmp_path, module="inventory", entity="Inventory", spec=None, python_exe=PY,
    )
    assert accepted is False
    assert note
# #EXT-059-REQ-8 End
