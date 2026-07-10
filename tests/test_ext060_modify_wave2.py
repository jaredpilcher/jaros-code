"""EXT-060 TASK-30/31/32/33/34: offline tests for the SECOND WAVE of MODIFY-half tasks (REQ-35
through REQ-39) -- five new `RealSystemModifyTask` entries, each reusing an ALREADY-VERIFIED
CREATE task's oracle dispatch verbatim (no new oracle code anywhere in this file): a FIFTH
LIFECYCLE-shaped modify (`HELPDESK_ADD_STATE_MODIFY`, "state_machine"), a SECOND payroll/tax
"import" modify (`TAX_ADD_CAP_MODIFY`), a SECOND elections "cli-exact" modify
(`IRV_ADD_TIE_RULE_MODIFY`), a SECOND web "service" modify (`SHORTENER_ADD_DELETE_MODIFY`), and a
SECOND auth "clock" modify (`LOCKOUT_ADMIN_UNLOCK_MODIFY`). Grows the MODIFY roster 6 -> 11.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every fixture module here is a small,
hand-written stdlib Python file written to a temp directory and driven directly against
`grade_real_system_task` (exactly the grading step `run_real_systems_modify_suite` performs
after a successful `applied=True` modification), never a live orchestrator/gemma run.

Per task, this file proves THREE things:
  (a) the task's `start_system` baseline ALONE -- run through its matching CREATE task's own
      oracle -- is accepted (proves the baseline is a genuinely correct implementation of the
      ORIGINAL contract, i.e. the REGRESSION checks hold for a fixture that has not been
      modified at all);
  (b) a hand-written CORRECT post-modification fixture is accepted by the new MODIFY task's own
      oracle (both the regression checks AND the new behavior hold);
  (c) at least one BROKEN fixture is rejected by the new MODIFY task's oracle -- covering both a
      fixture that never added the new behavior at all (the unmodified baseline itself, reused
      for this purpose exactly as REQ-14/REQ-16's own tests do) and a fixture that adds the new
      behavior but REGRESSES some piece of the original contract along the way.

Run in isolation: ``python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    HELPDESK_ADD_STATE_MODIFY,
    HELPDESK_SLA_TASK,
    IRV_ADD_TIE_RULE_MODIFY,
    IRV_TALLY_TASK,
    LOCKOUT_ADMIN_UNLOCK_MODIFY,
    LOCKOUT_BACKOFF_TASK,
    REAL_SYSTEMS_MODIFY_TASKS,
    REAL_SYSTEMS_TASKS,
    SHORTENER_ADD_DELETE_MODIFY,
    TAX_ADD_CAP_MODIFY,
    TAX_WITHHOLDING_TASK,
    URL_SHORTENER_TASK,
    _HELPDESK_SLA_BASELINE_PY,
    _IRV_TALLY_BASELINE_PY,
    _LOCKOUT_BACKOFF_BASELINE_PY,
    _TAX_WITHHOLDING_BASELINE_PY,
    _URL_SHORTENER_BASELINE_PY,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(source, encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-35 Start
# HELPDESK_ADD_STATE_MODIFY: add an on_hold state (hold()/release()) to the SLA-tiered helpdesk
# ticket state machine.
# ================================================================================================

def test_helpdesk_baseline_alone_passes_the_create_tasks_regression_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_helpdeskmod_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", _HELPDESK_SLA_BASELINE_PY)
        accepted, note = grade_real_system_task(HELPDESK_SLA_TASK, root, python_exe=PY)
        assert accepted is True, note


CORRECT_HELPDESK_WITH_ONHOLD = """class HelpdeskTicket:
    _TRANSITIONS = {
        ("new", "triage"): "triaged",
        ("triaged", "escalate"): "escalated",
        ("triaged", "resolve"): "resolved",
        ("escalated", "resolve"): "resolved",
        ("triaged", "wait_on_customer"): "waiting_customer",
        ("escalated", "wait_on_customer"): "waiting_customer",
        ("waiting_customer", "resume"): "triaged",
        ("resolved", "close"): "closed",
        ("closed", "reopen"): "new",
        ("triaged", "hold"): "on_hold",
        ("escalated", "hold"): "on_hold",
        ("on_hold", "release"): "triaged",
    }

    def __init__(self):
        self._state = "new"

    @property
    def state(self):
        return self._state

    def _transition(self, action):
        key = (self._state, action)
        if key not in self._TRANSITIONS:
            raise ValueError(f"illegal transition: {action} from {self._state}")
        self._state = self._TRANSITIONS[key]

    def triage(self):
        self._transition("triage")

    def escalate(self):
        self._transition("escalate")

    def resolve(self):
        self._transition("resolve")

    def wait_on_customer(self):
        self._transition("wait_on_customer")

    def resume(self):
        self._transition("resume")

    def close(self):
        self._transition("close")

    def reopen(self):
        self._transition("reopen")

    def hold(self):
        self._transition("hold")

    def release(self):
        self._transition("release")
"""


def test_correct_helpdesk_with_onhold_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_helpdeskmod_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", CORRECT_HELPDESK_WITH_ONHOLD)
        accepted, note = grade_real_system_task(HELPDESK_ADD_STATE_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_helpdesk_baseline_is_rejected_by_the_modify_task_oracle():
    # Lacks the new behavior entirely (no hold()/release()).
    with tempfile.TemporaryDirectory(prefix="ext060_helpdeskmod_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", _HELPDESK_SLA_BASELINE_PY)
        accepted, note = grade_real_system_task(HELPDESK_ADD_STATE_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: adds hold()/release() correctly, but ALSO regresses the ORIGINAL illegal
# close-from-triaged rejection (a "triaged" -> "close" -> "closed" transition sneaks in) --
# exactly the flagship "the modify accidentally breaks old behavior" bug this suite exists to
# catch.
BROKEN_HELPDESK_REGRESSES_CLOSE_GUARD = CORRECT_HELPDESK_WITH_ONHOLD.replace(
    '("resolved", "close"): "closed",',
    '("resolved", "close"): "closed",\n'
    '        ("triaged", "close"): "closed",  # BUG: regresses the original illegal-close guard',
)


def test_helpdesk_that_regresses_close_guard_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_helpdeskmod_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", BROKEN_HELPDESK_REGRESSES_CLOSE_GUARD)
        accepted, note = grade_real_system_task(HELPDESK_ADD_STATE_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_helpdesk_add_state_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(HELPDESK_ADD_STATE_MODIFY.mod_sentence) is None
    assert HELPDESK_ADD_STATE_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert HELPDESK_ADD_STATE_MODIFY.oracle_kind == "state_machine"
    assert HELPDESK_ADD_STATE_MODIFY.cls == "helpdesk-modify"
    assert "helpdesk.py" in HELPDESK_ADD_STATE_MODIFY.start_system
    assert HELPDESK_ADD_STATE_MODIFY.base_sentence == HELPDESK_SLA_TASK.sentence
# #EXT-060-REQ-35 End


# ================================================================================================
# #EXT-060-REQ-36 Start
# TAX_ADD_CAP_MODIFY: add an optional cap_cents kwarg to the progressive tax withholding library.
# ================================================================================================

def test_tax_baseline_alone_passes_the_create_tasks_regression_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_taxmod_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", _TAX_WITHHOLDING_BASELINE_PY)
        accepted, note = grade_real_system_task(TAX_WITHHOLDING_TASK, root, python_exe=PY)
        assert accepted is True, note


CORRECT_TAX_WITH_CAP = """def compute_withholding_cents(income_cents, brackets, cap_cents=None):
    total = 0
    lower = 0
    for upper, rate in brackets:
        if upper is None:
            portion = max(income_cents - lower, 0)
        else:
            portion = max(min(income_cents, upper) - lower, 0)
        total += (portion * rate) // 100
        if upper is not None:
            lower = upper
    if cap_cents is not None:
        total = min(total, cap_cents)
    return total
"""


def test_correct_tax_with_cap_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_taxmod_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", CORRECT_TAX_WITH_CAP)
        accepted, note = grade_real_system_task(TAX_ADD_CAP_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_tax_baseline_is_rejected_by_the_modify_task_oracle():
    # Lacks the new behavior entirely (no `cap_cents` parameter -> TypeError on the cap calls).
    with tempfile.TemporaryDirectory(prefix="ext060_taxmod_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", _TAX_WITHHOLDING_BASELINE_PY)
        accepted, note = grade_real_system_task(TAX_ADD_CAP_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: adds `cap_cents`, but with a WRONG nonzero default (1000) instead of `None` -- silently
# caps even the ORIGINAL uncapped calls, regressing REQ-26's own contract.
BROKEN_TAX_WRONG_DEFAULT_CAP = CORRECT_TAX_WITH_CAP.replace(
    "def compute_withholding_cents(income_cents, brackets, cap_cents=None):",
    "def compute_withholding_cents(income_cents, brackets, cap_cents=1000):"
    "  # BUG: regresses the uncapped default",
)


def test_tax_that_regresses_default_cap_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_taxmod_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", BROKEN_TAX_WRONG_DEFAULT_CAP)
        accepted, note = grade_real_system_task(TAX_ADD_CAP_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_tax_add_cap_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(TAX_ADD_CAP_MODIFY.mod_sentence) is None
    assert TAX_ADD_CAP_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert TAX_ADD_CAP_MODIFY.oracle_kind == "import"
    assert TAX_ADD_CAP_MODIFY.cls == "payroll-modify"
    assert "withholding.py" in TAX_ADD_CAP_MODIFY.start_system
    assert TAX_ADD_CAP_MODIFY.base_sentence == TAX_WITHHOLDING_TASK.sentence
# #EXT-060-REQ-36 End


# ================================================================================================
# #EXT-060-REQ-37 Start
# IRV_ADD_TIE_RULE_MODIFY: on a tie for fewest first-choice votes, eliminate the candidate LATER
# alphabetically.
# ================================================================================================

def test_irv_baseline_alone_passes_the_create_tasks_regression_oracle():
    # The baseline's own (different, earlier-alphabetically) tie-break is never exercised by
    # IRV_TALLY_TASK's own no-tie ballots, so it passes the ORIGINAL contract exactly.
    with tempfile.TemporaryDirectory(prefix="ext060_irvmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", _IRV_TALLY_BASELINE_PY)
        accepted, note = grade_real_system_task(IRV_TALLY_TASK, root, python_exe=PY)
        assert accepted is True, note


CORRECT_IRV_WITH_TIE_RULE = '''import sys
from collections import Counter


def main():
    ballots = []
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        ballots.append(line.split(","))

    candidates = set()
    for ballot in ballots:
        candidates.update(ballot)

    eliminated = set()
    round_num = 1
    while True:
        counts = Counter()
        for candidate in candidates - eliminated:
            counts[candidate] = 0
        for ballot in ballots:
            for name in ballot:
                if name not in eliminated:
                    counts[name] += 1
                    break

        remaining = sorted(counts.keys())
        line = ", ".join(f"{name}={counts[name]}" for name in remaining)
        print(f"Round {round_num}: {line}")

        total = sum(counts.values())
        winner = None
        for name in remaining:
            if counts[name] * 2 > total:
                winner = name
                break
        if winner is not None:
            print(f"Winner: {winner}")
            return

        min_count = min(counts[name] for name in remaining)
        tied = [name for name in remaining if counts[name] == min_count]
        fewest = max(tied)
        eliminated.add(fewest)
        print(f"Eliminated: {fewest}")
        round_num += 1


if __name__ == "__main__":
    main()
'''


def test_correct_irv_with_tie_rule_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_irvmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_IRV_WITH_TIE_RULE)
        accepted, note = grade_real_system_task(IRV_ADD_TIE_RULE_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_irv_baseline_is_rejected_by_the_modify_task_oracle():
    # Lacks the new behavior: breaks the tie the WRONG way (alphabetically earlier), producing a
    # different (wrong) winner.
    with tempfile.TemporaryDirectory(prefix="ext060_irvmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", _IRV_TALLY_BASELINE_PY)
        accepted, note = grade_real_system_task(IRV_ADD_TIE_RULE_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: implements the new tie rule correctly, but ALSO regresses the ORIGINAL `Round <N>: ...`
# separator format (", " -> "; ").
BROKEN_IRV_REGRESSES_FORMAT = CORRECT_IRV_WITH_TIE_RULE.replace(
    'line = ", ".join(f"{name}={counts[name]}" for name in remaining)',
    'line = "; ".join(f"{name}={counts[name]}" for name in remaining)'
    '  # BUG: regresses the separator',
)


def test_irv_that_regresses_round_format_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_irvmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", BROKEN_IRV_REGRESSES_FORMAT)
        accepted, note = grade_real_system_task(IRV_ADD_TIE_RULE_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_irv_add_tie_rule_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(IRV_ADD_TIE_RULE_MODIFY.mod_sentence) is None
    assert IRV_ADD_TIE_RULE_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert IRV_ADD_TIE_RULE_MODIFY.oracle_kind == "cli-exact"
    assert IRV_ADD_TIE_RULE_MODIFY.cls == "elections-modify"
    assert "main.py" in IRV_ADD_TIE_RULE_MODIFY.start_system
    assert IRV_ADD_TIE_RULE_MODIFY.base_sentence == IRV_TALLY_TASK.sentence
# #EXT-060-REQ-37 End


# ================================================================================================
# #EXT-060-REQ-38 Start
# SHORTENER_ADD_DELETE_MODIFY: add DELETE /links/<code> -> 204 to the URL-shortener service.
# ================================================================================================

def test_shortener_baseline_alone_passes_the_create_tasks_regression_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_shortmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", _URL_SHORTENER_BASELINE_PY)
        accepted, note = grade_real_system_task(URL_SHORTENER_TASK, root, python_exe=PY)
        assert accepted is True, note


CORRECT_SHORTENER_WITH_DELETE = _URL_SHORTENER_BASELINE_PY.replace(
    "    def log_message(self, fmt, *args):\n"
    "        pass\n",
    "    def do_DELETE(self):\n"
    "        link_id = _link_id(urlparse(self.path).path, \"links\")\n"
    "        if link_id is None:\n"
    "            self.send_response(404)\n"
    "            self.end_headers()\n"
    "            return\n"
    "        cur = CONN.execute(\"DELETE FROM links WHERE id = ?\", (link_id,))\n"
    "        CONN.commit()\n"
    "        if cur.rowcount == 0:\n"
    "            self.send_response(404)\n"
    "            self.end_headers()\n"
    "        else:\n"
    "            self.send_response(204)\n"
    "            self.end_headers()\n"
    "\n"
    "    def log_message(self, fmt, *args):\n"
    "        pass\n",
)

# Guard the fixture-authoring itself: the string-replace above must have actually landed a
# do_DELETE method (a silently no-op replace would otherwise make this whole fixture identical
# to the baseline, which would make the "correct" test below pass for the wrong reason).
assert "def do_DELETE" in CORRECT_SHORTENER_WITH_DELETE


def test_correct_shortener_with_delete_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_shortmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_SHORTENER_WITH_DELETE)
        accepted, note = grade_real_system_task(SHORTENER_ADD_DELETE_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_shortener_baseline_is_rejected_by_the_modify_task_oracle():
    # Lacks the new behavior entirely -- BaseHTTPRequestHandler with no do_DELETE responds 501.
    with tempfile.TemporaryDirectory(prefix="ext060_shortmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", _URL_SHORTENER_BASELINE_PY)
        accepted, note = grade_real_system_task(SHORTENER_ADD_DELETE_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: implements DELETE, but with NO `WHERE id = ?` clause -- wipes every row instead of just
# the targeted one, regressing the persistence the independent db assertion depends on.
BROKEN_SHORTENER_DELETE_WIPES_ALL = CORRECT_SHORTENER_WITH_DELETE.replace(
    'cur = CONN.execute("DELETE FROM links WHERE id = ?", (link_id,))',
    'cur = CONN.execute("DELETE FROM links")  # BUG: regresses persistence -- wipes every row',
)


def test_shortener_that_wipes_all_rows_on_delete_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_shortmod_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", BROKEN_SHORTENER_DELETE_WIPES_ALL)
        accepted, note = grade_real_system_task(SHORTENER_ADD_DELETE_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_shortener_add_delete_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(SHORTENER_ADD_DELETE_MODIFY.mod_sentence) is None
    assert SHORTENER_ADD_DELETE_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert SHORTENER_ADD_DELETE_MODIFY.oracle_kind == "service"
    assert SHORTENER_ADD_DELETE_MODIFY.cls == "web-modify"
    assert "main.py" in SHORTENER_ADD_DELETE_MODIFY.start_system
    assert SHORTENER_ADD_DELETE_MODIFY.base_sentence == URL_SHORTENER_TASK.sentence
# #EXT-060-REQ-38 End


# ================================================================================================
# #EXT-060-REQ-39 Start
# LOCKOUT_ADMIN_UNLOCK_MODIFY: add admin_unlock() clearing an active lock immediately.
# ================================================================================================

def test_lockout_baseline_alone_passes_the_create_tasks_regression_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lockoutmod_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", _LOCKOUT_BACKOFF_BASELINE_PY)
        accepted, note = grade_real_system_task(LOCKOUT_BACKOFF_TASK, root, python_exe=PY)
        assert accepted is True, note


CORRECT_LOCKOUT_WITH_ADMIN_UNLOCK = _LOCKOUT_BACKOFF_BASELINE_PY + (
    "\n"
    "    def admin_unlock(self):\n"
    "        self._locked_until = None\n"
)


def test_correct_lockout_with_admin_unlock_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lockoutmod_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", CORRECT_LOCKOUT_WITH_ADMIN_UNLOCK)
        accepted, note = grade_real_system_task(LOCKOUT_ADMIN_UNLOCK_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unmodified_lockout_baseline_is_rejected_by_the_modify_task_oracle():
    # Lacks the new behavior entirely (no admin_unlock() method at all -> AttributeError).
    with tempfile.TemporaryDirectory(prefix="ext060_lockoutmod_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", _LOCKOUT_BACKOFF_BASELINE_PY)
        accepted, note = grade_real_system_task(LOCKOUT_ADMIN_UNLOCK_MODIFY, root, python_exe=PY)
        assert accepted is False


# BROKEN: adds a genuinely-working admin_unlock(), but ALSO regresses the ORIGINAL 3-failure
# lock threshold (weakened to 4) -- the t=30 regression check (still locked from the t=20 third
# failure) now wrongly succeeds instead of raising LockedOut.
BROKEN_LOCKOUT_WRONG_THRESHOLD = CORRECT_LOCKOUT_WITH_ADMIN_UNLOCK.replace(
    "if self._streak_count >= 3:",
    "if self._streak_count >= 4:  # BUG: regresses the original 3-failure lock threshold",
)


def test_lockout_that_regresses_threshold_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lockoutmod_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", BROKEN_LOCKOUT_WRONG_THRESHOLD)
        accepted, note = grade_real_system_task(LOCKOUT_ADMIN_UNLOCK_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_lockout_admin_unlock_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(LOCKOUT_ADMIN_UNLOCK_MODIFY.mod_sentence) is None
    assert LOCKOUT_ADMIN_UNLOCK_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert LOCKOUT_ADMIN_UNLOCK_MODIFY.oracle_kind == "clock"
    assert LOCKOUT_ADMIN_UNLOCK_MODIFY.cls == "auth-modify"
    assert "lockout.py" in LOCKOUT_ADMIN_UNLOCK_MODIFY.start_system
    assert LOCKOUT_ADMIN_UNLOCK_MODIFY.base_sentence == LOCKOUT_BACKOFF_TASK.sentence
# #EXT-060-REQ-39 End


# ================================================================================================
# Roster-wide: the MODIFY half grew by exactly these five tasks (6 -> 11); the CREATE half is
# untouched by this file (still 26).
# ================================================================================================

def test_modify_roster_grew_by_exactly_five_tasks():
    assert len(REAL_SYSTEMS_TASKS) == 26
    assert len(REAL_SYSTEMS_MODIFY_TASKS) == 11
    names = {t.name for t in REAL_SYSTEMS_MODIFY_TASKS}
    assert {
        HELPDESK_ADD_STATE_MODIFY.name,
        TAX_ADD_CAP_MODIFY.name,
        IRV_ADD_TIE_RULE_MODIFY.name,
        SHORTENER_ADD_DELETE_MODIFY.name,
        LOCKOUT_ADMIN_UNLOCK_MODIFY.name,
    } <= names
