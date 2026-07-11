"""EXT-060 TASK-59/TASK-60/TASK-61/TASK-62: offline tests for FOUR NEW real-systems CREATE tasks
("batch-8", picked for ORACLE-KIND DIVERSITY across FOUR genuinely real production verticals --
devtools/build-systems, e-commerce/fulfillment, fintech/marketplace, saas/auth) -- one task each for
the ``import``/``state_machine``/``double_entry``/``clock`` oracle kinds, all reusing an
ALREADY-LANDED oracle (NO new oracle code) (REQ-64/65/66/67):

- ``DAG_TOPO_SORT_TASK`` (``oracle_kind="import"``, ``cls="devtools"``): a build-system-style
  dependency-graph resolver (`topo_sort`/`has_cycle`), graded by the ALREADY-LANDED
  ``harness.import_driver.drive_import`` dispatch (REQ-3's ``_grade_import``, no new oracle code).
- ``ORDER_FULFILLMENT_TASK`` (``oracle_kind="state_machine"``, ``cls="fulfillment"``): an 8-state
  e-commerce order fulfillment pipeline (placed/paid/picked/packed/shipped/delivered/cancelled/
  refunded) with branching cancel/refund sources, graded by the SAME ALREADY-LANDED
  ``state_machine`` dispatch (REQ-13's ``_grade_state_machine``, no new oracle code).
- ``MARKETPLACE_ESCROW_TASK`` (``oracle_kind="double_entry"``, ``cls="marketplace"``): a two-sided
  marketplace's buyer/escrow/seller/platform-fee escrow accounting across a
  fund-then-release-or-refund workflow, graded by the SAME ALREADY-LANDED ``double_entry`` dispatch
  (REQ-17's ``_grade_double_entry``, no new oracle code).
- ``SESSION_IDLE_TIMEOUT_TASK`` (``oracle_kind="clock"``, ``cls="auth"``): a sliding idle-timeout
  session store (every `touch()` slides the window forward, strict "<" boundary), graded by the
  SAME ALREADY-LANDED ``clock`` dispatch (REQ-28's ``_grade_clock``, no new oracle code).

Every hand-verified vector/delta/timeline value was independently recomputed (a standalone scratch
Python walk of the exact same tie-break rule / transition table / debit-credit legs / sliding-window
formula each task's sentence pins) BEFORE being written into the task's ``oracle_spec`` -- see each
task's own definition in ``harness/real_systems_suite.py`` for the recompute notes.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_batch8_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.clock_oracle import validate_spec as validate_clock_spec
from harness.double_entry_oracle import validate_spec as validate_double_entry_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    DAG_TOPO_SORT_TASK,
    MARKETPLACE_ESCROW_TASK,
    ORDER_FULFILLMENT_TASK,
    REAL_SYSTEMS_TASKS,
    SESSION_IDLE_TIMEOUT_TASK,
    grade_real_system_task,
)
from harness.state_machine_oracle import validate_spec as validate_state_machine_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-64 Start
# DAG_TOPO_SORT_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_DAG_TOPO_SORT = """
    def topo_sort(nodes, edges):
        indegree = {n: 0 for n in nodes}
        adj = {n: [] for n in nodes}
        for u, v in edges:
            indegree[v] += 1
            adj[u].append(v)
        placed = set()
        result = []
        while len(result) < len(nodes):
            eligible = sorted(n for n in nodes if n not in placed and indegree[n] == 0)
            if not eligible:
                raise ValueError("cycle detected -- no valid topological ordering exists")
            chosen = eligible[0]
            result.append(chosen)
            placed.add(chosen)
            for m in adj[chosen]:
                indegree[m] -= 1
        return result

    def has_cycle(nodes, edges):
        try:
            topo_sort(nodes, edges)
            return False
        except ValueError:
            return True
"""


def test_correct_dag_topo_sort_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_topotest_") as tmp:
        root = Path(tmp)
        _write(root, "dag_topo_sort.py", CORRECT_DAG_TOPO_SORT)
        accepted, note = grade_real_system_task(DAG_TOPO_SORT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: ignores the pinned lexicographic tie-break (walks candidates in raw input-list order
# instead of sorting them) AND never detects a cycle -- it silently returns whatever got placed
# instead of raising ValueError.
# ------------------------------------------------------------------------------------------------

BROKEN_DAG_TOPO_SORT_NO_TIEBREAK_NO_CYCLE_CHECK = """
    def topo_sort(nodes, edges):
        indegree = {n: 0 for n in nodes}
        adj = {n: [] for n in nodes}
        for u, v in edges:
            indegree[v] += 1
            adj[u].append(v)
        placed = set()
        result = []
        changed = True
        while changed and len(result) < len(nodes):
            changed = False
            # BUG: walks candidates in raw input-list order, never sorted lexicographically.
            for n in nodes:
                if n in placed or indegree[n] != 0:
                    continue
                result.append(n)
                placed.add(n)
                for m in adj[n]:
                    indegree[m] -= 1
                changed = True
        # BUG: never checks for leftover unplaced nodes -- a cycle silently yields a partial list
        # instead of raising ValueError.
        return result

    def has_cycle(nodes, edges):
        return len(topo_sort(nodes, edges)) != len(nodes)
"""


def test_broken_dag_topo_sort_no_tiebreak_no_cycle_check_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_topotest_") as tmp:
        root = Path(tmp)
        _write(root, "dag_topo_sort.py",
               BROKEN_DAG_TOPO_SORT_NO_TIEBREAK_NO_CYCLE_CHECK)
        accepted, note = grade_real_system_task(DAG_TOPO_SORT_TASK, root, python_exe=PY)
        assert accepted is False


def test_dag_topo_sort_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(DAG_TOPO_SORT_TASK.sentence) is None
    assert DAG_TOPO_SORT_TASK in REAL_SYSTEMS_TASKS
    assert DAG_TOPO_SORT_TASK.oracle_kind == "import"
    assert DAG_TOPO_SORT_TASK.cls == "devtools"
    assert DAG_TOPO_SORT_TASK.name == "dag-topological-sort-lib"
    assert DAG_TOPO_SORT_TASK.oracle_spec["module"] == "dag_topo_sort"
    checks = DAG_TOPO_SORT_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "topo_sort_diamond",
            "expected": ["a", "b", "c", "d"]} in checks
    assert {"kind": "returns_equals", "call_id": "topo_sort_no_edges",
            "expected": ["a", "b", "c"]} in checks
    assert {"kind": "raises", "call_id": "topo_sort_cycle", "exception": "ValueError"} in checks
    assert {"kind": "returns_equals", "call_id": "has_cycle_false", "expected": False} in checks
    assert {"kind": "returns_equals", "call_id": "has_cycle_true", "expected": True} in checks
# #EXT-060-REQ-64 End


# ================================================================================================
# #EXT-060-REQ-65 Start
# ORDER_FULFILLMENT_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_ORDER_FULFILLMENT = """
    class OrderFulfillment:
        _TRANSITIONS = {
            ("placed", "pay"): "paid",
            ("paid", "pick"): "picked",
            ("picked", "pack"): "packed",
            ("packed", "ship"): "shipped",
            ("shipped", "deliver"): "delivered",
            ("placed", "cancel"): "cancelled",
            ("paid", "cancel"): "cancelled",
            ("paid", "refund"): "refunded",
            ("picked", "refund"): "refunded",
            ("packed", "refund"): "refunded",
            ("shipped", "refund"): "refunded",
            ("delivered", "refund"): "refunded",
        }

        def __init__(self):
            self._state = "placed"

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

        def pick(self):
            self._transition("pick")

        def pack(self):
            self._transition("pack")

        def ship(self):
            self._transition("ship")

        def deliver(self):
            self._transition("deliver")

        def cancel(self):
            self._transition("cancel")

        def refund(self):
            self._transition("refund")
"""


def test_correct_order_fulfillment_passes_the_state_machine_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_fulfillmenttest_") as tmp:
        root = Path(tmp)
        _write(root, "order_fulfillment.py", CORRECT_ORDER_FULFILLMENT)
        accepted, note = grade_real_system_task(ORDER_FULFILLMENT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `ship()` never checks the current state -- it lets an order ship straight from
# "placed" (skipping payment, picking, and packing entirely), which must be rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_ORDER_FULFILLMENT_SHIPS_FROM_PLACED = """
    class OrderFulfillment:
        def __init__(self):
            self._state = "placed"

        @property
        def state(self):
            return self._state

        def pay(self):
            if self._state != "placed":
                raise ValueError("illegal pay")
            self._state = "paid"

        def pick(self):
            if self._state != "paid":
                raise ValueError("illegal pick")
            self._state = "picked"

        def pack(self):
            if self._state != "picked":
                raise ValueError("illegal pack")
            self._state = "packed"

        def ship(self):
            # BUG: never checks current state -- allows shipping straight from "placed".
            self._state = "shipped"

        def deliver(self):
            if self._state != "shipped":
                raise ValueError("illegal deliver")
            self._state = "delivered"

        def cancel(self):
            if self._state not in ("placed", "paid"):
                raise ValueError("illegal cancel")
            self._state = "cancelled"

        def refund(self):
            if self._state not in ("paid", "picked", "packed", "shipped", "delivered"):
                raise ValueError("illegal refund")
            self._state = "refunded"
"""


def test_broken_order_fulfillment_ships_from_placed_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_fulfillmenttest_") as tmp:
        root = Path(tmp)
        _write(root, "order_fulfillment.py", BROKEN_ORDER_FULFILLMENT_SHIPS_FROM_PLACED)
        accepted, note = grade_real_system_task(ORDER_FULFILLMENT_TASK, root, python_exe=PY)
        assert accepted is False


def test_order_fulfillment_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(ORDER_FULFILLMENT_TASK.sentence) is None
    assert ORDER_FULFILLMENT_TASK in REAL_SYSTEMS_TASKS
    assert ORDER_FULFILLMENT_TASK.oracle_kind == "state_machine"
    assert ORDER_FULFILLMENT_TASK.cls == "fulfillment"
    assert ORDER_FULFILLMENT_TASK.name == "order-fulfillment-state-machine"
    assert ORDER_FULFILLMENT_TASK.oracle_spec["module"] == "order_fulfillment"
    spec = ORDER_FULFILLMENT_TASK.oracle_spec["spec"]
    ok, note = validate_state_machine_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    # the three REQUIRED illegal cases (ship-from-placed, cancel-from-shipped, pick-from-placed)
    # are all present.
    assert {"action": "ship", "expect": "reject"} in drive
    assert {"action": "cancel", "expect": "reject"} in drive
    assert {"action": "pick", "expect": "reject"} in drive
    assert sum(1 for op in drive if op["expect"] == "reject") == 3
    assert spec["expect_final"] == "delivered"
# #EXT-060-REQ-65 End


# ================================================================================================
# #EXT-060-REQ-66 Start
# MARKETPLACE_ESCROW_TASK ("double_entry" oracle_kind)
# ================================================================================================

CORRECT_MARKETPLACE_ESCROW = """
    class MarketplaceEscrowLedger:
        def __init__(self):
            self._balances = {
                "buyer_wallet": 0, "escrow": 0, "seller_wallet": 0, "platform_fee": 0,
            }

        def buyer_wallet(self):
            return self._balances["buyer_wallet"]

        def escrow(self):
            return self._balances["escrow"]

        def seller_wallet(self):
            return self._balances["seller_wallet"]

        def platform_fee(self):
            return self._balances["platform_fee"]

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


def test_correct_marketplace_escrow_passes_the_double_entry_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_escrowtest_") as tmp:
        root = Path(tmp)
        _write(root, "marketplace_escrow_ledger.py", CORRECT_MARKETPLACE_ESCROW)
        accepted, note = grade_real_system_task(MARKETPLACE_ESCROW_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `post()` never checks that debits equal credits -- an unbalanced posting is silently
# applied instead of being rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_MARKETPLACE_ESCROW_ACCEPTS_UNBALANCED = """
    class MarketplaceEscrowLedger:
        def __init__(self):
            self._balances = {
                "buyer_wallet": 0, "escrow": 0, "seller_wallet": 0, "platform_fee": 0,
            }

        def buyer_wallet(self):
            return self._balances["buyer_wallet"]

        def escrow(self):
            return self._balances["escrow"]

        def seller_wallet(self):
            return self._balances["seller_wallet"]

        def platform_fee(self):
            return self._balances["platform_fee"]

        def post(self, legs):
            # BUG: never checks debits == credits -- posts unbalanced entries too.
            for leg in legs:
                if "debit" in leg:
                    self._balances[leg["account"]] += leg["debit"]
                else:
                    self._balances[leg["account"]] -= leg["credit"]
"""


def test_broken_marketplace_escrow_accepts_unbalanced_posting_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_escrowtest_") as tmp:
        root = Path(tmp)
        _write(root, "marketplace_escrow_ledger.py",
               BROKEN_MARKETPLACE_ESCROW_ACCEPTS_UNBALANCED)
        accepted, note = grade_real_system_task(MARKETPLACE_ESCROW_TASK, root, python_exe=PY)
        assert accepted is False


def test_marketplace_escrow_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(MARKETPLACE_ESCROW_TASK.sentence) is None
    assert MARKETPLACE_ESCROW_TASK in REAL_SYSTEMS_TASKS
    assert MARKETPLACE_ESCROW_TASK.oracle_kind == "double_entry"
    assert MARKETPLACE_ESCROW_TASK.cls == "marketplace"
    assert MARKETPLACE_ESCROW_TASK.name == "marketplace-escrow-double-entry-ledger"
    assert MARKETPLACE_ESCROW_TASK.oracle_spec["module"] == "marketplace_escrow_ledger"
    spec = MARKETPLACE_ESCROW_TASK.oracle_spec["spec"]
    ok, note = validate_double_entry_spec(spec)
    assert ok is True, note
    drive = spec["drive"]
    assert sum(1 for op in drive if op["expect"] == "reject") == 1
    assert spec["expect_final"] == {
        "buyer_wallet": -10000, "escrow": 0, "seller_wallet": 9000, "platform_fee": 1000,
    }
    # the double-entry invariant: every account final sums to exactly 0 across the whole ledger.
    assert sum(spec["expect_final"].values()) == 0
# #EXT-060-REQ-66 End


# ================================================================================================
# #EXT-060-REQ-67 Start
# SESSION_IDLE_TIMEOUT_TASK ("clock" oracle_kind)
# ================================================================================================

CORRECT_SESSION_IDLE_TIMEOUT = """
    class SessionStore:
        def __init__(self, idle_seconds, now_fn):
            self._idle_seconds = idle_seconds
            self._now_fn = now_fn
            self._last_activity = {}

        def touch(self, session_id):
            self._last_activity[session_id] = self._now_fn()

        def is_active(self, session_id):
            if session_id not in self._last_activity:
                return False
            elapsed = self._now_fn() - self._last_activity[session_id]
            return elapsed < self._idle_seconds
"""


def test_correct_session_idle_timeout_passes_the_clock_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_sessiontest_") as tmp:
        root = Path(tmp)
        _write(root, "session_idle_timeout.py", CORRECT_SESSION_IDLE_TIMEOUT)
        accepted, note = grade_real_system_task(SESSION_IDLE_TIMEOUT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses the REAL wall clock (`time.time()`) instead of the injected `now_fn` -- the driver
# never sleeps, so simulated seconds apart execute within real milliseconds of each other and the
# session never actually goes idle.
# ------------------------------------------------------------------------------------------------

BROKEN_SESSION_IDLE_TIMEOUT_USES_REAL_CLOCK = """
    import time

    class SessionStore:
        def __init__(self, idle_seconds, now_fn):
            self._idle_seconds = idle_seconds
            self._now_fn = now_fn
            self._last_activity = {}

        def touch(self, session_id):
            # BUG: uses the REAL wall clock instead of the injected now_fn.
            self._last_activity[session_id] = time.time()

        def is_active(self, session_id):
            if session_id not in self._last_activity:
                return False
            elapsed = time.time() - self._last_activity[session_id]
            return elapsed < self._idle_seconds
"""


def test_broken_session_idle_timeout_uses_real_clock_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_sessiontest_") as tmp:
        root = Path(tmp)
        _write(root, "session_idle_timeout.py", BROKEN_SESSION_IDLE_TIMEOUT_USES_REAL_CLOCK)
        accepted, note = grade_real_system_task(SESSION_IDLE_TIMEOUT_TASK, root, python_exe=PY)
        assert accepted is False


def test_session_idle_timeout_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SESSION_IDLE_TIMEOUT_TASK.sentence) is None
    assert SESSION_IDLE_TIMEOUT_TASK in REAL_SYSTEMS_TASKS
    assert SESSION_IDLE_TIMEOUT_TASK.oracle_kind == "clock"
    assert SESSION_IDLE_TIMEOUT_TASK.cls == "auth"
    assert SESSION_IDLE_TIMEOUT_TASK.name == "session-idle-timeout-lib"
    assert SESSION_IDLE_TIMEOUT_TASK.oracle_spec["module"] == "session_idle_timeout"
    spec = SESSION_IDLE_TIMEOUT_TASK.oracle_spec["spec"]
    ok, note = validate_clock_spec(spec)
    assert ok is True, note
    timeline = spec["timeline"]
    assert sum(1 for step in timeline if step["expect"] == {"returns": True}) == 3
    assert sum(1 for step in timeline if step["expect"] == {"returns": False}) == 3
    assert sum(1 for step in timeline if step["expect"] == {"returns": None}) == 2
    # the sentence pins the now_fn contract and the strict "<" boundary explicitly.
    assert "now_fn" in SESSION_IDLE_TIMEOUT_TASK.sentence
    assert "zero-argument callable" in SESSION_IDLE_TIMEOUT_TASK.sentence
    assert "STRICTLY LESS THAN" in SESSION_IDLE_TIMEOUT_TASK.sentence
# #EXT-060-REQ-67 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_batch7_tasks.py's own
# guard exactly).
# ------------------------------------------------------------------------------------------------

def test_no_new_batch8_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("lru", "least recently used", "priority queue", "priority-queue", "min-heap",
              "max-heap", "heapq", "ttl", "time-to-live", "time to live", "expire", "expiry",
              "expiration", "fifo", "first-in-first-out", "first in first out", "ring buffer",
              "ring-buffer", "circular buffer", "circular-buffer", "memoize", "cache", "stack",
              "queue", "hold", "buffer")
    for task in (DAG_TOPO_SORT_TASK, ORDER_FULFILLMENT_TASK, MARKETPLACE_ESCROW_TASK,
                 SESSION_IDLE_TIMEOUT_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_batch8_task_has_a_leaf_fingerprint():
    for task in (DAG_TOPO_SORT_TASK, ORDER_FULFILLMENT_TASK, MARKETPLACE_ESCROW_TASK,
                 SESSION_IDLE_TIMEOUT_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


def test_batch8_tasks_cover_import_state_machine_double_entry_clock_exactly_once():
    tasks = (DAG_TOPO_SORT_TASK, ORDER_FULFILLMENT_TASK, MARKETPLACE_ESCROW_TASK,
             SESSION_IDLE_TIMEOUT_TASK)
    kinds = {t.oracle_kind for t in tasks}
    assert kinds == {"import", "state_machine", "double_entry", "clock"}
    assert len(tasks) == 4
    verticals = {t.cls for t in tasks}
    assert len(verticals) == 4


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-64..67),
# one per oracle kind, in four new/reused genuinely real production verticals.
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_batch8_tasks():
    # bumped 50 -> 54: this module's own REQ-64/65/66/67 add four more CREATE tasks.
    assert len(REAL_SYSTEMS_TASKS) == 54
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "dag-topological-sort-lib" in names
    assert "order-fulfillment-state-machine" in names
    assert "marketplace-escrow-double-entry-ledger" in names
    assert "session-idle-timeout-lib" in names
    oracle_kinds = {
        "dag-topological-sort-lib": "import",
        "order-fulfillment-state-machine": "state_machine",
        "marketplace-escrow-double-entry-ledger": "double_entry",
        "session-idle-timeout-lib": "clock",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
