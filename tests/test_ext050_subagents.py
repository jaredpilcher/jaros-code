"""EXT-050: user-authorable subagents.

OFFLINE -- no live model. The orchestrator agent is stubbed via `cli._load_agent` (the same
pattern as tests/test_ext046_skills.py); `harness.subagents` is pure deterministic file I/O +
string composition -- exercised directly with `tmp_path` fixtures and a monkeypatched `Path.home()`
for the user tier. The centerpiece is THE SAFETY INVARIANT: a subagent's `tools:` allowlist is
consulted STRICTLY AFTER the hard gate has already accepted a Decision, so it can only NARROW what
the hard gates permit, never widen past them -- mirrors EXT-048's identical proof for permission
rules.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

from harness import subagents as sa
from harness.cli import JcodeCli
from harness.coding_loop import Runtime


class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
    """Records every context dict `decide()` receives; routes to a fixed action."""

    def __init__(self, action: str = "help", arg: str = "") -> None:
        self.calls: "list[dict]" = []
        self._action = action
        self._arg = arg

    def decide(self, context):
        self.calls.append(context)
        return [_FakeDecision(self._action, self._arg)]


def _stub_cli(action: str = "help", arg: str = "") -> "tuple[JcodeCli, _StubOrchestrator]":
    cli = JcodeCli()
    stub = _StubOrchestrator(action, arg)
    cli._load_agent = lambda filename, llm: stub   # any agent name -> the stub
    return cli, stub


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext046_skills.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir (both for harness.subagents' user tier and
    harness.skills/jcode_md's, which JcodeCli.__init__ also loads) so these tests never read/write
    anything under the REAL ~/.jcode/ on the machine running the suite."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(sa.Path, "home", staticmethod(lambda: fake_home))
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_subagent(root, name: str, body: str, description: str = "", tools: str = "",
                     model: str = "") -> None:
    d = root / ".jcode" / "agents"
    d.mkdir(parents=True, exist_ok=True)
    text = ""
    if description or tools or model:
        text += "---\n"
        if description:
            text += f"description: {description}\n"
        if tools:
            text += f"tools: {tools}\n"
        if model:
            text += f"model: {model}\n"
        text += "---\n"
    text += body
    (d / f"{name}.md").write_text(text, encoding="utf-8")


# =====================================================================================
# harness.subagents.discover_subagents -- pure file discovery, project + user tiers
# =====================================================================================

def test_discover_subagents_finds_a_project_tier_subagent(tmp_path):
    _write_subagent(tmp_path, "reviewer", "You are a careful code reviewer.",
                     description="reviews code", tools="fs.read, fs.grep", model="gemma-4-e2b")
    found = sa.discover_subagents(tmp_path)
    assert "reviewer" in found
    sub = found["reviewer"]
    assert sub.description == "reviews code"
    assert sub.tools == ("fs.read", "fs.grep")
    assert sub.model == "gemma-4-e2b"
    assert "careful code reviewer" in sub.body


def test_discover_subagents_no_frontmatter_whole_file_is_body(tmp_path):
    _write_subagent(tmp_path, "bare", "Just be a bare persona.")
    found = sa.discover_subagents(tmp_path)
    assert found["bare"].description == ""
    assert found["bare"].tools == ()
    assert found["bare"].model is None
    assert "bare persona" in found["bare"].body


def test_discover_subagents_missing_dir_yields_empty_registry(tmp_path):
    assert sa.discover_subagents(tmp_path) == {}


def test_discover_subagents_project_tier_wins_on_name_collision(tmp_path, _isolate_user_home):
    _write_subagent(tmp_path, "dup", "PROJECT persona body")
    _write_subagent(_isolate_user_home, "dup", "USER persona body")
    found = sa.discover_subagents(tmp_path)
    assert "PROJECT persona" in found["dup"].body


def test_discover_subagents_user_tier_contributes_when_no_collision(tmp_path, _isolate_user_home):
    _write_subagent(_isolate_user_home, "onlyuser", "USER-ONLY persona body")
    found = sa.discover_subagents(tmp_path)
    assert "onlyuser" in found
    assert "USER-ONLY" in found["onlyuser"].body


def test_discover_subagents_skips_invalid_identifier_filename(tmp_path):
    d = tmp_path / ".jcode" / "agents"
    d.mkdir(parents=True)
    (d / "my-agent.md").write_text("some persona text here", encoding="utf-8")
    found = sa.discover_subagents(tmp_path)
    assert found == {}


def test_discover_subagents_skips_empty_body_file(tmp_path):
    d = tmp_path / ".jcode" / "agents"
    d.mkdir(parents=True)
    (d / "empty.md").write_text("   \n\n   ", encoding="utf-8")
    found = sa.discover_subagents(tmp_path)
    assert "empty" not in found


def test_discover_subagents_never_raises_on_unresolvable_home(tmp_path, monkeypatch):
    _write_subagent(tmp_path, "foo", "some persona body")

    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(sa.Path, "home", staticmethod(_boom))
    found = sa.discover_subagents(tmp_path)   # must not raise despite a broken Path.home()
    assert "foo" in found                     # project tier still discovered


def test_discover_subagents_never_raises_on_none_root():
    assert sa.discover_subagents(None) == {}


def test_parse_tools_field_csv_split_and_dedupe():
    assert sa._parse_tools_field("fs.read, fs.grep,  fs.read ") == ("fs.read", "fs.grep")
    assert sa._parse_tools_field("") == ()
    assert sa._parse_tools_field(None) == ()


# =====================================================================================
# harness.subagents.render_subagent_prompt -- pure composition, no model call
# =====================================================================================

def test_render_subagent_prompt_composes_body_and_task():
    sub = sa.SubagentDef(name="x", description="", tools=(), model=None, body="You are X.")
    out = sa.render_subagent_prompt(sub, "read foo.py")
    assert "You are X." in out
    assert "read foo.py" in out


def test_render_subagent_prompt_degrades_when_task_empty():
    sub = sa.SubagentDef(name="x", description="", tools=(), model=None, body="You are X.")
    assert sa.render_subagent_prompt(sub, "") == "You are X."
    assert sa.render_subagent_prompt(sub, None) == "You are X."


def test_render_subagent_prompt_never_raises_on_none_subagent():
    assert sa.render_subagent_prompt(None, "do a thing") == "do a thing"
    assert sa.render_subagent_prompt(None, None) == ""


# =====================================================================================
# CLI integration -- /subagent, plain "delegate to X subagent" phrasing, /agents, /help
# =====================================================================================

def test_dropped_subagent_registers_and_delegation_reaches_orchestrator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "reviewer", "You are a meticulous reviewer persona.",
                     description="a test subagent")
    cli, stub = _stub_cli(action="help", arg="")
    assert "reviewer" in cli.subagents

    out = cli.dispatch("/subagent reviewer :: read foo.py")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    assert "meticulous reviewer persona" in routed_request
    assert "read foo.py" in routed_request
    assert isinstance(out, str)


def test_plain_delegation_phrasing_reaches_the_registered_subagent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "reviewer", "You are a meticulous reviewer persona.")
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.handle("delegate to reviewer subagent: check main.py for bugs")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    assert "meticulous reviewer persona" in routed_request
    assert "check main.py for bugs" in routed_request
    assert isinstance(out, str)


def test_plain_phrasing_naming_an_unregistered_subagent_falls_through_unchanged(tmp_path, monkeypatch):
    """No subagent named 'ghost' is registered -- this must NOT be misrouted to delegation; it
    falls through to the ordinary orchestrator chain exactly like any other plain request."""
    monkeypatch.chdir(tmp_path)
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.handle("delegate to ghost subagent: do something")

    assert len(stub.calls) == 1   # reached the ordinary orchestrator, not a subagent error path
    assert isinstance(out, str)


def test_subagent_command_unregistered_name_is_honest_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _stub = _stub_cli()
    out = cli.dispatch("/subagent ghost :: do a thing")
    assert "no subagent named" in out.lower()


def test_subagent_command_usage_message_on_bad_args(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _stub = _stub_cli()
    out = cli.dispatch("/subagent")
    assert "usage:" in out.lower()
    out2 = cli.dispatch("/subagent onlyname")
    assert "usage:" in out2.lower()


def test_agents_command_lists_discovered_subagents_with_descriptions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "alpha", "persona body", description="alpha does a thing")
    _write_subagent(tmp_path, "beta", "persona body")
    cli = JcodeCli()
    out = cli.cmd_agents("")
    assert "/alpha" in out and "alpha does a thing" in out
    assert "/beta" in out
    # the pre-existing built-in Python agent-fleet listing is still present (unchanged behavior)
    assert "agents:" in out


def test_agents_command_reports_honest_empty_message_for_subagents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_agents("")
    assert "no user-authored subagents" in out.lower()
    assert "agents:" in out   # built-in fleet listing still renders


def test_malformed_subagent_file_is_skipped_not_crashed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".jcode" / "agents"
    d.mkdir(parents=True)
    (d / "broken.md").write_text("", encoding="utf-8")
    _write_subagent(tmp_path, "good", "a real persona body")
    cli = JcodeCli()   # construction must not raise despite the malformed file
    assert "good" in cli.subagents
    assert "broken" not in cli.subagents


def test_no_agents_dir_registry_is_empty_and_dispatch_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.subagents == {}
    out = cli.dispatch("/nosuchcommand")
    assert "unknown command" in out


def test_help_documents_subagent_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/subagent" in out
    assert ".jcode/agents" in out


# =====================================================================================
# ★ THE TOOL-ALLOWLIST SAFETY INVARIANT ★ -- narrows, never widens, past the hard gates
# =====================================================================================

def test_tool_allowlist_none_is_a_complete_noop(tmp_path):
    """Runtime(tool_allowlist=None) (the default) behaves byte-identically -- a safe command
    passes exactly as it would have before this spec."""
    rt = Runtime(data_dir=tmp_path / "state", tool_allowlist=None)
    d = create_decision(id="ok", source="test", type="shell.exec", payload={"command": "echo hi"})
    out = rt.apply(d)
    assert out.get("exitCode") == 0


def test_tool_allowlist_refuses_a_type_not_in_the_list_even_though_hard_gate_would_allow(tmp_path):
    """The allowlist NARROWS: a Decision the hard gate would happily accept (a safe echo command)
    is still refused when its type isn't in the subagent's allowed tool set."""
    rt = Runtime(data_dir=tmp_path / "state", tool_allowlist=["fs.read"])
    d = create_decision(id="narrowed", source="test", type="shell.exec",
                         payload={"command": "echo hi"})
    with pytest.raises(RuntimeError, match="tool-allowlist"):
        rt.apply(d)


def test_tool_allowlist_cannot_unblock_a_hard_gate_refusal(tmp_path):
    """THE CENTERPIECE TEST: a subagent that ALLOWLISTS shell.exec is STILL refused by the hard
    gate for a denylisted/destructive command -- with the GATE's own rejection reason, not a
    tool-allowlist message. A subagent's tools: list can only narrow, never widen past the hard
    gates (mirrors EXT-048's identical proof for permission rules)."""
    rt = Runtime(data_dir=tmp_path / "state", tool_allowlist=["shell.exec"])
    d = create_decision(id="danger", source="test", type="shell.exec",
                         payload={"command": "rm -rf /tmp/should-never-run"})
    with pytest.raises(RuntimeError, match="gate rejected"):
        rt.apply(d)


def test_tool_allowlist_allows_a_safe_command_when_its_type_is_listed(tmp_path):
    rt = Runtime(data_dir=tmp_path / "state", tool_allowlist=["shell.exec"])
    d = create_decision(id="fine", source="test", type="shell.exec", payload={"command": "echo hi"})
    out = rt.apply(d)
    assert out.get("exitCode") == 0


def test_run_subagent_scopes_rt_to_the_declared_tool_allowlist_and_restores_it(tmp_path, monkeypatch):
    """End-to-end through the CLI: a subagent declaring `tools: fs.read` cannot make a `shell.exec`
    Decision succeed through `self.rt` during its delegated turn -- the scoped Runtime refuses it
    -- and `self.rt` is restored to the CLI's primary (unnarrowed) Runtime afterward. `_route_plain`
    is stubbed directly (rather than routed through the orchestrator) so this test isolates the
    Runtime-swap/allowlist mechanism from orchestrator/command plumbing."""
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "narrow", "You may only read files.", tools="fs.read")
    cli, _stub = _stub_cli()
    prior_rt = cli.rt

    def _fake_route_plain(line):
        d = create_decision(id="probe", source="test", type="shell.exec",
                             payload={"command": "echo hi"})
        try:
            cli.rt.apply(d)
            return "ran the shell command", "run"
        except RuntimeError as exc:
            return f"refused: {exc}", "run"

    cli._route_plain = _fake_route_plain

    out = cli.dispatch("/subagent narrow :: try to run a shell command")

    # refused by the narrowed allowlist (shell.exec not in {"fs.read"}), surfaced honestly --
    # NOT a hard-gate rejection, since "echo hi" is a perfectly safe command.
    assert "refused" in out.lower()
    assert "tool-allowlist" in out.lower()
    # self.rt is restored to the CLI's original, unnarrowed Runtime after delegation completes
    assert cli.rt is prior_rt


def test_run_subagent_without_tools_frontmatter_leaves_rt_unnarrowed(tmp_path, monkeypatch):
    """A subagent with no `tools:` frontmatter (empty allowlist) performs NO extra narrowing --
    `self.rt` is never swapped at all, so a safe shell.exec Decision through it succeeds."""
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "unscoped", "You may do anything the hard gates allow.")
    cli, _stub = _stub_cli()
    prior_rt = cli.rt

    def _fake_route_plain(line):
        d = create_decision(id="probe2", source="test", type="shell.exec",
                             payload={"command": "echo hi"})
        out = cli.rt.apply(d)
        return f"exit={out.get('exitCode')}", "run"

    cli._route_plain = _fake_route_plain

    out = cli.dispatch("/subagent unscoped :: run a safe command")

    assert "exit=0" in out
    assert cli.rt is prior_rt


def test_run_subagent_honors_model_override_and_restores_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "special", "You are a specialist persona.", model="qwen-coder-3b")
    cli, stub = _stub_cli(action="help", arg="")
    prior_llm = cli.llm

    calls = []

    def _fake_build_llm(model=None):
        calls.append(model)
        return object()

    import harness.coding_loop as coding_loop_mod
    monkeypatch.setattr(coding_loop_mod, "build_llm", _fake_build_llm)

    cli.dispatch("/subagent special :: do the specialist thing")

    assert calls == ["qwen-coder-3b"]
    # the CLI's primary llm is restored after the delegated turn completes
    assert cli.llm is prior_llm


def test_run_subagent_without_model_override_never_calls_build_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_subagent(tmp_path, "plain", "You are a plain persona.")
    cli, stub = _stub_cli(action="help", arg="")

    calls = []
    import harness.coding_loop as coding_loop_mod
    monkeypatch.setattr(coding_loop_mod, "build_llm", lambda model=None: calls.append(model))

    cli.dispatch("/subagent plain :: do a thing")

    assert calls == []   # no model: frontmatter -> build_llm never invoked
