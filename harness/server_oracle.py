"""EXT-036 REQ-22: a REAL server/HTTP acceptance oracle for web-service builds.

MEASURED GAP (owner directive 2026-07-03): ``harness/system_builder.py::build_system``'s
acceptance checklist runs each check via ``_run_check``, which executes
``python <entry>.py`` and inspects STDOUT. A FastAPI/Flask service prints nothing to
stdout (it blocks serving HTTP) -- so every model-proposed check for it gets filtered out
by the executable-check gate and the build falls back to ``_smoke_checklist`` (import the
entrypoint + assert the exported names exist). That smoke check passes the instant the
module IMPORTS, without ever starting the server or hitting a single endpoint -- a Tenet-3
hollow pass for the class of task this product most needs to nail (real web services).

This module is a DETERMINISTIC, execution-plane verifier (two-plane: no model call here)
that actually STARTS the detected web app on an ephemeral localhost port and drives real
HTTP requests against it, asserting real responses. It is intentionally self-contained and
NOT wired into ``build_system`` yet -- that composition is a follow-up task; this task only
builds + proves the oracle itself.

Safety/scope: localhost only, no external network. Every launched server process (and any
children) is torn down in a ``finally`` block, mirroring
``.jaros-data/tools/shell_exec_tool.py::_kill_tree`` (Windows: ``taskkill /F /T /PID``;
POSIX: signal the process group). Nothing here ever raises -- any failure (bad input, a
server that never binds, a broken app) is reported honestly as ``ok: False`` with a
diagnostic note, never coerced to a pass and never left as an orphaned process.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# #EXT-036-REQ-22 Start
_FASTAPI_APP_RE = re.compile(r"(\w+)\s*=\s*FastAPI\s*\(")
_STARLETTE_APP_RE = re.compile(r"(\w+)\s*=\s*Starlette\s*\(")
_FLASK_APP_RE = re.compile(r"(\w+)\s*=\s*Flask\s*\(")
_FASTAPI_IMPORT_RE = re.compile(r"^\s*(?:from\s+fastapi\b|import\s+fastapi\b)", re.M)
_STARLETTE_IMPORT_RE = re.compile(r"^\s*(?:from\s+starlette\b|import\s+starlette\b)", re.M)
_FLASK_IMPORT_RE = re.compile(r"^\s*(?:from\s+flask\b|import\s+flask\b)", re.M)


def detect_web_service(modules: "dict | None") -> "dict | None":
    """Best-effort, NEVER-RAISE scan of ``{filename: source}`` module SOURCES for a
    FastAPI/Starlette (ASGI) or Flask (WSGI) app object.

    Returns ``{"kind": "asgi"|"wsgi", "entry": <module stem>, "app": <attr name>}`` for the
    FIRST module where both a framework import and an app-object assignment are found
    (``app = FastAPI(...)`` / ``= Starlette(...)`` for ASGI, ``= Flask(...)`` for WSGI); the
    attr name is whatever the source actually assigns, defaulting to ``"app"`` if the
    assignment pattern isn't found but the import is present. Returns ``None`` when no web
    service is detected, or on any malformed input -- this function never raises.
    """
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return None
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            src = str(code)
            if _FASTAPI_IMPORT_RE.search(src) or _STARLETTE_IMPORT_RE.search(src):
                m = _FASTAPI_APP_RE.search(src) or _STARLETTE_APP_RE.search(src)
                app_attr = m.group(1) if m else "app"
                return {"kind": "asgi", "entry": Path(name).stem, "app": app_attr}
            if _FLASK_IMPORT_RE.search(src):
                m = _FLASK_APP_RE.search(src)
                app_attr = m.group(1) if m else "app"
                return {"kind": "wsgi", "entry": Path(name).stem, "app": app_attr}
        except Exception:
            continue
    return None


def _free_port() -> int:
    """Pick a FREE ephemeral localhost port: bind :0, read the OS-assigned port, close."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _kill_tree(proc) -> None:
    """Kill ``proc`` AND its descendants. Mirrors
    ``.jaros-data/tools/shell_exec_tool.py::_kill_tree`` exactly (Windows: ``taskkill /F /T
    /PID``, walks the whole tree; POSIX: signal the process group) so no orphaned
    uvicorn/flask process survives a check, even on an unexpected failure."""
    if proc is None:
        return
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


def _port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(port: int, proc, startup_timeout: float) -> bool:
    """Poll until the port accepts a TCP connection, bounded by ``startup_timeout``. Returns
    False immediately if the server process has already exited (no point waiting out the
    full timeout on a server that already crashed)."""
    try:
        deadline = time.monotonic() + max(0.0, float(startup_timeout))
    except (TypeError, ValueError):
        deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if _port_open(port):
            return True
        time.sleep(0.2)
    return False


def _tail(path, limit: int = 800) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def _launch(root: Path, service: dict, port: int, out_fh, err_fh):
    kind = service.get("kind")
    entry = service.get("entry") or "main"
    app = service.get("app") or "app"
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    if kind == "wsgi":
        cmd = [sys.executable, "-m", "flask", "--app", f"{entry}:{app}", "run", "--port", str(port)]
    else:
        cmd = [sys.executable, "-m", "uvicorn", f"{entry}:{app}", "--port", str(port),
               "--log-level", "warning"]
    popen_kwargs: dict = dict(cwd=str(root), stdout=out_fh, stderr=err_fh, env=env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def _subset(actual, expected) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    for k, v in expected.items():
        if k not in actual or actual[k] != v:
            return False
    return True


def _do_request(port: int, check: dict, request_timeout: float):
    method = str(check.get("method") or "GET").upper()
    path = check.get("path") or "/"
    if not str(path).startswith("/"):
        path = "/" + str(path)
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            status = resp.getcode()
            body_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body_bytes = exc.read()
        except Exception:
            body_bytes = b""
    body = body_bytes.decode("utf-8", errors="replace")
    return status, body


def _check_one(port: int, check, request_timeout: float) -> dict:
    """Run ONE http_check and grade it. Guarded per-check -- a malformed check dict or a
    request error never propagates, it is reported as a failed check."""
    try:
        if not isinstance(check, dict):
            raise TypeError(f"http_check must be a dict, got {type(check)!r}")
        status, body = _do_request(port, check, request_timeout)

        ok = True
        reasons: list[str] = []

        exp_status = check.get("status")
        if exp_status is not None and status != exp_status:
            ok = False
            reasons.append(f"status {status} != expected {exp_status}")

        if check.get("json_contains") is not None:
            try:
                parsed = json.loads(body)
            except Exception as jexc:
                parsed = None
                reasons.append(f"response not valid JSON: {jexc}")
                ok = False
            else:
                if not _subset(parsed, check["json_contains"]):
                    ok = False
                    reasons.append(f"json_contains not satisfied (got {body[:300]!r})")

        if check.get("body_contains") is not None:
            if str(check["body_contains"]) not in body:
                ok = False
                reasons.append("body_contains substring not found in response body")

        return {"check": check, "passed": ok, "status": status, "body": body[:2000],
                "reasons": reasons}
    except Exception as exc:
        return {"check": check, "passed": False, "status": None, "body": "",
                "reasons": [f"request error: {exc}"]}


def serve_and_check(root, service: "dict | None", http_checks, *,
                     startup_timeout: float = 15, request_timeout: float = 5) -> dict:
    """Start the detected web ``service`` (from :func:`detect_web_service`) on a FREE
    ephemeral localhost port, poll until it actually binds, then run every check in
    ``http_checks`` against it as a real HTTP request.

    NEVER raises: any failure at any stage (bad ``root``/``service``, an unlaunchable
    process, a server that never binds, a malformed check) is reported honestly as
    ``ok: False`` with a diagnostic ``note`` -- never coerced to a pass. ALWAYS tears the
    server process (and any descendants) down in a ``finally`` block, so a failed or
    completed check run never leaves an orphaned uvicorn/flask process behind.

    Returns ``{"ok": bool, "results": [per-check dicts], "note": str}`` where ``ok`` is True
    only when the server bound the port AND every check in ``http_checks`` passed.
    """
    if not isinstance(service, dict) or not service.get("entry"):
        return {"ok": False, "results": [], "note": "no service to serve (detect_web_service found none)"}
    try:
        root_path = Path(root)
    except TypeError:
        return {"ok": False, "results": [], "note": f"invalid root: {root!r}"}
    if not root_path.exists():
        return {"ok": False, "results": [], "note": f"root does not exist: {root_path}"}

    checks = list(http_checks) if isinstance(http_checks, (list, tuple)) else []

    try:
        port = _free_port()
    except OSError as exc:
        return {"ok": False, "results": [], "note": f"could not allocate a free port: {exc}"}

    proc = None
    out_fh = err_fh = None
    out_path = err_path = None
    try:
        fd_out, out_path = tempfile.mkstemp(prefix="jcode_server_oracle_out_")
        fd_err, err_path = tempfile.mkstemp(prefix="jcode_server_oracle_err_")
        os.close(fd_out)
        os.close(fd_err)
        out_fh = open(out_path, "w", encoding="utf-8")
        err_fh = open(err_path, "w", encoding="utf-8")
        proc = _launch(root_path, service, port, out_fh, err_fh)
    except Exception as exc:
        for fh in (out_fh, err_fh):
            try:
                if fh:
                    fh.close()
            except Exception:
                pass
        _kill_tree(proc)
        return {"ok": False, "results": [], "note": f"failed to launch service: {exc}"}

    results: list[dict] = []
    try:
        if not _wait_for_port(port, proc, startup_timeout):
            try:
                out_fh.flush()
                err_fh.flush()
            except Exception:
                pass
            note = "server never bound the port within startup_timeout"
            tail_out, tail_err = _tail(out_path), _tail(err_path)
            if tail_out or tail_err:
                note += f" -- stdout tail: {tail_out!r} stderr tail: {tail_err!r}"
            return {"ok": False, "results": [], "note": note}

        all_ok = True
        for check in checks:
            result = _check_one(port, check, request_timeout)
            results.append(result)
            all_ok = all_ok and bool(result.get("passed"))

        note = "ok" if all_ok else "one or more http checks failed"
        return {"ok": bool(all_ok), "results": results, "note": note}
    except Exception as exc:
        return {"ok": False, "results": results, "note": f"unexpected error: {exc}"}
    finally:
        _kill_tree(proc)
        for fh in (out_fh, err_fh):
            try:
                if fh:
                    fh.close()
            except Exception:
                pass
        for p in (out_path, err_path):
            try:
                if p:
                    os.remove(p)
            except OSError:
                pass
# #EXT-036-REQ-22 End
