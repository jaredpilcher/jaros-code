"""EXT-052: background runs surface (`jcode --bg` / `jobs` / `logs <id>` / `attach <id>` /
`stop <id>`, plus `/jobs` / `/logs <id>` / `/stop <id>` in the REPL).

OFFLINE and HERMETIC -- no live model, no real subprocess ever spawned or killed. Every test
points `JCODE_BG_JOBS_DIR` at an isolated `tmp_path` subdirectory (mirrors `harness.heartbeat`'s
`JCODE_HEARTBEAT_DIR` env-override precedent) and monkeypatches `harness.bg_jobs._spawn_worker` /
`_kill_pid_tree` / `_pid_alive` so nothing here ever starts or terminates a real OS process.
"""
from __future__ import annotations

import json

import pytest

from harness import bg_jobs
from harness.cli import JcodeCli, _dispatch_bg_subcommand


@pytest.fixture(autouse=True)
def _isolate_jobs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JCODE_BG_JOBS_DIR", str(tmp_path / "bg_jobs"))
    yield


@pytest.fixture()
def no_real_spawn(monkeypatch):
    """submit_job() never actually spawns a subprocess -- records THIS test process's own pid
    instead (so `_pid_alive` honestly reports "alive" for a "running" job without needing a real
    child process; `no_real_kill` below then guarantees this real pytest process is never
    actually sent a kill signal by a `stop_job` test)."""
    import os as _os

    def _fake_spawn(job_id, log_path):
        return _os.getpid()
    monkeypatch.setattr(bg_jobs, "_spawn_worker", _fake_spawn)
    return _fake_spawn


@pytest.fixture()
def no_real_kill(monkeypatch):
    """stop_job() never actually sends a kill signal -- records the call instead."""
    calls: "list[int]" = []
    monkeypatch.setattr(bg_jobs, "_kill_pid_tree", lambda pid: calls.append(pid))
    return calls


# --- submit_job / list_jobs / get_job ---------------------------------------------------

def test_submit_job_creates_record_and_returns_id(no_real_spawn):
    rec = bg_jobs.submit_job("do the thing")
    assert rec.id
    assert rec.request == "do the thing"
    assert rec.status == "running"
    assert isinstance(rec.pid, int) and rec.pid > 0  # a real, live pid (this test process itself)
    # persisted to disk
    reloaded = bg_jobs.get_job(rec.id)
    assert reloaded is not None
    assert reloaded.request == "do the thing"


def test_list_jobs_includes_submitted_job(no_real_spawn):
    rec = bg_jobs.submit_job("build a widget")
    jobs = bg_jobs.list_jobs()
    assert any(j.id == rec.id for j in jobs)


def test_list_jobs_empty_state_is_clean():
    assert bg_jobs.list_jobs() == []
    assert "no background jobs" in bg_jobs.format_jobs().lower()


def test_finished_job_shows_done_and_logs_readable(no_real_spawn):
    rec = bg_jobs.submit_job("run the suite")
    # Simulate what the real worker (harness.bg_worker) does on completion.
    from pathlib import Path
    Path(rec.log_path).write_text("suite passed: 42/42\n", encoding="utf-8")
    bg_jobs.mark_finished(rec.id, exit_code=0)

    updated = bg_jobs.get_job(rec.id)
    assert updated.status == "done"
    assert updated.exit_code == 0
    assert updated.ended_at is not None

    log = bg_jobs.read_log(rec.id)
    assert "suite passed: 42/42" in log


def test_mark_finished_nonzero_exit_is_failed(no_real_spawn):
    rec = bg_jobs.submit_job("break something")
    bg_jobs.mark_finished(rec.id, exit_code=1)
    updated = bg_jobs.get_job(rec.id)
    assert updated.status == "failed"
    assert updated.exit_code == 1


def test_mark_finished_unknown_job_is_a_noop():
    bg_jobs.mark_finished("doesnotexist", exit_code=0)  # must not raise


def test_reconcile_downgrades_dead_running_job_to_failed(no_real_spawn, monkeypatch):
    rec = bg_jobs.submit_job("orphaned work")
    assert rec.status == "running"
    # Simulate the worker process having died without ever calling mark_finished.
    monkeypatch.setattr(bg_jobs, "_pid_alive", lambda pid: False)
    reconciled = bg_jobs.get_job(rec.id)
    assert reconciled.status == "failed"
    # And list_jobs() reflects the same honest downgrade.
    assert bg_jobs.list_jobs()[0].status == "failed"


# --- stop_job ----------------------------------------------------------------------------

def test_stop_job_running_marks_stopped_and_kills_recorded_pid_only(no_real_spawn, no_real_kill):
    rec = bg_jobs.submit_job("long build")
    result = bg_jobs.stop_job(rec.id)
    assert result["ok"] is True
    assert result["job"].status == "stopped"
    assert no_real_kill == [rec.pid]  # exactly the recorded pid, never a name-based kill

    updated = bg_jobs.get_job(rec.id)
    assert updated.status == "stopped"


def test_stop_job_not_running_refuses_without_killing(no_real_spawn, no_real_kill):
    rec = bg_jobs.submit_job("quick job")
    bg_jobs.mark_finished(rec.id, exit_code=0)
    result = bg_jobs.stop_job(rec.id)
    assert result["ok"] is False
    assert "not running" in result["message"]
    assert no_real_kill == []  # never sent a kill signal to an already-finished job


def test_stop_job_unknown_id_is_honest_error(no_real_kill):
    result = bg_jobs.stop_job("bogus1234")
    assert result["ok"] is False
    assert "unknown job" in result["message"]
    assert no_real_kill == []


# --- read_log / get_job / list_jobs on unknown ids -- never crash -----------------------

def test_get_job_unknown_id_returns_none():
    assert bg_jobs.get_job("bogus1234") is None


def test_read_log_unknown_id_is_honest_message():
    msg = bg_jobs.read_log("bogus1234")
    assert "no such job" in msg


def test_malformed_job_file_is_skipped(tmp_path):
    jobs_dir = bg_jobs._jobs_dir()
    (jobs_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
    assert bg_jobs.list_jobs() == []  # skipped, never raises


# --- attach_job --------------------------------------------------------------------------

def test_attach_already_finished_job_returns_immediately_no_sleep(no_real_spawn):
    rec = bg_jobs.submit_job("already done")
    from pathlib import Path
    Path(rec.log_path).write_text("all done\n", encoding="utf-8")
    bg_jobs.mark_finished(rec.id, exit_code=0)

    sleep_calls = []
    printed = []
    code = bg_jobs.attach_job(rec.id, sleep_fn=lambda s: sleep_calls.append(s),
                               print_fn=lambda *a, **k: printed.append("".join(str(x) for x in a)))
    assert code == 0
    assert sleep_calls == []  # already finished -- exits after exactly one read, no sleep
    assert any("all done" in p for p in printed)
    assert any("finished" in p for p in printed)


def test_attach_unknown_job_is_honest_error():
    printed = []
    code = bg_jobs.attach_job("bogus1234", print_fn=lambda *a, **k: printed.append(str(a)))
    assert code == 1
    assert any("unknown job" in p for p in printed)


def test_attach_keyboard_interrupt_detaches_without_stopping(no_real_spawn, no_real_kill):
    rec = bg_jobs.submit_job("still running")  # status stays "running" (no mark_finished)

    def _raise_interrupt(_s):
        raise KeyboardInterrupt

    printed = []
    code = bg_jobs.attach_job(rec.id, sleep_fn=_raise_interrupt,
                               print_fn=lambda *a, **k: printed.append("".join(str(x) for x in a)))
    assert code == 0
    assert any("detached" in p for p in printed)
    assert no_real_kill == []  # a detach must NEVER stop the job

    still_running = bg_jobs.get_job(rec.id)
    assert still_running.status == "running"


# --- harness.cli wiring: _dispatch_bg_subcommand ------------------------------------------

def test_dispatch_bg_submit(monkeypatch, capsys):
    fake_rec = bg_jobs.JobRecord(id="abc12345", request="do stuff", status="running",
                                  pid=4242, started_at=0.0, ended_at=None, log_path="x.log")
    monkeypatch.setattr(bg_jobs, "submit_job", lambda req: fake_rec)
    code = _dispatch_bg_subcommand(["--bg", "do", "stuff"])
    assert code == 0
    out = capsys.readouterr().out
    assert "abc12345" in out


def test_dispatch_bg_submit_empty_request_is_refused(capsys):
    code = _dispatch_bg_subcommand(["--bg"])
    assert code == 1
    assert "error" in capsys.readouterr().out.lower()


def test_dispatch_jobs_bare_and_bg_list_alias(monkeypatch, capsys):
    monkeypatch.setattr(bg_jobs, "format_jobs", lambda: "JOBS-TABLE")
    assert _dispatch_bg_subcommand(["jobs"]) == 0
    assert "JOBS-TABLE" in capsys.readouterr().out
    assert _dispatch_bg_subcommand(["bg", "list"]) == 0
    assert "JOBS-TABLE" in capsys.readouterr().out


def test_dispatch_logs(monkeypatch, capsys):
    monkeypatch.setattr(bg_jobs, "read_log", lambda jid: f"LOG-FOR-{jid}")
    assert _dispatch_bg_subcommand(["logs", "abc12345"]) == 0
    assert "LOG-FOR-abc12345" in capsys.readouterr().out


def test_dispatch_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(bg_jobs, "attach_job", lambda jid: calls.append(jid) or 0)
    assert _dispatch_bg_subcommand(["attach", "abc12345"]) == 0
    assert calls == ["abc12345"]


def test_dispatch_stop(monkeypatch, capsys):
    monkeypatch.setattr(bg_jobs, "stop_job", lambda jid: {"ok": True, "message": f"stopped {jid}"})
    assert _dispatch_bg_subcommand(["stop", "abc12345"]) == 0
    assert "stopped abc12345" in capsys.readouterr().out


def test_dispatch_stop_not_ok_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(bg_jobs, "stop_job", lambda jid: {"ok": False, "message": "nope"})
    assert _dispatch_bg_subcommand(["stop", "abc12345"]) == 1


def test_dispatch_returns_none_for_ordinary_plain_request():
    assert _dispatch_bg_subcommand(["fix", "the", "bug", "in", "foo.py"]) is None


def test_dispatch_returns_none_for_empty_args():
    assert _dispatch_bg_subcommand([]) is None


# --- JcodeCli REPL commands (/jobs, /logs, /stop) ----------------------------------------

def test_cmd_jobs_renders(monkeypatch):
    cli = JcodeCli.__new__(JcodeCli)  # avoid full __init__ (no model/Runtime needed)
    monkeypatch.setattr(bg_jobs, "format_jobs", lambda: "TABLE-HERE")
    assert cli.cmd_jobs("") == "TABLE-HERE"


def test_cmd_logs_delegates(monkeypatch):
    cli = JcodeCli.__new__(JcodeCli)
    monkeypatch.setattr(bg_jobs, "read_log", lambda jid: f"LOG:{jid}")
    assert cli.cmd_logs("abc12345") == "LOG:abc12345"


def test_cmd_logs_no_arg_is_usage_message():
    cli = JcodeCli.__new__(JcodeCli)
    assert "usage" in cli.cmd_logs("").lower()


def test_cmd_stop_delegates(monkeypatch):
    cli = JcodeCli.__new__(JcodeCli)
    monkeypatch.setattr(bg_jobs, "stop_job", lambda jid: {"ok": True, "message": f"stopped {jid}"})
    assert cli.cmd_stop("abc12345") == "stopped abc12345"


def test_cmd_stop_no_arg_is_usage_message():
    cli = JcodeCli.__new__(JcodeCli)
    assert "usage" in cli.cmd_stop("").lower()


# --- bg_worker.py --------------------------------------------------------------------------

def test_bg_worker_runs_one_shot_and_marks_finished(no_real_spawn, monkeypatch):
    rec = bg_jobs.submit_job("worker test request")

    def _fake_one_shot(request, session_id, output_format, max_turns):
        assert request == "worker test request"
        return "the response text", 0

    import harness.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_run_one_shot", _fake_one_shot)

    from harness import bg_worker
    code = bg_worker.main([rec.id])
    assert code == 0

    updated = bg_jobs.get_job(rec.id)
    assert updated.status == "done"
    assert updated.exit_code == 0


def test_bg_worker_unknown_job_reports_error(capsys):
    from harness import bg_worker
    code = bg_worker.main(["bogus1234"])
    assert code == 1
    assert "unknown job" in capsys.readouterr().err


def test_bg_worker_exception_marks_failed(no_real_spawn, monkeypatch):
    rec = bg_jobs.submit_job("will crash")

    def _raise(*a, **k):
        raise RuntimeError("boom")

    import harness.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_run_one_shot", _raise)

    from harness import bg_worker
    code = bg_worker.main([rec.id])
    assert code == 1
    assert bg_jobs.get_job(rec.id).status == "failed"
