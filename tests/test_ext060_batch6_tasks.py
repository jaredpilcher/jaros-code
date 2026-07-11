"""EXT-060 TASK-51/TASK-52/TASK-53/TASK-54: offline tests for FOUR NEW real-systems CREATE tasks
("batch-6"), all graded by the SAME ALREADY-LANDED ``oracle_kind="import"`` dispatch (NO new
oracle code) across FOUR pure-function library classes (REQ-56/57/58/59):

- ``ROMAN_NUMERAL_CODEC_TASK`` (``cls="devtools"``): a classical Roman-numeral ``to_roman``/
  ``from_roman`` codec, graded by the ALREADY-LANDED ``harness.import_driver.drive_import``
  dispatch (REQ-3's ``_grade_import``, no new oracle code).
- ``BANKERS_ROUNDING_TASK`` (``cls="fintech"``): a ``round_half_even`` banker's-rounding
  primitive, graded by the SAME ALREADY-LANDED ``import`` dispatch. The rounding convention
  (round-half-TO-EVEN) is pinned exactly in both the task sentence and the oracle vectors, and
  every vector is chosen to be EXACT under IEEE-754 binary representation (2.5/3.5/0.5/1.5/
  0.125/0.375 -- never an ambiguous literal like 2.675) so the class is unambiguous.
- ``RUN_LENGTH_CODEC_TASK`` (``cls="data"``): a maximal-run ``encode``/``decode`` run-length
  codec, graded by the SAME ALREADY-LANDED ``import`` dispatch.
- ``PENNY_ALLOCATION_TASK`` (``cls="fintech"``): a cent-exact proportional-split ``allocate``
  primitive using integer floor division plus a pinned "give leftover cents to the FIRST parts"
  remainder rule, graded by the SAME ALREADY-LANDED ``import`` dispatch.

Every hand-verified vector was independently recomputed (a standalone scratch Python walk of the
exact same formula/algorithm each task's sentence pins) BEFORE being written into the task's
``oracle_spec`` -- see each task's own definition in ``harness/real_systems_suite.py`` for the
recompute notes.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_batch6_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    BANKERS_ROUNDING_TASK,
    PENNY_ALLOCATION_TASK,
    REAL_SYSTEMS_TASKS,
    ROMAN_NUMERAL_CODEC_TASK,
    RUN_LENGTH_CODEC_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-56 Start
# ROMAN_NUMERAL_CODEC_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_ROMAN_NUMERAL_CODEC = """
    _VALUES = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]

    def to_roman(n):
        out = []
        remaining = n
        for value, symbol in _VALUES:
            count, remaining = divmod(remaining, value)
            out.append(symbol * count)
        return "".join(out)

    _SYMBOL_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

    def from_roman(s):
        total = 0
        prev = 0
        for ch in reversed(s):
            value = _SYMBOL_VALUES[ch]
            if value < prev:
                total -= value
            else:
                total += value
                prev = value
        return total
"""


def test_correct_roman_numeral_codec_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_romantest_") as tmp:
        root = Path(tmp)
        _write(root, "roman_numeral_codec.py", CORRECT_ROMAN_NUMERAL_CODEC)
        accepted, note = grade_real_system_task(ROMAN_NUMERAL_CODEC_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses ADDITIVE-ONLY notation -- no subtractive pairs (CM/CD/XC/XL/IX/IV) are ever used,
# so e.g. to_roman(4) gives "IIII" instead of "IV".
# ------------------------------------------------------------------------------------------------

BROKEN_ROMAN_NUMERAL_CODEC_NO_SUBTRACTIVE_NOTATION = """
    # BUG: additive-only value table -- never uses a subtractive pair (CM/CD/XC/XL/IX/IV).
    _VALUES = [
        (1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I"),
    ]

    def to_roman(n):
        out = []
        remaining = n
        for value, symbol in _VALUES:
            count, remaining = divmod(remaining, value)
            out.append(symbol * count)
        return "".join(out)

    _SYMBOL_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

    def from_roman(s):
        total = 0
        prev = 0
        for ch in reversed(s):
            value = _SYMBOL_VALUES[ch]
            if value < prev:
                total -= value
            else:
                total += value
                prev = value
        return total
"""


def test_broken_roman_numeral_codec_no_subtractive_notation_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_romantest_") as tmp:
        root = Path(tmp)
        _write(root, "roman_numeral_codec.py",
               BROKEN_ROMAN_NUMERAL_CODEC_NO_SUBTRACTIVE_NOTATION)
        accepted, note = grade_real_system_task(ROMAN_NUMERAL_CODEC_TASK, root, python_exe=PY)
        assert accepted is False


def test_roman_numeral_codec_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(ROMAN_NUMERAL_CODEC_TASK.sentence) is None
    assert ROMAN_NUMERAL_CODEC_TASK in REAL_SYSTEMS_TASKS
    assert ROMAN_NUMERAL_CODEC_TASK.oracle_kind == "import"
    assert ROMAN_NUMERAL_CODEC_TASK.cls == "devtools"
    assert ROMAN_NUMERAL_CODEC_TASK.name == "roman-numeral-codec-lib"
    assert ROMAN_NUMERAL_CODEC_TASK.oracle_spec["module"] == "roman_numeral_codec"
    checks = ROMAN_NUMERAL_CODEC_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "to_roman_4", "expected": "IV"} in checks
    assert {"kind": "returns_equals", "call_id": "to_roman_9", "expected": "IX"} in checks
    assert {"kind": "returns_equals", "call_id": "to_roman_58", "expected": "LVIII"} in checks
    assert {"kind": "returns_equals", "call_id": "to_roman_1994",
            "expected": "MCMXCIV"} in checks
    assert {"kind": "returns_equals", "call_id": "to_roman_3999",
            "expected": "MMMCMXCIX"} in checks
    assert {"kind": "returns_equals", "call_id": "from_roman_1994", "expected": 1994} in checks
    assert {"kind": "returns_equals", "call_id": "from_roman_roundtrip_444",
            "expected": 444} in checks
# #EXT-060-REQ-56 End


# ================================================================================================
# #EXT-060-REQ-57 Start
# BANKERS_ROUNDING_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_BANKERS_ROUNDING = """
    import decimal

    def round_half_even(x, ndigits=0):
        d = decimal.Decimal(str(x))
        if ndigits == 0:
            quantum = decimal.Decimal("1")
        else:
            quantum = decimal.Decimal("1").scaleb(-ndigits)
        result = d.quantize(quantum, rounding=decimal.ROUND_HALF_EVEN)
        if ndigits == 0:
            return int(result)
        return float(result)
"""


def test_correct_bankers_rounding_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_bankerstest_") as tmp:
        root = Path(tmp)
        _write(root, "bankers_rounding.py", CORRECT_BANKERS_ROUNDING)
        accepted, note = grade_real_system_task(BANKERS_ROUNDING_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses round-HALF-UP (always away from zero) instead of round-half-to-EVEN.
# ------------------------------------------------------------------------------------------------

BROKEN_BANKERS_ROUNDING_USES_HALF_UP = """
    import decimal

    def round_half_even(x, ndigits=0):
        # BUG: rounds half-UP (always away from zero) instead of half-to-EVEN.
        d = decimal.Decimal(str(x))
        if ndigits == 0:
            quantum = decimal.Decimal("1")
        else:
            quantum = decimal.Decimal("1").scaleb(-ndigits)
        result = d.quantize(quantum, rounding=decimal.ROUND_HALF_UP)
        if ndigits == 0:
            return int(result)
        return float(result)
"""


def test_broken_bankers_rounding_uses_half_up_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_bankerstest_") as tmp:
        root = Path(tmp)
        _write(root, "bankers_rounding.py", BROKEN_BANKERS_ROUNDING_USES_HALF_UP)
        accepted, note = grade_real_system_task(BANKERS_ROUNDING_TASK, root, python_exe=PY)
        assert accepted is False


def test_bankers_rounding_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(BANKERS_ROUNDING_TASK.sentence) is None
    assert BANKERS_ROUNDING_TASK in REAL_SYSTEMS_TASKS
    assert BANKERS_ROUNDING_TASK.oracle_kind == "import"
    assert BANKERS_ROUNDING_TASK.cls == "fintech"
    assert BANKERS_ROUNDING_TASK.name == "bankers-rounding-lib"
    assert BANKERS_ROUNDING_TASK.oracle_spec["module"] == "bankers_rounding"
    checks = BANKERS_ROUNDING_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "round_2_5", "expected": 2} in checks
    assert {"kind": "returns_equals", "call_id": "round_3_5", "expected": 4} in checks
    assert {"kind": "returns_equals", "call_id": "round_0_5", "expected": 0} in checks
    assert {"kind": "returns_equals", "call_id": "round_1_5", "expected": 2} in checks
    assert {"kind": "returns_equals", "call_id": "round_0_125_2", "expected": 0.12} in checks
    assert {"kind": "returns_equals", "call_id": "round_0_375_2", "expected": 0.38} in checks
# #EXT-060-REQ-57 End


# ================================================================================================
# #EXT-060-REQ-58 Start
# RUN_LENGTH_CODEC_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_RUN_LENGTH_CODEC = """
    def encode(s):
        if not s:
            return []
        result = []
        prev = s[0]
        count = 1
        for ch in s[1:]:
            if ch == prev:
                count += 1
            else:
                result.append([prev, count])
                prev = ch
                count = 1
        result.append([prev, count])
        return result

    def decode(pairs):
        out = []
        for ch, count in pairs:
            out.append(ch * count)
        return "".join(out)
"""


def test_correct_run_length_codec_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_rletest_") as tmp:
        root = Path(tmp)
        _write(root, "run_length_codec.py", CORRECT_RUN_LENGTH_CODEC)
        accepted, note = grade_real_system_task(RUN_LENGTH_CODEC_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: forgets to flush the FINAL run after the scan loop ends -- the last run is silently
# dropped.
# ------------------------------------------------------------------------------------------------

BROKEN_RUN_LENGTH_CODEC_DROPS_FINAL_RUN = """
    def encode(s):
        if not s:
            return []
        result = []
        prev = s[0]
        count = 1
        for ch in s[1:]:
            if ch == prev:
                count += 1
            else:
                result.append([prev, count])
                prev = ch
                count = 1
        # BUG: never flushes the final run -- it is silently dropped.
        return result

    def decode(pairs):
        out = []
        for ch, count in pairs:
            out.append(ch * count)
        return "".join(out)
"""


def test_broken_run_length_codec_drops_final_run_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_rletest_") as tmp:
        root = Path(tmp)
        _write(root, "run_length_codec.py", BROKEN_RUN_LENGTH_CODEC_DROPS_FINAL_RUN)
        accepted, note = grade_real_system_task(RUN_LENGTH_CODEC_TASK, root, python_exe=PY)
        assert accepted is False


def test_run_length_codec_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(RUN_LENGTH_CODEC_TASK.sentence) is None
    assert RUN_LENGTH_CODEC_TASK in REAL_SYSTEMS_TASKS
    assert RUN_LENGTH_CODEC_TASK.oracle_kind == "import"
    assert RUN_LENGTH_CODEC_TASK.cls == "data"
    assert RUN_LENGTH_CODEC_TASK.name == "run-length-codec-lib"
    assert RUN_LENGTH_CODEC_TASK.oracle_spec["module"] == "run_length_codec"
    checks = RUN_LENGTH_CODEC_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "encode_mixed",
            "expected": [["a", 3], ["b", 2], ["c", 1]]} in checks
    assert {"kind": "returns_equals", "call_id": "encode_empty", "expected": []} in checks
    assert {"kind": "returns_equals", "call_id": "encode_single_run",
            "expected": [["a", 4]]} in checks
    assert {"kind": "returns_equals", "call_id": "decode_mixed",
            "expected": "aaabbc"} in checks
    assert {"kind": "returns_equals", "call_id": "decode_roundtrip_mixed",
            "expected": "aaabbc"} in checks
# #EXT-060-REQ-58 End


# ================================================================================================
# #EXT-060-REQ-59 Start
# PENNY_ALLOCATION_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_PENNY_ALLOCATION = """
    def allocate(total_cents, weights):
        total_weight = sum(weights)
        shares = [(total_cents * w) // total_weight for w in weights]
        remainder = total_cents - sum(shares)
        for i in range(remainder):
            shares[i] += 1
        return shares
"""


def test_correct_penny_allocation_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_pennytest_") as tmp:
        root = Path(tmp)
        _write(root, "penny_allocation.py", CORRECT_PENNY_ALLOCATION)
        accepted, note = grade_real_system_task(PENNY_ALLOCATION_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: computes the base floor shares but never redistributes the leftover remainder -- the
# returned parts LOSE cents (their sum falls short of `total_cents`).
# ------------------------------------------------------------------------------------------------

BROKEN_PENNY_ALLOCATION_LOSES_REMAINDER_CENTS = """
    def allocate(total_cents, weights):
        total_weight = sum(weights)
        # BUG: never redistributes the leftover remainder -- the parts lose cents.
        shares = [(total_cents * w) // total_weight for w in weights]
        return shares
"""


def test_broken_penny_allocation_loses_remainder_cents_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_pennytest_") as tmp:
        root = Path(tmp)
        _write(root, "penny_allocation.py", BROKEN_PENNY_ALLOCATION_LOSES_REMAINDER_CENTS)
        accepted, note = grade_real_system_task(PENNY_ALLOCATION_TASK, root, python_exe=PY)
        assert accepted is False


def test_penny_allocation_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(PENNY_ALLOCATION_TASK.sentence) is None
    assert PENNY_ALLOCATION_TASK in REAL_SYSTEMS_TASKS
    assert PENNY_ALLOCATION_TASK.oracle_kind == "import"
    assert PENNY_ALLOCATION_TASK.cls == "fintech"
    assert PENNY_ALLOCATION_TASK.name == "penny-allocation-lib"
    assert PENNY_ALLOCATION_TASK.oracle_spec["module"] == "penny_allocation"
    checks = PENNY_ALLOCATION_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "allocate_equal_three",
            "expected": [34, 33, 33]} in checks
    assert {"kind": "returns_equals", "call_id": "allocate_equal_two",
            "expected": [50, 50]} in checks
    assert {"kind": "returns_equals", "call_id": "allocate_weighted",
            "expected": [700, 300]} in checks
    assert {"kind": "returns_equals", "call_id": "allocate_small_remainder",
            "expected": [2, 2, 1]} in checks
# #EXT-060-REQ-59 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_batch5_tasks.py's own
# guard exactly).
# ------------------------------------------------------------------------------------------------

def test_no_new_batch6_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("lru", "least recently used", "priority queue", "priority-queue", "min-heap",
              "max-heap", "heapq", "ttl", "time-to-live", "time to live", "expire", "expiry",
              "expiration", "fifo", "first-in-first-out", "first in first out", "ring buffer",
              "ring-buffer", "circular buffer", "circular-buffer", "memoize", "cache", "stack",
              "queue", "hold", "buffer")
    for task in (ROMAN_NUMERAL_CODEC_TASK, BANKERS_ROUNDING_TASK, RUN_LENGTH_CODEC_TASK,
                 PENNY_ALLOCATION_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_batch6_task_has_a_leaf_fingerprint():
    for task in (ROMAN_NUMERAL_CODEC_TASK, BANKERS_ROUNDING_TASK, RUN_LENGTH_CODEC_TASK,
                 PENNY_ALLOCATION_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


def test_no_new_batch6_task_has_a_non_import_oracle_kind():
    for task in (ROMAN_NUMERAL_CODEC_TASK, BANKERS_ROUNDING_TASK, RUN_LENGTH_CODEC_TASK,
                 PENNY_ALLOCATION_TASK):
        assert task.oracle_kind == "import", task.name


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-56..59),
# all on the SAME already-landed "import" oracle, in four pure-function library classes.
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_batch6_tasks():
    # bumped 42 -> 46: this module's own REQ-56/57/58/59 add four more CREATE tasks (then
    # REQ-60..63 in tests/test_ext060_batch7_tasks.py bumped it again, 46 -> 50, then REQ-64..67 in
    # tests/test_ext060_batch8_tasks.py bumped it again, 50 -> 54).
    assert len(REAL_SYSTEMS_TASKS) == 54
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "roman-numeral-codec-lib" in names
    assert "bankers-rounding-lib" in names
    assert "run-length-codec-lib" in names
    assert "penny-allocation-lib" in names
    oracle_kinds = {
        "roman-numeral-codec-lib": "import",
        "bankers-rounding-lib": "import",
        "run-length-codec-lib": "import",
        "penny-allocation-lib": "import",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
