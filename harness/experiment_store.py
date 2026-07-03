"""EXT-036 REQ-19: Experiment creation + management (user-facing).

Claude-Code-style experiments: define (hypothesis + how to run + how to measure) -> run ->
record the result against the hypothesis. Mirrors ``harness/task_store.py``'s two-plane split
and robustness style, with one difference: TASK-9 has NO model judgment at all — ``run_experiment``
is a REAL deterministic subprocess execution (never faked), guarded + bounded like
``harness/multi_file.py::_run`` (Popen + tree-kill on timeout so a hanging/bad command can never
orphan a process or crash the store).

  - ``define_experiment`` / ``run_experiment`` / ``list_experiments``: deterministic file I/O +
    a real guarded subprocess run, a per-repo store at ``<root>/.jaros/experiments.jsonl``.
    Guarded — never raise.

HONESTY (Tenet 3): the recorded ``exit_code``/``output`` on a run is ALWAYS the real subprocess
result (or a real guard failure like "timed out" / "failed to start") — never invented, never
silently upgraded to a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

EXPERIMENTS_REL_PATH = Path(".jaros") / "experiments.jsonl"
MAX_EXPERIMENTS = 500      # bound the store (cap experiments kept/read)
MAX_OUTPUT_CHARS = 4000    # bound the recorded output (tail kept, like a log tail)
DEFAULT_TIMEOUT_S = 60

# #EXT-036-REQ-19 Start


def _experiments_path(root: "str | Path" = ".") -> Path:
    return Path(root) / EXPERIMENTS_REL_PATH


def _load_all(root: "str | Path" = ".") -> list[dict]:
    """All stored experiment records (oldest-first), unbounded (run/list need the full set to
    find-by-id). Deterministic; guarded — returns [] when the store is absent, empty, or
    corrupt (never raises)."""
    try:
        p = _experiments_path(root)
        if not p.is_file():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(rec, dict) and rec.get("id") and rec.get("hypothesis") and rec.get("run_cmd"):
                out.append(rec)
        return out
    except OSError:
        return []


def _write_all(records: "list[dict]", root: "str | Path" = ".") -> bool:
    try:
        p = _experiments_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return True
    except OSError:
        return False


def define_experiment(hypothesis: str, run_cmd: str, root: "str | Path" = ".",
                       measure: str = "") -> "dict | None":
    """Define an experiment (hypothesis + how to run it + how to measure it) in the per-repo
    store (``<root>/.jaros/experiments.jsonl``) and return it (with a stable ``id`` and
    ``status: "defined"``). Deterministic file I/O; guarded — never raises. Returns None for a
    blank hypothesis/run_cmd or any I/O failure."""
    hypothesis = (hypothesis or "").strip()
    run_cmd = (run_cmd or "").strip()
    if not hypothesis or not run_cmd:
        return None
    measure = (measure or "").strip()
    exp = {
        "id": uuid.uuid4().hex[:8],
        "hypothesis": hypothesis,
        "run_cmd": run_cmd,
        "measure": measure,
        "status": "defined",
        "ts": time.time(),
    }
    try:
        records = _load_all(root)
        records.append(exp)
        records = records[-MAX_EXPERIMENTS:]
        if not _write_all(records, root):
            return None
    except OSError:
        return None
    return exp


def _execute(run_cmd: str, cwd: "str | Path", timeout: float) -> "tuple[int, str]":
    """Run `run_cmd` for real via a guarded subprocess (Popen + tree-kill on timeout, mirrors
    ``harness/multi_file.py::_run``) so a hanging/bad command can never orphan a process or hang
    the caller. Returns the REAL ``(exit_code, combined stdout+stderr)`` — a timeout or a
    failure-to-start is recorded as a real non-zero exit_code + explanatory output, never
    fabricated as a pass."""
    try:
        kwargs: dict = dict(shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if os.name != "nt":
            kwargs["start_new_session"] = True
        p = subprocess.Popen(run_cmd, cwd=str(cwd), **kwargs)
    except OSError as exc:
        return 1, f"failed to start experiment command: {exc}"
    try:
        stdout, stderr = p.communicate(timeout=timeout)
        code = p.returncode if p.returncode is not None else 1
        return code, (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                f"taskkill /F /T /PID {p.pid}",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            p.communicate(timeout=5)
        except Exception:
            pass
        return 1, f"experiment command timed out after {timeout}s (real guard failure, not a fabricated pass): {run_cmd}"


def run_experiment(experiment_id: str, root: "str | Path" = ".", *,
                    timeout: float = DEFAULT_TIMEOUT_S) -> "dict | None":
    """Actually RUN the experiment's ``run_cmd`` (a REAL guarded subprocess in `root`, never
    fabricated) and record the outcome: ``exit_code`` (the real process exit code — or a real
    guard failure such as a timeout, still non-zero), ``output`` (a bounded tail of combined
    stdout+stderr), and ``status: "run"``. Deterministic; guarded — never raises. Returns None
    when `experiment_id` isn't found or the write fails."""
    experiment_id = (experiment_id or "").strip()
    if not experiment_id:
        return None
    try:
        records = _load_all(root)
    except OSError:
        return None
    target: "dict | None" = None
    for rec in records:
        if rec.get("id") == experiment_id:
            target = rec
            break
    if target is None:
        return None
    try:
        exit_code, output = _execute(target.get("run_cmd", ""), Path(root), timeout)
    except Exception as exc:
        # A guard-layer error itself must not raise, and must never be reported as a pass.
        exit_code, output = 1, f"experiment run guard error (treated as failure, never fabricated): {exc}"
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[-MAX_OUTPUT_CHARS:]
    target["exit_code"] = exit_code
    target["output"] = output
    target["status"] = "run"
    target["ran_ts"] = time.time()
    if not _write_all(records, root):
        return None
    return target


def list_experiments(root: "str | Path" = ".", cap: int = MAX_EXPERIMENTS) -> "list[dict]":
    """The stored experiments for `root`'s repo (oldest-first), bounded to the most recent
    `cap` entries. Deterministic; guarded — [] when the store is absent/empty/corrupt."""
    try:
        return _load_all(root)[-cap:]
    except Exception:
        return []
# #EXT-036-REQ-19 End
