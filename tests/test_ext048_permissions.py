"""EXT-048: user-configurable permission rules + REPL modes.

OFFLINE -- no live model. `harness.permissions` is pure deterministic file I/O + a first-match
glob lookup; `harness.coding_loop.Runtime.apply` is the real Jaros gate -> executor -> decision-log
choke point every tool call already passes through -- exercised end-to-end with REAL deterministic
Decisions (fs.read/code.write_file/shell.exec), no model involved. The centerpiece is THE SAFETY
INVARIANT: a permission rule is consulted STRICTLY AFTER the hard gate has already accepted the
Decision, so a user `allow` rule can never un-block a hard-gate refusal.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness import permissions as perm
from harness.cli import JcodeCli
from harness.coding_loop import Runtime


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext047_hooks.py / test_ext046_skills.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir for harness.permissions' user tier (and
    harness.hooks/skills/jcode_md, which JcodeCli.__init__ also loads) so these tests never touch
    the REAL ~/.jcode/ on the machine running the suite."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(perm.Path, "home", staticmethod(lambda: fake_home))
    import harness.hooks as hk
    monkeypatch.setattr(hk.Path, "home", staticmethod(lambda: fake_home))
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_permissions_json(root, rules) -> None:
    d = root / ".jcode"
    d.mkdir(parents=True, exist_ok=True)
    (d / "permissions.json").write_text(json.dumps({"rules": rules}), encoding="utf-8")


# =====================================================================================
# harness.permissions.load_permission_rules / load_project_permissions / load_user_permissions
# =====================================================================================

def test_load_project_permissions_parses_rules(tmp_path):
    _write_permissions_json(tmp_path, [
        {"tool": "shell.exec", "arg": "pytest*", "action": "allow"},
        {"tool": "git.commit", "action": "deny"},
    ])
    rules = perm.load_project_permissions(tmp_path)
    assert rules[0].tool == "shell.exec"
    assert rules[0].arg == "pytest*"
    assert rules[0].action == "allow"
    assert rules[1].tool == "git.commit"
    assert rules[1].arg is None
    assert rules[1].action == "deny"


def test_load_permission_rules_missing_config_yields_empty(tmp_path):
    assert perm.load_permission_rules(tmp_path) == []


def test_load_permission_rules_combines_project_and_user_tiers_project_first(tmp_path, _isolate_user_home):
    _write_permissions_json(tmp_path, [{"tool": "fs.read", "action": "deny"}])
    _write_permissions_json(_isolate_user_home, [{"tool": "fs.read", "action": "allow"}])
    rules = perm.load_permission_rules(tmp_path)
    assert [r.action for r in rules if r.tool == "fs.read"] == ["deny", "allow"]


def test_load_permission_rules_accepts_bare_list_top_level(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "permissions.json").write_text(
        json.dumps([{"tool": "fs.read", "action": "allow"}]), encoding="utf-8")
    rules = perm.load_permission_rules(tmp_path)
    assert len(rules) == 1 and rules[0].action == "allow"


def test_load_permission_rules_malformed_json_degrades_to_empty_not_crash(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "permissions.json").write_text("{not valid json", encoding="utf-8")
    assert perm.load_permission_rules(tmp_path) == []


def test_load_permission_rules_non_dict_non_list_top_level_degrades_to_empty(tmp_path):
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "permissions.json").write_text("42", encoding="utf-8")
    assert perm.load_permission_rules(tmp_path) == []


def test_load_permission_rules_skips_malformed_individual_entries_keeps_good_ones(tmp_path):
    _write_permissions_json(tmp_path, [
        {"tool": "fs.read", "action": "allow"},
        {"tool": "fs.grep"},                  # missing 'action' -- skipped
        {"tool": "fs.grep", "action": "bogus"},  # invalid action -- skipped
        "not-a-dict",                          # skipped
        123,                                    # skipped
    ])
    rules = perm.load_permission_rules(tmp_path)
    assert len(rules) == 1
    assert rules[0].tool == "fs.read" and rules[0].action == "allow"


def test_load_permission_rules_never_raises_on_unresolvable_home(tmp_path, monkeypatch):
    _write_permissions_json(tmp_path, [{"tool": "fs.read", "action": "allow"}])

    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(perm.Path, "home", staticmethod(_boom))
    rules = perm.load_permission_rules(tmp_path)   # must not raise despite a broken Path.home()
    assert rules[0].tool == "fs.read"   # project tier still discovered


def test_load_permission_rules_never_raises_on_none_root():
    assert perm.load_permission_rules(None) == []


# =====================================================================================
# harness.permissions.decide -- first-match-wins glob resolution
# =====================================================================================

def test_decide_no_rules_resolves_allow():
    assert perm.decide([], "shell.exec") == "allow"
    assert perm.decide(None, "shell.exec") == "allow"


def test_decide_no_matching_rule_resolves_allow():
    rules = [perm.PermissionRule(tool="git.commit", arg=None, action="deny")]
    assert perm.decide(rules, "fs.read") == "allow"


def test_decide_first_match_wins():
    rules = [
        perm.PermissionRule(tool="shell.exec", arg=None, action="ask"),
        perm.PermissionRule(tool="shell.exec", arg=None, action="deny"),
    ]
    assert perm.decide(rules, "shell.exec") == "ask"   # first rule wins, second never consulted


def test_decide_tool_glob_scoping():
    rules = [perm.PermissionRule(tool="code.*", arg=None, action="ask")]
    assert perm.decide(rules, "code.write_file") == "ask"
    assert perm.decide(rules, "shell.exec") == "allow"   # doesn't match the glob -> falls through


def test_decide_arg_glob_scoping():
    rules = [perm.PermissionRule(tool="code.write_file", arg="*.md", action="ask")]
    assert perm.decide(rules, "code.write_file", "notes.md") == "ask"
    assert perm.decide(rules, "code.write_file", "main.py") == "allow"
    assert perm.decide(rules, "code.write_file", None) == "allow"   # arg required, none given


def test_resolve_decision_arg_pulls_path_command_target_message():
    d1 = create_decision(id="a", source="t", type="code.write_file", payload={"path": "x.py"})
    assert perm.resolve_decision_arg(d1) == "x.py"
    d2 = create_decision(id="b", source="t", type="shell.exec", payload={"command": "echo hi"})
    assert perm.resolve_decision_arg(d2) == "echo hi"
    d3 = create_decision(id="c", source="t", type="fs.read", payload={})
    assert perm.resolve_decision_arg(d3) is None


# =====================================================================================
# Runtime.apply -- THE SAFETY INVARIANT: hard gate runs first, unconditionally
# =====================================================================================

def test_safety_invariant_allow_rule_cannot_unblock_a_hard_gate_refusal(tmp_path):
    """The centerpiece test: a permissions.json that ALLOWS a denylisted/destructive shell
    command is STILL refused by the hard gate -- with the GATE's own rejection reason, not a
    permission message. A user `allow` rule can only narrow, never widen."""
    rules = [perm.PermissionRule(tool="shell.exec", arg=None, action="allow")]
    rt = Runtime(data_dir=tmp_path / "state", permission_rules=rules)
    d = create_decision(id="danger", source="test", type="shell.exec",
                         payload={"command": "rm -rf /tmp/should-never-run"})
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(d)


def test_safety_invariant_holds_even_with_acceptEdits_mode(tmp_path):
    """acceptEdits only auto-approves an ASK result for WRITE types after the gate passed -- it
    never touches the hard gate either."""
    rules = [perm.PermissionRule(tool="shell.exec", arg=None, action="allow")]
    rt = Runtime(data_dir=tmp_path / "state", permission_rules=rules, mode="acceptEdits")
    d = create_decision(id="danger2", source="test", type="shell.exec",
                         payload={"command": "curl http://example.com/exfiltrate"})
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(d)


# =====================================================================================
# Runtime.apply -- deny / ask (interactive approve+decline, headless safe-fallback)
# =====================================================================================

def test_deny_rule_blocks_before_executor_runs(tmp_path):
    target = tmp_path / "should_not_exist.txt"
    rules = [perm.PermissionRule(tool="code.write_file", arg=None, action="deny")]
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), permission_rules=rules)
    d = create_decision(id="d1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "nope"})
    with pytest.raises(RuntimeError, match="permission rule denied"):
        rt.apply(d)
    assert not target.exists()


def test_ask_rule_with_approving_callback_proceeds(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rules = [perm.PermissionRule(tool="fs.read", arg=None, action="ask")]
    rt = Runtime(data_dir=tmp_path / "state", permission_rules=rules,
                 ask_callback=lambda tool, arg: True)
    d = create_decision(id="a1", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"


def test_ask_rule_with_declining_callback_blocks(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rules = [perm.PermissionRule(tool="fs.read", arg=None, action="ask")]
    rt = Runtime(data_dir=tmp_path / "state", permission_rules=rules,
                 ask_callback=lambda tool, arg: False)
    d = create_decision(id="a2", source="test", type="fs.read", payload={"path": str(target)})
    with pytest.raises(RuntimeError, match="permission ask declined"):
        rt.apply(d)


def test_ask_rule_with_no_callback_headless_safe_default_denies_never_hangs(tmp_path):
    """No ask_callback wired (the headless default) -- an `ask` result must degrade to a safe
    deny WITHOUT ever calling input() or blocking."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rules = [perm.PermissionRule(tool="fs.read", arg=None, action="ask")]
    rt = Runtime(data_dir=tmp_path / "state", permission_rules=rules)   # ask_callback=None default
    d = create_decision(id="a3", source="test", type="fs.read", payload={"path": str(target)})
    with pytest.raises(RuntimeError, match="no interactive prompt"):
        rt.apply(d)


# =====================================================================================
# Runtime.apply -- modes: plan (propose only) / acceptEdits (auto-approve writes on ask)
# =====================================================================================

def test_plan_mode_withholds_write_decision_no_side_effect(tmp_path):
    target = tmp_path / "should_not_exist.txt"
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path), mode="plan")
    d = create_decision(id="p1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "should never land"})
    out = rt.apply(d)
    assert out["planned"] is True
    assert not target.exists()


def test_plan_mode_withholds_shell_exec_no_side_effect(tmp_path):
    marker = tmp_path / "marker.txt"
    rt = Runtime(data_dir=tmp_path / "state", mode="plan")
    d = create_decision(id="p2", source="test", type="shell.exec",
                         payload={"command": f"echo hi > {marker}"})
    out = rt.apply(d)
    assert out["planned"] is True
    assert not marker.exists()


def test_plan_mode_does_not_withhold_read_only_types(tmp_path):
    """Information-gathering must still work while proposing a plan."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state", mode="plan")
    d = create_decision(id="p3", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"   # fs.read is not in PLAN_MODE_WITHHELD_TYPES


def test_default_mode_is_byte_identical_to_pre_ext048(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")   # mode defaults to "default"
    d = create_decision(id="def1", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"


def test_accept_edits_mode_auto_approves_ask_on_write_type(tmp_path):
    target = tmp_path / "out.txt"
    rules = [perm.PermissionRule(tool="code.write_file", arg=None, action="ask")]
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path),
                 mode="acceptEdits", permission_rules=rules)   # no ask_callback needed
    d = create_decision(id="ae1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "written"})
    out = rt.apply(d)
    assert out["applied"] is True
    assert target.read_text(encoding="utf-8") == "written"


def test_accept_edits_mode_does_not_auto_approve_ask_on_shell_exec(tmp_path):
    """acceptEdits only auto-approves the narrower WRITE set -- shell.exec still needs a callback
    or falls back to the safe deny."""
    rules = [perm.PermissionRule(tool="shell.exec", arg=None, action="ask")]
    rt = Runtime(data_dir=tmp_path / "state", mode="acceptEdits", permission_rules=rules)
    d = create_decision(id="ae2", source="test", type="shell.exec",
                         payload={"command": "echo hi"})
    with pytest.raises(RuntimeError, match="no interactive prompt"):
        rt.apply(d)


def test_no_permission_rules_is_a_complete_noop(tmp_path):
    """Backward-compat: Runtime(...) with no permission_rules (the default) never consults
    harness.permissions at all -- proven by an allow-everything monkeypatch of `decide` that
    would still let this pass, but more directly by simply confirming default behavior is
    unaffected end-to-end."""
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    rt = Runtime(data_dir=tmp_path / "state")   # no permission_rules, no mode, no ask_callback
    d = create_decision(id="noop1", source="test", type="fs.read", payload={"path": str(target)})
    out = rt.apply(d)
    assert out["content"] == "hi\n"


def test_set_mode_updates_live_runtime(tmp_path):
    target = tmp_path / "should_not_exist.txt"
    rt = Runtime(data_dir=tmp_path / "state", root=str(tmp_path))   # default mode
    rt.set_mode("plan")
    d = create_decision(id="sm1", source="test", type="code.write_file",
                         payload={"path": str(target), "content": "x"})
    out = rt.apply(d)
    assert out["planned"] is True
    assert not target.exists()


# =====================================================================================
# JcodeCli -- /mode, /permissions, /help, interactive vs headless ask_callback wiring
# =====================================================================================

def test_cli_defaults_to_default_mode_and_empty_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.mode == "default"
    assert cli.permission_rules == []


def test_cmd_mode_cycles_with_no_argument(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.mode == "default"
    out = cli.cmd_mode("")
    assert cli.mode == "acceptEdits"
    assert "acceptEdits" in out
    out = cli.cmd_mode("")
    assert cli.mode == "plan"
    out = cli.cmd_mode("")
    assert cli.mode == "default"


def test_cmd_mode_sets_explicit_valid_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_mode("plan")
    assert cli.mode == "plan"
    assert "plan" in out


def test_cmd_mode_rejects_unknown_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_mode("bogus")
    assert cli.mode == "default"   # unchanged
    assert "unknown mode" in out.lower()


def test_cmd_mode_takes_effect_on_the_live_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    cli.cmd_mode("plan")
    target = tmp_path / "should_not_exist.txt"
    out = cli.rt.apply(cli._mk(id="live1", source="test", type="code.write_file",
                                payload={"path": str(target), "content": "x"}))
    assert out["planned"] is True
    assert not target.exists()


def test_cmd_permissions_lists_configured_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_permissions_json(tmp_path, [{"tool": "shell.exec", "action": "ask"}])
    cli = JcodeCli()
    out = cli.cmd_permissions("")
    assert "shell.exec" in out
    assert "ask" in out


def test_cmd_permissions_reports_honest_empty_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_permissions("")
    assert "no permission rules configured" in out.lower()


def test_malformed_permissions_json_never_crashes_cli_construction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".jcode"
    d.mkdir(parents=True)
    (d / "permissions.json").write_text("{ this is not json", encoding="utf-8")
    cli = JcodeCli()   # construction must not raise despite the malformed config
    assert cli.permission_rules == []


def test_help_documents_mode_and_permissions_commands():
    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/mode" in out
    assert "/permissions" in out
    assert ".jcode/permissions.json" in out


def test_headless_cli_never_wires_an_ask_callback(tmp_path, monkeypatch):
    """A headless (interactive=False, the default) CLI's Runtime has no ask_callback -- an `ask`
    rule degrades to the safe deny rather than trying to call input() with no terminal."""
    monkeypatch.chdir(tmp_path)
    _write_permissions_json(tmp_path, [{"tool": "fs.read", "action": "ask"}])
    cli = JcodeCli()   # interactive=False (default)
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no interactive prompt"):
        cli.rt.apply(cli._mk(id="h1", source="test", type="fs.read", payload={"path": str(target)}))


def test_interactive_cli_wires_ask_permission_as_callback(tmp_path, monkeypatch):
    """repl()-style construction (interactive=True) wires an input()-based callback -- proven here
    by monkeypatching input() to approve, never actually blocking the test."""
    monkeypatch.chdir(tmp_path)
    _write_permissions_json(tmp_path, [{"tool": "fs.read", "action": "ask"}])
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "y")
    cli = JcodeCli(interactive=True)
    target = tmp_path / "hello.txt"
    target.write_text("hi\n", encoding="utf-8")
    out = cli.rt.apply(cli._mk(id="i1", source="test", type="fs.read", payload={"path": str(target)}))
    assert out["content"] == "hi\n"
