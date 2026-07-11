"""EXT-060 TASK-19/TASK-20/TASK-21/TASK-22: offline tests for FOUR NEW real-systems CREATE tasks
pulled from the production-systems atlas's top impact x buildability lists, growing the canonical
scoreboard's roster into new verticals (REQ-24/25/26/27):

- ``HELPDESK_SLA_TASK`` (``oracle_kind="state_machine"``, ``cls="helpdesk"``): an SLA-tiered
  helpdesk ticket -- distinct from ``TICKET_WORKFLOW_TASK`` (REQ-20's plain support ticket) in
  that its defining behavior is SLA-tier ESCALATION -- graded by the ALREADY-LANDED
  ``harness.state_machine_oracle.grade_state_machine`` dispatch (REQ-13's
  ``_grade_state_machine``, no new oracle code).
- ``IRV_TALLY_TASK`` (``oracle_kind="cli-exact"``, ``cls="elections"``): an instant-runoff
  ranked-choice tally CLI, graded by the ALREADY-LANDED ``exact_stdout`` check-variant dispatch
  (REQ-4's ``_grade_cli_exact``, no new oracle code).
- ``TAX_WITHHOLDING_TASK`` (``oracle_kind="import"``, ``cls="payroll"``): a progressive
  bracket-withholding library, graded by the ALREADY-LANDED
  ``harness.import_driver.drive_import`` dispatch (REQ-3's ``_grade_import``, no new oracle
  code).
- ``COURT_DEADLINE_TASK`` (``oracle_kind="import"``, ``cls="legal"``): a court-filing deadline
  date-math library, graded by the SAME ALREADY-LANDED ``_grade_import`` dispatch.

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module here is a small, hand-written
stdlib Python fixture written to a temp directory and driven against the existing deterministic
oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a live
orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_atlas_wave1_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    COURT_DEADLINE_TASK,
    HELPDESK_SLA_TASK,
    IRV_TALLY_TASK,
    REAL_SYSTEMS_TASKS,
    TAX_WITHHOLDING_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-24 Start
# HELPDESK_SLA_TASK ("state_machine" oracle_kind)
# ================================================================================================

CORRECT_HELPDESK = """
    class HelpdeskTicket:
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

        def wait_on_customer(self):
            self._transition("wait_on_customer")

        def resume(self):
            self._transition("resume")

        def resolve(self):
            self._transition("resolve")

        def close(self):
            self._transition("close")

        def reopen(self):
            self._transition("reopen")
"""


def test_correct_helpdesk_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_helpdesktest_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", CORRECT_HELPDESK)
        accepted, note = grade_real_system_task(HELPDESK_SLA_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# a BROKEN fixture that allows escalate() from ANY state (including a brand-new, never-triaged
# ticket) is rejected -- the honesty core the state_machine oracle exists to catch.
# ------------------------------------------------------------------------------------------------

BROKEN_HELPDESK_UNGUARDED_ESCALATE = """
    class HelpdeskTicket:
        def __init__(self):
            self._state = "new"

        @property
        def state(self):
            return self._state

        def triage(self):
            self._state = "triaged"

        def escalate(self):
            # BUG: no state guard at all -- escalate() is legal from ANY state, including "new"
            # (which must be rejected per the task's contract: escalate() requires a prior
            # triage()).
            self._state = "escalated"

        def wait_on_customer(self):
            self._state = "waiting_customer"

        def resume(self):
            self._state = "triaged"

        def resolve(self):
            self._state = "resolved"

        def close(self):
            self._state = "closed"

        def reopen(self):
            self._state = "new"
"""


def test_broken_helpdesk_with_unguarded_escalate_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_helpdesktest_") as tmp:
        root = Path(tmp)
        _write(root, "helpdesk.py", BROKEN_HELPDESK_UNGUARDED_ESCALATE)
        accepted, note = grade_real_system_task(HELPDESK_SLA_TASK, root, python_exe=PY)
        assert accepted is False


def test_helpdesk_sla_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(HELPDESK_SLA_TASK.sentence) is None
    assert HELPDESK_SLA_TASK in REAL_SYSTEMS_TASKS
    assert HELPDESK_SLA_TASK.oracle_kind == "state_machine"
    assert HELPDESK_SLA_TASK.cls == "helpdesk"
    assert HELPDESK_SLA_TASK.name == "helpdesk-ticket-sla-state-machine"
    # distinct from the existing plain-ticket class: SLA/escalation is the defining behavior.
    assert "sla" in HELPDESK_SLA_TASK.sentence.lower()
    assert "escalat" in HELPDESK_SLA_TASK.sentence.lower()
# #EXT-060-REQ-24 End


# ================================================================================================
# #EXT-060-REQ-25 Start
# IRV_TALLY_TASK ("cli-exact" oracle_kind)
# ================================================================================================

CORRECT_IRV_TALLY_STUB = """
    import sys
    from collections import Counter


    def main():
        ballots = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            ballots.append(line.split(","))

        candidates = set()
        for ballot in ballots:
            candidates.update(ballot)
        eliminated = set()

        while True:
            counts = Counter()
            for ballot in ballots:
                for name in ballot:
                    if name in eliminated:
                        continue
                    counts[name] += 1
                    break

            remaining = sorted(candidates - eliminated)
            total = sum(counts.get(name, 0) for name in remaining)
            line = ", ".join(f"{name}={counts.get(name, 0)}" for name in remaining)
            print(f"Round {len(eliminated) + 1}: {line}")

            winner = None
            for name in remaining:
                if counts.get(name, 0) * 2 > total:
                    winner = name
                    break
            if winner is not None:
                print(f"Winner: {winner}")
                return

            loser = min(remaining, key=lambda name: counts.get(name, 0))
            eliminated.add(loser)
            print(f"Eliminated: {loser}")


    if __name__ == "__main__":
        main()
"""

# WRONG: declares the round-1 PLURALITY leader the winner outright (never transfers eliminated
# ballots to later preferences) -- a common non-IRV shortcut that gets this exact fixture wrong
# (declares A the winner instead of B).
WRONG_PLURALITY_ONLY_STUB = """
    import sys
    from collections import Counter


    def main():
        ballots = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            ballots.append(line.split(","))

        counts = Counter(ballot[0] for ballot in ballots)
        remaining = sorted(counts)
        line = ", ".join(f"{name}={counts[name]}" for name in remaining)
        print(f"Round 1: {line}")
        winner = max(remaining, key=lambda name: counts[name])
        print(f"Winner: {winner}")


    if __name__ == "__main__":
        main()
"""


def test_correct_irv_tally_stub_passes_the_cli_exact_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_irvtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_IRV_TALLY_STUB)
        accepted, note = grade_real_system_task(IRV_TALLY_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_plurality_only_irv_stub_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_irvtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_PLURALITY_ONLY_STUB)
        accepted, note = grade_real_system_task(IRV_TALLY_TASK, root, python_exe=PY)
        assert accepted is False


def test_irv_tally_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(IRV_TALLY_TASK.sentence) is None
    assert IRV_TALLY_TASK in REAL_SYSTEMS_TASKS
    assert IRV_TALLY_TASK.oracle_kind == "cli-exact"
    assert IRV_TALLY_TASK.cls == "elections"
    assert IRV_TALLY_TASK.name == "ranked-choice-irv-tally-cli"
    # the fixture proves real IRV transfer logic: the round-1 plurality leader (A, 10 votes)
    # must NOT be the winner (B, who only reaches a majority after C's votes transfer).
    expected = IRV_TALLY_TASK.oracle_spec["expected_stdout"]
    assert "Round 1: A=10, B=6, C=5" in expected
    assert "Eliminated: C" in expected
    assert "Winner: B" in expected
    assert "Winner: A" not in expected
# #EXT-060-REQ-25 End


# ================================================================================================
# #EXT-060-REQ-26 Start
# TAX_WITHHOLDING_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_WITHHOLDING = """
    def compute_withholding_cents(income_cents, brackets):
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
        return total
"""

# WRONG: off-by-one bracket boundary -- treats each bracket's ceiling as EXCLUSIVE
# (`upper - 1`) instead of inclusive, shortchanging every bracket's portion by up to 1 cent.
BROKEN_WITHHOLDING_OFF_BY_ONE_BOUNDARY = """
    def compute_withholding_cents(income_cents, brackets):
        total = 0
        lower = 0
        for upper, rate in brackets:
            if upper is None:
                portion = max(income_cents - lower, 0)
            else:
                # BUG: off-by-one -- the boundary itself is excluded from this bracket, so
                # income exactly at (or above) a bracket ceiling is shortchanged by 1 cent of
                # that bracket's portion.
                capped = upper - 1
                portion = max(min(income_cents, capped) - lower, 0)
            total += (portion * rate) // 100
            if upper is not None:
                lower = upper
        return total
"""


def test_correct_withholding_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_taxtest_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", CORRECT_WITHHOLDING)
        accepted, note = grade_real_system_task(TAX_WITHHOLDING_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_off_by_one_boundary_withholding_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_taxtest_") as tmp:
        root = Path(tmp)
        _write(root, "withholding.py", BROKEN_WITHHOLDING_OFF_BY_ONE_BOUNDARY)
        accepted, note = grade_real_system_task(TAX_WITHHOLDING_TASK, root, python_exe=PY)
        assert accepted is False


def test_tax_withholding_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(TAX_WITHHOLDING_TASK.sentence) is None
    assert TAX_WITHHOLDING_TASK in REAL_SYSTEMS_TASKS
    assert TAX_WITHHOLDING_TASK.oracle_kind == "import"
    assert TAX_WITHHOLDING_TASK.cls == "payroll"
    assert TAX_WITHHOLDING_TASK.name == "progressive-tax-withholding-lib"
    assert TAX_WITHHOLDING_TASK.oracle_spec["module"] == "withholding"
    checks = TAX_WITHHOLDING_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "zero", "expected": 0} in checks
    assert {"kind": "returns_equals", "call_id": "boundary", "expected": 10000} in checks
    assert {"kind": "returns_equals", "call_id": "mid", "expected": 35007} in checks
    assert {"kind": "returns_equals", "call_id": "top", "expected": 100000} in checks
# #EXT-060-REQ-26 End


# ================================================================================================
# #EXT-060-REQ-27 Start
# COURT_DEADLINE_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_DEADLINE = """
    import datetime


    def compute_deadline(trigger_date, day_count, counting_rule, holidays):
        holidays_set = set(holidays)
        start = datetime.date.fromisoformat(trigger_date)

        def is_court_day(d):
            return d.weekday() < 5 and d.isoformat() not in holidays_set

        if counting_rule == "calendar":
            raw = start + datetime.timedelta(days=day_count)
        elif counting_rule == "court":
            cur = start
            counted = 0
            while counted < day_count:
                cur = cur + datetime.timedelta(days=1)
                if is_court_day(cur):
                    counted += 1
            raw = cur
        else:
            raise ValueError(f"unknown counting_rule: {counting_rule!r}")

        while not is_court_day(raw):
            raw = raw + datetime.timedelta(days=1)
        return raw.isoformat()
"""

# WRONG: forgets to honor the `holidays` list at all -- only rolls forward across weekends, so
# any deadline that lands on (or counts through) an explicit holiday is computed incorrectly.
BROKEN_DEADLINE_FORGETS_HOLIDAY_ROLL = """
    import datetime


    def compute_deadline(trigger_date, day_count, counting_rule, holidays):
        # BUG: `holidays` is accepted but never consulted -- only weekends are honored.
        start = datetime.date.fromisoformat(trigger_date)

        def is_court_day(d):
            return d.weekday() < 5

        if counting_rule == "calendar":
            raw = start + datetime.timedelta(days=day_count)
        elif counting_rule == "court":
            cur = start
            counted = 0
            while counted < day_count:
                cur = cur + datetime.timedelta(days=1)
                if is_court_day(cur):
                    counted += 1
            raw = cur
        else:
            raise ValueError(f"unknown counting_rule: {counting_rule!r}")

        while not is_court_day(raw):
            raw = raw + datetime.timedelta(days=1)
        return raw.isoformat()
"""


def test_correct_deadline_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_deadlinetest_") as tmp:
        root = Path(tmp)
        _write(root, "deadline.py", CORRECT_DEADLINE)
        accepted, note = grade_real_system_task(COURT_DEADLINE_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_deadline_that_forgets_holiday_roll_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_deadlinetest_") as tmp:
        root = Path(tmp)
        _write(root, "deadline.py", BROKEN_DEADLINE_FORGETS_HOLIDAY_ROLL)
        accepted, note = grade_real_system_task(COURT_DEADLINE_TASK, root, python_exe=PY)
        assert accepted is False


def test_court_deadline_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(COURT_DEADLINE_TASK.sentence) is None
    assert COURT_DEADLINE_TASK in REAL_SYSTEMS_TASKS
    assert COURT_DEADLINE_TASK.oracle_kind == "import"
    assert COURT_DEADLINE_TASK.cls == "legal"
    assert COURT_DEADLINE_TASK.name == "court-deadline-date-math-lib"
    assert COURT_DEADLINE_TASK.oracle_spec["module"] == "deadline"
    checks = COURT_DEADLINE_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "sat_roll", "expected": "2027-01-04"} in checks
    assert {"kind": "returns_equals", "call_id": "court_skip", "expected": "2027-01-07"} in checks
    assert {
        "kind": "returns_equals", "call_id": "holiday_landing", "expected": "2027-01-07",
    } in checks
# #EXT-060-REQ-27 End


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-24/25/26/27).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_tasks():
    # bumped 19 -> 22 -> 26 -> 30 -> 34 -> 38: EXT-060 REQ-28/29/30 (tests/test_ext060_clock_agent_
    # tasks.py) added three more CREATE tasks after this module's own REQ-24..27 landed, then
    # REQ-31..34 (tests/test_ext060_atlas_wave2_tasks.py), REQ-40..43 (tests/test_ext060_atlas_
    # wave7_tasks.py), REQ-44..47 (tests/test_ext060_atlas_batch4_tasks.py), REQ-48..51
    # (tests/test_ext060_wave8_import_tasks.py), and REQ-52..55 (tests/test_ext060_batch5_tasks.py)
    # each added four more.
    assert len(REAL_SYSTEMS_TASKS) == 42
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "helpdesk-ticket-sla-state-machine" in names
    assert "ranked-choice-irv-tally-cli" in names
    assert "progressive-tax-withholding-lib" in names
    assert "court-deadline-date-math-lib" in names
