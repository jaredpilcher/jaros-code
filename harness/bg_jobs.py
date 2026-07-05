"""Background job store (EXT-052) -- the durable, deterministic bookkeeping half of the
"background runs surface" (`docs/GAP-MAP.md` Product-surface parity row #23).

A background job is a durable RECORD (id, request, status, pid, started/ended, log path, exit
code) persisted in `.jaros-data/bg_jobs/` -- internal runtime state, exactly like the session
store (`harness/session.py`) or the heartbeat trail (`harness/heartbeat.py`), NOT a host-project
write. Submission, listing, log-reading, and stop are pure execution-plane bookkeeping (Tenet 1):
no model call anywhere in this module.

The job's OWN work is intentionally NOT this module's concern: `harness/bg_worker.py` runs the
EXISTING, UNCHANGED EXT-043 `harness.cli._run_one_shot` as the unit of work, out-of-process, so
any host-project write a backgrounded request performs still passes through the real gated
`code.write_file` Decision exactly as a foreground run would -- backgrounding only changes WHERE
the work runs, never what safety gates it passes through.

Process spawn/kill mirrors the repo's existing tree-kill discipline
(`harness.secure_exec._kill_tree` / `.jaros-data/tools/shell_exec_tool.py::_kill_tree`) rather than
inventing a new one -- adapted here to operate on a bare recorded ``pid`` (a job record crosses
process boundaries: by the time `stop_job`/`list_jobs` run, in a brand-new CLI invocation, there is
no live ``Popen`` handle left to call ``.pid`` on). Never kill-by-name -- only the one recorded pid
(and its process-group descendants) is ever targeted.
"""
from __future__ import annotations

import dataclasses
import glob as _glob
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# #EXT-052-REQ-1 Start

VALID_STATUSES = ("running", "done", "failed", "stopped")


@dataclass(frozen=True)
class JobRecord:
    """One durable background-job record."""

    id: str
    request: str
    status: str          # one of VALID_STATUSES
    pid: "int | None"
    started_at: float
    ended_at: "float | None"
    log_path: str
    exit_code: "int | None" = None


def _jobs_dir() -> Path:
    """Resolve the jobs directory, overridable via ``JCODE_BG_JOBS_DIR`` (mirrors
    ``harness.heartbeat``'s ``JCODE_HEARTBEAT_DIR`` env-override precedent) so tests are fully
    hermetic. Never raises -- a `mkdir` failure just means later reads/writes degrade honestly."""
    d = Path(os.environ.get("JCODE_BG_JOBS_DIR", ".jaros-data/bg_jobs"))
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _job_path(job_id: str) -> Path:
    return _jobs_dir() / f"{job_id}.json"


def _log_path_for(job_id: str) -> Path:
    return _jobs_dir() / f"{job_id}.log"


def _new_job_id() -> str:
    """An 8-char lowercase-hex id -- short, URL/shell-safe, and deliberately shaped so it can
    never plausibly collide with ordinary natural-language request text (see design.md's
    reserved-bare-subcommand-words note). Retries on the vanishingly rare collision."""
    for _ in range(50):
        jid = secrets.token_hex(4)
        if not _job_path(jid).exists():
            return jid
    return secrets.token_hex(8)  # pragma: no cover -- astronomically unlikely fallback


def _read_record(job_id: str) -> "JobRecord | None":
    """Load a job record. Never raises -- a missing/malformed file is honestly ``None``."""
    try:
        path = _job_path(job_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return JobRecord(
            id=str(data.get("id", job_id)),
            request=str(data.get("request", "")),
            status=str(data.get("status", "failed")),
            pid=data.get("pid"),
            started_at=float(data.get("started_at", 0.0)),
            ended_at=data.get("ended_at"),
            log_path=str(data.get("log_path", "")),
            exit_code=data.get("exit_code"),
        )
    except Exception:
        return None


def _write_record(rec: JobRecord) -> None:
    """Persist a job record. Never raises -- a write failure degrades silently (mirrors
    ``harness.heartbeat.beat``'s "observability must never break the thing it observes")."""
    try:
        _job_path(rec.id).write_text(json.dumps(dataclasses.asdict(rec), indent=2), encoding="utf-8")
    except Exception:
        pass


def _pid_alive(pid: "int | None") -> bool:
    """Best-effort liveness check, guarded per-OS (mirrors
    ``tests/test_ext005_proc_treekill.py::_pid_alive``). Never raises."""
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                f'tasklist /FI "PID eq {pid}"', shell=True,
                capture_output=True, text=True,
            ).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _kill_pid_tree(pid: int) -> None:
    """Kill *pid* AND its descendants. Mirrors ``harness.secure_exec._kill_tree`` /
    ``.jaros-data/tools/shell_exec_tool.py::_kill_tree`` exactly (the same choke point, not a
    divergent copy) -- adapted to a bare recorded pid rather than a live ``Popen`` object, since a
    background job's record crosses process boundaries (``stop_job`` typically runs in a brand new
    CLI invocation, not the one that spawned the worker). Never kill-by-name -- only this one pid
    (and its process-group descendants) is ever targeted."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL if sys.platform != "win32" else 9)
        except Exception:
            pass


def _spawn_worker(job_id: str, log_path: Path) -> int:
    """Spawn the detached worker process for *job_id*. A separately-named function so tests can
    monkeypatch it to a fast stub -- never spawning a real long-lived process in the suite.

    Uses plain ``subprocess.Popen`` -- the same primitive already used throughout this repo
    (``harness/secure_exec.py``, ``harness/run_with_heartbeat.py``,
    ``.jaros-data/tools/shell_exec_tool.py``) -- with the FULL inherited environment (this is our
    OWN trusted `jcode` invocation, not model-generated code; scrubbing it would silently make a
    backgrounded run behave differently from the same request run in the foreground -- see
    design.md) and ``start_new_session``/``CREATE_NEW_PROCESS_GROUP`` so the child becomes its own
    process-group/tree root, the precondition ``_kill_pid_tree`` relies on.
    """
    cmd = [sys.executable, "-m", "harness.bg_worker", job_id]
    log_fh = open(log_path, "a", encoding="utf-8")
    try:
        kwargs: dict = dict(cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT,
                             env=os.environ.copy())
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        return proc.pid
    finally:
        log_fh.close()


def submit_job(request: str) -> JobRecord:
    """Submit *request* to run detached; returns the new ``JobRecord`` (with a real pid unless
    the spawn itself failed, in which case ``status="failed"`` is persisted rather than raising).
    The record is persisted BEFORE spawning so a crash-during-spawn is still observable."""
    request = str(request or "").strip()
    job_id = _new_job_id()
    log_path = _log_path_for(job_id)
    now = time.time()
    rec = JobRecord(id=job_id, request=request, status="running", pid=None,
                     started_at=now, ended_at=None, log_path=str(log_path), exit_code=None)
    _write_record(rec)
    try:
        pid = _spawn_worker(job_id, log_path)
        rec = dataclasses.replace(rec, pid=pid)
        _write_record(rec)
    except Exception as exc:
        rec = dataclasses.replace(rec, status="failed", ended_at=time.time())
        _write_record(rec)
        try:
            log_path.write_text(f"error: failed to spawn background worker: {exc}\n",
                                 encoding="utf-8")
        except Exception:
            pass
    return rec


def mark_finished(job_id: str, *, exit_code: int) -> None:
    """Called by the worker process itself on completion (a self-reporting pattern, since the
    submitting process is typically long gone by the time the job finishes). A no-op for an
    unknown job id -- never raises."""
    rec = _read_record(job_id)
    if rec is None:
        return
    status = "done" if exit_code == 0 else "failed"
    rec = dataclasses.replace(rec, status=status, ended_at=time.time(), exit_code=exit_code)
    _write_record(rec)


def _reconcile(rec: JobRecord) -> JobRecord:
    """A ``"running"`` record whose pid is no longer alive means the worker crashed before it
    could call ``mark_finished`` -- honestly downgraded to ``"failed"`` here (never left as a
    permanent false "running" ghost). Any other status passes through unchanged."""
    if rec.status == "running" and not _pid_alive(rec.pid):
        rec = dataclasses.replace(rec, status="failed", ended_at=time.time())
        _write_record(rec)
    return rec


def get_job(job_id: str) -> "JobRecord | None":
    """Look up one job by id, reconciled. ``None`` for an unknown id -- never raises."""
    rec = _read_record(job_id)
    if rec is None:
        return None
    return _reconcile(rec)


def list_jobs() -> "list[JobRecord]":
    """Every persisted job, reconciled, newest-first. An empty/absent jobs dir yields ``[]``; a
    malformed record file is skipped rather than aborting the whole listing."""
    out: "list[JobRecord]" = []
    try:
        paths = _glob.glob(str(_jobs_dir() / "*.json"))
    except Exception:
        paths = []
    for p in paths:
        job_id = Path(p).stem
        rec = _read_record(job_id)
        if rec is None:
            continue
        out.append(_reconcile(rec))
    out.sort(key=lambda r: r.started_at, reverse=True)
    return out


def stop_job(job_id: str) -> dict:
    """Cancel a running job: kills the process tree rooted at its RECORDED pid only (never a
    name-based kill) and marks it ``"stopped"``. Returns ``{"ok": bool, "message": str, "job":
    JobRecord | None}``; never raises. A job that is unknown or not currently ``"running"`` is
    refused honestly WITHOUT sending any kill signal."""
    rec = get_job(job_id)
    if rec is None:
        return {"ok": False, "message": f"unknown job {job_id!r}", "job": None}
    if rec.status != "running":
        return {"ok": False,
                 "message": f"job {job_id} is not running (status={rec.status})", "job": rec}
    if rec.pid:
        _kill_pid_tree(rec.pid)
    rec = dataclasses.replace(rec, status="stopped", ended_at=time.time())
    _write_record(rec)
    return {"ok": True, "message": f"job {job_id} stopped", "job": rec}


def read_log(job_id: str) -> str:
    """That job's recorded output. An honest message for an unknown id or an unreadable/empty
    log -- never raises."""
    rec = get_job(job_id)
    if rec is None:
        return f"no such job {job_id!r} -- try `jcode jobs` to list known ids"
    try:
        path = Path(rec.log_path) if rec.log_path else None
        if not path or not path.is_file():
            return f"(job {job_id} has produced no output yet -- status={rec.status})"
        text = path.read_text(encoding="utf-8", errors="replace")
        return text if text.strip() else f"(job {job_id} produced no output -- status={rec.status})"
    except Exception as exc:
        return f"(could not read log for job {job_id}: {exc})"


def format_jobs(jobs: "list[JobRecord] | None" = None) -> str:
    """Render a readable job table for `jcode jobs`/`/jobs`. Never raises."""
    try:
        jobs = jobs if jobs is not None else list_jobs()
        if not jobs:
            return "(no background jobs -- submit one with `jcode --bg \"<request>\"`)"
        lines = [f"{'id':<10} {'status':<9} {'started':<20} {'request'}", "-" * 70]
        for rec in jobs:
            started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec.started_at)) \
                if rec.started_at else "?"
            req = rec.request if len(rec.request) <= 40 else rec.request[:37] + "..."
            lines.append(f"{rec.id:<10} {rec.status:<9} {started:<20} {req}")
        return "\n".join(lines)
    except Exception:
        return "(background jobs list unavailable)"


def attach_job(job_id: str, *, poll_interval: float = 0.5, sleep_fn=None, print_fn=print) -> int:
    """Stream a job's NEW output until it ends or the caller detaches (``KeyboardInterrupt``,
    which NEVER stops the job -- only a real `stop_job` call does that). Returns an exit code
    (0 on a clean stream/detach, 1 for an unknown job). Injectable ``sleep_fn``/``print_fn`` let
    tests drive this deterministically without a real sleep or a real subprocess."""
    import time as _time
    sleep_fn = sleep_fn if sleep_fn is not None else _time.sleep

    rec = get_job(job_id)
    if rec is None:
        print_fn(f"error: unknown job {job_id!r}")
        return 1

    log_path = Path(rec.log_path) if rec.log_path else None
    pos = 0
    print_fn(f"attaching to job {job_id} (Ctrl-C to detach -- the job keeps running)...")
    try:
        while True:
            rec = get_job(job_id) or rec
            if log_path and log_path.is_file():
                try:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    text = ""
                if len(text) > pos:
                    print_fn(text[pos:], end="")
                    pos = len(text)
            if rec.status != "running":
                break
            sleep_fn(poll_interval)
    except KeyboardInterrupt:
        print_fn("\n(detached -- job keeps running in the background)")
        return 0
    print_fn(f"\n[job {job_id} finished: {rec.status}]")
    return 0
# #EXT-052-REQ-1 End
