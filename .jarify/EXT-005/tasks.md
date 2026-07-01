# Implementation Tasks — EXT-005 Convergence Evaluation Harness

### [TASK-1] Shared process-tree-kill helper for the remaining local pytest-timeout sites

Close the REQ-12 coverage gap: the proven tree-kill fix (`harness/pass1_eval.py::_run_with_treekill`)
covers the eval-harness sites, but four local `shell=True` + timeout pytest sites in the
behavioral-solve / CLI paths still use a bare `subprocess.run(..., timeout=...)` and orphan the pytest
grandchild on a Windows timeout. Extract the proven logic into a SHARED helper (single source of truth,
Tenet 3) and rewire those four sites. Fully offline + test-gated; no Jetson / Docker.

#### Steps
1. Add `harness/proc_treekill.py` exposing `run_with_treekill(cmd: str, cwd: str, timeout: int) -> bool`
   — lift the EXACT proven implementation from `harness/pass1_eval.py::_run_with_treekill` (Popen +
   `communicate(timeout)`; on `TimeoutExpired`: Windows `taskkill /F /T /PID`, POSIX
   `os.killpg(os.getpgid(pid), SIGKILL)` with `start_new_session=True`; then a short reap
   `communicate(timeout=5)`; return `returncode == 0`). Preserve the same stdout/stderr handling the
   call sites currently rely on (they capture output — accept an optional `capture: bool=False` param, or
   provide a variant that returns `(ok, output)`, matching what each site needs; inspect each site).
2. Rewire the four bare-`subprocess.run` pytest sites to use the shared helper so a Windows timeout kills
   the whole tree: `harness/agent_loop.py` (~L118), `harness/cli.py` (~L451, and the `_run` at ~L507 if
   it wraps the same call), `harness/intent_loop.py` (~L107), `harness/build_eval.py` (~L160). Keep each
   site's existing return/΅semantics (ok bool / captured text) unchanged apart from the timeout-safety.
   Tag the shared helper `# #EXT-005-REQ-12` for traceability.
3. Do NOT change the already-correct `pass1_eval.py` (`run_pass1`/`run_gated`/`_run_with_treekill`) or
   `multi_file.py` behavior — they work and are covered; leave their proven code intact (optionally they
   may delegate to the shared helper ONLY if byte-for-byte behavior-preserving, but priority is the four
   unfixed sites + zero regression to the working eval paths).
4. Add `tests/test_ext005_proc_treekill.py` (offline, cross-platform-aware): spawn via the shared helper
   a shell command that starts a long-lived child (e.g. `python -c "import time; time.sleep(60)"`) with a
   short timeout; assert the call returns `False` within a few seconds AND that the spawned child process
   is dead afterward (poll by PID). Guard any Windows-only / POSIX-only assertions with `os.name`.
   Run the full suite green (baseline 1055 passing).

#### Implements
- [REQ-12] Robust test-exec — hang-proof process tree kill (shared helper + remaining sites)
