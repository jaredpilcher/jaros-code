"""EXT-059 REQ-6: offline tests for the agent-loop oracle (`harness/agent_oracle.py`).

Every fixture here is a small, hand-written Python "agent" script written to a temp directory --
never a live orchestrator/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network beyond the oracle's OWN localhost stub server, no
model call anywhere: stdlib only on both sides. These tests are pure execution-plane verification
of a deterministic control-flow loop and must never reach the Jetson.
"""

# #EXT-059-REQ-6 Start
# TASK-4
from __future__ import annotations

import socket
import sys
import textwrap
import time
from pathlib import Path

from harness.agent_oracle import check_agent, drive_agent, final_turn, tool_call_turn

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


def _port_is_free(port: "int | None") -> bool:
    """True when NOTHING is listening on 127.0.0.1:port -- proves drive_agent tore its stub
    server down and left no orphaned listener behind."""
    if port is None:
        return True
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.close()
        return False  # something answered -- still listening
    except OSError:
        return True


# --------------------------------------------------------------------------------------------
# Fixture agents -- hand-written, plain stdlib Python. Each reads the pinned injection contract
# (OPENAI_BASE_URL / JAROS_TOOL_URL env vars, goal as argv[1]) and loops against the stub.
# --------------------------------------------------------------------------------------------

# A CORRECT agent: asks the stub model what to do, invokes whatever tool it is told to (via the
# controlled tool sandbox), feeds the tool's observation back into the conversation, and repeats
# until the stub returns a final answer -- then prints the pinned sentinel and exits 0. Works for
# ANY script length (0, 1, 2, ... tool calls then a final), which is what lets the SAME fixture
# drive both the "few steps" and "multi-step" tests below.
CORRECT_AGENT = """
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

        for _ in range(25):
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

        print("__JAROS_AGENT_FINAL__gave up after 25 steps__END__", flush=True)


    if __name__ == "__main__":
        main()
"""

# A BROKEN agent: ignores whatever the scripted model actually says and always invokes a fixed,
# WRONG tool -- never the one the stub instructed. Terminates cleanly (so `terminated` stays
# True), but the ORDERED tool-call sequence the oracle captured is wrong -- exactly the class of
# orchestration bug this oracle exists to catch, and one that no reasoning-only grader could see
# (the agent still produces "a" final answer, it just wired the wrong tool calls to get there).
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

# A CRASHING agent: exits non-zero immediately, never touching the stub at all.
CRASH_AGENT = """
    import sys
    sys.exit(3)
"""

# A HANGING agent: never contacts the stub and never exits -- exercises drive_agent's overall
# `timeout` + process-tree teardown path (the "never-binding" failure mode -- it never even binds
# to the stub, let alone terminates).
HANG_AGENT = """
    import time
    while True:
        time.sleep(0.05)
"""


# --------------------------------------------------------------------------------------------
# (a) a correct agent, few-step script -> check_agent passes
# --------------------------------------------------------------------------------------------

def test_correct_agent_passes_a_two_step_tool_then_final_script(tmp_path):
    _write(tmp_path, "agent.py", CORRECT_AGENT)
    script = [
        tool_call_turn("list_files", {"path": "."}),
        final_turn("here are your files"),
    ]
    result = drive_agent(
        tmp_path, "agent.py",
        script=script,
        tools={"list_files": {"names": ["a.txt", "b.txt"]}},
        goal="show me the files",
        python_exe=PY,
    )
    assert result["ok"] is True, result["note"]
    assert result["steps"] == 2
    ok, note = check_agent(
        result,
        expect_tool_calls=[{"name": "list_files", "args": {"path": "."}}],
        expect_final_contains="files",
        expect_terminated=True,
    )
    assert ok is True, note


def test_correct_agent_fails_check_agent_when_expectation_is_wrong(tmp_path):
    """The SAME correct run, graded against a WRONG expected sequence -- proves check_agent
    actually discriminates, not just rubber-stamps a passing drive_agent result."""
    _write(tmp_path, "agent.py", CORRECT_AGENT)
    script = [tool_call_turn("list_files", {"path": "."}), final_turn("here are your files")]
    result = drive_agent(tmp_path, "agent.py", script=script,
                          tools={"list_files": {"names": []}}, goal="go", python_exe=PY)
    assert result["ok"] is True, result["note"]
    ok, note = check_agent(
        result, expect_tool_calls=[{"name": "delete_everything"}], expect_terminated=True)
    assert ok is False
    assert "name mismatch" in note.lower()


# --------------------------------------------------------------------------------------------
# (b) a broken agent (calls the wrong tool) -> check_agent returns False
# --------------------------------------------------------------------------------------------

def test_broken_agent_wrong_tool_is_caught_by_check_agent(tmp_path):
    _write(tmp_path, "agent.py", BROKEN_WRONG_TOOL_AGENT)
    script = [
        tool_call_turn("list_files", {"path": "."}),
        tool_call_turn("read_file", {"path": "a.txt"}),
        final_turn("done"),
    ]
    result = drive_agent(
        tmp_path, "agent.py", script=script,
        tools={"list_files": {"names": ["a.txt"]}, "read_file": {"content": "hi"}},
        goal="read a.txt", max_steps=10, python_exe=PY,
    )
    # drive_agent itself just reports what happened, honestly -- it is check_agent's job to
    # decide pass/fail against the EXPECTED sequence.
    assert isinstance(result["tool_calls"], list)
    assert all(tc["name"] == "always_the_wrong_tool" for tc in result["tool_calls"])

    ok, note = check_agent(
        result,
        expect_tool_calls=[
            {"name": "list_files", "args": {"path": "."}},
            {"name": "read_file", "args": {"path": "a.txt"}},
        ],
        expect_final_contains="done",
        expect_terminated=True,
    )
    assert ok is False
    assert "name mismatch" in note.lower() or "count mismatch" in note.lower()


# --------------------------------------------------------------------------------------------
# (c) drive_agent never raises on a crashing / hanging agent, and leaves no orphaned stub server
# --------------------------------------------------------------------------------------------

def test_drive_agent_never_raises_on_a_crashing_agent_and_leaves_no_orphan(tmp_path):
    _write(tmp_path, "agent.py", CRASH_AGENT)
    result = drive_agent(
        tmp_path, "agent.py", script=[final_turn("unreachable")], goal="go",
        timeout=5, python_exe=PY,
    )
    assert result["ok"] is False
    assert result["terminated"] is False
    assert "returncode 3" in result["note"]
    assert _port_is_free(result.get("port")), "stub server port still accepting connections"


def test_drive_agent_never_raises_on_a_hanging_agent_and_leaves_no_orphan(tmp_path):
    _write(tmp_path, "agent.py", HANG_AGENT)
    started = time.perf_counter()
    result = drive_agent(
        tmp_path, "agent.py", script=[final_turn("unreachable")], goal="go",
        timeout=1.0, python_exe=PY,
    )
    elapsed = time.perf_counter() - started
    assert result["ok"] is False
    assert result["terminated"] is False
    assert "timed out" in result["note"].lower()
    assert elapsed < 10.0, f"took {elapsed:.2f}s -- process tree teardown looks stuck"
    assert _port_is_free(result.get("port")), "stub server port still accepting connections"


def test_drive_agent_never_raises_on_malformed_input(tmp_path):
    assert drive_agent(object(), "agent.py", script=[final_turn("x")])["ok"] is False
    assert drive_agent(tmp_path, "does_not_exist.py", script=[final_turn("x")])["ok"] is False
    assert drive_agent(tmp_path, "", script=[final_turn("x")])["ok"] is False
    _write(tmp_path, "agent.py", CORRECT_AGENT)
    assert drive_agent(tmp_path, "agent.py", script=[])["ok"] is False
    assert drive_agent(tmp_path, "agent.py", script="not-a-list")["ok"] is False
    assert drive_agent(tmp_path, "agent.py", script=[{"bogus": True}])["ok"] is False
    assert drive_agent(tmp_path, "agent.py", script=[final_turn("x")], max_steps=0)["ok"] is False


# --------------------------------------------------------------------------------------------
# (d) a multi-step script (2 tool calls then final) exercises the loop + observation-feedback
# --------------------------------------------------------------------------------------------

def test_multistep_script_threads_observations_through_the_loop(tmp_path):
    _write(tmp_path, "agent.py", CORRECT_AGENT)
    script = [
        tool_call_turn("search", {"query": "invoices"}),
        tool_call_turn("open_record", {"id": 42}),
        final_turn("invoice #42 says paid"),
    ]
    result = drive_agent(
        tmp_path, "agent.py", script=script,
        tools={"search": [{"ids": [42, 43]}], "open_record": {"status": "paid"}},
        goal="find the invoice", max_steps=10, python_exe=PY,
    )
    assert result["ok"] is True, result["note"]
    assert result["steps"] == 3  # three scripted chat-completion round trips
    ok, note = check_agent(
        result,
        expect_tool_calls=[
            {"name": "search", "args": {"query": "invoices"}},
            {"name": "open_record", "args": {"id": 42}},
        ],
        expect_final_contains="paid",
        expect_terminated=True,
    )
    assert ok is True, note


def test_per_call_observation_list_cycles_by_invocation_count(tmp_path):
    """A tool's canned observation may be a LIST -- consumed call-by-call -- so a task can make
    the same tool return something different on its second invocation."""
    _write(tmp_path, "agent.py", CORRECT_AGENT)
    script = [
        tool_call_turn("roll_die", {}),
        tool_call_turn("roll_die", {}),
        final_turn("rolled twice"),
    ]
    result = drive_agent(
        tmp_path, "agent.py", script=script,
        tools={"roll_die": [1, 6]},
        goal="roll twice", max_steps=10, python_exe=PY,
    )
    assert result["ok"] is True, result["note"]
    assert len(result["tool_calls"]) == 2
    ok, note = check_agent(
        result,
        expect_tool_calls=[{"name": "roll_die"}, {"name": "roll_die"}],
        expect_final_contains="rolled",
    )
    assert ok is True, note


# --------------------------------------------------------------------------------------------
# max_steps enforcement -- a loop that never reads the final turn is caught as non-terminated
# --------------------------------------------------------------------------------------------

NEVER_STOPS_AGENT = """
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
        # BROKEN: never checks for a final answer at all, keeps calling the SAME tool forever
        # (bounded locally only so the test process itself can't truly hang) -- the oracle's
        # own max_steps backstop is what is really being exercised here.
        for _ in range(200):
            _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
            _post(tool_url + "/poll", {})


    if __name__ == "__main__":
        main()
"""


def test_agent_exceeding_max_steps_is_reported_as_not_terminated(tmp_path):
    _write(tmp_path, "agent.py", NEVER_STOPS_AGENT)
    result = drive_agent(
        tmp_path, "agent.py",
        script=[tool_call_turn("poll", {}), final_turn("stop please")],
        tools={"poll": "still going"},
        goal="poll until done", max_steps=5, timeout=15, python_exe=PY,
    )
    assert result["ok"] is False
    assert result["terminated"] is False
    assert "max_steps" in result["note"]
    # Grade against the SAME tool_calls the oracle captured (so the length always matches
    # whatever cutoff point max_steps hit) -- the point of this assertion is that check_agent
    # catches the TERMINATION mismatch specifically, not the tool-call sequence.
    ok, note = check_agent(result, expect_tool_calls=result["tool_calls"], expect_terminated=True)
    assert ok is False
    assert "termination mismatch" in note.lower()
# #EXT-059-REQ-6 End
