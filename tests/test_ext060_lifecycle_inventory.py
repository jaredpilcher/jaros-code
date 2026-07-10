"""EXT-060 TASK-10/TASK-11: offline tests for the first LIFECYCLE-shaped tasks (`oracle_kind=
"state_machine"`, REQ-13/REQ-14) and the first INVENTORY-shaped tasks (`oracle_kind="conservation"`,
REQ-15/REQ-16) on the canonical real-systems scoreboard.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every "order"/"inventory" module here is a
small, hand-written stdlib Python class written to a temp directory and driven against
`harness.state_machine_oracle`/`harness.conservation_oracle`'s own deterministic
import-and-drive machinery (exactly what `grade_real_system_task` itself wires for
`oracle_kind="state_machine"`/`"conservation"`) -- never a live orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_lifecycle_inventory.py
tests/test_ext060_real_systems_suite.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    INVENTORY_ADD_BACKORDER_MODIFY,
    INVENTORY_TASK,
    ORDER_ADD_REFUND_MODIFY,
    ORDER_LIFECYCLE_TASK,
    REAL_SYSTEMS_MODIFY_TASKS,
    REAL_SYSTEMS_TASKS,
    _INVENTORY_BASELINE_PY,
    _ORDER_BASELINE_PY,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-13 Start
# (a) a CORRECT Order fixture passes ORDER_LIFECYCLE_TASK's oracle
# ================================================================================================

def test_correct_order_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lifecycletest_") as tmp:
        root = Path(tmp)
        _write(root, "order.py", _ORDER_BASELINE_PY)
        accepted, note = grade_real_system_task(ORDER_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# (b) a BROKEN fixture (allows an illegal transition -- unguarded ship()) is rejected
# ------------------------------------------------------------------------------------------------

BROKEN_SHIP_UNGUARDED_ORDER = """
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


def test_broken_unguarded_ship_order_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lifecycletest_") as tmp:
        root = Path(tmp)
        _write(root, "order.py", BROKEN_SHIP_UNGUARDED_ORDER)
        accepted, note = grade_real_system_task(ORDER_LIFECYCLE_TASK, root, python_exe=PY)
        assert accepted is False


# ------------------------------------------------------------------------------------------------
# (c) leaves-OFF + roster membership
# ------------------------------------------------------------------------------------------------

def test_order_lifecycle_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(ORDER_LIFECYCLE_TASK.sentence) is None
    assert ORDER_LIFECYCLE_TASK in REAL_SYSTEMS_TASKS
    assert ORDER_LIFECYCLE_TASK.oracle_kind == "state_machine"
    assert ORDER_LIFECYCLE_TASK.cls == "lifecycle"
# #EXT-060-REQ-13 End


# ================================================================================================
# #EXT-060-REQ-14 Start
# (d) the MODIFY task's oracle accepts a GUARDED refund(), rejects the unmodified baseline AND an
#     unguarded refund()
# ================================================================================================

# A correct post-modification order: identical to the baseline, but adds a `refund()` action legal
# ONLY from "delivered" -- exactly what ORDER_ADD_REFUND_MODIFY.mod_sentence asks for.
CORRECT_GUARDED_REFUND_ORDER = """
    class Order:
        _TRANSITIONS = {
            ("created", "pay"): "paid",
            ("paid", "ship"): "shipped",
            ("shipped", "deliver"): "delivered",
            ("created", "cancel"): "cancelled",
            ("delivered", "refund"): "refunded",
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

        def refund(self):
            self._transition("refund")
"""


def test_correct_guarded_refund_order_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lifecyclemodtest_") as tmp:
        root = Path(tmp)
        _write(root, "order.py", CORRECT_GUARDED_REFUND_ORDER)
        accepted, note = grade_real_system_task(ORDER_ADD_REFUND_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_baseline_order_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lifecyclemodtest_") as tmp:
        root = Path(tmp)
        _write(root, "order.py", _ORDER_BASELINE_PY)
        accepted, note = grade_real_system_task(ORDER_ADD_REFUND_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: `refund()` is added but with NO guard at all -- legal from ANY state, including
# "created" -- the flagship illegal-transition-leakage bug this oracle exists to catch.
BROKEN_UNGUARDED_REFUND_ORDER = """
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

        def refund(self):
            # BUG: no guard at all -- refunds from any state, including before delivery.
            self._state = "refunded"
"""


def test_unguarded_refund_order_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lifecyclemodtest_") as tmp:
        root = Path(tmp)
        _write(root, "order.py", BROKEN_UNGUARDED_REFUND_ORDER)
        accepted, note = grade_real_system_task(ORDER_ADD_REFUND_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_order_add_refund_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(ORDER_ADD_REFUND_MODIFY.mod_sentence) is None
    assert ORDER_ADD_REFUND_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert ORDER_ADD_REFUND_MODIFY.oracle_kind == "state_machine"
    assert ORDER_ADD_REFUND_MODIFY.cls == "lifecycle-modify"
    assert "order.py" in ORDER_ADD_REFUND_MODIFY.start_system
# #EXT-060-REQ-14 End


# ================================================================================================
# #EXT-060-REQ-15 Start
# (e) a CORRECT Inventory fixture passes INVENTORY_TASK's oracle
# ================================================================================================

def test_correct_inventory_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_inventorytest_") as tmp:
        root = Path(tmp)
        _write(root, "inventory.py", _INVENTORY_BASELINE_PY)
        accepted, note = grade_real_system_task(INVENTORY_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# (f) a BROKEN fixture (allows an oversell -- unguarded reserve()) is rejected
# ------------------------------------------------------------------------------------------------

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


def test_broken_oversell_inventory_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_inventorytest_") as tmp:
        root = Path(tmp)
        _write(root, "inventory.py", BROKEN_OVERSELL_INVENTORY)
        accepted, note = grade_real_system_task(INVENTORY_TASK, root, python_exe=PY)
        assert accepted is False


# ------------------------------------------------------------------------------------------------
# (g) leaves-OFF + roster membership
# ------------------------------------------------------------------------------------------------

def test_inventory_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INVENTORY_TASK.sentence) is None
    assert INVENTORY_TASK in REAL_SYSTEMS_TASKS
    assert INVENTORY_TASK.oracle_kind == "conservation"
    assert INVENTORY_TASK.cls == "inventory"
# #EXT-060-REQ-15 End


# ================================================================================================
# #EXT-060-REQ-16 Start
# (h) the MODIFY task's oracle accepts a CORRECT backorder(), rejects the unmodified baseline AND a
#     backorder() that incorrectly mutates available/reserved
# ================================================================================================

# A correct post-modification inventory: identical to the baseline, but adds `backorder(qty)` plus
# its mirrored `backordered()`/`backorder_credit()` readers -- exactly what
# INVENTORY_ADD_BACKORDER_MODIFY.mod_sentence asks for. `available`/`reserved` are never touched.
CORRECT_BACKORDER_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0
            self._backordered = 0
            self._backorder_credit = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def backordered(self):
            return self._backordered

        def backorder_credit(self):
            return self._backorder_credit

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

        def backorder(self, qty):
            self._backordered += qty
            self._backorder_credit -= qty
"""


def test_correct_backorder_inventory_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_inventorymodtest_") as tmp:
        root = Path(tmp)
        _write(root, "inventory.py", CORRECT_BACKORDER_INVENTORY)
        accepted, note = grade_real_system_task(INVENTORY_ADD_BACKORDER_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_baseline_inventory_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_inventorymodtest_") as tmp:
        root = Path(tmp)
        _write(root, "inventory.py", _INVENTORY_BASELINE_PY)
        accepted, note = grade_real_system_task(INVENTORY_ADD_BACKORDER_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: `backorder()` is added, but it ALSO mutates `available` -- exactly the conservation-
# disturbing bug this oracle exists to catch (the mod_sentence explicitly forbids this).
BROKEN_BACKORDER_MUTATES_AVAILABLE_INVENTORY = """
    class Inventory:
        def __init__(self, initial_stock):
            self._available = initial_stock
            self._reserved = 0
            self._backordered = 0
            self._backorder_credit = 0

        def available(self):
            return self._available

        def reserved(self):
            return self._reserved

        def backordered(self):
            return self._backordered

        def backorder_credit(self):
            return self._backorder_credit

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

        def backorder(self, qty):
            # BUG: incorrectly mutates `available` -- backorder() must never touch it.
            self._available -= qty
            self._backordered += qty
            self._backorder_credit -= qty
"""


def test_backorder_that_mutates_available_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_inventorymodtest_") as tmp:
        root = Path(tmp)
        _write(root, "inventory.py", BROKEN_BACKORDER_MUTATES_AVAILABLE_INVENTORY)
        accepted, note = grade_real_system_task(INVENTORY_ADD_BACKORDER_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_inventory_add_backorder_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INVENTORY_ADD_BACKORDER_MODIFY.mod_sentence) is None
    assert INVENTORY_ADD_BACKORDER_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert INVENTORY_ADD_BACKORDER_MODIFY.oracle_kind == "conservation"
    assert INVENTORY_ADD_BACKORDER_MODIFY.cls == "inventory-modify"
    assert "inventory.py" in INVENTORY_ADD_BACKORDER_MODIFY.start_system
# #EXT-060-REQ-16 End
