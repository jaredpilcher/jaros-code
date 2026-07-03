"""EXT-036 TASK-8: TODO task management, user-facing (REQ-18).

OFFLINE — no live model. ``propose_tasks`` is exercised directly against a stub LLM client
(mirrors the shape ``.complete(LlmRequest) -> .text`` used by ``repo_memory.select_relevant``);
the CLI-wiring tests stub the orchestrator the same way as the other EXT-036 test files.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.task_store import add_task, list_tasks, propose_tasks, update_task


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
    """Mirrors the `.complete(LlmRequest) -> .text` shape propose_tasks() calls."""

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


# --- (a) add/list/update round-trip + per-repo isolation + status transitions ----------

def test_add_task_returns_task_with_stable_id(tmp_path):
    t = add_task("write the parser", root=tmp_path)
    assert t is not None
    assert t["text"] == "write the parser"
    assert t["status"] == "pending"
    assert t["id"]


def test_add_list_roundtrip(tmp_path):
    assert list_tasks(tmp_path) == []
    add_task("first task", root=tmp_path)
    add_task("second task", root=tmp_path)
    tasks = list_tasks(tmp_path)
    assert [t["text"] for t in tasks] == ["first task", "second task"]
    assert all(t["status"] == "pending" for t in tasks)


def test_add_task_empty_or_blank_is_noop(tmp_path):
    assert add_task("", root=tmp_path) is None
    assert add_task("   ", root=tmp_path) is None
    assert list_tasks(tmp_path) == []


def test_tasks_isolated_by_repo_root(tmp_path):
    root_a = tmp_path / "repo_a"
    root_b = tmp_path / "repo_b"
    root_a.mkdir()
    root_b.mkdir()
    add_task("task only for repo A", root=root_a)
    add_task("task only for repo B", root=root_b)
    assert [t["text"] for t in list_tasks(root_a)] == ["task only for repo A"]
    assert [t["text"] for t in list_tasks(root_b)] == ["task only for repo B"]


def test_status_transitions_pending_to_in_progress_to_done(tmp_path):
    t = add_task("ship the feature", root=tmp_path)
    tid = t["id"]
    updated = update_task(tid, root=tmp_path, status="in_progress")
    assert updated["status"] == "in_progress"
    assert list_tasks(tmp_path)[0]["status"] == "in_progress"
    updated = update_task(tid, root=tmp_path, status="done")
    assert updated["status"] == "done"
    assert list_tasks(tmp_path)[0]["status"] == "done"


def test_update_task_text(tmp_path):
    t = add_task("original text", root=tmp_path)
    updated = update_task(t["id"], root=tmp_path, text="revised text")
    assert updated["text"] == "revised text"
    assert list_tasks(tmp_path)[0]["text"] == "revised text"


def test_update_task_unknown_id_returns_none(tmp_path):
    add_task("some task", root=tmp_path)
    assert update_task("does-not-exist", root=tmp_path, status="done") is None


def test_update_task_invalid_status_returns_none(tmp_path):
    t = add_task("some task", root=tmp_path)
    assert update_task(t["id"], root=tmp_path, status="bogus") is None
    assert list_tasks(tmp_path)[0]["status"] == "pending"   # unchanged


def test_load_tasks_never_raises_on_corrupt_store(tmp_path):
    p = tmp_path / ".jaros"
    p.mkdir()
    (p / "tasks.jsonl").write_text(
        "not valid json\n{\"id\": \"abc\", \"text\": \"a good one\", \"status\": \"pending\"}\n",
        encoding="utf-8",
    )
    tasks = list_tasks(tmp_path)
    assert [t["text"] for t in tasks] == ["a good one"]


def test_list_tasks_absent_store_is_empty_list(tmp_path):
    assert list_tasks(tmp_path) == []


# --- (b) propose_tasks: stubbed breakdown, [] on unparseable (never fabricates) --------

def test_propose_tasks_returns_stubbed_breakdown():
    llm = _StubLlm('["set up the CLI parser", "add the arg validation", "write tests"]')
    tasks = propose_tasks("build a CLI tool", llm=llm)
    assert tasks == ["set up the CLI parser", "add the arg validation", "write tests"]
    assert len(llm.calls) == 1   # one narrow decomposition call


def test_propose_tasks_unparseable_returns_empty():
    llm = _StubLlm("Sure! Here's what you should do: first do X, then do Y.")
    assert propose_tasks("build a CLI tool", llm=llm) == []


def test_propose_tasks_non_list_json_returns_empty():
    llm = _StubLlm('{"not": "a list"}')
    assert propose_tasks("build a CLI tool", llm=llm) == []


def test_propose_tasks_model_failure_returns_empty():
    class _BoomLlm:
        def complete(self, request):
            raise RuntimeError("model unreachable")
    assert propose_tasks("build a CLI tool", llm=_BoomLlm()) == []


def test_propose_tasks_empty_request_never_calls_model():
    llm = _StubLlm('["a", "b"]')
    assert propose_tasks("", llm=llm) == []
    assert llm.calls == []


def test_propose_tasks_capped_to_six():
    items = [f"step {i}" for i in range(10)]
    import json as _json
    llm = _StubLlm(_json.dumps(items))
    tasks = propose_tasks("do a big thing", llm=llm)
    assert len(tasks) == 6
    assert tasks == items[:6]


# --- (c) CLI /task, /tasks, /task done|doing commands work ------------------------------

def test_cli_task_add_and_tasks_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/task write the parser")
    assert "added" in out.lower()
    listing = cli.dispatch("/tasks")
    assert "write the parser" in listing
    assert "pending" in listing


def test_cli_task_usage_message_on_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/task   ")
    assert "usage" in out.lower()


def test_cli_tasks_empty_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/tasks")
    assert "no tasks" in out.lower()


def test_cli_task_done_and_doing_update_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    from harness.task_store import list_tasks
    cli.dispatch("/task fix the bug")
    tid = list_tasks(".")[0]["id"]

    out = cli.dispatch(f"/task doing {tid}")
    assert "in_progress" in out
    assert list_tasks(".")[0]["status"] == "in_progress"

    out = cli.dispatch(f"/task done {tid}")
    assert "done" in out
    assert list_tasks(".")[0]["status"] == "done"


def test_cli_task_done_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/task done nope")
    assert "no task found" in out.lower()


def test_cli_task_done_without_id_is_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/task done")
    assert "usage" in out.lower()


# --- (d) slash commands unaffected -------------------------------------------------------

def test_slash_dispatch_never_invokes_task_proposal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    called: list[int] = []
    monkeypatch.setattr("harness.task_store.propose_tasks", lambda *a, **k: called.append(1) or [])
    cli, _ = _stub_cli()
    cli.dispatch("/task write the parser")
    cli.dispatch("/tasks")
    assert called == []   # /task and /tasks never trigger the model-proposal path


def test_slash_command_output_unaffected_by_stored_tasks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_task("some task", root=".")
    cli, _ = _stub_cli()
    out_with_tasks = cli.dispatch("/help")

    other = tmp_path.parent
    monkeypatch.chdir(other)
    fresh = JcodeCli()
    out_without_tasks = fresh.dispatch("/help")
    assert out_with_tasks == out_without_tasks
