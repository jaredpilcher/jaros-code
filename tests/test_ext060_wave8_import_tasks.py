"""EXT-060 TASK-43/TASK-44/TASK-45/TASK-46: offline tests for FOUR NEW real-systems CREATE tasks,
all graded by the SAME ALREADY-LANDED `oracle_kind="import"` dispatch (REQ-3's `_grade_import` ->
`harness.import_driver.drive_import`, NO new oracle code), spread across FOUR distinct verticals
(REQ-48/49/50/51):

- ``NPV_CALCULATOR_TASK`` (``cls="fintech"``): a Net Present Value calculator library.
- ``INTERVAL_MERGE_TASK`` (``cls="scheduling"``): an overlapping-closed-interval merger library.
- ``BASE32_CODEC_TASK`` (``cls="devtools"``): an RFC 4648 Base32 encode/decode codec library.
- ``HAVERSINE_DISTANCE_TASK`` (``cls="logistics"``): a great-circle haversine distance library.

Every hand-verified vector was independently recomputed against a reference implementation
(``math``/``base64`` stdlib) BEFORE being written into the task's ``oracle_spec`` -- see each
task's own definition in ``harness/real_systems_suite.py`` for the recompute notes.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_wave8_import_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    BASE32_CODEC_TASK,
    HAVERSINE_DISTANCE_TASK,
    INTERVAL_MERGE_TASK,
    NPV_CALCULATOR_TASK,
    REAL_SYSTEMS_TASKS,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-48 Start
# NPV_CALCULATOR_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_NPV = """
    def npv(rate, cashflows):
        total = 0.0
        for t, cf in enumerate(cashflows):
            total += cf / (1 + rate) ** t
        return round(total, 2)
"""


def test_correct_npv_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_npvtest_") as tmp:
        root = Path(tmp)
        _write(root, "npv.py", CORRECT_NPV)
        accepted, note = grade_real_system_task(NPV_CALCULATOR_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: discounts EVERY cashflow, including the `t=0` initial outlay (uses exponent `t + 1`
# instead of `t`) -- the classic "forgets t=0 is never discounted" NPV bug.
# ------------------------------------------------------------------------------------------------

BROKEN_NPV_DISCOUNTS_T0 = """
    def npv(rate, cashflows):
        # BUG: discounts every cashflow including t=0 (uses exponent t+1 for every entry).
        total = 0.0
        for t, cf in enumerate(cashflows):
            total += cf / (1 + rate) ** (t + 1)
        return round(total, 2)
"""


def test_broken_npv_discounts_t0_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_npvtest_") as tmp:
        root = Path(tmp)
        _write(root, "npv.py", BROKEN_NPV_DISCOUNTS_T0)
        accepted, note = grade_real_system_task(NPV_CALCULATOR_TASK, root, python_exe=PY)
        assert accepted is False


def test_npv_calculator_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(NPV_CALCULATOR_TASK.sentence) is None
    assert NPV_CALCULATOR_TASK in REAL_SYSTEMS_TASKS
    assert NPV_CALCULATOR_TASK.oracle_kind == "import"
    assert NPV_CALCULATOR_TASK.cls == "fintech"
    assert NPV_CALCULATOR_TASK.name == "net-present-value-calculator-lib"
    assert NPV_CALCULATOR_TASK.oracle_spec["module"] == "npv"
    checks = NPV_CALCULATOR_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "npv_multi_period", "expected": 243.43} in checks
    assert {"kind": "returns_equals", "call_id": "npv_zero_rate", "expected": 0.0} in checks
    assert {"kind": "returns_equals", "call_id": "npv_single_inflow", "expected": 100.0} in checks
# #EXT-060-REQ-48 End


# ================================================================================================
# #EXT-060-REQ-49 Start
# INTERVAL_MERGE_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_INTERVAL_MERGE = """
    def merge(intervals):
        if not intervals:
            return []
        ordered = sorted(intervals, key=lambda iv: iv[0])
        result = [list(ordered[0])]
        for start, end in ordered[1:]:
            last = result[-1]
            if start <= last[1]:
                last[1] = max(last[1], end)
            else:
                result.append([start, end])
        return result
"""


def test_correct_interval_merge_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_mergetest_") as tmp:
        root = Path(tmp)
        _write(root, "interval_merge.py", CORRECT_INTERVAL_MERGE)
        accepted, note = grade_real_system_task(INTERVAL_MERGE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses a STRICT `<` overlap test instead of `<=` -- two intervals that merely TOUCH
# (one's start equals the previous merged interval's end) are wrongly left unmerged.
# ------------------------------------------------------------------------------------------------

BROKEN_INTERVAL_MERGE_FAILS_ON_TOUCHING = """
    def merge(intervals):
        if not intervals:
            return []
        ordered = sorted(intervals, key=lambda iv: iv[0])
        result = [list(ordered[0])]
        for start, end in ordered[1:]:
            last = result[-1]
            # BUG: strict < drops the touching (equal-boundary) merge case.
            if start < last[1]:
                last[1] = max(last[1], end)
            else:
                result.append([start, end])
        return result
"""


def test_broken_interval_merge_fails_on_touching_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_mergetest_") as tmp:
        root = Path(tmp)
        _write(root, "interval_merge.py", BROKEN_INTERVAL_MERGE_FAILS_ON_TOUCHING)
        accepted, note = grade_real_system_task(INTERVAL_MERGE_TASK, root, python_exe=PY)
        assert accepted is False


def test_interval_merge_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(INTERVAL_MERGE_TASK.sentence) is None
    assert INTERVAL_MERGE_TASK in REAL_SYSTEMS_TASKS
    assert INTERVAL_MERGE_TASK.oracle_kind == "import"
    assert INTERVAL_MERGE_TASK.cls == "scheduling"
    assert INTERVAL_MERGE_TASK.name == "interval-merge-lib"
    assert INTERVAL_MERGE_TASK.oracle_spec["module"] == "interval_merge"
    checks = INTERVAL_MERGE_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "merge_overlap_and_gap",
            "expected": [[1, 6], [8, 10], [15, 18]]} in checks
    assert {"kind": "returns_equals", "call_id": "merge_touching", "expected": [[1, 5]]} in checks
    assert {"kind": "returns_equals", "call_id": "merge_empty", "expected": []} in checks
    assert {"kind": "returns_equals", "call_id": "merge_single_point",
            "expected": [[5, 5]]} in checks
# #EXT-060-REQ-49 End


# ================================================================================================
# #EXT-060-REQ-50 Start
# BASE32_CODEC_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_BASE32_CODEC = """
    import base64

    def encode(data):
        return base64.b32encode(bytes(data)).decode("ascii")

    def decode(s):
        return list(base64.b32decode(s.encode("ascii")))
"""


def test_correct_base32_codec_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_b32test_") as tmp:
        root = Path(tmp)
        _write(root, "base32_codec.py", CORRECT_BASE32_CODEC)
        accepted, note = grade_real_system_task(BASE32_CODEC_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: strips the standard `=` padding characters from `encode`'s output (and compensates in
# `decode`) -- violates the RFC 4648 contract's explicit padding requirement.
# ------------------------------------------------------------------------------------------------

BROKEN_BASE32_CODEC_NO_PADDING = """
    import base64

    def encode(data):
        # BUG: strips the standard = padding characters the contract requires.
        return base64.b32encode(bytes(data)).decode("ascii").rstrip("=")

    def decode(s):
        pad = (-len(s)) % 8
        return list(base64.b32decode((s + "=" * pad).encode("ascii")))
"""


def test_broken_base32_codec_no_padding_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_b32test_") as tmp:
        root = Path(tmp)
        _write(root, "base32_codec.py", BROKEN_BASE32_CODEC_NO_PADDING)
        accepted, note = grade_real_system_task(BASE32_CODEC_TASK, root, python_exe=PY)
        assert accepted is False


def test_base32_codec_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(BASE32_CODEC_TASK.sentence) is None
    assert BASE32_CODEC_TASK in REAL_SYSTEMS_TASKS
    assert BASE32_CODEC_TASK.oracle_kind == "import"
    assert BASE32_CODEC_TASK.cls == "devtools"
    assert BASE32_CODEC_TASK.name == "base32-codec-lib"
    assert BASE32_CODEC_TASK.oracle_spec["module"] == "base32_codec"
    checks = BASE32_CODEC_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "encode_empty", "expected": ""} in checks
    assert {"kind": "returns_equals", "call_id": "encode_f", "expected": "MY======"} in checks
    assert {"kind": "returns_equals", "call_id": "encode_foo", "expected": "MZXW6==="} in checks
    assert {"kind": "returns_equals", "call_id": "encode_foobar",
            "expected": "MZXW6YTBOI======"} in checks
    assert {"kind": "returns_equals", "call_id": "decode_f", "expected": [102]} in checks
    assert {"kind": "returns_equals", "call_id": "decode_foobar",
            "expected": [102, 111, 111, 98, 97, 114]} in checks
    assert {"kind": "returns_equals", "call_id": "decode_roundtrip_foobar",
            "expected": [102, 111, 111, 98, 97, 114]} in checks
# #EXT-060-REQ-50 End


# ================================================================================================
# #EXT-060-REQ-51 Start
# HAVERSINE_DISTANCE_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_HAVERSINE_DISTANCE = """
    import math

    def distance_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return round(R * c, 2)
"""


def test_correct_haversine_distance_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_havtest_") as tmp:
        root = Path(tmp)
        _write(root, "geo_distance.py", CORRECT_HAVERSINE_DISTANCE)
        accepted, note = grade_real_system_task(HAVERSINE_DISTANCE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: never converts degrees to radians before calling `math.sin`/`math.cos` -- the classic
# "forgot math.radians" haversine bug.
# ------------------------------------------------------------------------------------------------

BROKEN_HAVERSINE_DISTANCE_NO_RADIANS = """
    import math

    def distance_km(lat1, lon1, lat2, lon2):
        # BUG: forgets to convert degrees to radians before calling sin/cos.
        R = 6371.0
        phi1 = lat1
        phi2 = lat2
        dphi = lat2 - lat1
        dlambda = lon2 - lon1
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return round(R * c, 2)
"""


def test_broken_haversine_distance_no_radians_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_havtest_") as tmp:
        root = Path(tmp)
        _write(root, "geo_distance.py", BROKEN_HAVERSINE_DISTANCE_NO_RADIANS)
        accepted, note = grade_real_system_task(HAVERSINE_DISTANCE_TASK, root, python_exe=PY)
        assert accepted is False


def test_haversine_distance_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(HAVERSINE_DISTANCE_TASK.sentence) is None
    assert HAVERSINE_DISTANCE_TASK in REAL_SYSTEMS_TASKS
    assert HAVERSINE_DISTANCE_TASK.oracle_kind == "import"
    assert HAVERSINE_DISTANCE_TASK.cls == "logistics"
    assert HAVERSINE_DISTANCE_TASK.name == "haversine-distance-lib"
    assert HAVERSINE_DISTANCE_TASK.oracle_spec["module"] == "geo_distance"
    checks = HAVERSINE_DISTANCE_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "distance_same_point", "expected": 0.0} in checks
    assert {"kind": "returns_equals", "call_id": "distance_equator_quarter",
            "expected": 10007.54} in checks
    assert {"kind": "returns_equals", "call_id": "distance_warsaw_poznan",
            "expected": 278.46} in checks
# #EXT-060-REQ-51 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth (mirrors tests/test_ext060_atlas_batch4_tasks.py's own
# guard exactly).
# ------------------------------------------------------------------------------------------------

def test_no_new_wave8_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("lru", "least recently used", "priority queue", "priority-queue", "min-heap",
              "max-heap", "heapq", "ttl", "time-to-live", "time to live", "expire", "expiry",
              "expiration", "fifo", "first-in-first-out", "first in first out", "ring buffer",
              "ring-buffer", "circular buffer", "circular-buffer", "memoize", "cache", "stack",
              "queue")
    for task in (NPV_CALCULATOR_TASK, INTERVAL_MERGE_TASK, BASE32_CODEC_TASK,
                 HAVERSINE_DISTANCE_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


def test_no_new_wave8_task_has_a_leaf_fingerprint():
    for task in (NPV_CALCULATOR_TASK, INTERVAL_MERGE_TASK, BASE32_CODEC_TASK,
                 HAVERSINE_DISTANCE_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-48..51),
# all spread across the SAME already-landed "import" oracle in four distinct verticals.
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_wave8_tasks():
    # bumped 34 -> 38 -> 42 -> 46: this module's own REQ-48/49/50/51 add four more CREATE tasks,
    # then REQ-52..55 (tests/test_ext060_batch5_tasks.py) added four more, then REQ-56..59
    # (tests/test_ext060_batch6_tasks.py) added four more.
    assert len(REAL_SYSTEMS_TASKS) == 46
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "net-present-value-calculator-lib" in names
    assert "interval-merge-lib" in names
    assert "base32-codec-lib" in names
    assert "haversine-distance-lib" in names
    oracle_kinds = {
        "net-present-value-calculator-lib": "import",
        "interval-merge-lib": "import",
        "base32-codec-lib": "import",
        "haversine-distance-lib": "import",
    }
    by_name = {t.name: t for t in REAL_SYSTEMS_TASKS}
    for name, kind in oracle_kinds.items():
        assert by_name[name].oracle_kind == kind
