"""Scratch research-script investigation plane (EXT-037 / REQ-6).

PRIME-001 intent capability (e): the product must be able to INVESTIGATE, not just build --
the exact Claude-Code "write a probe, run it, read the result" loop. This module is a plain,
deterministic execution-plane function module (not a Jaros custom tool -- it is called
directly by orchestration code rather than dispatched as a Decision), reused by any agent or
loop that needs to write a throwaway ``.py`` probe, run it, and read the result.

Every effect stays OUTSIDE the target repo: the script file, and any file it writes (e.g. an
oversized ``output.txt``), live only under a scratch directory -- a fresh
``tempfile.mkdtemp(prefix="jcode_research_")`` by default, or a caller-supplied ``scratch_dir``
-- both resolved through the existing ``_pathjail.path_jail`` choke point (EXT-037 / REQ-1) so
nothing can ever be written outside scratch. This module NEVER mutates the target/project repo.

The subprocess is run with a timeout and a process-TREE kill on expiry, reusing the exact
``taskkill /F /T /PID`` (Windows) / ``killpg`` (POSIX) discipline proven in
``.jaros-data/tools/shell_exec_tool.py::_kill_tree`` (EXT-001/EXT-037 REQ-2), so a hanging probe
(``while True: pass``) never orphans a process. ``run_research_script`` NEVER raises: any
failure (bad input, a Popen start failure, an unwritable scratch dir) comes back as a
structured ``{"ok": False, ...}`` observation instead of propagating.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile

# #EXT-037-REQ-6 Start

_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".jaros-data", "tools"
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

try:
    from _pathjail import PathEscapeError, path_jail  # root-jail choke point (EXT-037 / REQ-1)
except Exception:  # pragma: no cover - fail safe if the helper is ever missing
    class PathEscapeError(Exception):
        pass

    def path_jail(root, target):  # type: ignore
        return target if os.path.isabs(target) else os.path.join(root, target)


_DEFAULT_TIMEOUT_S = 30
_HEAD_TAIL_CHARS = 2000  # fixed head/tail slice size for a truncated result, independent of stdout_limit
_STDERR_TAIL_CHARS = 5000  # stderr is always bounded to its last N chars


def _kill_tree(proc) -> None:
    """Kill *proc* AND its descendants. Mirrors ``shell_exec_tool.py::_kill_tree`` exactly (the
    same choke point, not a divergent copy in spirit) so a hung research script (e.g. an
    infinite loop) can never orphan a grandchild process and hang the caller."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_research_script(
    code: str,
    *,
    scratch_dir: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
    args: list | None = None,
    stdout_limit: int = 20000,
) -> dict:
    """Write ``code`` to a throwaway ``.py`` script in a scratch dir OUTSIDE the target repo,
    run it as a gated subprocess, and return an honest, bounded observation of the result.

    Never raises -- any failure is reported as ``{"ok": False, ...}`` with a diagnostic
    ``note`` instead of propagating an exception.
    """
    scratch_dir_out = scratch_dir
    try:
        if not scratch_dir:
            scratch_dir_out = tempfile.mkdtemp(prefix="jcode_research_")
        else:
            os.makedirs(scratch_dir, exist_ok=True)
            scratch_dir_out = os.path.abspath(scratch_dir)

        script_path = path_jail(scratch_dir_out, "script.py")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(code)

        cmd = [sys.executable, script_path, *[str(a) for a in (args or [])]]
        popen_kwargs: dict = dict(
            cwd=scratch_dir_out, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True  # own process group, so killpg reaches kids

        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                out, err = proc.communicate(timeout=5)
            except Exception:
                out, err = "", ""
            return {
                "ok": False,
                "returncode": None,
                "stdout": out or "",
                "stderr": (err or "")[-_STDERR_TAIL_CHARS:],
                "timed_out": True,
                "scratch_dir": scratch_dir_out,
                "note": f"research script timed out after {timeout}s; process tree killed",
            }

        out = out or ""
        err = (err or "")[-_STDERR_TAIL_CHARS:]
        returncode = proc.returncode
        ok = returncode == 0

        if len(out) <= stdout_limit:
            return {
                "ok": ok,
                "returncode": returncode,
                "stdout": out,
                "stderr": err,
                "timed_out": False,
                "scratch_dir": scratch_dir_out,
                "note": "completed" if ok else f"script exited with code {returncode}",
            }

        # Too large to return inline: write the FULL output to a file the caller can parse
        # in bounded chunks (via read_research_output), and return only a head/tail preview.
        output_path = path_jail(scratch_dir_out, "output.txt")
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(out)
        return {
            "ok": ok,
            "returncode": returncode,
            "stdout_file": output_path,
            "stdout_head": out[:_HEAD_TAIL_CHARS],
            "stdout_tail": out[-_HEAD_TAIL_CHARS:],
            "truncated": True,
            "total_bytes": len(out.encode("utf-8", errors="replace")),
            "stderr": err,
            "timed_out": False,
            "scratch_dir": scratch_dir_out,
            "note": (
                f"stdout exceeded stdout_limit ({stdout_limit} chars); "
                f"full output written to {output_path}"
            ),
        }
    except Exception as exc:  # never raise -- an honest diagnostic observation instead
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "scratch_dir": scratch_dir_out or "",
            "note": f"research script failed to run: {exc}",
        }


def read_research_output(path, *, max_bytes: int = 20000) -> str:
    """Return a bounded slice of a (possibly large) research-output file for a reader agent:
    the whole decoded content when it fits in ``max_bytes``, else a head+tail slice joined by a
    truncation marker. Never raises -- a missing/unreadable path or garbage input returns a
    short diagnostic string instead."""
    try:
        if not isinstance(path, str) or not path:
            return f"read_research_output: invalid path {path!r}"
        size = os.path.getsize(path)
        if size <= max_bytes:
            with open(path, "rb") as fh:
                data = fh.read()
            return data.decode("utf-8", errors="replace")

        half = max(max_bytes // 2, 1)
        with open(path, "rb") as fh:
            head = fh.read(half)
            fh.seek(max(size - half, 0))
            tail = fh.read()
        skipped = max(size - len(head) - len(tail), 0)
        marker = f"\n...[truncated {skipped} bytes]...\n".encode("utf-8")
        return (head + marker + tail).decode("utf-8", errors="replace")
    except Exception as exc:  # never raise
        return f"read_research_output: failed to read {path!r}: {exc}"
# #EXT-037-REQ-6 End
