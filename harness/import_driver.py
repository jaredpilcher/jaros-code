"""EXT-059 REQ-3: a deterministic, model-free IMPORT-AND-CALL acceptance oracle.

**The gap this closes (Tenet 3), mirroring `harness/fs_oracle.py` (EXT-059 REQ-1) and
`harness/datastore_oracle.py` / `harness/server_oracle.py` exactly:** today's black-box CLI oracle
(`harness.system_suite._run_single_check`) only ever runs a built system as `python entry.py` and
reads its STDOUT -- it has no way to grade a *reusable library* task (a module/package meant to be
`import`-ed and called, not run as a script). This module closes that gap for the "import-and-call"
task class: it renders a tiny stdlib-only driver snippet, runs it in a FRESH sandboxed subprocess
that `sys.path`-inserts the built module's directory, imports the built module by name, calls the
contract-named public API with oracle-chosen arguments, and reports each result via a unique
sentinel line -- the built module's own `print()` output is never trusted for anything but that
sentinel protocol.

Two-plane discipline holds throughout: this module is pure, deterministic execution-plane code
(stdlib `base64`/`json`/`re`/`subprocess`/`tempfile` only -- no new dependency, no model/reasoning
call anywhere). The generated driver is launched SANDBOXED, reusing (not reimplementing) the same
audited primitives `harness/fs_oracle.py` reuses: `harness.secure_exec._scrubbed_env` /
`_make_preexec_fn` for the scrubbed-environment + POSIX-resource-capped subprocess launch, and
`harness.server_oracle._kill_tree` for unconditional process-tree teardown in a `finally` block, so
a built library that spawns a detached child never survives a check.

**Injected dependencies for determinism:** a caller can ask the driver to install a small preamble
BEFORE any API call runs -- an injected "clock" seam that monkeypatches `time.sleep` to a
recording no-op (never real wall-clock), and/or named "spy" callables (each records its own call
count and can be configured to raise for its first N invocations before returning a fixed value) --
so retry/backoff/cache libraries can be graded deterministically. A spy is threaded into an API
call's arguments via the `{"__jaros_ref__": "<spy name>"}` marker.

**NEVER RAISES**, mirroring `harness/fs_oracle.py` exactly: a missing/unimportable module, a
broken/crashing/timing-out driver, or a malformed spec/check is always an honest `ok=False` (or a
per-check failure message) with a diagnostic `note` -- never coerced to a pass, never an uncaught
exception.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# #EXT-059-REQ-3 Start
# TASK-3: reuse (not reimplement) the exact same audited sandboxed-launch primitives
# `harness/fs_oracle.py` reuses -- the scrubbed-env/resource-cap launch convention from
# `secure_exec`, and the process-tree teardown helper `server_oracle` already defines.
from harness.secure_exec import _make_preexec_fn, _scrubbed_env
from harness.server_oracle import _kill_tree

DEFAULT_TIMEOUT_S = 15.0  # a hang is a real failure, never a hang (mirrors fs_oracle's default)

_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass
class ImportDriveResult:
    """Result of :func:`drive_import`. ``ok`` is True only when the module could be imported in
    the sandboxed driver AND EVERY post-condition in ``checks`` held against the driver's
    sentinel-reported behavior. ``failures`` is a list of human-readable diagnostic strings
    (empty when ``ok`` is True); ``note`` always carries a short, honest summary -- never
    fabricated, never silently swallowed. ``sleep_call_count`` is the number of times the driven
    code called the injected clock seam (``None`` when no clock was injected) -- exposed so a
    caller can independently confirm no real wall-clock sleep occurred."""

    ok: bool
    checks_passed: int = 0
    failures: "list" = field(default_factory=list)
    note: str = ""
    sleep_call_count: "int | None" = None


# --------------------------------------------------------------------------------------------
# Sentinel protocol -- each is exactly ONE stdout line, greeped by regex (never the module's own
# arbitrary printing). Payload is bounded by the FIRST occurrence of the fixed prefix and the
# LAST occurrence of the fixed "__END__" suffix on that line (greedy `.*` + `$` anchor), so an
# embedded "__END__" substring inside a JSON payload can never truncate parsing early.
# --------------------------------------------------------------------------------------------
_RESULT_RE = re.compile(r"^__JAROS_RESULT__(?P<id>[A-Za-z0-9_]+)__(?P<payload>.*)__END__$")
_RAISED_RE = re.compile(r"^__JAROS_RAISED__(?P<id>[A-Za-z0-9_]+)__(?P<exc>[A-Za-z0-9_.]+)__END__$")
_CALLCOUNT_RE = re.compile(r"^__JAROS_CALLCOUNT__(?P<name>[A-Za-z0-9_]+)__(?P<count>\d+)__END__$")
_SLEEPCALLS_RE = re.compile(r"^__JAROS_SLEEPCALLS__(?P<count>\d+)__END__$")
_IMPORT_ERROR_RE = re.compile(r"^__JAROS_IMPORT_ERROR__(?P<exc>[A-Za-z0-9_.]*)__(?P<msg>.*)__END__$")


# The rendered driver is stdlib-only and NEVER `eval`/`exec`s any caller-supplied string -- every
# API call target is resolved purely via chained `getattr()` (validated safe by `_TARGET_RE`
# before rendering), and every argument is plain JSON data (or a `{"__jaros_ref__": ...}` marker
# resolved to an injected spy). A raw string (`r'''...'''`) so `\n` etc. inside the generated
# script's own source stays literal two-character text, not an interpreted escape at render time.
_DRIVER_TEMPLATE = r'''"""Auto-generated by harness.import_driver -- runs in a fresh sandboxed
subprocess. Stdlib only. Reports every result via a unique sentinel line; never trusts its own
printing for anything but the sentinel protocol itself."""
import base64
import builtins
import importlib
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

_PAYLOAD = json.loads(base64.b64decode("__PAYLOAD_B64__").decode("utf-8"))

_sleep_calls = None
if _PAYLOAD.get("injected", {}).get("clock"):
    _sleep_calls = []

    def _fake_sleep(seconds):
        _sleep_calls.append(seconds)

    time.sleep = _fake_sleep


def _make_spy(cfg):
    calls = []
    return_value = cfg.get("return_value")
    raise_exception_name = cfg.get("raise_exception")
    raise_count = int(cfg.get("raise_count") or 0)
    raise_message = cfg.get("raise_message") or "injected spy failure"

    def _spy(*args, **kwargs):
        calls.append(1)
        if raise_exception_name and len(calls) <= raise_count:
            exc_cls = getattr(builtins, raise_exception_name, Exception)
            raise exc_cls(raise_message)
        return return_value

    _spy.__jaros_calls__ = calls
    return _spy


_spies = {}
for _spy_name, _spy_cfg in (_PAYLOAD.get("injected", {}).get("spies") or {}).items():
    _spies[_spy_name] = _make_spy(_spy_cfg)

_bindings = {}


def _resolve_ref(value):
    if isinstance(value, dict) and set(value.keys()) == {"__jaros_ref__"}:
        name = value["__jaros_ref__"]
        if name in _spies:
            return _spies[name]
        if name in _bindings:
            return _bindings[name]
        raise NameError("unknown injected ref: " + repr(name))
    if isinstance(value, list):
        return [_resolve_ref(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_ref(v) for k, v in value.items()}
    return value


try:
    _mod = importlib.import_module(_PAYLOAD["module"])
except Exception as _exc:
    _msg = str(_exc).replace("\n", " ")
    print("__JAROS_IMPORT_ERROR__" + type(_exc).__name__ + "__" + _msg + "__END__", flush=True)
    sys.exit(1)


def _resolve_target(path):
    parts = path.split(".")
    first = parts[0]
    if first in _bindings:
        obj = _bindings[first]
    elif first in _spies:
        obj = _spies[first]
    else:
        obj = getattr(_mod, first)
    for part in parts[1:]:
        obj = getattr(obj, part)
    return obj


for _call in _PAYLOAD.get("api_calls", []):
    _call_id = _call["id"]
    _target = _call["target"]
    _args = [_resolve_ref(a) for a in _call.get("args", [])]
    _kwargs = {k: _resolve_ref(v) for k, v in (_call.get("kwargs") or {}).items()}
    try:
        _fn = _resolve_target(_target)
        _result = _fn(*_args, **_kwargs)
        _bindings[_call_id] = _result
        try:
            _payload_str = json.dumps(_result)
        except TypeError:
            _payload_str = json.dumps({"__unserializable__": repr(_result)})
        print("__JAROS_RESULT__" + _call_id + "__" + _payload_str + "__END__", flush=True)
    except Exception as _exc:
        _bindings[_call_id] = None
        print("__JAROS_RAISED__" + _call_id + "__" + type(_exc).__name__ + "__END__", flush=True)

for _spy_name, _spy_obj in _spies.items():
    print("__JAROS_CALLCOUNT__" + _spy_name + "__" + str(len(_spy_obj.__jaros_calls__)) + "__END__",
          flush=True)

if _sleep_calls is not None:
    print("__JAROS_SLEEPCALLS__" + str(len(_sleep_calls)) + "__END__", flush=True)
'''


def _render_driver_source(module: str, api_calls: "list", injected: "dict") -> str:
    """Render the stdlib-only driver script as a string, embedding ``module``/``api_calls``/
    ``injected`` as a base64-encoded JSON payload (avoids any quoting/escaping hazard -- the
    payload can contain arbitrary strings, including quote characters or ``__END__``-like
    substrings, without corrupting the generated Python source)."""
    payload = {"module": module, "api_calls": api_calls, "injected": injected or {}}
    payload_json = json.dumps(payload)
    payload_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
    return _DRIVER_TEMPLATE.replace("__PAYLOAD_B64__", payload_b64)


def _launch_driver(root_path: Path, py_exe: str, driver_path: Path, out_fh, err_fh, *,
                    mem_mb: int = 512, cpu_budget_s: float = 60):
    """Launch the rendered driver as a foreground, SANDBOXED subprocess -- the exact same launch
    discipline `harness.fs_oracle._launch_entrypoint` uses (scrubbed environment, POSIX resource
    caps, its own process group/session for whole-tree teardown), just pointed at our own
    generated driver file instead of a built-system entrypoint file living under ``root``. The
    driver's ``os.getcwd()`` (== ``root_path``, since that is the subprocess ``cwd``) is what it
    inserts onto ``sys.path`` to locate the built module -- so no host path is embedded into the
    rendered script itself."""
    env = _scrubbed_env({
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(root_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    })
    cmd = [py_exe, str(driver_path)]
    popen_kwargs: dict = dict(cwd=str(root_path), stdout=out_fh, stderr=err_fh, env=env)
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
        preexec_fn = _make_preexec_fn(mem_mb, cpu_budget_s)
        if preexec_fn is not None:
            popen_kwargs["preexec_fn"] = preexec_fn
    return subprocess.Popen(cmd, **popen_kwargs)


def _tail(path, limit: int = 800) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def _cleanup(*paths: "Path | str | None") -> None:
    for p in paths:
        if not p:
            continue
        try:
            os.remove(str(p))
        except OSError:
            pass


def _parse_sentinels(stdout_text: str) -> dict:
    """Parse every sentinel line the driver printed. Returns a dict of ``results`` (call_id ->
    parsed JSON value), ``raised`` (call_id -> exception type name), ``call_counts`` (spy name ->
    int), ``sleep_calls`` (int, or ``None`` when no clock was injected), and ``import_error``
    (``(exception_type_name, message)`` or ``None``). Malformed/unparseable lines are ignored --
    never raises."""
    results: dict = {}
    raised: dict = {}
    call_counts: dict = {}
    sleep_calls = None
    import_error = None
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _IMPORT_ERROR_RE.match(line)
        if m:
            import_error = (m.group("exc"), m.group("msg"))
            continue
        m = _RESULT_RE.match(line)
        if m:
            try:
                results[m.group("id")] = json.loads(m.group("payload"))
            except Exception:
                results[m.group("id")] = {"__unparseable__": m.group("payload")}
            continue
        m = _RAISED_RE.match(line)
        if m:
            raised[m.group("id")] = m.group("exc")
            continue
        m = _CALLCOUNT_RE.match(line)
        if m:
            call_counts[m.group("name")] = int(m.group("count"))
            continue
        m = _SLEEPCALLS_RE.match(line)
        if m:
            sleep_calls = int(m.group("count"))
            continue
    return {
        "results": results, "raised": raised, "call_counts": call_counts,
        "sleep_calls": sleep_calls, "import_error": import_error,
    }


def _eval_check(parsed: dict, check: Any) -> "tuple[bool, str]":
    """Evaluate ONE declarative post-condition against ``parsed`` (the driver's sentinel-reported
    behavior -- this function never looks at anything the built module printed on its own).
    Supported ``check["kind"]`` values: ``returns_equals`` (the named call's sentinel-reported
    return value equals ``check["expected"]``), ``raises`` (the named call's sentinel-reported
    exception type name equals ``check["exception"]``), ``call_count`` (the named injected spy's
    sentinel-reported invocation count equals ``check["expected"]``). Never raises -- a malformed
    check or a missing call_id/spy name is reported as an honest ``(False, <reason>)``."""
    try:
        if not isinstance(check, dict):
            return False, f"malformed check (must be a dict), got {type(check)!r}"
        kind = check.get("kind")

        if kind == "returns_equals":
            call_id = check.get("call_id")
            if call_id in parsed["raised"]:
                return False, (f"call {call_id!r} raised {parsed['raised'][call_id]} instead of "
                                f"returning a value")
            if call_id not in parsed["results"]:
                return False, f"no result recorded for call_id {call_id!r} (driver may have crashed)"
            actual = parsed["results"][call_id]
            expected = check.get("expected")
            if actual != expected:
                return False, f"call {call_id!r} returned {actual!r}, expected {expected!r}"
            return True, "ok"

        if kind == "raises":
            call_id = check.get("call_id")
            expected_exc = check.get("exception")
            if call_id in parsed["results"]:
                return False, (f"call {call_id!r} returned {parsed['results'][call_id]!r} instead "
                                f"of raising {expected_exc!r}")
            if call_id not in parsed["raised"]:
                return False, f"no result recorded for call_id {call_id!r} (driver may have crashed)"
            actual_exc = parsed["raised"][call_id]
            if actual_exc != expected_exc:
                return False, f"call {call_id!r} raised {actual_exc}, expected {expected_exc}"
            return True, "ok"

        if kind == "call_count":
            spy_name = check.get("spy")
            expected = check.get("expected")
            if spy_name not in parsed["call_counts"]:
                return False, f"no call-count recorded for spy {spy_name!r}"
            actual = parsed["call_counts"][spy_name]
            if actual != expected:
                return False, f"spy {spy_name!r} was called {actual} time(s), expected {expected}"
            return True, "ok"

        return False, f"unknown check kind: {kind!r}"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"check evaluation raised: {exc}"


def drive_import(root: Any, module: Any, api_calls: "list", checks: "list", *,
                  timeout: float = DEFAULT_TIMEOUT_S, injected: "dict | None" = None,
                  python_exe: "str | None" = None, mem_mb: int = 512) -> ImportDriveResult:
    """The load-bearing oracle: render a driver, run it as a FRESH sandboxed subprocess that
    imports ``module`` (a module/package name resolvable under ``root`` via ``sys.path``) and
    calls each entry of ``api_calls`` (``{"id": str, "target": "dotted.path", "args": [...],
    "kwargs": {...}}``), then grade ``checks`` against the driver's sentinel-reported behavior --
    never trusting anything the built module printed on its own.

    ``injected`` optionally supplies ``{"clock": True}`` (monkeypatches ``time.sleep`` to a
    recording no-op BEFORE any API call runs -- never real wall-clock) and/or
    ``{"spies": {"<name>": {"return_value": ..., "raise_exception": "<ExcName>",
    "raise_count": N}}}`` (each spy records its own call count and raises for its first N
    invocations, then returns ``return_value``); reference a spy from an API call's
    ``args``/``kwargs`` via ``{"__jaros_ref__": "<name>"}``.

    1. **Launch** -- the rendered driver is run via :func:`_launch_driver` (a scrubbed environment
       + POSIX resource caps, mirroring `harness.fs_oracle`'s own sandboxed launch convention),
       bounded by ``timeout``.
    2. **Teardown** -- the process (and any descendants it spawned) is ALWAYS torn down via
       ``server_oracle._kill_tree`` in a ``finally`` block, whether it finished cleanly, crashed,
       or timed out.
    3. **Grade** -- every entry in ``checks`` is evaluated by :func:`_eval_check` against the
       sentinel-reported results/raised-exceptions/call-counts the driver printed; an unimportable
       module short-circuits as an honest failure before any check is evaluated.

    Returns an :class:`ImportDriveResult` with ``ok=True`` only when the module imported and EVERY
    check held. NEVER RAISES: any failure at any stage (missing/unimportable module, a timeout, a
    malformed spec/check) is reported as an honest ``ok=False`` with a diagnostic ``note``.
    """
    try:
        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return ImportDriveResult(ok=False, note=f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return ImportDriveResult(ok=False, note=f"root does not exist: {root_path}")

        if not isinstance(module, str) or not module.strip():
            return ImportDriveResult(ok=False, note=f"module must be a non-empty string, got {module!r}")

        calls_list = list(api_calls) if isinstance(api_calls, (list, tuple)) else None
        if calls_list is None:
            return ImportDriveResult(ok=False, note=f"api_calls must be a list, got {type(api_calls)!r}")

        seen_ids: set = set()
        for i, call in enumerate(calls_list):
            if not isinstance(call, dict):
                return ImportDriveResult(ok=False, note=f"api_calls[{i}] must be a dict, got {type(call)!r}")
            call_id = call.get("id")
            target = call.get("target")
            if not isinstance(call_id, str) or not _ID_RE.match(call_id):
                return ImportDriveResult(ok=False, note=f"api_calls[{i}] has an invalid/missing 'id': {call_id!r}")
            if call_id in seen_ids:
                return ImportDriveResult(ok=False, note=f"api_calls[{i}] duplicate id: {call_id!r}")
            seen_ids.add(call_id)
            if not isinstance(target, str) or not _TARGET_RE.match(target):
                return ImportDriveResult(
                    ok=False, note=f"api_calls[{i}] has an invalid/missing 'target': {target!r}")

        checks_list = list(checks) if isinstance(checks, (list, tuple)) else None
        if not checks_list:
            return ImportDriveResult(ok=False, note="no checks supplied (must be a non-empty list)")

        injected_cfg = injected if isinstance(injected, dict) else {}
        spies_cfg = injected_cfg.get("spies")
        spies_cfg = spies_cfg if isinstance(spies_cfg, dict) else {}
        for spy_name in spies_cfg:
            if not isinstance(spy_name, str) or not _ID_RE.match(spy_name):
                return ImportDriveResult(ok=False, note=f"invalid injected spy name: {spy_name!r}")

        try:
            driver_source = _render_driver_source(module, calls_list, injected_cfg)
        except Exception as exc:
            return ImportDriveResult(ok=False, note=f"failed to render driver script: {exc}")

        py_exe = python_exe or sys.executable or "python"

        proc = None
        out_fh = err_fh = None
        out_path = err_path = driver_path = None
        try:
            fd_driver, driver_path_str = tempfile.mkstemp(prefix="jcode_import_driver_", suffix=".py")
            os.close(fd_driver)
            driver_path = Path(driver_path_str)
            driver_path.write_text(driver_source, encoding="utf-8")

            fd_out, out_path = tempfile.mkstemp(prefix="jcode_import_driver_out_")
            fd_err, err_path = tempfile.mkstemp(prefix="jcode_import_driver_err_")
            os.close(fd_out)
            os.close(fd_err)
            out_fh = open(out_path, "w", encoding="utf-8")
            err_fh = open(err_path, "w", encoding="utf-8")
            cpu_budget_s = float(timeout) + 30
            proc = _launch_driver(root_path, py_exe, driver_path, out_fh, err_fh,
                                   mem_mb=mem_mb, cpu_budget_s=cpu_budget_s)
        except Exception as exc:
            for fh in (out_fh, err_fh):
                try:
                    if fh:
                        fh.close()
                except Exception:
                    pass
            _kill_tree(proc)
            _cleanup(driver_path, out_path, err_path)
            return ImportDriveResult(ok=False, note=f"failed to launch import driver: {exc}")

        timed_out = False
        try:
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

        if timed_out:
            tail_out, tail_err = _tail(out_path), _tail(err_path)
            note = f"import driver timed out after {timeout}s; process tree killed"
            if tail_out or tail_err:
                note += f" -- stdout tail: {tail_out!r} stderr tail: {tail_err!r}"
            _cleanup(driver_path, out_path, err_path)
            return ImportDriveResult(ok=False, note=note)

        stdout_text = _tail(out_path, limit=1_000_000)
        stderr_text = _tail(err_path, limit=1_000_000)
        _cleanup(driver_path, out_path, err_path)

        parsed = _parse_sentinels(stdout_text)

        if parsed["import_error"] is not None:
            exc_name, msg = parsed["import_error"]
            note = f"module {module!r} failed to import in the sandboxed driver: {exc_name}: {msg}"
            if stderr_text.strip():
                note += f" -- stderr tail: {stderr_text[-400:]!r}"
            return ImportDriveResult(ok=False, note=note)

        passed = 0
        failures: "list" = []
        for i, check in enumerate(checks_list):
            ok, msg = _eval_check(parsed, check)
            if ok:
                passed += 1
            else:
                kind = check.get("kind") if isinstance(check, dict) else check
                failures.append(f"check[{i}] (kind={kind!r}) failed: {msg}")

        if failures:
            return ImportDriveResult(
                ok=False, checks_passed=passed, failures=failures,
                sleep_call_count=parsed["sleep_calls"],
                note="one or more post-conditions failed against the sandboxed import-and-call "
                     "driver's sentinel-reported behavior -- the built module's own printing is "
                     "never trusted",
            )

        return ImportDriveResult(
            ok=True, checks_passed=passed, failures=[], sleep_call_count=parsed["sleep_calls"],
            note="ok: every post-condition verified via the sandboxed import-and-call driver",
        )
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return ImportDriveResult(ok=False, note=f"drive_import failed unexpectedly: {exc}")
# #EXT-059-REQ-3 End
