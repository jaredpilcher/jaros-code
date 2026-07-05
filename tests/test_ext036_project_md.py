"""EXT-036 TASK-2: JAROS.md — per-repo project instructions auto-injected every prompt (REQ-17).

OFFLINE — no live model. The orchestrator agent is stubbed via `cli._load_agent` (same
pattern as tests/test_ext036_cli_session.py); the NL-fix path is exercised by monkeypatching
harness.multi_file.multi_file_fix. `JcodeCli.__init__` loads JAROS.md from the CURRENT
working directory, so tests that need a JAROS.md present chdir into a tmp_path first.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.project_md import MAX_CHARS, load_project_md


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
    test_ext036_cli_session.py)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


# --- (a) load_project_md: read + bound + absent-returns-"" -----------------------------

def test_load_project_md_reads_repo_root_jaros_md(tmp_path):
    (tmp_path / "JAROS.md").write_text("Always use type hints.\nPrefer pathlib.\n", encoding="utf-8")
    text = load_project_md(tmp_path)
    assert "Always use type hints." in text
    assert "Prefer pathlib." in text


def test_load_project_md_falls_back_to_dot_jaros_dir(tmp_path):
    (tmp_path / ".jaros").mkdir()
    (tmp_path / ".jaros" / "JAROS.md").write_text("Fallback-location instructions.", encoding="utf-8")
    text = load_project_md(tmp_path)
    assert "Fallback-location instructions." in text


def test_load_project_md_prefers_root_over_fallback(tmp_path):
    (tmp_path / "JAROS.md").write_text("root wins", encoding="utf-8")
    (tmp_path / ".jaros").mkdir()
    (tmp_path / ".jaros" / "JAROS.md").write_text("fallback loses", encoding="utf-8")
    assert load_project_md(tmp_path) == "root wins"


def test_load_project_md_bounds_long_content(tmp_path):
    (tmp_path / "JAROS.md").write_text("x" * (MAX_CHARS + 500), encoding="utf-8")
    text = load_project_md(tmp_path)
    assert len(text) <= MAX_CHARS + len("...")
    assert text.startswith("x" * 50)


def test_load_project_md_absent_returns_empty_string(tmp_path):
    assert load_project_md(tmp_path) == ""


def test_load_project_md_never_raises_on_unreadable_dir():
    assert load_project_md("Z:\\definitely\\does\\not\\exist\\anywhere") == ""


# --- (b) JAROS.md content appears in the request on a plain-language turn --------------

def test_orchestrator_receives_project_md_preamble(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Use snake_case for everything.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("do the thing")
    ctx = stub.calls[0]
    assert "PROJECT INSTRUCTIONS:" in ctx["request"]
    assert "Use snake_case for everything." in ctx["request"]
    assert "do the thing" in ctx["request"]
    # PROJECT INSTRUCTIONS precede the request marker
    assert ctx["request"].index("PROJECT INSTRUCTIONS:") < ctx["request"].index("(current request)")


def test_project_md_precedes_conversation_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Project rule X.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("first turn")
    cli.handle("second turn")
    ctx = stub.calls[1]
    req = ctx["request"]
    assert req.index("PROJECT INSTRUCTIONS:") < req.index("(recent conversation)")
    assert "Project rule X." in req
    assert "first turn" in req


def test_nl_fix_receives_project_md_preamble(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Always add docstrings.", encoding="utf-8")
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True,
                            runtime=None):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    assert "Always add docstrings." in seen_instructions[0]
    assert "PROJECT INSTRUCTIONS:" in seen_instructions[0]
    assert "please fix something" in seen_instructions[0]


def test_project_md_loaded_once_per_session_not_per_keystroke(tmp_path, monkeypatch):
    """Cached on JcodeCli at construction (REQ-17 step 2) — mutating the file after
    construction must NOT change what subsequent turns see."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("version one", encoding="utf-8")
    cli, stub = _stub_cli()
    (tmp_path / "JAROS.md").write_text("version two", encoding="utf-8")   # changed after construction
    cli.handle("a request")
    assert "version one" in stub.calls[0]["request"]
    assert "version two" not in stub.calls[0]["request"]


# --- (c) absent JAROS.md -> request unchanged (no-op) -----------------------------------

def test_absent_project_md_leaves_request_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # no JAROS.md written here
    cli, stub = _stub_cli()
    cli.handle("solo request")
    ctx = stub.calls[0]
    assert ctx["request"] == "solo request"   # byte-identical, exactly like empty history
    assert "PROJECT INSTRUCTIONS" not in ctx["request"]


def test_absent_project_md_nl_fix_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True,
                            runtime=None):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    assert seen_instructions[0] == "please fix something"


# --- (d) slash commands unaffected -------------------------------------------------------

def test_slash_command_output_unaffected_by_project_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Some project rule.", encoding="utf-8")
    cli, _ = _stub_cli()
    out_with_md = cli.dispatch("/help")

    other = tmp_path.parent  # a directory with no JAROS.md
    monkeypatch.chdir(other)
    fresh = JcodeCli()
    out_without_md = fresh.dispatch("/help")
    assert out_with_md == out_without_md


def test_slash_dispatch_never_invokes_the_orchestrator_with_project_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Some project rule.", encoding="utf-8")
    cli, stub = _stub_cli()
    cli.handle("plain request")   # invokes the orchestrator once
    calls_before = len(stub.calls)
    cli.dispatch("/status")
    cli.dispatch("/ls .")
    assert len(stub.calls) == calls_before   # slash commands stay direct/stateless
