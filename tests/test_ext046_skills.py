"""EXT-046: custom skills / commands (user drop-ins).

OFFLINE -- no live model. The orchestrator agent is stubbed via `cli._load_agent` (the same
pattern as tests/test_ext042_jcode_md.py / tests/test_ext036_project_md.py); nothing here calls
an LLM. `harness.skills` is pure deterministic file I/O + string substitution -- exercised
directly with `tmp_path` fixtures and a monkeypatched `Path.home()` for the user tier.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness import skills as sk
from harness.cli import JcodeCli


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
    test_ext042_jcode_md.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir (both for harness.skills' user tier and
    harness.jcode_md's, which JcodeCli.__init__ also loads) so these tests never read/write
    anything under the REAL ~/.jcode/ on the machine running the suite."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_skill(root, name: str, body: str, description: str = "", argument_hint: str = "") -> None:
    d = root / ".jcode" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    text = ""
    if description or argument_hint:
        text += "---\n"
        if description:
            text += f"description: {description}\n"
        if argument_hint:
            text += f"argument-hint: {argument_hint}\n"
        text += "---\n"
    text += body
    (d / f"{name}.md").write_text(text, encoding="utf-8")


# =====================================================================================
# harness.skills.discover_skills -- pure file discovery, project + user tiers
# =====================================================================================

def test_discover_skills_finds_a_project_tier_skill(tmp_path):
    _write_skill(tmp_path, "foo", "Please process $ARGUMENTS now.", description="do a thing",
                 argument_hint="<x>")
    found = sk.discover_skills(tmp_path)
    assert "foo" in found
    skill = found["foo"]
    assert skill.description == "do a thing"
    assert skill.argument_hint == "<x>"
    assert "process $ARGUMENTS" in skill.body


def test_discover_skills_no_frontmatter_whole_file_is_body(tmp_path):
    _write_skill(tmp_path, "bare", "Just do the thing with $ARGUMENTS.")
    found = sk.discover_skills(tmp_path)
    assert found["bare"].description == ""
    assert found["bare"].argument_hint == ""
    assert "Just do the thing" in found["bare"].body


def test_discover_skills_missing_dir_yields_empty_registry(tmp_path):
    assert sk.discover_skills(tmp_path) == {}


def test_discover_skills_project_tier_wins_on_name_collision(tmp_path, _isolate_user_home):
    _write_skill(tmp_path, "dup", "PROJECT body $ARGUMENTS")
    _write_skill(_isolate_user_home, "dup", "USER body $ARGUMENTS")
    found = sk.discover_skills(tmp_path)
    assert "PROJECT body" in found["dup"].body


def test_discover_skills_user_tier_contributes_when_no_collision(tmp_path, _isolate_user_home):
    _write_skill(_isolate_user_home, "onlyuser", "USER-ONLY body $ARGUMENTS")
    found = sk.discover_skills(tmp_path)
    assert "onlyuser" in found
    assert "USER-ONLY" in found["onlyuser"].body


def test_discover_skills_skips_invalid_identifier_filename(tmp_path):
    d = tmp_path / ".jcode" / "skills"
    d.mkdir(parents=True)
    (d / "my-skill.md").write_text("some body text here", encoding="utf-8")
    found = sk.discover_skills(tmp_path)
    assert found == {}


def test_discover_skills_skips_empty_body_file(tmp_path):
    d = tmp_path / ".jcode" / "skills"
    d.mkdir(parents=True)
    (d / "empty.md").write_text("   \n\n   ", encoding="utf-8")
    found = sk.discover_skills(tmp_path)
    assert "empty" not in found


def test_discover_skills_never_raises_on_unresolvable_home(tmp_path, monkeypatch):
    _write_skill(tmp_path, "foo", "some body $ARGUMENTS")

    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(sk.Path, "home", staticmethod(_boom))
    found = sk.discover_skills(tmp_path)   # must not raise despite a broken Path.home()
    assert "foo" in found                  # project tier still discovered


def test_discover_skills_never_raises_on_none_root():
    # A garbage root degrades to an empty registry rather than raising.
    assert sk.discover_skills(None) == {}


# =====================================================================================
# harness.skills.render_template -- $ARGUMENTS / $1 / $2 ... substitution
# =====================================================================================

def test_render_template_substitutes_arguments_and_positional_tokens():
    body = "Do $ARGUMENTS: first=$1 second=$2 third=$3"
    out = sk.render_template(body, "bar baz")
    assert out == "Do bar baz: first=bar second=baz third="


def test_render_template_no_placeholders_passes_through():
    assert sk.render_template("a plain fixed template", "whatever") == "a plain fixed template"


def test_render_template_never_raises_on_none_body():
    assert sk.render_template(None, "x") == ""


def test_render_template_never_raises_on_none_args():
    out = sk.render_template("hello $ARGUMENTS ($1)", None)
    assert out == "hello  ()"


def test_render_template_never_raises_on_both_none():
    assert sk.render_template(None, None) == ""


# =====================================================================================
# CLI integration -- /name dispatches a skill, built-ins always win, /skills, backward-compat
# =====================================================================================

def test_dropped_skill_registers_a_slash_command_and_reaches_orchestrator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "foo", "Please process $ARGUMENTS now (first=$1 second=$2).",
                 description="a test skill")
    cli, stub = _stub_cli(action="help", arg="")
    assert "foo" in cli.skills

    out = cli.dispatch("/foo bar baz")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    # The rendered (substituted) text reached the orchestrator -- not the raw, unsubstituted
    # template (no literal "$ARGUMENTS"/"$1"/"$2" left in what the orchestrator saw).
    assert "process bar baz now" in routed_request
    assert "first=bar" in routed_request
    assert "second=baz" in routed_request
    assert "$ARGUMENTS" not in routed_request
    assert "$1" not in routed_request
    assert isinstance(out, str)


def test_builtin_command_is_never_shadowed_by_a_same_named_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "status", "this text should NEVER be seen by the orchestrator")
    cli, stub = _stub_cli()
    out = cli.dispatch("/status")
    # The built-in cmd_status ran (its output shape, e.g. "model:"), not the skill's template,
    # and the orchestrator was never even consulted.
    assert "model:" in out
    assert stub.calls == []


def test_skills_command_lists_discovered_skills_with_descriptions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "alpha", "body $ARGUMENTS", description="alpha does a thing")
    _write_skill(tmp_path, "beta", "body $ARGUMENTS")
    cli = JcodeCli()
    out = cli.cmd_skills("")
    assert "/alpha" in out and "alpha does a thing" in out
    assert "/beta" in out


def test_skills_command_reports_honest_empty_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.cmd_skills("")
    assert "no custom skills" in out.lower()


def test_malformed_skill_file_is_skipped_not_crashed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".jcode" / "skills"
    d.mkdir(parents=True)
    (d / "broken.md").write_text("", encoding="utf-8")
    _write_skill(tmp_path, "good", "a real body $ARGUMENTS")
    cli = JcodeCli()   # construction must not raise despite the malformed file
    assert "good" in cli.skills
    assert "broken" not in cli.skills


def test_no_skills_dir_registry_is_empty_and_dispatch_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert cli.skills == {}
    out = cli.dispatch("/nosuchcommand")
    assert "unknown command" in out


def test_help_documents_skills_command():
    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/skills" in out
    assert ".jcode/skills" in out
