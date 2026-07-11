"""EXT-060 TASK-23/TASK-24/TASK-25: offline tests for THREE NEW real-systems CREATE tasks --
the FIRST injectable-clock-graded class plus the first two NEW agent/LLM-infrastructure classes
from the atlas's wave-5 research pass (REQ-28/29/30):

- ``LOCKOUT_BACKOFF_TASK`` (``oracle_kind="clock"``, ``cls="auth"``): an account login-attempt
  lockout/backoff policy -- the FIRST task on this scoreboard graded by the injectable-clock
  oracle (EXT-059 REQ-10's ``harness.clock_oracle.grade_clock``, wired here via the NEW
  ``_grade_clock`` dispatch, REQ-28's own change -- no reimplementation of the oracle itself).
- ``OUTPUT_PARSER_TASK`` (``oracle_kind="import"``, ``cls="agent-infra"``): an LLM-output parsing
  library, graded by the ALREADY-LANDED ``harness.import_driver.drive_import`` dispatch (REQ-3's
  ``_grade_import``, no new oracle code).
- ``VALIDATION_RETRY_TASK`` (``oracle_kind="agent"``, ``cls="agent-infra"``): a Pydantic-AI-shaped
  schema-validation-retry loop, graded by the ALREADY-LANDED
  ``harness.agent_oracle.drive_agent``/``check_agent`` dispatch (REQ-11's ``_grade_agent``, no new
  oracle code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module/program here is a small,
hand-written stdlib Python fixture written to a temp directory and driven against the existing
deterministic oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a
live orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_clock_agent_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.agent_oracle import drive_agent
from harness.clock_oracle import validate_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    LOCKOUT_BACKOFF_TASK,
    OUTPUT_PARSER_TASK,
    REAL_SYSTEMS_TASKS,
    VALIDATION_RETRY_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-28 Start
# LOCKOUT_BACKOFF_TASK ("clock" oracle_kind)
# ================================================================================================

CORRECT_LOCKOUT = """
    class LockedOut(Exception):
        pass


    class LoginAttemptTracker:
        def __init__(self, now_fn):
            self._now_fn = now_fn
            self._failures = 0
            self._streak_start = None
            self._locked_until = None

        def is_locked(self):
            if self._locked_until is None:
                return False
            return self._now_fn() < self._locked_until

        def record_attempt(self, success):
            now = self._now_fn()
            if self._locked_until is not None and now < self._locked_until:
                raise LockedOut("account is locked")
            if self._locked_until is not None and now >= self._locked_until:
                self._locked_until = None
                self._failures = 0
                self._streak_start = None
            if success:
                self._failures = 0
                self._streak_start = None
                return None
            if self._failures == 0 or (now - self._streak_start) > 300:
                self._failures = 1
                self._streak_start = now
            else:
                self._failures += 1
            if self._failures >= 3:
                self._locked_until = now + 600
            return None
"""


def test_correct_lockout_passes_the_clock_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_lockouttest_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", CORRECT_LOCKOUT)
        accepted, note = grade_real_system_task(LOCKOUT_BACKOFF_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# the FLAGSHIP dishonesty case: a build that accepts `now_fn` (so construction never raises) but
# secretly consults the REAL wall clock instead of calling it -- the whole timeline executes in
# real milliseconds, so this build cannot tell t=30 (still locked) apart from t=650 (620
# SIMULATED seconds later, unlocked) and must be rejected.
# ------------------------------------------------------------------------------------------------

BROKEN_LOCKOUT_REAL_TIME_CHEAT = """
    import time


    class LockedOut(Exception):
        pass


    class LoginAttemptTracker:
        def __init__(self, now_fn):
            # BUG: accepts now_fn (so construction looks compliant) but never calls it -- every
            # time decision below uses the REAL wall clock instead.
            self._now_fn = now_fn
            self._failures = 0
            self._streak_start = None
            self._locked_until = None

        def is_locked(self):
            if self._locked_until is None:
                return False
            return time.time() < self._locked_until

        def record_attempt(self, success):
            now = time.time()
            if self._locked_until is not None and now < self._locked_until:
                raise LockedOut("account is locked")
            if self._locked_until is not None and now >= self._locked_until:
                self._locked_until = None
                self._failures = 0
                self._streak_start = None
            if success:
                self._failures = 0
                self._streak_start = None
                return None
            if self._failures == 0 or (now - self._streak_start) > 300:
                self._failures = 1
                self._streak_start = now
            else:
                self._failures += 1
            if self._failures >= 3:
                self._locked_until = now + 600
            return None
"""


def test_broken_lockout_real_time_cheat_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_lockouttest_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", BROKEN_LOCKOUT_REAL_TIME_CHEAT)
        accepted, note = grade_real_system_task(LOCKOUT_BACKOFF_TASK, root, python_exe=PY)
        assert accepted is False


# ------------------------------------------------------------------------------------------------
# a SECOND, independent broken fixture: a build that never locks at all (no guard whatsoever).
# ------------------------------------------------------------------------------------------------

BROKEN_LOCKOUT_NO_LOCK_GUARD = """
    class LockedOut(Exception):
        pass


    class LoginAttemptTracker:
        def __init__(self, now_fn):
            self._now_fn = now_fn

        def is_locked(self):
            # BUG: never locks -- always reports unlocked.
            return False

        def record_attempt(self, success):
            # BUG: no failure-streak tracking, no lock, ever -- every attempt is accepted.
            return None
"""


def test_broken_lockout_no_lock_guard_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_lockouttest_") as tmp:
        root = Path(tmp)
        _write(root, "lockout.py", BROKEN_LOCKOUT_NO_LOCK_GUARD)
        accepted, note = grade_real_system_task(LOCKOUT_BACKOFF_TASK, root, python_exe=PY)
        assert accepted is False


def test_lockout_clock_spec_validates_and_task_is_leaves_off_and_a_roster_member():
    ok, note = validate_spec(LOCKOUT_BACKOFF_TASK.oracle_spec["spec"])
    assert (ok, note) == (True, "ok")
    assert leaf_for_spec(LOCKOUT_BACKOFF_TASK.sentence) is None
    assert LOCKOUT_BACKOFF_TASK in REAL_SYSTEMS_TASKS
    assert LOCKOUT_BACKOFF_TASK.oracle_kind == "clock"
    assert LOCKOUT_BACKOFF_TASK.cls == "auth"
    assert LOCKOUT_BACKOFF_TASK.name == "account-lockout-backoff-lib"
    # the sentence pins the now_fn contract explicitly.
    assert "now_fn" in LOCKOUT_BACKOFF_TASK.sentence
    assert "zero-argument callable" in LOCKOUT_BACKOFF_TASK.sentence
    # no leaf-fingerprinting token anywhere in the sentence (says the lock "clears"/is "no
    # longer locked", never "expires").
    lowered = LOCKOUT_BACKOFF_TASK.sentence.lower()
    for banned in ("expire", "cache", "ttl", "queue", "stack", "ring", "buffer", "memoize"):
        assert banned not in lowered, banned
# #EXT-060-REQ-28 End


# ================================================================================================
# #EXT-060-REQ-29 Start
# OUTPUT_PARSER_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_OUTPUT_PARSER = """
    import json


    def parse_json_block(text):
        lines = text.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "```json":
                start = i
                break
        if start is None:
            raise ValueError("no fenced json block found")
        end = None
        for j in range(start + 1, len(lines)):
            if lines[j].strip() == "```":
                end = j
                break
        if end is None:
            raise ValueError("unterminated fenced json block")
        inner = "\\n".join(lines[start + 1:end])
        return json.loads(inner)


    def parse_key_values(text):
        result = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
        return result


    def strip_fences(text):
        out = []
        for line in text.splitlines():
            if line.strip().startswith("```"):
                continue
            out.append(line)
        return "\\n".join(out)
"""


def test_correct_output_parser_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_parsertest_") as tmp:
        root = Path(tmp)
        _write(root, "output_parser.py", CORRECT_OUTPUT_PARSER)
        accepted, note = grade_real_system_task(OUTPUT_PARSER_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `parse_json_block` returns the WRONG nesting -- it silently re-wraps every top-level
# dict value into a `{"value": ...}` shell instead of preserving the nested structure as-is.
# ------------------------------------------------------------------------------------------------

BROKEN_OUTPUT_PARSER_WRONG_NESTING = """
    import json


    def parse_json_block(text):
        lines = text.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "```json":
                start = i
                break
        if start is None:
            raise ValueError("no fenced json block found")
        end = None
        for j in range(start + 1, len(lines)):
            if lines[j].strip() == "```":
                end = j
                break
        if end is None:
            raise ValueError("unterminated fenced json block")
        inner = "\\n".join(lines[start + 1:end])
        parsed = json.loads(inner)
        # BUG: corrupts the nested shape -- wraps every nested dict value in an extra "value" key
        # instead of preserving it as-is.
        fixed = {}
        for k, v in parsed.items():
            if isinstance(v, dict):
                fixed[k] = {"value": v}
            else:
                fixed[k] = v
        return fixed


    def parse_key_values(text):
        result = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
        return result


    def strip_fences(text):
        out = []
        for line in text.splitlines():
            if line.strip().startswith("```"):
                continue
            out.append(line)
        return "\\n".join(out)
"""


def test_broken_output_parser_wrong_nesting_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_parsertest_") as tmp:
        root = Path(tmp)
        _write(root, "output_parser.py", BROKEN_OUTPUT_PARSER_WRONG_NESTING)
        accepted, note = grade_real_system_task(OUTPUT_PARSER_TASK, root, python_exe=PY)
        assert accepted is False


def test_output_parser_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(OUTPUT_PARSER_TASK.sentence) is None
    assert OUTPUT_PARSER_TASK in REAL_SYSTEMS_TASKS
    assert OUTPUT_PARSER_TASK.oracle_kind == "import"
    assert OUTPUT_PARSER_TASK.cls == "agent-infra"
    assert OUTPUT_PARSER_TASK.name == "llm-output-parser-lib"
    assert OUTPUT_PARSER_TASK.oracle_spec["module"] == "output_parser"
    checks = OUTPUT_PARSER_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "json_ok",
            "expected": {"a": 1, "b": {"c": 2, "d": [1, 2, 3]}}} in checks
    assert {"kind": "raises", "call_id": "json_error", "exception": "ValueError"} in checks
    assert {"kind": "returns_equals", "call_id": "kv",
            "expected": {"Name": "Alice", "Age": "30", "Time": "10:30"}} in checks
    assert {"kind": "returns_equals", "call_id": "fences",
            "expected": "before\ncode_line_1\ncode_line_2\nafter"} in checks
# #EXT-060-REQ-29 End


# ================================================================================================
# #EXT-060-REQ-30 Start
# VALIDATION_RETRY_TASK ("agent" oracle_kind)
# ================================================================================================

CORRECT_VALIDATION_RETRY_AGENT = """
    import json
    import os
    import sys
    import urllib.request

    OPENAI_BASE_URL = os.environ["OPENAI_BASE_URL"]
    JAROS_TOOL_URL = os.environ["JAROS_TOOL_URL"]
    REQUIRED_KEYS = ("name", "email")


    def _post_json(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1]
        messages = [{"role": "user", "content": goal}]
        for attempt in range(2):
            response = _post_json(
                f"{OPENAI_BASE_URL}/chat/completions", {"model": "stub", "messages": messages})
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                print("__JAROS_AGENT_FINAL__no structured output produced__END__")
                return
            call = tool_calls[0]
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            messages.append({"role": "assistant", "tool_calls": message["tool_calls"]})
            result = _post_json(f"{JAROS_TOOL_URL}/{name}", args)
            observation = result.get("observation")
            messages.append({
                "role": "tool", "tool_call_id": call["id"], "content": json.dumps(observation),
            })
            missing = [k for k in REQUIRED_KEYS if k not in args]
            if not missing:
                print("__JAROS_AGENT_FINAL__" + json.dumps(args) + "__END__")
                return
            if attempt == 0:
                error = "Validation error: missing required field(s): " + ", ".join(missing)
                messages.append({"role": "user", "content": error})
                continue
            print("__JAROS_AGENT_FINAL__validation failed after retry__END__")
            return


    if __name__ == "__main__":
        main()
"""


def test_correct_validation_retry_agent_passes_the_agent_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_retrytest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_VALIDATION_RETRY_AGENT)
        accepted, note = grade_real_system_task(VALIDATION_RETRY_TASK, root, python_exe=PY)
        assert accepted is True, note


# also directly confirm the orchestration this task exists to prove: exactly 2 model calls (not
# a hollow 1-shot pass), driven straight through drive_agent (not just check_agent's summary).
def test_correct_validation_retry_agent_makes_exactly_two_model_calls():
    with tempfile.TemporaryDirectory(prefix="ext060_retrytest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_VALIDATION_RETRY_AGENT)
        spec = VALIDATION_RETRY_TASK.oracle_spec
        result = drive_agent(
            root, spec["entry"], script=spec["script"], tools=spec["tools"], goal=spec["goal"],
            python_exe=PY,
        )
        assert result["ok"] is True, result["note"]
        assert result["steps"] == 2
        assert [tc["name"] for tc in result["tool_calls"]] == ["submit_output", "submit_output"]


# ------------------------------------------------------------------------------------------------
# BROKEN: never retries on invalid -- finalizes immediately with the model's FIRST (invalid)
# structured-output attempt instead of sending the validation error back for a retry.
# ------------------------------------------------------------------------------------------------

BROKEN_VALIDATION_RETRY_NEVER_RETRIES = """
    import json
    import os
    import sys
    import urllib.request

    OPENAI_BASE_URL = os.environ["OPENAI_BASE_URL"]
    JAROS_TOOL_URL = os.environ["JAROS_TOOL_URL"]


    def _post_json(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1]
        messages = [{"role": "user", "content": goal}]
        response = _post_json(
            f"{OPENAI_BASE_URL}/chat/completions", {"model": "stub", "messages": messages})
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        call = tool_calls[0]
        name = call["function"]["name"]
        args = json.loads(call["function"]["arguments"])
        _post_json(f"{JAROS_TOOL_URL}/{name}", args)
        # BUG: never validates, never retries -- finalizes with whatever the FIRST attempt was,
        # even though it is missing the required "email" key.
        print("__JAROS_AGENT_FINAL__" + json.dumps(args) + "__END__")


    if __name__ == "__main__":
        main()
"""


def test_broken_validation_retry_never_retries_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_retrytest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", BROKEN_VALIDATION_RETRY_NEVER_RETRIES)
        accepted, note = grade_real_system_task(VALIDATION_RETRY_TASK, root, python_exe=PY)
        assert accepted is False


def test_validation_retry_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(VALIDATION_RETRY_TASK.sentence) is None
    assert VALIDATION_RETRY_TASK in REAL_SYSTEMS_TASKS
    assert VALIDATION_RETRY_TASK.oracle_kind == "agent"
    assert VALIDATION_RETRY_TASK.cls == "agent-infra"
    assert VALIDATION_RETRY_TASK.name == "schema-validation-retry-loop"
    assert len(VALIDATION_RETRY_TASK.oracle_spec["script"]) == 2
    assert len(VALIDATION_RETRY_TASK.oracle_spec["expect_tool_calls"]) == 2
# #EXT-060-REQ-30 End


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these three new tasks (REQ-28/29/30).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_three_new_tasks():
    # bumped 22 -> 26 -> 30 -> 34 -> 38 -> 42 -> 46 -> 50: EXT-060 REQ-31/32/33/34 (tests/test_ext060_
    # atlas_wave2_tasks.py), REQ-40/41/42/43 (tests/test_ext060_atlas_wave7_tasks.py),
    # REQ-44/45/46/47 (tests/test_ext060_atlas_batch4_tasks.py), REQ-48/49/50/51
    # (tests/test_ext060_wave8_import_tasks.py), REQ-52/53/54/55
    # (tests/test_ext060_batch5_tasks.py), REQ-56/57/58/59 (tests/test_ext060_batch6_tasks.py), and
    # REQ-60/61/62/63 (tests/test_ext060_batch7_tasks.py), and REQ-64/65/66/67
    # (tests/test_ext060_batch8_tasks.py) each added four more CREATE tasks after this module's own
    # REQ-28/29/30 landed.
    assert len(REAL_SYSTEMS_TASKS) == 54  # was 19 (REQ-24..27), +3 (REQ-28/29/30), +4 (REQ-31..34),
    # +4 (REQ-40..43), +4 (REQ-44..47), +4 (REQ-48..51), +4 (REQ-52..55), +4 (REQ-56..59),
    # +4 (REQ-60..63), +4 (REQ-64..67)
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "account-lockout-backoff-lib" in names
    assert "llm-output-parser-lib" in names
    assert "schema-validation-retry-loop" in names


def test_no_new_task_has_a_leaf_fingerprint():
    for task in (LOCKOUT_BACKOFF_TASK, OUTPUT_PARSER_TASK, VALIDATION_RETRY_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name
