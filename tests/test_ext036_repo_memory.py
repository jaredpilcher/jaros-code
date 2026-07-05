"""EXT-036 TASK-3: per-repo long-term memory + memory-AGENT recall (REQ-16).

OFFLINE — no live model. The memory-agent selection (`harness.repo_memory.select_relevant`)
is exercised two ways: directly against a stub LLM client (mirrors the shape
`.jaros-data/mem_experiment2.py` validated: a `.complete(LlmRequest)` -> `.text`), and — for
the CLI-wiring tests — monkeypatched at the module level (same pattern as
tests/test_ext036_cli_session.py's `_load_agent` stub) so `JcodeCli._recall_memory` picks up
the stub without ever calling a real model. The orchestrator is stubbed the same way as the
other EXT-036 test files.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.repo_memory import add_fact, load_facts, select_relevant


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


class _StubLlmResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubLlm:
    """Mirrors the `.complete(LlmRequest) -> .text` shape select_relevant() calls."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list = []

    def complete(self, request):
        self.calls.append(request)
        return _StubLlmResponse(self._text)


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors the other
    EXT-036 test files)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


# --- (a) add_fact -> load_facts round-trips + isolated by root -------------------------

def test_add_fact_load_facts_roundtrip(tmp_path):
    assert load_facts(tmp_path) == []
    assert add_fact("uses postgres via sqlalchemy", root=tmp_path) is True
    assert load_facts(tmp_path) == ["uses postgres via sqlalchemy"]
    add_fact("short codes must be exactly 8 characters", root=tmp_path)
    assert load_facts(tmp_path) == [
        "uses postgres via sqlalchemy",
        "short codes must be exactly 8 characters",
    ]


def test_add_fact_empty_or_blank_is_noop(tmp_path):
    assert add_fact("", root=tmp_path) is False
    assert add_fact("   ", root=tmp_path) is False
    assert load_facts(tmp_path) == []


def test_load_facts_absent_store_is_empty_list(tmp_path):
    assert load_facts(tmp_path) == []


def test_facts_isolated_by_repo_root(tmp_path):
    root_a = tmp_path / "repo_a"
    root_b = tmp_path / "repo_b"
    root_a.mkdir()
    root_b.mkdir()
    add_fact("fact only for repo A", root=root_a)
    add_fact("fact only for repo B", root=root_b)
    assert load_facts(root_a) == ["fact only for repo A"]
    assert load_facts(root_b) == ["fact only for repo B"]


def test_load_facts_bounded_to_cap(tmp_path):
    for i in range(10):
        add_fact(f"fact {i}", root=tmp_path)
    facts = load_facts(tmp_path, cap=3)
    assert facts == ["fact 7", "fact 8", "fact 9"]   # most recent `cap` kept


def test_load_facts_never_raises_on_corrupt_store(tmp_path):
    p = tmp_path / ".jaros"
    p.mkdir()
    (p / "memory.jsonl").write_text("not valid json\n{\"text\": \"a good one\"}\n", encoding="utf-8")
    assert load_facts(tmp_path) == ["a good one"]   # corrupt line skipped, good one kept


# --- (b) select_relevant: stubbed relevant subset, [] on unparseable -------------------

def test_select_relevant_returns_only_stubbed_subset():
    facts = ["fact0 irrelevant", "fact1 RELEVANT", "fact2 irrelevant", "fact3 RELEVANT"]
    llm = _StubLlm("1, 3")
    picked = select_relevant("some task", facts, llm=llm)
    assert picked == ["fact1 RELEVANT", "fact3 RELEVANT"]
    assert len(llm.calls) == 1   # one narrow selection call


def test_select_relevant_none_relevant_returns_empty():
    facts = ["fact a", "fact b"]
    llm = _StubLlm("none of these apply")
    assert select_relevant("some task", facts, llm=llm) == []


def test_select_relevant_unparseable_output_returns_empty():
    facts = ["fact a", "fact b"]
    llm = _StubLlm("I'm not sure how to answer that question.")
    # digits DO appear nowhere, or an out-of-range digit if they do -> never a dump of all facts
    assert select_relevant("some task", facts, llm=llm) == []


def test_select_relevant_out_of_range_numbers_ignored():
    facts = ["fact a", "fact b"]
    llm = _StubLlm("5, 9, 100")
    assert select_relevant("some task", facts, llm=llm) == []


def test_select_relevant_no_facts_never_calls_model():
    llm = _StubLlm("0")
    assert select_relevant("some task", [], llm=llm) == []
    assert llm.calls == []


def test_select_relevant_model_failure_returns_empty():
    class _BoomLlm:
        def complete(self, request):
            raise RuntimeError("model unreachable")
    assert select_relevant("some task", ["fact a"], llm=_BoomLlm()) == []


# --- (c) selected facts injected as RELEVANT MEMORY; empty selection = no-op -----------

def test_relevant_memory_injected_on_plain_turn(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("short codes must be exactly 8 characters", root=".")
    add_fact("charset is lowercase letters and digits only", root=".")
    seen_calls: list[tuple] = []

    def fake_select(request, facts, llm=None):
        seen_calls.append((request, list(facts)))
        return [facts[0]]   # select only the first fact

    monkeypatch.setattr("harness.repo_memory.select_relevant", fake_select)
    cli, stub = _stub_cli()
    cli.handle("write the code validator")
    ctx = stub.calls[0]
    assert "RELEVANT MEMORY:" in ctx["request"]
    assert "short codes must be exactly 8 characters" in ctx["request"]
    assert "charset is lowercase letters and digits only" not in ctx["request"]
    assert "write the code validator" in ctx["request"]
    assert seen_calls and seen_calls[0][0] == "write the code validator"


def test_relevant_memory_between_project_instructions_and_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "JAROS.md").write_text("Project rule Z.", encoding="utf-8")
    add_fact("fact X", root=".")
    monkeypatch.setattr("harness.repo_memory.select_relevant",
                         lambda request, facts, llm=None: list(facts[:1]))
    cli, stub = _stub_cli()
    cli.handle("first turn")
    cli.handle("second turn")
    req = stub.calls[1]["request"]
    assert req.index("PROJECT INSTRUCTIONS:") < req.index("RELEVANT MEMORY:") < req.index("(recent conversation)")


def test_empty_selection_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("an irrelevant fact", root=".")
    monkeypatch.setattr("harness.repo_memory.select_relevant",
                         lambda request, facts, llm=None: [])
    cli, stub = _stub_cli()
    cli.handle("solo request")
    ctx = stub.calls[0]
    assert ctx["request"] == "solo request"   # byte-identical — no injection at all
    assert "RELEVANT MEMORY" not in ctx["request"]


def test_no_stored_facts_never_calls_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # nothing remembered here
    called: list[int] = []
    monkeypatch.setattr("harness.repo_memory.select_relevant",
                         lambda *a, **k: called.append(1) or [])
    cli, stub = _stub_cli()
    cli.handle("solo request")
    assert called == []
    assert stub.calls[0]["request"] == "solo request"


def test_recall_guards_selection_exceptions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("some fact", root=".")

    def boom(request, facts, llm=None):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr("harness.repo_memory.select_relevant", boom)
    cli, stub = _stub_cli()
    out = cli.handle("solo request")   # must not raise
    assert out
    assert "RELEVANT MEMORY" not in stub.calls[0]["request"]


def test_nl_fix_receives_relevant_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("always add type hints on public functions", root=".")
    monkeypatch.setattr("harness.repo_memory.select_relevant",
                         lambda request, facts, llm=None: list(facts[:1]))
    cli, _ = _stub_cli(action="fix", arg="")
    seen_instructions: list[str] = []

    def fake_multi_file_fix(root, testcmd, instruction, test_file, max_iters=3, verbose=True):
        seen_instructions.append(instruction)
        return {"solved": True, "fixed": []}

    monkeypatch.setattr("harness.multi_file.multi_file_fix", fake_multi_file_fix)
    cli.handle("please fix something")
    assert "RELEVANT MEMORY:" in seen_instructions[0]
    assert "always add type hints on public functions" in seen_instructions[0]
    assert "please fix something" in seen_instructions[0]


# --- (d) /remember persists, /memory lists ----------------------------------------------

def test_remember_persists_fact_and_memory_lists_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/remember short codes must be exactly 8 characters")
    assert "remembered" in out.lower()
    assert load_facts(".") == ["short codes must be exactly 8 characters"]
    assert "short codes must be exactly 8 characters" in cli.repo_facts   # cache updated too

    listing = cli.dispatch("/memory")
    assert "short codes must be exactly 8 characters" in listing
    assert "long-term facts" in listing.lower()


def test_remember_empty_is_usage_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/remember   ")
    assert "usage" in out.lower()
    assert load_facts(".") == []


def test_memory_with_no_facts_has_no_long_term_section(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/memory")
    assert "long-term facts" not in out.lower()


# --- (e) EXT-042 REQ-5: /remember routes its .jcode/memory.md write through a real
#     code.write_file Decision (Tenet 1) --------------------------------------------------

def test_remember_writes_through_write_file_decision(tmp_path, monkeypatch):
    """The write really lands on disk end-to-end through the real Runtime/gate (no mocking of
    the write path itself) -- proves cmd_remember's Decision routing didn't silently no-op."""
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/remember prefer explicit over implicit")
    assert "remembered" in out.lower()
    assert (tmp_path / ".jcode" / "memory.md").is_file()
    assert "prefer explicit over implicit" in (tmp_path / ".jcode" / "memory.md").read_text(
        encoding="utf-8")


def test_remember_gate_rejection_is_honest_not_a_crash(tmp_path, monkeypatch):
    """A gate rejection from the write Decision degrades to an honest string, never a crash."""
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()

    class _RejectingRuntime:
        def apply(self, decision):
            raise RuntimeError("gate rejected code.write_file: refused path outside root")

    monkeypatch.setattr(cli, "_write_runtime", lambda: _RejectingRuntime())
    out = cli.dispatch("/remember this should be refused")
    assert "refused" in out.lower()
    assert not (tmp_path / ".jcode" / "memory.md").is_file()


# --- (e) slash commands unaffected -------------------------------------------------------

def test_slash_dispatch_never_invokes_memory_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("some fact", root=".")
    called: list[int] = []
    monkeypatch.setattr("harness.repo_memory.select_relevant",
                         lambda *a, **k: called.append(1) or [])
    cli, stub = _stub_cli()
    cli.handle("plain request")           # one recall call
    calls_before = len(called)
    cli.dispatch("/status")
    cli.dispatch("/ls .")
    assert len(called) == calls_before    # slash commands never trigger memory recall


def test_slash_command_output_unaffected_by_stored_facts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_fact("some fact", root=".")
    cli, _ = _stub_cli()
    out_with_facts = cli.dispatch("/help")

    other = tmp_path.parent
    monkeypatch.chdir(other)
    fresh = JcodeCli()
    out_without_facts = fresh.dispatch("/help")
    assert out_with_facts == out_without_facts
