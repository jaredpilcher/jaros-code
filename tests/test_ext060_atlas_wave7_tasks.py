"""EXT-060 TASK-35/TASK-36/TASK-37/TASK-38: offline tests for FOUR NEW real-systems CREATE tasks
from the atlas's wave-7 engineering-blog-mining "gradable-today" shortlist (REQ-40/41/42/43):

- ``RECOVERY_POINT_TASK`` (``oracle_kind="import"``, ``cls="reliability"``): a Stripe-style
  recovery-point request executor, graded by the ALREADY-LANDED ``harness.import_driver.
  drive_import`` dispatch (REQ-3's ``_grade_import``, no new oracle code).
- ``PERMISSION_OVERWRITE_TASK`` (``oracle_kind="import"``, ``cls="authz"``): a Discord-style
  layered permission-overwrite resolver, graded by the SAME ALREADY-LANDED ``import`` dispatch
  (no new oracle code).
- ``BLENDED_OVERTIME_TASK`` (``oracle_kind="import"``, ``cls="payroll"``): an FLSA blended
  (weighted-average) overtime calculator, graded by the SAME ALREADY-LANDED ``import`` dispatch
  (no new oracle code).
- ``SMS_SEGMENT_TASK`` (``oracle_kind="import"``, ``cls="comms"``): a Twilio-style SMS
  segmentation calculator, graded by the SAME ALREADY-LANDED ``import`` dispatch (no new oracle
  code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_atlas_wave7_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    BLENDED_OVERTIME_TASK,
    PERMISSION_OVERWRITE_TASK,
    REAL_SYSTEMS_TASKS,
    RECOVERY_POINT_TASK,
    SMS_SEGMENT_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-40 Start
# RECOVERY_POINT_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_RECOVERY_POINT = """
    def replay_execution(steps, recovery_point):
        result = []
        for i, step in enumerate(steps):
            if i < recovery_point:
                if step["kind"] == "idempotent":
                    result.append(step["name"])
            else:
                result.append(step["name"])
        return result
"""


def test_correct_recovery_point_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_rptest_") as tmp:
        root = Path(tmp)
        _write(root, "recovery_point.py", CORRECT_RECOVERY_POINT)
        accepted, note = grade_real_system_task(RECOVERY_POINT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: reruns every step before the checkpoint regardless of idempotency -- a non-idempotent
# step is unsafely re-run instead of being skipped.
# ------------------------------------------------------------------------------------------------

BROKEN_RECOVERY_POINT_RERUNS_NON_IDEMPOTENT = """
    def replay_execution(steps, recovery_point):
        # BUG: ignores `kind` entirely -- reruns everything before the checkpoint, including
        # non-idempotent steps that must be skipped.
        return [step["name"] for step in steps]
"""


def test_broken_recovery_point_reruns_non_idempotent_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_rptest_") as tmp:
        root = Path(tmp)
        _write(root, "recovery_point.py", BROKEN_RECOVERY_POINT_RERUNS_NON_IDEMPOTENT)
        accepted, note = grade_real_system_task(RECOVERY_POINT_TASK, root, python_exe=PY)
        assert accepted is False


def test_recovery_point_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(RECOVERY_POINT_TASK.sentence) is None
    assert RECOVERY_POINT_TASK in REAL_SYSTEMS_TASKS
    assert RECOVERY_POINT_TASK.oracle_kind == "import"
    assert RECOVERY_POINT_TASK.cls == "reliability"
    assert RECOVERY_POINT_TASK.name == "reliability-recovery-point-executor-lib"
    assert RECOVERY_POINT_TASK.oracle_spec["module"] == "recovery_point"
    checks = RECOVERY_POINT_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "resume_from_zero",
            "expected": ["A", "B", "C"]} in checks
    assert {"kind": "returns_equals", "call_id": "resume_mid_skip",
            "expected": ["A", "C", "D", "E"]} in checks
    assert {"kind": "returns_equals", "call_id": "resume_at_end",
            "expected": ["A", "C", "D"]} in checks
# #EXT-060-REQ-40 End


# ================================================================================================
# #EXT-060-REQ-41 Start
# PERMISSION_OVERWRITE_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_PERMISSION_OVERWRITE = """
    def resolve_permissions(everyone_allow, everyone_deny, role_overwrites, member_allow,
                             member_deny):
        value = 0
        value = (value & ~everyone_deny) | everyone_allow
        role_deny = 0
        role_allow = 0
        for ov in role_overwrites:
            role_deny |= ov.get("deny", 0)
            role_allow |= ov.get("allow", 0)
        value = (value & ~role_deny) | role_allow
        value = (value & ~member_deny) | member_allow
        return value
"""


def test_correct_permission_overwrite_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_permtest_") as tmp:
        root = Path(tmp)
        _write(root, "permission_overwrite.py", CORRECT_PERMISSION_OVERWRITE)
        accepted, note = grade_real_system_task(PERMISSION_OVERWRITE_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: wrong precedence order -- the member-specific layer is applied BEFORE the role-overwrite
# layer, so a role can incorrectly override a member overwrite instead of the reverse.
# ------------------------------------------------------------------------------------------------

BROKEN_PERMISSION_OVERWRITE_WRONG_ORDER = """
    def resolve_permissions(everyone_allow, everyone_deny, role_overwrites, member_allow,
                             member_deny):
        # BUG: applies the member layer BEFORE the role layer -- wrong precedence order (role
        # ends up overriding member instead of the documented member-overrides-role order).
        value = 0
        value = (value & ~everyone_deny) | everyone_allow
        value = (value & ~member_deny) | member_allow
        role_deny = 0
        role_allow = 0
        for ov in role_overwrites:
            role_deny |= ov.get("deny", 0)
            role_allow |= ov.get("allow", 0)
        value = (value & ~role_deny) | role_allow
        return value
"""


def test_broken_permission_overwrite_wrong_precedence_order_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_permtest_") as tmp:
        root = Path(tmp)
        _write(root, "permission_overwrite.py", BROKEN_PERMISSION_OVERWRITE_WRONG_ORDER)
        accepted, note = grade_real_system_task(PERMISSION_OVERWRITE_TASK, root, python_exe=PY)
        assert accepted is False


def test_permission_overwrite_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(PERMISSION_OVERWRITE_TASK.sentence) is None
    assert PERMISSION_OVERWRITE_TASK in REAL_SYSTEMS_TASKS
    assert PERMISSION_OVERWRITE_TASK.oracle_kind == "import"
    assert PERMISSION_OVERWRITE_TASK.cls == "authz"
    assert PERMISSION_OVERWRITE_TASK.name == "discord-permission-overwrite-resolution-lib"
    assert PERMISSION_OVERWRITE_TASK.oracle_spec["module"] == "permission_overwrite"
    checks = PERMISSION_OVERWRITE_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "member_overrides_role_deny",
            "expected": 2} in checks
    assert {"kind": "returns_equals", "call_id": "role_overrides_everyone_deny",
            "expected": 1} in checks
    assert {"kind": "returns_equals", "call_id": "ungranted_permission_stays_denied",
            "expected": 3} in checks
# #EXT-060-REQ-41 End


# ================================================================================================
# #EXT-060-REQ-42 Start
# BLENDED_OVERTIME_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_BLENDED_OVERTIME = """
    import math


    def compute_blended_overtime_pay(entries):
        total_hours = sum(h for _, h in entries)
        total_straight = sum(r * h for r, h in entries)
        if total_hours <= 40:
            total = total_straight
        else:
            blended = total_straight / total_hours
            ot_hours = total_hours - 40
            premium = 0.5 * blended * ot_hours
            total = total_straight + premium
        return math.floor(total + 0.5)
"""


def test_correct_blended_overtime_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_ottest_") as tmp:
        root = Path(tmp)
        _write(root, "blended_overtime.py", CORRECT_BLENDED_OVERTIME)
        accepted, note = grade_real_system_task(BLENDED_OVERTIME_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: forgets to blend -- uses only the FIRST entry's rate for the overtime premium instead of
# the weighted-average blended rate across every entry.
# ------------------------------------------------------------------------------------------------

BROKEN_BLENDED_OVERTIME_NO_BLEND = """
    import math


    def compute_blended_overtime_pay(entries):
        total_hours = sum(h for _, h in entries)
        total_straight = sum(r * h for r, h in entries)
        if total_hours <= 40:
            return math.floor(total_straight + 0.5)
        # BUG: uses only the FIRST entry's rate instead of the blended (weighted-average) rate.
        rate = entries[0][0]
        ot_hours = total_hours - 40
        premium = 0.5 * rate * ot_hours
        total = total_straight + premium
        return math.floor(total + 0.5)
"""


def test_broken_blended_overtime_no_blend_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_ottest_") as tmp:
        root = Path(tmp)
        _write(root, "blended_overtime.py", BROKEN_BLENDED_OVERTIME_NO_BLEND)
        accepted, note = grade_real_system_task(BLENDED_OVERTIME_TASK, root, python_exe=PY)
        assert accepted is False


def test_blended_overtime_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(BLENDED_OVERTIME_TASK.sentence) is None
    assert BLENDED_OVERTIME_TASK in REAL_SYSTEMS_TASKS
    assert BLENDED_OVERTIME_TASK.oracle_kind == "import"
    assert BLENDED_OVERTIME_TASK.cls == "payroll"
    assert BLENDED_OVERTIME_TASK.name == "flsa-blended-overtime-calculator-lib"
    assert BLENDED_OVERTIME_TASK.oracle_spec["module"] == "blended_overtime"
    checks = BLENDED_OVERTIME_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "under_40_no_ot", "expected": 60000} in checks
    assert {"kind": "returns_equals", "call_id": "over_40_single_rate",
            "expected": 71250} in checks
    assert {"kind": "returns_equals", "call_id": "over_40_two_rates_blended",
            "expected": 73889} in checks
    assert {"kind": "returns_equals", "call_id": "exactly_40_boundary",
            "expected": 48000} in checks
# #EXT-060-REQ-42 End


# ================================================================================================
# #EXT-060-REQ-43 Start
# SMS_SEGMENT_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_SMS_SEGMENTS = """
    def segment_sms(message):
        def is_gsm(ch):
            return (0x20 <= ord(ch) <= 0x7E) or ord(ch) == 0x0A

        n = len(message)
        is_gsm7 = all(is_gsm(c) for c in message)
        if is_gsm7:
            single, concat = 160, 153
            encoding = "GSM-7"
        else:
            single, concat = 70, 67
            encoding = "UCS-2"
        if n <= single:
            segs = 1
        else:
            segs = -(-n // concat)
        return (encoding, segs, n)
"""


def test_correct_sms_segments_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_smstest_") as tmp:
        root = Path(tmp)
        _write(root, "sms_segments.py", CORRECT_SMS_SEGMENTS)
        accepted, note = grade_real_system_task(SMS_SEGMENT_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: uses the GSM-7 160/153 segment thresholds even for a UCS-2 message instead of the
# correct 70/67 thresholds.
# ------------------------------------------------------------------------------------------------

BROKEN_SMS_SEGMENTS_USES_GSM_THRESHOLD_FOR_UCS2 = """
    def segment_sms(message):
        def is_gsm(ch):
            return (0x20 <= ord(ch) <= 0x7E) or ord(ch) == 0x0A

        n = len(message)
        is_gsm7 = all(is_gsm(c) for c in message)
        encoding = "GSM-7" if is_gsm7 else "UCS-2"
        # BUG: always uses the GSM-7 160/153 thresholds, even for a UCS-2 message.
        if n <= 160:
            segs = 1
        else:
            segs = -(-n // 153)
        return (encoding, segs, n)
"""


def test_broken_sms_segments_uses_gsm_threshold_for_ucs2_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_smstest_") as tmp:
        root = Path(tmp)
        _write(root, "sms_segments.py", BROKEN_SMS_SEGMENTS_USES_GSM_THRESHOLD_FOR_UCS2)
        accepted, note = grade_real_system_task(SMS_SEGMENT_TASK, root, python_exe=PY)
        assert accepted is False


def test_sms_segment_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SMS_SEGMENT_TASK.sentence) is None
    assert SMS_SEGMENT_TASK in REAL_SYSTEMS_TASKS
    assert SMS_SEGMENT_TASK.oracle_kind == "import"
    assert SMS_SEGMENT_TASK.cls == "comms"
    assert SMS_SEGMENT_TASK.name == "sms-segmentation-calculator-lib"
    assert SMS_SEGMENT_TASK.oracle_spec["module"] == "sms_segments"
    checks = SMS_SEGMENT_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "gsm_160",
            "expected": ["GSM-7", 1, 160]} in checks
    assert {"kind": "returns_equals", "call_id": "gsm_161",
            "expected": ["GSM-7", 2, 161]} in checks
    assert {"kind": "returns_equals", "call_id": "ucs2_70",
            "expected": ["UCS-2", 1, 70]} in checks
    assert {"kind": "returns_equals", "call_id": "ucs2_71",
            "expected": ["UCS-2", 2, 71]} in checks
    assert {"kind": "returns_equals", "call_id": "empty_message",
            "expected": ["GSM-7", 1, 0]} in checks
# #EXT-060-REQ-43 End


# ------------------------------------------------------------------------------------------------
# leaves-OFF banned-keyword defense-in-depth: none of the four new sentences say anything that
# could false-positive against a verified leaf's contract keyword table (mirrors the equivalent
# guard in tests/test_ext060_atlas_wave2_tasks.py for TOKEN_VALIDITY_TASK).
# ------------------------------------------------------------------------------------------------

def test_no_new_wave7_task_sentence_contains_a_banned_leaf_keyword():
    banned = ("expire", "expiry", "expiration", "cache", "ttl", "queue", "stack",
              "ring buffer", "ring-buffer", "circular buffer", "circular-buffer", "memoize")
    for task in (RECOVERY_POINT_TASK, PERMISSION_OVERWRITE_TASK, BLENDED_OVERTIME_TASK,
                 SMS_SEGMENT_TASK):
        lowered = task.sentence.lower()
        for word in banned:
            assert word not in lowered, (task.name, word)


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-40..43).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_wave7_tasks():
    # bumped 26 -> 30 -> 34: this module's own REQ-40/41/42/43 add four more CREATE tasks, then
    # REQ-44..47 (tests/test_ext060_atlas_batch4_tasks.py) added four more.
    assert len(REAL_SYSTEMS_TASKS) == 34
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "reliability-recovery-point-executor-lib" in names
    assert "discord-permission-overwrite-resolution-lib" in names
    assert "flsa-blended-overtime-calculator-lib" in names
    assert "sms-segmentation-calculator-lib" in names


def test_no_new_wave7_task_has_a_leaf_fingerprint():
    for task in (RECOVERY_POINT_TASK, PERMISSION_OVERWRITE_TASK, BLENDED_OVERTIME_TASK,
                 SMS_SEGMENT_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name
