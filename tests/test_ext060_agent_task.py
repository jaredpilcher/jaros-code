"""EXT-060 TASK-9: offline tests for the first AGENT-shaped tasks on the canonical real-systems
scoreboard -- `oracle_kind="agent"` (REQ-11) + the plain-Python tool-calling CREATE task
(`PLAIN_AGENT_TASK`) and the step-guard MODIFY task (`AGENT_ADD_STEP_GUARD_MODIFY`, REQ-12).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every "agent" here is a small, hand-written
stdlib Python script written to a temp directory and driven against `harness.agent_oracle`'s own
SCRIPTED stub model + controlled tool sandbox (exactly what `grade_real_system_task` itself wires
for `oracle_kind="agent"`) -- never a live orchestrator/gemma run.
"""

# #EXT-060-REQ-11 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    AGENT_ADD_STEP_GUARD_MODIFY,
    PLAIN_AGENT_TASK,
    REAL_SYSTEMS_MODIFY_TASKS,
    REAL_SYSTEMS_TASKS,
    _AGENT_UNGUARDED_BASELINE_PY,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# (a) a CORRECT plain-Python agent fixture passes PLAIN_AGENT_TASK's oracle
# --------------------------------------------------------------------------------------------

CORRECT_PLAIN_AGENT = """
    import json
    import os
    import sys
    import urllib.request


    def _post(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1] if len(sys.argv) > 1 else ""
        base_url = os.environ["OPENAI_BASE_URL"]
        tool_url = os.environ["JAROS_TOOL_URL"]
        messages = [{"role": "user", "content": goal}]

        while True:
            resp = _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            message = resp["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                call = tool_calls[0]
                name = call["function"]["name"]
                args = json.loads(call["function"]["arguments"])
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                observed = _post(tool_url + "/" + name, args)
                messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps(observed.get("observation")),
                })
                continue
            content = message.get("content") or ""
            print("__JAROS_AGENT_FINAL__" + content + "__END__", flush=True)
            return


    if __name__ == "__main__":
        main()
"""


def test_correct_plain_agent_passes_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_agenttest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_PLAIN_AGENT)
        accepted, note = grade_real_system_task(PLAIN_AGENT_TASK, root, python_exe=PY)
        assert accepted is True, note


# --------------------------------------------------------------------------------------------
# (b) BROKEN fixtures (ignores the observation / never terminates / wrong tool) fail
# --------------------------------------------------------------------------------------------

# BROKEN: ignores whatever the scripted model actually says and always invokes a fixed, WRONG
# tool -- never the two tools (`list_files` then `read_file`) the stub instructs. Terminates
# cleanly (so `terminated` stays True), but the ORDERED tool-call sequence the oracle captured is
# wrong -- exactly the class of orchestration bug this oracle exists to catch.
BROKEN_WRONG_TOOL_AGENT = """
    import json
    import os
    import sys
    import urllib.request


    def _post(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1] if len(sys.argv) > 1 else ""
        base_url = os.environ["OPENAI_BASE_URL"]
        tool_url = os.environ["JAROS_TOOL_URL"]
        messages = [{"role": "user", "content": goal}]

        for _ in range(4):
            _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            # BROKEN: always calls the same wrong tool, never the one the model actually named.
            _post(tool_url + "/always_the_wrong_tool", {"oops": True})

        print("__JAROS_AGENT_FINAL__done (but wired wrong)__END__", flush=True)


    if __name__ == "__main__":
        main()
"""

# Never terminates: keeps calling chat/completions and a fixed tool, never checking for (or
# printing) a final answer at all.
NEVER_TERMINATES_AGENT = """
    import json
    import os
    import sys
    import urllib.request


    def _post(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1] if len(sys.argv) > 1 else ""
        base_url = os.environ["OPENAI_BASE_URL"]
        tool_url = os.environ["JAROS_TOOL_URL"]
        messages = [{"role": "user", "content": goal}]
        for _ in range(50):
            _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            _post(tool_url + "/list_files", {"path": "."})


    if __name__ == "__main__":
        main()
"""


def test_broken_wrong_tool_agent_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_agenttest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", BROKEN_WRONG_TOOL_AGENT)
        accepted, note = grade_real_system_task(PLAIN_AGENT_TASK, root, python_exe=PY)
        assert accepted is False


def test_never_terminating_agent_is_rejected_by_the_create_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_agenttest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", NEVER_TERMINATES_AGENT)
        accepted, note = grade_real_system_task(PLAIN_AGENT_TASK, root, python_exe=PY)
        assert accepted is False


# --------------------------------------------------------------------------------------------
# (c) leaves-OFF + roster membership
# --------------------------------------------------------------------------------------------

def test_plain_agent_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(PLAIN_AGENT_TASK.sentence) is None
    assert PLAIN_AGENT_TASK in REAL_SYSTEMS_TASKS
    assert PLAIN_AGENT_TASK.oracle_kind == "agent"
    assert PLAIN_AGENT_TASK.cls == "agent"
# #EXT-060-REQ-11 End


# #EXT-060-REQ-12 Start
# --------------------------------------------------------------------------------------------
# (d) the MODIFY task's oracle accepts a GUARDED agent, rejects the UNGUARDED baseline
# --------------------------------------------------------------------------------------------

# A correct post-modification agent: identical to the unguarded baseline, but tracks consecutive
# tool calls made without a final answer and stops itself (printing the pinned gave-up message)
# once that count reaches 3 -- exactly what AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence asks for.
CORRECT_GUARDED_AGENT = """
    import json
    import os
    import sys
    import urllib.request


    def _post(url, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


    def main():
        goal = sys.argv[1] if len(sys.argv) > 1 else ""
        base_url = os.environ["OPENAI_BASE_URL"]
        tool_url = os.environ["JAROS_TOOL_URL"]
        messages = [{"role": "user", "content": goal}]
        tool_calls_in_a_row = 0

        while True:
            resp = _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            message = resp["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                call = tool_calls[0]
                name = call["function"]["name"]
                args = json.loads(call["function"]["arguments"])
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                observed = _post(tool_url + "/" + name, args)
                messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps(observed.get("observation")),
                })
                tool_calls_in_a_row += 1
                if tool_calls_in_a_row >= 3:
                    print("__JAROS_AGENT_FINAL__gave up after 3 tool calls__END__", flush=True)
                    return
                continue
            tool_calls_in_a_row = 0
            content = message.get("content") or ""
            print("__JAROS_AGENT_FINAL__" + content + "__END__", flush=True)
            return


    if __name__ == "__main__":
        main()
"""


def test_correct_guarded_agent_passes_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_agentmodtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_GUARDED_AGENT)
        accepted, note = grade_real_system_task(AGENT_ADD_STEP_GUARD_MODIFY, root, python_exe=PY)
        assert accepted is True, note


def test_unguarded_baseline_agent_is_rejected_by_the_modify_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_agentmodtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", _AGENT_UNGUARDED_BASELINE_PY)
        accepted, note = grade_real_system_task(AGENT_ADD_STEP_GUARD_MODIFY, root, python_exe=PY)
        assert accepted is False


def test_agent_step_guard_modify_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence) is None
    assert AGENT_ADD_STEP_GUARD_MODIFY in REAL_SYSTEMS_MODIFY_TASKS
    assert AGENT_ADD_STEP_GUARD_MODIFY.oracle_kind == "agent"
    assert AGENT_ADD_STEP_GUARD_MODIFY.cls == "agent-modify"
    assert "main.py" in AGENT_ADD_STEP_GUARD_MODIFY.start_system
# #EXT-060-REQ-12 End
