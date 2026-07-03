"""EXT-036 TASK-9: Experiment management, user-facing (REQ-19).

OFFLINE — no model needed at all (TASK-9 has no model judgment, unlike TASK-8's
propose_tasks). ``run_experiment`` executes REAL, trivial subprocess commands
(``python -c "import sys; sys.exit(0)"`` / ``...sys.exit(1)``) so the pass/fail exit code
recorded is genuinely the subprocess result, never invented.
"""

from __future__ import annotations

import sys

import pytest

from harness.cli import JcodeCli
from harness.experiment_store import define_experiment, list_experiments, run_experiment

PASS_CMD = f'"{sys.executable}" -c "import sys; sys.exit(0)"'
FAIL_CMD = f'"{sys.executable}" -c "import sys; sys.exit(1)"'
HANG_CMD = f'"{sys.executable}" -c "import time; time.sleep(30)"'


class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
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
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors the other
    EXT-036 test files)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


# --- (a) define/list/run round-trip + per-repo isolation --------------------------------

def test_define_experiment_returns_record_with_stable_id(tmp_path):
    e = define_experiment("the parser handles empty input", PASS_CMD, root=tmp_path)
    assert e is not None
    assert e["hypothesis"] == "the parser handles empty input"
    assert e["run_cmd"] == PASS_CMD
    assert e["status"] == "defined"
    assert e["id"]


def test_define_list_roundtrip(tmp_path):
    assert list_experiments(tmp_path) == []
    define_experiment("hyp one", PASS_CMD, root=tmp_path)
    define_experiment("hyp two", PASS_CMD, root=tmp_path)
    exps = list_experiments(tmp_path)
    assert [e["hypothesis"] for e in exps] == ["hyp one", "hyp two"]
    assert all(e["status"] == "defined" for e in exps)


def test_define_experiment_blank_hypothesis_or_cmd_is_noop(tmp_path):
    assert define_experiment("", PASS_CMD, root=tmp_path) is None
    assert define_experiment("hyp", "", root=tmp_path) is None
    assert define_experiment("   ", PASS_CMD, root=tmp_path) is None
    assert list_experiments(tmp_path) == []


def test_experiments_isolated_by_repo_root(tmp_path):
    root_a = tmp_path / "repo_a"
    root_b = tmp_path / "repo_b"
    root_a.mkdir()
    root_b.mkdir()
    define_experiment("only for A", PASS_CMD, root=root_a)
    define_experiment("only for B", PASS_CMD, root=root_b)
    assert [e["hypothesis"] for e in list_experiments(root_a)] == ["only for A"]
    assert [e["hypothesis"] for e in list_experiments(root_b)] == ["only for B"]


def test_run_experiment_round_trips_into_store(tmp_path):
    e = define_experiment("passes", PASS_CMD, root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path)
    assert ran is not None
    assert ran["status"] == "run"
    assert ran["exit_code"] == 0
    stored = list_experiments(tmp_path)[0]
    assert stored["status"] == "run"
    assert stored["exit_code"] == 0


def test_run_experiment_unknown_id_returns_none(tmp_path):
    define_experiment("some hyp", PASS_CMD, root=tmp_path)
    assert run_experiment("does-not-exist", root=tmp_path) is None


def test_list_experiments_absent_store_is_empty_list(tmp_path):
    assert list_experiments(tmp_path) == []


def test_load_experiments_never_raises_on_corrupt_store(tmp_path):
    p = tmp_path / ".jaros"
    p.mkdir()
    (p / "experiments.jsonl").write_text(
        "not valid json\n"
        '{"id": "abc", "hypothesis": "a good one", "run_cmd": "echo hi", "status": "defined"}\n',
        encoding="utf-8",
    )
    exps = list_experiments(tmp_path)
    assert [e["hypothesis"] for e in exps] == ["a good one"]


# --- (b) a passing run_cmd records exit_code 0, a failing one records non-zero (REAL) ----

def test_passing_run_cmd_records_real_exit_code_zero(tmp_path):
    e = define_experiment("this should pass", PASS_CMD, root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path)
    assert ran["exit_code"] == 0
    assert ran["status"] == "run"


def test_failing_run_cmd_records_real_nonzero_exit_code(tmp_path):
    e = define_experiment("this should fail", FAIL_CMD, root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path)
    assert ran["exit_code"] != 0
    assert ran["exit_code"] == 1
    assert ran["status"] == "run"   # honestly recorded as run, NOT silently upgraded to a pass


def test_run_output_is_bounded(tmp_path):
    big_output_cmd = (
        f'"{sys.executable}" -c "import sys; sys.stdout.write(\'x\' * 20000); sys.exit(0)"'
    )
    e = define_experiment("big output", big_output_cmd, root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path)
    from harness.experiment_store import MAX_OUTPUT_CHARS
    assert len(ran["output"]) <= MAX_OUTPUT_CHARS


# --- (c) run guards a bad/hanging cmd (short timeout) without raising --------------------

def test_run_experiment_hanging_command_times_out_without_raising(tmp_path):
    e = define_experiment("hangs forever", HANG_CMD, root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path, timeout=1)
    assert ran is not None
    assert ran["exit_code"] != 0   # a real guard failure, never fabricated as a pass
    assert "timed out" in ran["output"].lower()


def test_run_experiment_bad_command_does_not_raise(tmp_path):
    e = define_experiment("bogus command", "this-command-does-not-exist-xyz123", root=tmp_path)
    ran = run_experiment(e["id"], root=tmp_path)
    assert ran is not None
    assert ran["exit_code"] != 0


# --- (d) CLI commands work ----------------------------------------------------------------

def test_cli_experiment_define_and_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch(f"/experiment the parser handles empty input :: {PASS_CMD}")
    assert "defined" in out.lower()
    listing = cli.dispatch("/experiments")
    assert "the parser handles empty input" in listing
    assert "defined" in listing


def test_cli_experiment_usage_message_on_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/experiment   ")
    assert "usage" in out.lower()


def test_cli_experiments_empty_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/experiments")
    assert "no experiments" in out.lower()


def test_cli_experiment_run_reports_real_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    cli.dispatch(f"/experiment fails on purpose :: {FAIL_CMD}")
    from harness.experiment_store import list_experiments as _list
    exp_id = _list(".")[0]["id"]

    out = cli.dispatch(f"/experiment run {exp_id}")
    assert "exit_code=1" in out

    listing = cli.dispatch("/experiments")
    assert "run" in listing
    assert "exit_code=1" in listing


def test_cli_experiment_run_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/experiment run nope")
    assert "no experiment found" in out.lower()


def test_cli_experiment_run_without_id_is_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _ = _stub_cli()
    out = cli.dispatch("/experiment run")
    assert "usage" in out.lower()


# --- (e) slash commands unaffected --------------------------------------------------------

def test_slash_dispatch_never_touches_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, stub = _stub_cli()
    cli.dispatch(f"/experiment hyp :: {PASS_CMD}")
    cli.dispatch("/experiments")
    from harness.experiment_store import list_experiments as _list
    exp_id = _list(".")[0]["id"]
    cli.dispatch(f"/experiment run {exp_id}")
    assert stub.calls == []   # experiment commands never invoke the orchestrator/model


def test_slash_command_output_unaffected_by_stored_experiments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    define_experiment("some hyp", PASS_CMD, root=".")
    cli, _ = _stub_cli()
    out_with_experiments = cli.dispatch("/help")

    other = tmp_path.parent
    monkeypatch.chdir(other)
    fresh = JcodeCli()
    out_without_experiments = fresh.dispatch("/help")
    assert out_with_experiments == out_without_experiments
