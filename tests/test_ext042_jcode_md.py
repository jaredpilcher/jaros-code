"""EXT-042: JCODE.md — project instruction memory hierarchy (project + user levels, auto-loaded
into the orchestrator/planner context every session) + the `/init` starter-file generator.

OFFLINE — no live model. The orchestrator agent is stubbed via `cli._load_agent` (the same
pattern as tests/test_ext036_project_md.py); the NL-fix path is exercised by monkeypatching
harness.multi_file.multi_file_fix. `JcodeCli.__init__` loads JCODE.md from the CURRENT working
directory, so tests that need one present chdir into a tmp_path first.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.jcode_md import (
    MAX_CHARS,
    init_jcode_md,
    load_jcode_md,
    load_project_jcode_md,
    load_user_jcode_md,
)


class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
    """Records every context dict `decide()` receives; routes to a fixed action."""

    def __init__(self, action: str = "help", arg: str = "") -> None:
        self.calls: list[dict] = []
        self._action = action
        self._arg = arg

    def decide(self, context):
        self.calls.append(context)
        return [_FakeDecision(self._action, self._arg)]


def _stub_cli(action: str = "help", arg: str = "") -> tuple[JcodeCli, _StubOrchestrator]:
    cli = JcodeCli()
    stub = _StubOrchestrator(action, arg)
    cli._load_agent = lambda filename, llm: stub   # any agent name -> the stub
    return cli, stub


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext036_project_md.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir so these tests never read/write the REAL
    ~/.jcode/JCODE.md on the machine running the suite."""
    import harness.jcode_md as jm
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


# --- (a) load_project_jcode_md: read + bound + absent-returns-"" -----------------------------

def test_load_project_jcode_md_reads_repo_root(tmp_path):
    (tmp_path / "JCODE.md").write_text("Always use type hints.\nPrefer pathlib.\n", encoding="utf-8")
    text = load_project_jcode_md(tmp_path)
    assert "Always use type hints." in text
    assert "Prefer pathlib." in text


def test_load_project_jcode_md_bounds_long_content(tmp_path):
    (tmp_path / "JCODE.md").write_text("x" * (MAX_CHARS + 500), encoding="utf-8")
    text = load_project_jcode_md(tmp_path)
    assert len(text) <= MAX_CHARS + len("...")
    assert text.startswith("x" * 50)


def test_load_project_jcode_md_absent_returns_empty_string(tmp_path):
    assert load_project_jcode_md(tmp_path) == ""


def test_load_project_jcode_md_never_raises_on_unreadable_dir():
    assert load_project_jcode_md("Z:\\definitely\\does\\not\\exist\\anywhere") == ""


# --- (b) load_user_jcode_md: read + bound + absent-returns-"" --------------------------------

def test_load_user_jcode_md_reads_home_dot_jcode(_isolate_user_home):
    fake_home = _isolate_user_home
    (fake_home / ".jcode").mkdir()
    (fake_home / ".jcode" / "JCODE.md").write_text("Global user convention.", encoding="utf-8")
    assert "Global user convention." in load_user_jcode_md()


def test_load_user_jcode_md_absent_returns_empty_string(_isolate_user_home):
    assert load_user_jcode_md() == ""


def test_load_user_jcode_md_bounds_long_content(_isolate_user_home):
    fake_home = _isolate_user_home
    (fake_home / ".jcode").mkdir()
    (fake_home / ".jcode" / "JCODE.md").write_text("y" * (MAX_CHARS + 500), encoding="utf-8")
    text = load_user_jcode_md()
    assert len(text) <= MAX_CHARS + len("...")


def test_load_user_jcode_md_never_raises_when_home_unresolvable(monkeypatch):
    import harness.jcode_md as jm

    def _boom():
        raise RuntimeError("no home")

    monkeypatch.setattr(jm.Path, "home", staticmethod(_boom))
    assert load_user_jcode_md() == ""


# --- (c) load_jcode_md: combined, clearly-labeled, project+user -------------------------------

def test_load_jcode_md_combines_project_and_user(tmp_path, _isolate_user_home):
    (tmp_path / "JCODE.md").write_text("Project rule A.", encoding="utf-8")
    fake_home = _isolate_user_home
    (fake_home / ".jcode").mkdir()
    (fake_home / ".jcode" / "JCODE.md").write_text("User rule B.", encoding="utf-8")
    combined = load_jcode_md(tmp_path)
    assert "PROJECT INSTRUCTIONS (JCODE.md)" in combined
    assert "Project rule A." in combined
    assert "USER INSTRUCTIONS (JCODE.md)" in combined
    assert "User rule B." in combined
    assert combined.index("PROJECT INSTRUCTIONS (JCODE.md)") < combined.index("USER INSTRUCTIONS (JCODE.md)")


def test_load_jcode_md_project_only(tmp_path):
    (tmp_path / "JCODE.md").write_text("Project only rule.", encoding="utf-8")
    combined = load_jcode_md(tmp_path)
    assert "PROJECT INSTRUCTIONS (JCODE.md)" in combined
    assert "USER INSTRUCTIONS (JCODE.md)" not in combined


def test_load_jcode_md_absent_returns_empty_string(tmp_path):
    assert load_jcode_md(tmp_path) == ""


# --- (d) JCODE.md content appears in the orchestrator/planner context (REQ-2) -----------------

def test_orchestrator_receives_jcode_md_preamble(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JCODE.md").write_text("Use snake_case for everything.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("do the thing")
    ctx = stub.calls[0]
    assert "PROJECT INSTRUCTIONS (JCODE.md)" in ctx["request"]
    assert "Use snake_case for everything." in ctx["request"]
    assert "do the thing" in ctx["request"]
    # JCODE.md precedes the request marker
    assert ctx["request"].index("PROJECT INSTRUCTIONS (JCODE.md)") < ctx["request"].index("(current request)")


def test_jcode_md_precedes_conversation_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JCODE.md").write_text("Project rule X.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("first turn")
    cli.handle("second turn")
    ctx = stub.calls[1]
    req = ctx["request"]
    assert req.index("PROJECT INSTRUCTIONS (JCODE.md)") < req.index("(recent conversation)")
    assert "Project rule X." in req


def test_nl_fix_receives_jcode_md_preamble(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JCODE.md").write_text("Always add docstrings.", encoding="utf-8")
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    assert "Always add docstrings." in seen_instructions[0]
    assert "PROJECT INSTRUCTIONS (JCODE.md)" in seen_instructions[0]
    assert "please fix something" in seen_instructions[0]


def test_jcode_md_loaded_once_per_session_not_per_keystroke(tmp_path, monkeypatch):
    """Cached on JcodeCli at construction (REQ-2) — mutating the file after construction must
    NOT change what subsequent turns see."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JCODE.md").write_text("version one", encoding="utf-8")
    cli, stub = _stub_cli()
    (tmp_path / "JCODE.md").write_text("version two", encoding="utf-8")   # changed after construction
    cli.handle("a request")
    assert "version one" in stub.calls[0]["request"]
    assert "version two" not in stub.calls[0]["request"]


def test_jcode_md_and_jaros_md_coexist(tmp_path, monkeypatch):
    """This spec is additive — an existing JAROS.md (EXT-036 REQ-17) keeps working unchanged
    alongside a new JCODE.md; both blocks appear."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Jaros rule.", encoding="utf-8")
    (tmp_path / "JCODE.md").write_text("Jcode rule.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("a request")
    req = stub.calls[0]["request"]
    assert "PROJECT INSTRUCTIONS (JCODE.md)" in req
    assert "Jcode rule." in req
    assert "PROJECT INSTRUCTIONS:" in req   # the JAROS.md block, unchanged
    assert "Jaros rule." in req


# --- (e) absent JCODE.md -> request unchanged (backward-compat no-op) -------------------------

def test_absent_jcode_md_leaves_request_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # no JCODE.md written here
    cli, stub = _stub_cli()
    cli.handle("solo request")
    ctx = stub.calls[0]
    assert ctx["request"] == "solo request"   # byte-identical, exactly like empty history
    assert "PROJECT INSTRUCTIONS (JCODE.md)" not in ctx["request"]


def test_absent_jcode_md_nl_fix_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    assert seen_instructions[0] == "please fix something"


def test_slash_command_output_unaffected_by_jcode_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JCODE.md").write_text("Some project rule.", encoding="utf-8")
    cli, _ = _stub_cli()
    out_with_md = cli.dispatch("/help")

    other = tmp_path.parent  # a directory with no JCODE.md
    monkeypatch.chdir(other)
    fresh = JcodeCli()
    out_without_md = fresh.dispatch("/help")
    assert out_with_md == out_without_md


# --- (f) init_jcode_md: the `/init` generator --------------------------------------------------

def test_init_jcode_md_writes_nonempty_file(tmp_path):
    result = init_jcode_md(tmp_path)
    target = tmp_path / "JCODE.md"
    assert target.is_file()
    assert target.read_text(encoding="utf-8").strip()
    assert str(target.resolve()) in result or "wrote" in result


def test_init_jcode_md_includes_structure_from_repo_map(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    init_jcode_md(tmp_path)
    content = (tmp_path / "JCODE.md").read_text(encoding="utf-8")
    assert "## Structure" in content
    assert "## How to run" in content


def test_init_jcode_md_does_not_clobber_existing(tmp_path):
    (tmp_path / "JCODE.md").write_text("MY CUSTOM INSTRUCTIONS", encoding="utf-8")
    result = init_jcode_md(tmp_path)
    assert (tmp_path / "JCODE.md").read_text(encoding="utf-8") == "MY CUSTOM INSTRUCTIONS"
    assert "already exists" in result


def test_init_jcode_md_never_raises_on_repo_map_failure(tmp_path, monkeypatch):
    import harness.repo_map as rm

    def _boom(root, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(rm, "build_repo_map", _boom)
    result = init_jcode_md(tmp_path)
    assert "wrote" in result
    assert (tmp_path / "JCODE.md").is_file()


def test_init_jcode_md_never_raises_on_bad_root():
    result = init_jcode_md("Z:\\definitely\\does\\not\\exist\\anywhere")
    assert isinstance(result, str)


# --- (g) /init CLI wiring ------------------------------------------------------------------

def test_slash_init_writes_jcode_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/init")
    assert (tmp_path / "JCODE.md").is_file()
    assert "wrote" in out


def test_slash_init_listed_in_help(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    assert "/init" in cli.dispatch("/help")
