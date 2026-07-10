"""EXT-059 REQ-6: the AGENT-LOOP ORACLE -- a deterministic, model-free verifier that grades a
built AGENT's ORCHESTRATION, not its reasoning.

**The gap this closes (Tenet 3):** agent systems (multi-step tool-calling loops -- and jaros-code
itself is one) are a high-priority real-system class, but nothing in the verification substrate
can grade one honestly. Running a built agent against a REAL local model would make every
assertion non-deterministic (a different completion -> a different tool-call sequence -> a flaky
test), and a stub that skips the model call entirely would test nothing about the agent's actual
control flow. The key insight this module is built on: an agent's REASONING is non-deterministic,
but its CONTROL FLOW is deterministic given a FIXED model. So this oracle fixes the model (a
scripted stub server that always returns the same sequence of canned "decisions") and grades the
WIRING the built agent constructed around it -- does it call the right tools, in the right order,
with the right arguments, feed the tool's observation back into the loop, and terminate cleanly --
never the model's intelligence.

**Injection seam (the agent contract this oracle pins):** a built agent under this oracle MUST
read its LLM endpoint from the cloud-standard OpenAI-compatible env-var convention --
``OPENAI_BASE_URL`` (also mirrored to ``MODEL_URL`` for callers that prefer that name) plus a
dummy ``OPENAI_API_KEY`` -- and POST ``{"model": ..., "messages": [...]}`` to
``f"{OPENAI_BASE_URL}/chat/completions"``, exactly the request shape a real OpenAI-compatible
client (including one pointed at the local Gemma llama.cpp endpoint) would send. Its tools must
call out to a second, oracle-hosted endpoint named by ``JAROS_TOOL_URL`` -- ``POST
f"{JAROS_TOOL_URL}/{tool_name}"`` with the tool's arguments as a JSON body, returning
``{"observation": <value>}`` -- this is the "controlled tool sandbox": every tool invocation is
observed and recorded by the oracle, in order, before the agent ever sees a response. The goal is
passed as ``sys.argv[1]``. A REAL build points ``OPENAI_BASE_URL``/``MODEL_URL`` at the local
Jetson llama.cpp endpoint instead -- this oracle only ever swaps the endpoint, never the contract,
so the exact same agent code is graded here and run for real. NEVER a paid/cloud model: the stub
IS the model.

Two-plane discipline holds throughout: this module is pure, deterministic execution-plane code
(stdlib ``http.server``/``json``/``subprocess``/``threading`` only -- no new dependency, no
model/reasoning call anywhere; the "model" the built agent talks to is this module's own scripted
stub). The built agent is launched SANDBOXED, reusing (not reimplementing) the existing audited
primitives: ``harness.secure_exec._scrubbed_env``/``_make_preexec_fn`` for the
scrubbed-environment + POSIX-resource-capped subprocess launch, and
``harness.server_oracle._kill_tree`` for process-tree teardown -- unconditionally, in a
``finally`` block, so a built agent that spawns a detached child never survives a check. The
stub HTTP server itself is ALWAYS shut down and its socket closed in that same ``finally`` block,
so a check run never leaves an orphaned listener behind either.

**NEVER RAISES**, mirroring ``harness/fs_oracle.py``/``harness/import_driver.py`` exactly: a
missing entrypoint, a broken/crashing/hanging/never-terminating agent, or a malformed
script/tools/checks spec is always an honest ``ok=False`` (or a per-check failure message) with a
diagnostic ``note`` -- never coerced to a pass, never an uncaught exception.

**FOLLOW-UP (not built here):** a Jaros-flavor extension that additionally asserts two-plane
Decision-emission and ``jaros replay`` byte-identical determinism for built agents is a deliberate,
separate follow-up requirement -- this module only grades the orchestration control flow itself.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

# #EXT-059-REQ-6 Start
# TASK-4: reuse (not reimplement) the exact same audited sandboxed-launch primitives
# `harness/fs_oracle.py` / `harness/import_driver.py` reuse -- the scrubbed-env/resource-cap
# launch convention from `secure_exec`, and the process-tree teardown helper `server_oracle`
# already defines.
from harness.secure_exec import _make_preexec_fn, _scrubbed_env
from harness.server_oracle import _kill_tree

DEFAULT_TIMEOUT_S = 20.0  # a hang is a real failure, never a hang (mirrors fs_oracle's default)
DEFAULT_MAX_STEPS = 20  # scripted model round-trips tolerated before declaring non-termination
DEFAULT_STARTUP_TIMEOUT_S = 5.0  # the STUB server binding is near-instant; generous headroom only

# Sentinel protocol for the agent's FINAL answer -- exactly ONE stdout line, greped by regex
# (never any other printing the agent does). Mirrors `import_driver`'s sentinel-line convention.
_FINAL_RE = re.compile(r"^__JAROS_AGENT_FINAL__(?P<payload>.*)__END__$")


# --------------------------------------------------------------------------------------------
# StubModel script -- a list of canned assistant turns, each either a tool-call or a final answer
# --------------------------------------------------------------------------------------------

def tool_call_turn(name: str, args: "dict | None" = None) -> dict:
    """Build ONE scripted assistant turn that instructs the built agent to call tool ``name``
    with ``args`` -- a convenience constructor for a ``script`` entry passed to
    :func:`drive_agent`."""
    return {"tool_call": {"name": str(name), "args": dict(args or {})}}


def final_turn(content: Any) -> dict:
    """Build ONE scripted assistant turn that ends the loop with a final answer -- a convenience
    constructor for a ``script`` entry passed to :func:`drive_agent`."""
    return {"final": str(content)}


def _validate_script(script: Any) -> "tuple[list | None, str]":
    if not isinstance(script, (list, tuple)) or not script:
        return None, "script must be a non-empty list of turns"
    turns: "list" = []
    for i, turn in enumerate(script):
        if not isinstance(turn, dict):
            return None, f"script[{i}] must be a dict, got {type(turn)!r}"
        has_tool = "tool_call" in turn
        has_final = "final" in turn
        if has_tool and not has_final:
            tc = turn["tool_call"]
            if not isinstance(tc, dict) or not isinstance(tc.get("name"), str) or not tc.get("name"):
                return None, f"script[{i}] tool_call must be {{'name': str, 'args': dict}}"
            turns.append({"tool_call": {"name": tc["name"], "args": dict(tc.get("args") or {})}})
        elif has_final and not has_tool:
            turns.append({"final": str(turn["final"])})
        else:
            return None, f"script[{i}] must have exactly one of 'tool_call' or 'final'"
    return turns, "ok"


def _render_completion(turn: dict, step: int) -> dict:
    """Render ONE scripted turn as an OpenAI-compatible ``/v1/chat/completions`` response body."""
    if "tool_call" in turn:
        tc = turn["tool_call"]
        return {
            "id": f"chatcmpl-stub-{step}",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"call_{step}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc.get("args") or {})},
                    }],
                },
            }],
        }
    content = turn.get("final", "")
    return {
        "id": f"chatcmpl-stub-{step}",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content, "tool_calls": None},
        }],
    }


class _StubState:
    """Shared, thread-safe state behind the stub server: the scripted turns, the controlled tool
    sandbox's canned observations, and the ORDERED log of every tool invocation the built agent
    actually made (the oracle's ground truth -- never what the agent merely claims it did)."""

    def __init__(self, turns: "list", tools: "dict | None"):
        self.turns = turns
        self.tools = tools if isinstance(tools, dict) else {}
        self._lock = threading.Lock()
        self.chat_count = 0
        self.tool_calls: "list" = []
        self._tool_name_counts: "dict" = {}

    def next_chat_response(self, max_steps: int) -> "tuple[int, dict | None]":
        """Consume one scripted turn. Returns ``(step, turn_or_None)`` -- ``turn`` is ``None``
        once ``step`` exceeds ``max_steps`` (signals the handler to refuse with an error, which
        forces a well-behaved agent to stop rather than loop unboundedly)."""
        with self._lock:
            self.chat_count += 1
            step = self.chat_count
            if step > max_steps:
                return step, None
            idx = min(step - 1, len(self.turns) - 1)
            return step, self.turns[idx]

    def record_tool_call(self, name: str, args: Any) -> Any:
        """Record ONE tool invocation (in order) and return the canned observation configured for
        it. A tool's canned value may be a single JSON value (returned for every call) or a list
        (consumed in order, clamped to the last entry once exhausted) -- so a tool's observation
        can vary call-by-call when a task needs that."""
        with self._lock:
            self.tool_calls.append({"name": name, "args": args})
            n = self._tool_name_counts.get(name, 0)
            self._tool_name_counts[name] = n + 1
            spec = self.tools.get(name)
            if isinstance(spec, list):
                return spec[min(n, len(spec) - 1)] if spec else None
            return spec

    def snapshot(self) -> "tuple[int, list]":
        with self._lock:
            return self.chat_count, list(self.tool_calls)


def _make_handler(state: "_StubState", max_steps: int):
    """Build a ``BaseHTTPRequestHandler`` subclass closing over ``state``/``max_steps`` -- serves
    the scripted OpenAI-compatible chat-completions endpoint AND the controlled tool-sandbox
    endpoint from the SAME localhost server (one port, two routes)."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # silence the default stderr access log
            pass

        def _read_json_body(self) -> Any:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def _write_json(self, status: int, payload: dict) -> None:
            try:
                body = json.dumps(payload).encode("utf-8")
            except Exception:
                body = b'{"error": "unserializable stub response"}'
                status = 500
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass  # the client may have already gone away -- never let this raise

        def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler's naming convention)
            try:
                path = self.path.split("?", 1)[0].rstrip("/")
                if path in ("/v1/chat/completions", "/chat/completions"):
                    self._read_json_body()  # drain the request body; content is not inspected
                    step, turn = state.next_chat_response(max_steps)
                    if turn is None:
                        self._write_json(
                            500, {"error": {"message": "agent_oracle: max_steps exceeded"}})
                        return
                    self._write_json(200, _render_completion(turn, step))
                    return
                if path.startswith("/tool/"):
                    name = path[len("/tool/"):]
                    args = self._read_json_body()
                    observation = state.record_tool_call(name, args)
                    self._write_json(200, {"observation": observation})
                    return
                self._write_json(404, {"error": f"agent_oracle stub: no such route {self.path!r}"})
            except Exception as exc:  # never let a per-request error kill the server thread
                try:
                    self._write_json(500, {"error": str(exc)})
                except Exception:
                    pass

        def do_GET(self):  # noqa: N802 -- readiness probes only
            self._write_json(200, {"ok": True})

    return _Handler


def _wait_stub_ready(port: int, timeout: float) -> bool:
    """Poll until the stub server's port accepts a TCP connection, bounded by ``timeout``. The
    server's listen socket is already bound (and backlog-listening) before this is ever called --
    this is defensive headroom, not the actual bind wait."""
    try:
        deadline = time.monotonic() + max(0.0, float(timeout))
    except (TypeError, ValueError):
        deadline = time.monotonic() + DEFAULT_STARTUP_TIMEOUT_S
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def _launch_agent(root_path: Path, py_exe: str, entry_path: Path, goal: Any, extra_env: dict,
                   out_fh, err_fh, *, mem_mb: int = 512, cpu_budget_s: float = 60):
    """Launch the built agent as a foreground, SANDBOXED subprocess -- the exact same launch
    discipline ``harness.fs_oracle._launch_entrypoint``/``harness.import_driver._launch_driver``
    use (scrubbed environment, POSIX resource caps, its own process group/session for whole-tree
    teardown), pointed at the built agent's declared entrypoint with the goal as ``argv[1]`` (the
    pinned agent injection contract)."""
    env = _scrubbed_env({
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(root_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        **extra_env,
    })
    cmd = [py_exe, str(entry_path), str(goal)]
    popen_kwargs: dict = dict(cwd=str(root_path), stdout=out_fh, stderr=err_fh, env=env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
        preexec_fn = _make_preexec_fn(mem_mb, cpu_budget_s)
        if preexec_fn is not None:
            popen_kwargs["preexec_fn"] = preexec_fn
    return subprocess.Popen(cmd, **popen_kwargs)


def _tail(path, limit: int = 200_000) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def _fail(note: str, *, port: "int | None" = None) -> dict:
    return {"ok": False, "tool_calls": [], "final": None, "steps": 0, "terminated": False,
            "note": note, "port": port}


def drive_agent(root: Any, entry: Any, *, script: "list", tools: "dict | None" = None,
                 goal: Any = "", env: "dict | None" = None,
                 max_steps: int = DEFAULT_MAX_STEPS, timeout: float = DEFAULT_TIMEOUT_S,
                 startup_timeout: float = DEFAULT_STARTUP_TIMEOUT_S,
                 python_exe: "str | None" = None, mem_mb: int = 512) -> dict:
    """The load-bearing oracle: host a SCRIPTED stub model + controlled tool sandbox on one
    ephemeral localhost port, point the built agent at ``entry`` (relative to ``root``) at it via
    the pinned env-var contract, run it as a real subprocess against ``goal``, and report the
    ORDERED tool-call sequence the agent actually made, its final answer, and whether the loop
    terminated cleanly.

    ``script`` is a non-empty list of turns (see :func:`tool_call_turn`/:func:`final_turn`),
    served in order -- one per ``/v1/chat/completions`` request the agent makes. ``tools`` maps a
    tool name to the canned observation the tool-sandbox endpoint returns when that tool is
    invoked (a single value, or a list consumed call-by-call). Once the agent has made more than
    ``max_steps`` chat-completion requests without terminating, the stub starts refusing further
    requests and the run is reported as non-terminated (a deterministic, bounded backstop against
    a truly runaway loop, on top of the overall ``timeout``).

    Returns ``{"ok", "tool_calls", "final", "steps", "terminated", "note", "port"}``:
    ``tool_calls`` is the ORDERED list of ``{"name", "args"}`` the tool sandbox actually observed
    (never anything the agent merely printed); ``final`` is the agent's final answer (parsed from
    its one sentinel stdout line) or ``None`` if it never printed one; ``steps`` is the number of
    scripted chat-completion turns consumed; ``terminated`` is True only when the agent exited
    with code 0 having printed its final-answer sentinel, before exceeding ``max_steps`` or the
    overall ``timeout``.

    NEVER RAISES: any failure at any stage (missing entrypoint, an unlaunchable stub server, a
    crashing/hanging/never-terminating agent, a malformed ``script``/``tools`` spec) is reported
    as an honest ``ok=False`` with a diagnostic ``note``. ALWAYS tears the stub server AND the
    agent subprocess (and any descendants) down in a ``finally`` block, so a failed or completed
    run never leaves an orphaned process or listening port behind.
    """
    httpd = None
    proc = None
    out_fh = err_fh = None
    out_path = err_path = None
    port: "int | None" = None
    try:
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return _fail(f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return _fail(f"root does not exist: {root_path}")

        if not entry:
            return _fail("no entrypoint supplied")
        entry_path = root_path / str(entry)
        if not entry_path.is_file():
            return _fail(f"entrypoint not found: {entry_path.name}")

        turns, note = _validate_script(script)
        if turns is None:
            return _fail(f"invalid script: {note}")

        try:
            max_steps_int = int(max_steps)
        except (TypeError, ValueError):
            return _fail(f"max_steps must be an int, got {max_steps!r}")
        if max_steps_int < 1:
            return _fail("max_steps must be >= 1")

        state = _StubState(turns, tools)
        handler_cls = _make_handler(state, max_steps_int)

        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        except OSError as exc:
            return _fail(f"could not start the stub model server: {exc}")
        httpd.daemon_threads = True
        port = httpd.server_address[1]
        server_thread = threading.Thread(
            target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        server_thread.start()

        if not _wait_stub_ready(port, startup_timeout):
            return _fail("stub model server did not become ready within startup_timeout", port=port)

        base_url = f"http://127.0.0.1:{port}/v1"
        tool_url = f"http://127.0.0.1:{port}/tool"
        extra_env = {
            "OPENAI_BASE_URL": base_url,
            "OPENAI_API_KEY": "sk-jaros-agent-oracle-dummy",
            "MODEL_URL": base_url,
            "JAROS_TOOL_URL": tool_url,
        }
        if isinstance(env, dict):
            try:
                extra_env.update({str(k): str(v) for k, v in env.items()})
            except Exception:
                pass

        py_exe = python_exe or sys.executable or "python"

        try:
            fd_out, out_path = tempfile.mkstemp(prefix="jcode_agent_oracle_out_")
            fd_err, err_path = tempfile.mkstemp(prefix="jcode_agent_oracle_err_")
            os.close(fd_out)
            os.close(fd_err)
            out_fh = open(out_path, "w", encoding="utf-8")
            err_fh = open(err_path, "w", encoding="utf-8")
            cpu_budget_s = float(timeout) + 30
            proc = _launch_agent(root_path, py_exe, entry_path, goal, extra_env, out_fh, err_fh,
                                  mem_mb=mem_mb, cpu_budget_s=cpu_budget_s)
        except Exception as exc:
            return _fail(f"failed to launch agent: {exc}", port=port)

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            _kill_tree(proc)
            for fh in (out_fh, err_fh):
                try:
                    if fh:
                        fh.close()
                except Exception:
                    pass

        steps, tool_calls = state.snapshot()
        exceeded_max_steps = steps > max_steps_int

        stdout_text = _tail(out_path)
        stderr_text = _tail(err_path)

        final_text = None
        for line in stdout_text.splitlines():
            m = _FINAL_RE.match(line.strip())
            if m:
                final_text = m.group("payload")  # keep the LAST sentinel line, if more than one

        if timed_out:
            note = f"agent timed out after {timeout}s; process tree killed"
            if stderr_text.strip():
                note += f" -- stderr tail: {stderr_text[-400:]!r}"
            return {"ok": False, "tool_calls": tool_calls, "final": final_text, "steps": steps,
                    "terminated": False, "note": note, "port": port}

        if exceeded_max_steps:
            return {
                "ok": False, "tool_calls": tool_calls, "final": final_text, "steps": steps,
                "terminated": False, "port": port,
                "note": f"agent exceeded max_steps={max_steps_int} scripted model turns "
                         f"without terminating",
            }

        rc = proc.returncode
        if rc != 0:
            note = f"agent exited with returncode {rc}"
            if stderr_text.strip():
                note += f" -- stderr tail: {stderr_text[-400:]!r}"
            return {"ok": False, "tool_calls": tool_calls, "final": final_text, "steps": steps,
                    "terminated": False, "note": note, "port": port}

        if final_text is None:
            return {
                "ok": False, "tool_calls": tool_calls, "final": None, "steps": steps,
                "terminated": False, "port": port,
                "note": "agent exited cleanly but never printed the __JAROS_AGENT_FINAL__ sentinel",
            }

        return {
            "ok": True, "tool_calls": tool_calls, "final": final_text, "steps": steps,
            "terminated": True, "port": port,
            "note": "ok: agent ran to completion against the scripted stub model",
        }
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return _fail(f"drive_agent failed unexpectedly: {exc}", port=port)
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
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass


# --------------------------------------------------------------------------------------------
# check_agent -- pure, never-raise grader over drive_agent's captured evidence
# --------------------------------------------------------------------------------------------

def _args_are_subset(actual: Any, expected: Any) -> bool:
    """True when every key in ``expected`` is present in ``actual`` with an equal value (a
    partial-args check, mirroring ``server_oracle._subset``) -- or when ``expected`` supplies no
    args constraint at all."""
    if expected is None or (isinstance(expected, dict) and not expected):
        return True
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    for k, v in expected.items():
        if k not in actual or actual[k] != v:
            return False
    return True


def check_agent(result: Any, *, expect_tool_calls: "list", expect_final_contains: "str | None" = None,
                 expect_terminated: bool = True) -> "tuple[bool, str]":
    """Assert :func:`drive_agent`'s captured evidence matches expectations. Pure -- never
    launches anything, never touches the network. NEVER RAISES: malformed input is reported as an
    honest ``(False, <reason>)``, never an uncaught exception.

    - ``expect_tool_calls``: an ORDERED list of ``{"name": str, "args": dict}`` (``args`` is
      optional and checked as a SUBSET of the actually-captured args, so a caller can assert only
      the keys it cares about). The captured ``tool_calls`` sequence must match this list
      EXACTLY in length and order.
    - ``expect_terminated`` (default ``True``): the agent must have exited cleanly with its final
      sentinel printed, before exceeding ``max_steps`` or the overall timeout.
    - ``expect_final_contains``: when supplied, the final answer must contain this substring.

    Returns ``(ok, note)``.
    """
    try:
        if not isinstance(result, dict):
            return False, f"result must be a dict (as returned by drive_agent), got {type(result)!r}"

        expected_calls = list(expect_tool_calls) if isinstance(expect_tool_calls, (list, tuple)) else None
        if expected_calls is None:
            return False, f"expect_tool_calls must be a list, got {type(expect_tool_calls)!r}"

        actual_calls_raw = result.get("tool_calls")
        actual_calls = list(actual_calls_raw) if isinstance(actual_calls_raw, list) else []

        if len(actual_calls) != len(expected_calls):
            return False, (
                f"tool_call count mismatch: expected {len(expected_calls)}, got "
                f"{len(actual_calls)} -- expected {expected_calls!r}, actual {actual_calls!r}"
            )

        for i, (expected, actual) in enumerate(zip(expected_calls, actual_calls)):
            if not isinstance(expected, dict) or not expected.get("name"):
                return False, f"expect_tool_calls[{i}] must be a dict with a non-empty 'name' key"
            if not isinstance(actual, dict):
                return False, f"tool_calls[{i}] captured by drive_agent is malformed: {actual!r}"
            if actual.get("name") != expected["name"]:
                return False, (f"tool_calls[{i}] name mismatch: expected {expected['name']!r}, "
                                f"got {actual.get('name')!r}")
            if not _args_are_subset(actual.get("args"), expected.get("args")):
                return False, (
                    f"tool_calls[{i}] ({expected['name']!r}) args mismatch: expected a superset "
                    f"of {expected.get('args')!r}, got {actual.get('args')!r}"
                )

        actual_terminated = bool(result.get("terminated"))
        if actual_terminated != bool(expect_terminated):
            return False, (
                f"termination mismatch: expected terminated={bool(expect_terminated)}, got "
                f"{actual_terminated} (drive_agent note: {result.get('note')!r})"
            )

        if expect_final_contains is not None:
            final = result.get("final") or ""
            if str(expect_final_contains) not in str(final):
                return False, f"final answer does not contain {expect_final_contains!r}: got {final!r}"

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"check_agent failed unexpectedly: {exc}"
# #EXT-059-REQ-6 End
