"""Shared process-tree-kill helper (EXT-005 / REQ-12): single source of truth for running a
``shell=True`` subprocess with a timeout that kills the WHOLE process tree — not just the
immediate shell child — when the timeout fires.

On Windows with ``shell=True`` the immediate child is ``cmd.exe``; a plain
``subprocess.run(..., timeout=N)`` kills only ``cmd.exe`` on ``TimeoutExpired``, leaving the
pytest grandchild alive and the caller hanging on a broken pipe (the task-71 / bug-#19 class
of hang). This module extracts the proven fix out of
``harness/pass1_eval.py::_run_with_treekill`` so every local ``shell=True`` + timeout pytest
site can share ONE implementation (Tenet 3 — no divergent copies) instead of re-deriving it.

``pass1_eval.py`` (``run_pass1`` / ``run_gated``) and ``multi_file.py`` (``_run``) already had
this fix inline before this helper existed and are left untouched (proven + covered); this
helper is for the remaining bare-``subprocess.run`` sites in ``agent_loop.py``, ``cli.py``,
``intent_loop.py`` and ``build_eval.py``.
"""
from __future__ import annotations

import os
import subprocess


# #EXT-005-REQ-12 Start
def run_with_treekill(cmd: str, cwd: str, timeout: int, *, capture: bool = False):
    """Run *cmd* (``shell=True``) in *cwd*, returning within *timeout* even if the process
    tree hangs (e.g. an infinite-loop solution under test).

    capture=False (default): returns ``bool`` -- True iff the process exited 0.
    capture=True: returns ``(ok: bool, output: str)`` where *output* is stdout+stderr
    (empty string on a timeout).

    On timeout, kills the ENTIRE process tree (not just the shell), then reaps the process
    with a short ``communicate(timeout=5)`` before returning, so an infinite-loop solution
    can never orphan a pytest grandchild and hang the caller on a broken pipe.

    Windows: ``taskkill /F /T /PID`` kills the whole tree (cmd.exe + grandchildren).
    POSIX:   ``start_new_session=True`` + SIGKILL to the process group.
    """
    kwargs: dict = dict(shell=True)
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    else:
        kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name != "nt":
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, cwd=cwd, **kwargs)
    try:
        out, err = p.communicate(timeout=timeout)
        ok = p.returncode == 0
        return (ok, (out or "") + (err or "")) if capture else ok
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
        return (False, "") if capture else False
# #EXT-005-REQ-12 End
