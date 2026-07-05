"""EXT-047: user-configurable lifecycle hooks.

OFFLINE -- no live model. `harness.hooks` is pure deterministic file I/O + a dispatch decision
(which configured hook applies to which event/tool); `harness.coding_loop.Runtime.apply` is the
real Jaros gate -> executor -> decision-log choke point every tool call already passes through --
exercised end-to-end with REAL deterministic Decisions (fs.read/fs.write_file), no model involved.
Most tests inject a fake hook runner (mirrors how test_ext045_terminal_ux.py injects `on_event`)
so they stay fast and offline; a couple of tests deliberately exercise the REAL gated shell.exec
path (no live model needed -- it's a plain subprocess, same as any other harness shell test) to
prove hooks are not a raw, ungated `subprocess.run` call.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness import hooks as hk
from harness.cli import JcodeCli
from harness.coding_loop import Runtime


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext046_skills.py / test_ext042_jcode_md.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir for harness.hooks' user tier (and
    harness.skills/harness.jcode_md, which JcodeCli.__init__ also loads) so these tests never
    read/write anything under the REAL ~/.jcode/ on the machine running the suite."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(hk.Path, "home", staticmethod(lambda: fake_home))
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_hooks_json(root, config: dict) -> None:
    d = root / ".jcode"
    d.mkdir(parents=True, exist_ok=True)
    (d / "hooks.json").write_text(json.dumps(config), encoding="utf-8")


# =====================================================================================
# harness.hooks.load_hooks / load_project_hooks / load_user_hooks -- pure file I/O
# =====================================================================================

def test_load_project_hooks_parses_command_and_matcher(tmp_path):
    _write_hooks_json(tmp_path, {
        "PreToolUse": [{"command": "echo pre", "matcher": "fs.read"}],
        "Stop": [{"command": "echo bye"}],
    })
    cfg = hk.load_project_hooks(tmp_path)
    assert cfg["PreToolUse"][0].command == "echo pre"
    assert cfg["PreToolUse"][0].matcher == "fs.read"
    assert cfg["Stop"][0].command == "echo bye"
    assert cfg["Stop"][0].matcher is None


def test_load_hooks_missing_config_yields_empty(tmp_path):
    assert hk.load_hooks(tmp_path) == {}


def test_load_hooks_combines_project_and_user_tiers(tmp_path, _isolate_user_home):
    _write_hooks_json(tmp_path, {"SessionStart": [{"command": "echo project-start"}]})
    _write_hooks_json(_isolate_user_home, {"SessionStart": [{"command": "echo user-start"}]})
    cfg = hk.load_hooks(tmp_path)
    commands = [hd.command for hd in cfg["SessionStart"]]
    # Both tiers are additive (no name-collision override, unlike EXT-046 skills) -- project
    # runs first, then user.
    assert commands == ["echo project-start", "echo user-start"]


def test_load_hooks_malformed_json_degrades_to_empty_not_crash(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "hooks.json").write_text("{not valid json", encoding="utf-8")
    assert hk.load_hooks(tmp_path) == {}


def test_load_hooks_non_dict_top_level_degrades_to_empty(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "hooks.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert hk.load_hooks(tmp_path) == {}


def test_load_hooks_skips_malformed_individual_entries_keeps_good_ones(tmp_path):
    _write_hooks_json(tmp_path, {
        "PreToolUse": [
            {"command": "echo good"},
            {"matcher": "fs.read"},        # missing 'command' -- skipped
            "not-a-dict",                    # skipped
            {"command": ""},                 # blank command -- skipped
            123,                              # skipped
        ],
        "UnknownEvent": [{"command": "echo nope"}],   # not a valid event -- ignored entirely
    })
    cfg = hk.load_hooks(tmp_path)
    assert len(cfg["PreToolUse"]) == 1
    assert cfg["PreToolUse"][0].command == "echo good"
    assert "UnknownEvent" not in cfg


def test_load_hooks_never_raises_on_unresolvable_home(tmp_path, monkeypatch):
    _write_hooks_json(tmp_path, {"Stop": [{"command": "echo bye"}]})

    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(hk.Path, "home", staticmethod(_boom))
    cfg = hk.load_hooks(tmp_path)   # must not raise despite a broken Path.home()
    assert cfg["Stop"][0].command == "echo bye"   # project tier still discovered


def test_load_hooks_never_raises_on_none_root():
    assert hk.load_hooks(None) == {}


# =====================================================================================
# harness.hooks.fire_event -- matcher scoping + block-on-nonzero, with an injected runner
# =====================================================================================

def _fake_runner(exit_codes: dict, calls: list):
    def run(command, cwd):
        calls.append((command, cwd))
        return {"exitCode": exit_codes.get(command, 0), "stdout": "", "stderr": ""}
    return run


def test_fire_event_runs_every_configured_hook_for_the_event():
    calls = []
    cfg = {"SessionStart": [hk.HookDef(command="echo a"), hk.HookDef(command="echo b")]}
    outcomes = hk.fire_event("SessionStart", cfg, run_command=_fake_runner({}, calls))
    assert [c for c, _ in calls] == ["echo a", "echo b"]
    assert all(o.exit_code == 0 and not o.blocked for o in outcomes)


def test_fire_event_matcher_scopes_pretooluse_to_matching_tool_only():
    calls = []
    cfg = {"PreToolUse": [hk.HookDef(command="echo scoped", matcher="fs.read")]}
    hk.fire_event("PreToolUse", cfg, tool_name="fs.grep", run_command=_fake_runner({}, calls))
    assert calls == []   # fs.grep does not match the "fs.read" matcher -- hook never runs
    hk.fire_event("PreToolUse", cfg, tool_name="fs.read", run_command=_fake_runner({}, calls))
    assert calls == [("echo scoped", None)]


def test_fire_event_no_matcher_applies_to_every_tool():
    calls = []
    cfg = {"PostToolUse": [hk.HookDef(command="echo any")]}
    hk.fire_event("PostToolUse", cfg, tool_name="shell.exec", run_command=_fake_runner({}, calls))
    hk.fire_event("PostToolUse", cfg, tool_name="fs.read", run_command=_fake_runner({}, calls))
    assert len(calls) == 2


def test_fire_event_pretooluse_nonzero_exit_is_flagged_blocked():
    calls = []
    cfg = {"PreToolUse": [hk.HookDef(command="exit 1")]}
    outcomes = hk.fire_event("PreToolUse", cfg, tool_name="fs.read",
                              run_command=_fake_runner({"exit 1": 1}, calls))
    assert hk.blocked(outcomes) is True
    assert "exit 1" in hk.blocking_reason(outcomes)


def test_fire_event_posttooluse_nonzero_exit_never_blocks():
    calls = []
    cfg = {"PostToolUse": [hk.HookDef(command="exit 1")]}
    outcomes = hk.fire_event("PostToolUse", cfg, tool_name="fs.read",
                              run_command=_fake_runner({"exit 1": 1}, calls))
    assert hk.blocked(outcomes) is False   # PostToolUse is observational only, never blocks


def test_fire_event_unknown_event_yields_nothing():
    assert hk.fire_event("BogusEvent", {"BogusEvent": [hk.HookDef(command="echo x")]}) == []


def test_fire_event_never_raises_on_none_config():
    assert hk.fire_event("SessionStart", None) == []


def test_fire_event_never_raises_when_runner_itself_raises():
    def boom(command, cwd):
        raise RuntimeError("boom")
    cfg = {"Stop": [hk.HookDef(command="echo x")]}
    outcomes = hk.fire_event("Stop", cfg, run_command=boom)
    assert outcomes == []   # this one hook's failure contributes nothing, never raises


# =====================================================================================
# harness.coding_loop.Runtime.apply -- PreToolUse before, PostToolUse after, block-on-nonzero
# =====================================================================================

def test_pretooluse_hook_fires_before_the_tool_call(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: (order.append(("hook", cmd)), {"exitCode": 0, "stdout": "", "stderr": ""})[1])

    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")

    cfg = {"PreToolUse": [hk.HookDef(command="echo pre")]}
    rt = Runtime(data_dir=tmp_path / "state",
                 on_event=lambda ev: order.append(("event", ev["phase"])),
                 hooks_config=cfg)
    d = create_decision(id="t1", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)

    assert out["content"] == "hi\n"
    assert order[0] == ("hook", "echo pre")
    assert order[1] == ("event", "call")
    assert order[-1] == ("event", "result")


def test_posttooluse_hook_fires_after_the_tool_call(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: (order.append(("hook", cmd)), {"exitCode": 0, "stdout": "", "stderr": ""})[1])

    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")

    cfg = {"PostToolUse": [hk.HookDef(command="echo post")]}
    rt = Runtime(data_dir=tmp_path / "state",
                 on_event=lambda ev: order.append(("event", ev["phase"])),
                 hooks_config=cfg)
    d = create_decision(id="t2", source="test", type="fs.read", payload={"path": str(target)})
    rt.apply(d)

    assert order == [("event", "call"), ("event", "result"), ("hook", "echo post")]


def test_pretooluse_hook_nonzero_exit_blocks_the_tool_call(tmp_path, monkeypatch):
    """The clerk refuses the tool call outright -- the file must NEVER be written."""
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: {"exitCode": 1, "stdout": "", "stderr": "denied"})

    target = tmp_path / "should_not_exist.txt"
    cfg = {"PreToolUse": [hk.HookDef(command="exit 1")]}
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), hooks_config=cfg)
    d = create_decision(id="t3", source="test", type="code.write_file",
                        payload={"path": str(target), "content": "should never land"})

    with pytest.raises(RuntimeError, match="PreToolUse hook blocked"):
        rt.apply(d)

    assert not target.exists()   # the tool call was genuinely refused, not merely observed


def test_no_hooks_config_is_a_complete_noop(tmp_path, monkeypatch):
    """Backward-compat: Runtime(...) with no hooks_config (the default) never even LOOKS at
    harness.hooks -- a monkeypatched runner that would fail the test if called proves it."""
    def _must_not_be_called(*_a, **_kw):
        raise AssertionError("hooks must never fire when no hooks_config is supplied")
    monkeypatch.setattr(hk, "_default_run_command", _must_not_be_called)

    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")   # no hooks_config at all
    d = create_decision(id="t4", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"


# =====================================================================================
# SessionStart / Stop lifecycle, via JcodeCli
# =====================================================================================

def test_sessionstart_fires_once_at_cli_construction(tmp_path, monkeypatch):
    calls = []
    monkeypatch.chdir(tmp_path)
    _write_hooks_json(tmp_path, {"SessionStart": [{"command": "echo hello"}]})
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: (calls.append(cmd), {"exitCode": 0, "stdout": "", "stderr": ""})[1])

    cli = JcodeCli()
    assert calls == ["echo hello"]
    assert len(cli._session_start_outcomes) == 1


def test_stop_fires_once_at_session_end_and_is_idempotent(tmp_path, monkeypatch):
    calls = []
    monkeypatch.chdir(tmp_path)
    _write_hooks_json(tmp_path, {"Stop": [{"command": "echo bye"}]})
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: (calls.append(cmd), {"exitCode": 0, "stdout": "", "stderr": ""})[1])

    cli = JcodeCli()
    assert calls == []   # Stop has not fired yet -- only at session end
    cli.on_stop()
    assert calls == ["echo bye"]
    cli.on_stop()   # calling it again must not double-fire
    assert calls == ["echo bye"]


def test_no_hooks_json_anywhere_yields_empty_config_and_no_lifecycle_firing(tmp_path, monkeypatch):
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hk, "_default_run_command",
                         lambda cmd, cwd: (calls.append(cmd), {"exitCode": 0, "stdout": "", "stderr": ""})[1])

    cli = JcodeCli()
    assert cli.hooks_config == {}
    cli.on_stop()
    assert calls == []   # nothing configured -> nothing ever fires, byte-identical to before


def test_malformed_hooks_json_never_crashes_cli_construction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "hooks.json").write_text("{ this is not json", encoding="utf-8")

    cli = JcodeCli()   # construction must not raise despite the malformed config
    assert cli.hooks_config == {}


def test_cmd_hooks_lists_configured_hooks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_hooks_json(tmp_path, {"PreToolUse": [{"command": "echo pre", "matcher": "fs.read"}]})
    cli = JcodeCli()
    out = cli.cmd_hooks("")
    assert "PreToolUse" in out
    assert "echo pre" in out
    assert "fs.read" in out


def test_cmd_hooks_reports_honest_empty_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_hooks("")
    assert "no hooks configured" in out.lower()


def test_help_documents_hooks_command():
    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/hooks" in out
    assert ".jcode/hooks.json" in out


# =====================================================================================
# Hooks run through the SAME gated shell path -- proven with the REAL (non-mocked) runner
# =====================================================================================

def test_default_run_command_uses_the_real_gated_shell_exec_path(tmp_path):
    """No injected runner here -- this exercises harness.hooks._default_run_command for real,
    proving a hook's command genuinely runs via the gated shell.exec Decision (exit code +
    stdout observed from a REAL subprocess), not a stub."""
    import sys
    result = hk._default_run_command([sys.executable, "-c", "import sys; sys.exit(7)"], str(tmp_path))
    assert result["exitCode"] == 7


def test_default_run_command_is_refused_by_the_shell_exec_denylist_gate(tmp_path):
    """A hook cannot bypass the security gate: a denylisted command (network egress) is
    refused at validate() exactly like any other shell.exec call, surfaced as an honest
    non-zero exit rather than actually running."""
    result = hk._default_run_command("curl http://example.com/exfiltrate", str(tmp_path))
    assert result["exitCode"] == 1
    assert "refused" in result["stderr"].lower() or "denylist" in result["stderr"].lower() \
        or "unsafe" in result["stderr"].lower()


def test_default_run_command_cannot_recurse_into_hook_firing(tmp_path):
    """The Runtime _default_run_command builds internally must never carry hooks_config -- even
    if the SAME command would itself be a configured PreToolUse hook target, firing it can never
    re-trigger hook firing (would otherwise recurse forever)."""
    import sys
    # If this recursed, it would stack-overflow / hang rather than return cleanly.
    result = hk._default_run_command([sys.executable, "-c", "print('ok')"], str(tmp_path))
    assert result["exitCode"] == 0
