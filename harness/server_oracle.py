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

# #EXT-037-REQ-7 Start
# TASK-11: Reuse (not reimplement) `harness.secure_exec`'s scrubbed-environment + POSIX-resource-cap
# building blocks for the server subprocess this module launches. `run_sandboxed` itself is NOT
# called here: it is a blocking helper (it `communicate()`s until the child exits or times out),
# which is fundamentally incompatible with a long-running HTTP server that must keep running
# WHILE this module polls its port and drives real requests against it, then tears it down in a
# `finally` block. So the launch/poll/request/kill lifecycle below stays exactly as it was;
# only the Popen's environment/resource-limit CONSTRUCTION is now the same sandboxed mechanism
# `run_sandboxed` uses, via its own internal helpers.
from harness.secure_exec import EgressPolicy, _make_preexec_fn, _scrubbed_env

# The server binds a LOCALHOST listen socket and this module's PARENT process (not the server
# subprocess) makes the HTTP requests to it -- binding a socket is not egress, and the parent
# making localhost requests is not sandboxed at all (only the launched subprocess is). This
# policy exists to document that intent for any future runtime-egress-enforcement follow-up; it
# is NOT itself enforced at the OS level here (same honest limitation `run_sandboxed` documents
# -- today's gate is static/AST-scan-time only, see `harness/secure_exec.py`).
SERVER_EGRESS_POLICY = EgressPolicy.allow("127.0.0.1", "localhost")
# #EXT-037-REQ-7 End

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


# #EXT-036-REQ-47 Start
_STDLIB_HTTP_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+http\.server\b|import\s+http\.server\b|from\s+socketserver\b|import\s+socketserver\b)",
    re.M,
)
_STDLIB_HTTP_USAGE_RE = re.compile(r"\b(?:HTTPServer|ThreadingHTTPServer)\s*\(")


def detect_stdlib_http_service(modules: "dict | None") -> "str | None":
    """Best-effort, NEVER-RAISE scan of ``{filename: source}`` module SOURCES for a plain
    ``http.server``/``socketserver`` (``HTTPServer``/``ThreadingHTTPServer``) service, with NO
    Flask/FastAPI/Starlette import present (those route through :func:`detect_web_service`
    instead).

    Returns the entry FILENAME (e.g. ``"main.py"``) of the first module that both imports
    ``http.server``/``socketserver`` and instantiates ``HTTPServer(...)``/
    ``ThreadingHTTPServer(...)``. Returns ``None`` when no such service is detected, or on any
    malformed input -- this function never raises.
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
            if _FASTAPI_IMPORT_RE.search(src) or _STARLETTE_IMPORT_RE.search(src) or _FLASK_IMPORT_RE.search(src):
                continue
            if _STDLIB_HTTP_IMPORT_RE.search(src) and _STDLIB_HTTP_USAGE_RE.search(src):
                return Path(name).name
        except Exception:
            continue
    return None
# #EXT-036-REQ-47 End


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


# #EXT-037-REQ-7 Start
# TASK-11
def _launch(root: Path, service: dict, port: int, out_fh, err_fh, *,
            mem_mb: int = 512, cpu_budget_s: float = 120):
    """Launch the detected web service's server subprocess SANDBOXED (REQ-7 follow-up): a
    SCRUBBED environment (``harness.secure_exec._scrubbed_env`` -- no ambient host secrets, API
    keys, or tokens reach the model-generated app) plus ``PYTHONUNBUFFERED``/``PYTHONPATH`` so
    the app still imports and logs exactly as before, and (POSIX only) the same RLIMIT_AS/
    RLIMIT_CPU resource caps ``harness.secure_exec.run_sandboxed`` applies
    (``harness.secure_exec._make_preexec_fn``), guarded against a mem-bombing/CPU-runaway
    generated app. ``cpu_budget_s`` is a generous cap (not the actual test-run timeout -- that is
    still enforced by ``_wait_for_port``/the per-check ``request_timeout`` and the unconditional
    ``_kill_tree`` teardown in :func:`serve_and_check`'s ``finally`` block), sized to comfortably
    exceed a legitimate startup + full check run."""
    kind = service.get("kind")
    entry = service.get("entry") or "main"
    app = service.get("app") or "app"
    env = _scrubbed_env({
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    })
    if kind == "wsgi":
        cmd = [sys.executable, "-m", "flask", "--app", f"{entry}:{app}", "run", "--port", str(port)]
    else:
        cmd = [sys.executable, "-m", "uvicorn", f"{entry}:{app}", "--port", str(port),
               "--log-level", "warning"]
    popen_kwargs: dict = dict(cwd=str(root), stdout=out_fh, stderr=err_fh, env=env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
        preexec_fn = _make_preexec_fn(mem_mb, cpu_budget_s)
        if preexec_fn is not None:
            popen_kwargs["preexec_fn"] = preexec_fn
    return subprocess.Popen(cmd, **popen_kwargs)
# #EXT-037-REQ-7 End


# #EXT-036-REQ-47 Start
def _launch_stdlib(root: Path, entry: str, port: int, out_fh, err_fh, *,
                    env: "dict | None" = None, mem_mb: int = 512, cpu_budget_s: float = 120):
    """Launch a plain stdlib ``http.server``/``socketserver`` service as a SCRIPT: ``python
    <entry>`` in ``root``, with the child given ``PORT=<port>`` in its environment -- the
    12-factor contract a stdlib service is expected to read via ``os.environ["PORT"]`` (there is
    no ``--port`` CLI flag convention to launch it with, unlike uvicorn/flask). Reuses the same
    scrubbed-environment (``harness.secure_exec._scrubbed_env``) and POSIX resource-cap
    (``harness.secure_exec._make_preexec_fn``) conventions :func:`_launch` uses, so the process is
    sandboxed identically."""
    extra_env = {
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if isinstance(env, dict):
        try:
            extra_env.update({str(k): str(v) for k, v in env.items()})
        except Exception:
            pass
    # PORT is the launch contract this function guarantees to the child -- never let a
    # caller-supplied env override it with a stale/wrong value.
    extra_env["PORT"] = str(port)
    scrubbed_env = _scrubbed_env(extra_env)
    cmd = [sys.executable, str(entry)]
    popen_kwargs: dict = dict(cwd=str(root), stdout=out_fh, stderr=err_fh, env=scrubbed_env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
        preexec_fn = _make_preexec_fn(mem_mb, cpu_budget_s)
        if preexec_fn is not None:
            popen_kwargs["preexec_fn"] = preexec_fn
    return subprocess.Popen(cmd, **popen_kwargs)
# #EXT-036-REQ-47 End


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
    # #EXT-060-REQ-9 Start
    # TASK-8: the prior contract had no way to send a REQUEST BODY at all -- a REST CRUD API's
    # POST/PUT endpoints can't be exercised honestly without one. Additive + backward-compatible:
    # a check that omits `json_body` builds the exact same `Request(url, method=method)` as before
    # (`data=None`, no extra headers).
    data = None
    headers: dict = {}
    if check.get("json_body") is not None:
        data = json.dumps(check["json_body"]).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    # #EXT-060-REQ-9 End
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
    """Run ONE http_check and grade it. ``check`` accepts ``method``, ``path``, ``status``,
    ``json_contains``, ``body_contains``, and (EXT-060 REQ-9) an optional ``json_body`` sent as the
    request's JSON-encoded body (``Content-Type: application/json``) -- omitted by default, so a
    check with no ``json_body`` sends no body at all, exactly as before this key existed. Guarded
    per-check -- a malformed check dict or a request error never propagates, it is reported as a
    failed check."""
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


# #EXT-037-REQ-7 Start
# TASK-11: new `mem_mb` parameter + docstring paragraph documenting the sandboxed launch below.
def serve_and_check(root, service: "dict | None", http_checks, *,
                     startup_timeout: float = 15, request_timeout: float = 5,
                     mem_mb: int = 512) -> dict:
    """Start the detected web ``service`` (from :func:`detect_web_service`) on a FREE
    ephemeral localhost port, poll until it actually binds, then run every check in
    ``http_checks`` against it as a real HTTP request.

    NEVER raises: any failure at any stage (bad ``root``/``service``, an unlaunchable
    process, a server that never binds, a malformed check) is reported honestly as
    ``ok: False`` with a diagnostic ``note`` -- never coerced to a pass. ALWAYS tears the
    server process (and any descendants) down in a ``finally`` block, so a failed or
    completed check run never leaves an orphaned uvicorn/flask process behind.

    **SANDBOXED (EXT-037 REQ-7 follow-up, TASK-11):** the launched server subprocess runs with a
    SCRUBBED environment and (POSIX) resource caps -- see :func:`_launch`. This module's PARENT
    process makes the HTTP requests to the server (not sandboxed itself); the server subprocess
    binds a localhost listen socket, which is not egress. ``SERVER_EGRESS_POLICY`` documents that
    the server is expected to only need localhost -- it is not itself enforced at the OS level
    (the honest static-only limitation ``harness.secure_exec`` already documents).

    Returns ``{"ok": bool, "results": [per-check dicts], "note": str}`` where ``ok`` is True
    only when the server bound the port AND every check in ``http_checks`` passed.
    """
    # #EXT-037-REQ-7 End
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
        # #EXT-037-REQ-7 Start
        # TASK-11: generous CPU-time budget: comfortably covers startup + every check's
        # request_timeout, never the actual enforcement mechanism (that stays `_wait_for_port` +
        # `_kill_tree` below) -- just a backstop resource cap against a runaway/mem-bombing
        # generated app.
        cpu_budget_s = float(startup_timeout) + float(request_timeout) * max(len(checks), 1) + 30
        proc = _launch(root_path, service, port, out_fh, err_fh,
                        mem_mb=mem_mb, cpu_budget_s=cpu_budget_s)
        # #EXT-037-REQ-7 End
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


# #EXT-036-REQ-47 Start
def serve_and_check_stdlib(root, entry: "str | None", http_checks, *,
                            startup_timeout: float = 15, request_timeout: float = 5,
                            env: "dict | None" = None, mem_mb: int = 512) -> dict:
    """The stdlib analog of :func:`serve_and_check` -- for a service built on plain
    ``http.server``/``socketserver`` (detected via :func:`detect_stdlib_http_service`), NOT a
    Flask/FastAPI app. Launches ``python <entry>`` in ``root`` as a plain script (no ASGI/WSGI
    server wrapper), on a FREE ephemeral localhost port passed via ``PORT=<port>`` in the child's
    environment (the 12-factor "listen on $PORT" contract) since there is no uvicorn/flask-style
    ``--port`` flag to launch a stdlib script with. Polls until the port actually binds, then runs
    every check in ``http_checks`` against it as a REAL HTTP request via the SAME
    :func:`_check_one`/:func:`_do_request` this module already uses for ``serve_and_check`` --
    same ``http_check`` dict contract (``method``, ``path``, optional ``status``/
    ``json_contains``/``body_contains``/``json_body``, the last (EXT-060 REQ-9) sent as the
    request's JSON-encoded body when present).

    NEVER raises: any failure at any stage (missing/invalid ``entry``, bad ``root``, an
    unlaunchable process, a server that never binds, a malformed check) is reported honestly as
    ``ok: False`` with a diagnostic ``note`` -- never coerced to a pass. ALWAYS tears the server
    process (and any descendants) down via :func:`_kill_tree` in a ``finally`` block, so a failed
    or completed check run never leaves an orphaned process behind.

    Returns ``{"ok": bool, "results": [per-check dicts], "note": str}`` -- the SAME shape
    :func:`serve_and_check` returns -- where ``ok`` is True only when the server bound the port
    AND every check in ``http_checks`` passed.
    """
    if not entry or not isinstance(entry, (str, os.PathLike)):
        return {"ok": False, "results": [], "note": f"no stdlib entry to serve (got {entry!r})"}
    try:
        root_path = Path(root)
    except TypeError:
        return {"ok": False, "results": [], "note": f"invalid root: {root!r}"}
    if not root_path.exists():
        return {"ok": False, "results": [], "note": f"root does not exist: {root_path}"}
    if not (root_path / entry).exists():
        return {"ok": False, "results": [], "note": f"entry does not exist under root: {entry}"}

    checks = list(http_checks) if isinstance(http_checks, (list, tuple)) else []

    try:
        port = _free_port()
    except OSError as exc:
        return {"ok": False, "results": [], "note": f"could not allocate a free port: {exc}"}

    proc = None
    out_fh = err_fh = None
    out_path = err_path = None
    try:
        fd_out, out_path = tempfile.mkstemp(prefix="jcode_server_oracle_stdlib_out_")
        fd_err, err_path = tempfile.mkstemp(prefix="jcode_server_oracle_stdlib_err_")
        os.close(fd_out)
        os.close(fd_err)
        out_fh = open(out_path, "w", encoding="utf-8")
        err_fh = open(err_path, "w", encoding="utf-8")
        cpu_budget_s = float(startup_timeout) + float(request_timeout) * max(len(checks), 1) + 30
        proc = _launch_stdlib(root_path, entry, port, out_fh, err_fh,
                               env=env, mem_mb=mem_mb, cpu_budget_s=cpu_budget_s)
    except Exception as exc:
        for fh in (out_fh, err_fh):
            try:
                if fh:
                    fh.close()
            except Exception:
                pass
        _kill_tree(proc)
        return {"ok": False, "results": [], "note": f"failed to launch stdlib service: {exc}"}

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
# #EXT-036-REQ-47 End
