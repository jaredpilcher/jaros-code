"""EXT-036 REQ-49: offline tests for the deterministic tool-calling AGENT-LOOP SCAFFOLD repair
(`harness/agent_scaffold.py`) -- the direct analog of `tests/test_ext036_http_service_scaffold.py`
for REQ-48's `http.server` scaffold.

FULLY OFFLINE -- no real model/Jetson call anywhere. The KEY test reconstructs gemma's MEASURED
broken shapes (`.jaros-data/artifacts/realsys_agent.log`: zero tool calls made, or the wrong JSON
field extracted for a tool's arguments), applies `apply_agent_scaffold`, then DRIVES the repaired
agent through `harness.agent_oracle.drive_agent`/`check_agent` (the SAME scripted-stub-model +
controlled-tool-sandbox oracle a real build is graded by) and asserts it PASSES -- proving the
scaffold produces a genuinely WORKING tool-calling agent, not merely code that looks plausible.
"""

# #EXT-036-REQ-49 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from harness.agent_oracle import check_agent, drive_agent
from harness.agent_scaffold import (
    apply_agent_scaffold,
    generate_agent_skeleton,
    has_correct_agent_loop,
    spec_demands_tool_calling_agent,
)
from harness.real_systems_suite import PLAIN_AGENT_TASK

PY = sys.executable or "python"

_SPEC_TEXT = PLAIN_AGENT_TASK.sentence
_ORACLE_SPEC = PLAIN_AGENT_TASK.oracle_spec

_NOT_AGENT_SPEC_TEXT = (
    "Write a single-file Python program in a file named calc.py implementing a simple "
    "command-line calculator that adds two numbers given as arguments."
)

# --------------------------------------------------------------------------------------------
# MEASURED broken fixtures (`.jaros-data/artifacts/realsys_agent.log`, plain-tool-calling-agent
# 0/3): (a) zero tool calls ever made (2/3 builds), (b) the wrong JSON field extracted for a
# tool's arguments -- `tool_call_id`/`id` instead of `function.arguments` (1/3 builds).
# --------------------------------------------------------------------------------------------

_BROKEN_NO_TOOL_CALLS_PY = textwrap.dedent('''
    import os
    import sys


    def main():
        goal = sys.argv[1] if len(sys.argv) > 1 else ""
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        # BROKEN: never sends a single chat-completions request, never dispatches any tool --
        # just echoes the goal straight to the final sentinel.
        print("__JAROS_AGENT_FINAL__" + goal + "__END__", flush=True)


    if __name__ == "__main__":
        main()
''')

_BROKEN_WRONG_FIELD_PY = textwrap.dedent('''
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

        for _ in range(6):
            resp = _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            message = resp["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                call = tool_calls[0]
                # BROKEN: grabs the tool call's OWN id, never the parsed function arguments.
                args = {"tool_call_id": call.get("id")}
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                observed = _post(tool_url + "/" + call["function"]["name"], args)
                messages.append({
                    "role": "tool", "tool_call_id": call.get("id"),
                    "content": json.dumps(observed.get("observation")),
                })
                continue
            content = message.get("content") or ""
            print("__JAROS_AGENT_FINAL__" + content + "__END__", flush=True)
            return


    if __name__ == "__main__":
        main()
''')

_ALREADY_CORRECT_PY = textwrap.dedent('''
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
''')


def _drive_and_check(main_py_source: str):
    with tempfile.TemporaryDirectory(prefix="ext036_agentscaffold_") as tmp:
        root = Path(tmp)
        (root / _ORACLE_SPEC["entry"]).write_text(main_py_source, encoding="utf-8")
        result = drive_agent(
            root, _ORACLE_SPEC["entry"],
            script=_ORACLE_SPEC["script"], tools=_ORACLE_SPEC["tools"],
            goal=_ORACLE_SPEC["goal"], python_exe=PY,
        )
        return check_agent(
            result,
            expect_tool_calls=_ORACLE_SPEC["expect_tool_calls"],
            expect_final_contains=_ORACLE_SPEC["expect_final_contains"],
            expect_terminated=_ORACLE_SPEC["expect_terminated"],
        )


# --------------------------------------------------------------------------------------------
# (a) THE KEY TEST: the scaffold turns each MEASURED-broken shape into a genuinely PASSING agent.
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "broken_source",
    [_BROKEN_NO_TOOL_CALLS_PY, _BROKEN_WRONG_FIELD_PY],
    ids=["zero-tool-calls", "wrong-field-extracted"],
)
def test_scaffold_repairs_measured_broken_shapes_into_a_passing_agent(broken_source):
    modules = {"main.py": broken_source}
    repaired, notes = apply_agent_scaffold(modules, _SPEC_TEXT)

    assert "main.py" in repaired
    assert repaired["main.py"] != broken_source
    assert any("skeleton" in n for n in notes)
    # never mutates the caller's dict
    assert modules["main.py"] == broken_source

    ok, note = _drive_and_check(repaired["main.py"])
    assert ok, note


def test_scaffold_repairs_an_empty_build_into_a_passing_agent():
    # A build that produced no logic at all (e.g. an empty/whitespace-only entrypoint).
    modules = {"main.py": "# TODO\n"}
    repaired, notes = apply_agent_scaffold(modules, _SPEC_TEXT)
    assert any("skeleton" in n for n in notes)
    ok, note = _drive_and_check(repaired["main.py"])
    assert ok, note


# --------------------------------------------------------------------------------------------
# (b) non-degrading: no-op when a correct loop already exists / not an agent spec
# --------------------------------------------------------------------------------------------

def test_noop_when_a_correct_loop_already_exists():
    modules = {"main.py": _ALREADY_CORRECT_PY}
    repaired, notes = apply_agent_scaffold(modules, _SPEC_TEXT)
    assert repaired == modules
    assert any("already exists" in n for n in notes)


def test_generated_skeleton_is_itself_recognized_as_already_correct():
    # Idempotency: applying the scaffold to its OWN generated output must be a no-op.
    skeleton = generate_agent_skeleton()
    assert has_correct_agent_loop({"main.py": skeleton})
    modules = {"main.py": skeleton}
    repaired, notes = apply_agent_scaffold(modules, _SPEC_TEXT)
    assert repaired == modules
    assert any("already exists" in n for n in notes)


def test_noop_when_spec_is_not_a_tool_calling_agent():
    modules = {"calc.py": "def add(a, b):\n    return a + b\n"}
    repaired, notes = apply_agent_scaffold(modules, _NOT_AGENT_SPEC_TEXT)
    assert repaired == modules
    assert notes == []


def test_noop_when_modules_is_empty():
    repaired, notes = apply_agent_scaffold({}, _SPEC_TEXT)
    assert repaired == {}


# --------------------------------------------------------------------------------------------
# (c) detector unit checks
# --------------------------------------------------------------------------------------------

def test_spec_demands_tool_calling_agent_detector():
    assert spec_demands_tool_calling_agent(_SPEC_TEXT) is True
    assert spec_demands_tool_calling_agent(_NOT_AGENT_SPEC_TEXT) is False
    assert spec_demands_tool_calling_agent(None) is False
    assert spec_demands_tool_calling_agent("") is False


def test_has_correct_agent_loop_rejects_measured_broken_shapes():
    assert has_correct_agent_loop({"main.py": _BROKEN_NO_TOOL_CALLS_PY}) is False
    assert has_correct_agent_loop({"main.py": _BROKEN_WRONG_FIELD_PY}) is False
    assert has_correct_agent_loop({"main.py": _ALREADY_CORRECT_PY}) is True


# --------------------------------------------------------------------------------------------
# (d) NEVER RAISES on garbage input
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "modules, spec_text",
    [
        (None, None),
        (None, _SPEC_TEXT),
        ("not a dict", _SPEC_TEXT),
        (123, _SPEC_TEXT),
        ({"main.py": None}, _SPEC_TEXT),
        ({123: "print(1)"}, _SPEC_TEXT),
        ({"main.py": "def broken(:\n  pass"}, _SPEC_TEXT),  # unparseable source
        ({"main.py": "OPENAI_BASE_URL JAROS_TOOL_URL tool_calls"}, {"not": "a string"}),
        ({}, 12345),
    ],
)
def test_apply_agent_scaffold_never_raises_on_garbage(modules, spec_text):
    repaired, notes = apply_agent_scaffold(modules, spec_text)
    assert isinstance(repaired, dict)
    assert isinstance(notes, list)


def test_detectors_never_raise_on_garbage():
    assert spec_demands_tool_calling_agent(12345) is False
    assert spec_demands_tool_calling_agent(object()) is False
    assert has_correct_agent_loop(None) is False
    assert has_correct_agent_loop("not a dict") is False
    assert has_correct_agent_loop({None: None}) is False
# #EXT-036-REQ-49 End
