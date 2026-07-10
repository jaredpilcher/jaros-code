# #EXT-059-REQ-10 Start
"""EXT-059 REQ-10: the INJECTABLE-CLOCK ORACLE -- a deterministic, model-free verifier that grades
TIME-DEPENDENT behavior by injecting a fully controllable clock into a built entity and driving it
through a scripted timeline.

**The gap this closes (Tenet 3), and why it is the single highest-demand missing oracle in the
substrate:** three independent atlas research waves converged on the SAME gap -- 39 mapped classes
across SLA/deadline timers, token/magic-link validity windows, auth lockout/backoff, digest/batch
windows, interest/subscription accrual math, monitor/scheduler cadence, grace-period logic, and
retention/expiry sweepers ALL share one honesty core that no existing oracle in this substrate
checks: correctness that depends on the PASSAGE OF TIME. Grading that honestly with a real
`time.sleep()` would make every test slow and flaky (and an actual multi-hour SLA window is not
something a test suite can wait out at all); grading it by mocking `datetime.now()`/`time.time()`
at the TEST level trusts the built code to call exactly the function the oracle patched, which is
itself part of what needs verifying. This module instead makes clock injection the CONTRACT: the
built entity's constructor must accept a keyword argument (named by `spec['clock_param']`, e.g.
`now_fn`) that is a zero-argument callable returning the current epoch-seconds `int` -- the entity
must call THAT whenever it needs the current time -- and the oracle drives that callable directly,
jumping it forward, backward, or across a boundary in zero real wall-clock time, so a script can
assert both "valid at t" and "expired at t+3601" as two ordinary asserts in the same run, no matter
how large the gap is in simulated seconds.

**The pinned contract (mirrors `harness/conservation_oracle.py`/`harness/double_entry_oracle.py`'s
class-based-entity discipline, extended with a per-call clock seam that has no analogue in either
sibling):** the built module exposes an entity CLASS whose constructor accepts the
`spec['clock_param']`-named keyword argument described above, and one method per timeline call
(`spec['timeline'][i]['call']`) whose behavior is a pure function of that injected clock's CURRENT
reading, never of the real wall clock.

**How the timeline is driven (the structural trick -- no analogue in the sibling oracles, which
never touch time at all):** `spec['timeline']` is an ORDERED list of steps, each declaring an
epoch-seconds `at`, a `call` (method name), optional `args`/`kwargs`, and an `expect` of exactly
`{"returns": <value>}` or `{"raises": "<ExceptionName>"}`. Before EACH step's call, the oracle's
generated driver sets the injected clock to that step's `at` -- so the built entity's `now_fn()`
reads exactly that value at exactly that call, regardless of how much (or how little) REAL time has
elapsed since the previous step. `validate_spec` requires the timeline's `at` values to be
non-decreasing UNLESS a step explicitly opts in via `"allow_backward": true` (clock-skew/NTP-
adjustment scenarios), so a spec that silently time-travels backward by accident is rejected before
anything is ever driven.

**Why this catches the flagship dishonesty case (a build that secretly uses the REAL clock instead
of the injected one):** a correctly-wired entity's behavior tracks the INJECTED `now_fn`, so a
timeline that asserts "valid at t" then jumps the injected clock to "t + 3601s, now expired" and
asserts the SECOND behavior can only pass if the entity actually consulted `now_fn()` both times.
An entity that instead calls `time.time()`/`datetime.now()` internally sees the two calls happen
within real MILLISECONDS of each other (the driver never sleeps) -- so it reports the SAME
(t-relative) answer both times, and the expiry assertion fails naturally. No timing hack, no flaky
`time.sleep()` in the test: the wall-clock-impossible jump is the proof.

**How this reuses the substrate (no reimplementation of `harness/import_driver.py`, imported and
called, never modified):** unlike the sibling oracles (which render exactly one
`harness.import_driver.drive_import` `api_calls` plan because their contract needs no per-call
mutation between calls), the clock contract needs the injected clock MUTATED between successive
calls in the SAME live subprocess -- something `import_driver`'s existing driver template has no
seam for (its injected-clock support only fakes `time.sleep()`, and its `spies` are configured with
a single static return value, not a per-call value sequence). Rather than modify
`harness/import_driver.py` to add a seam only this oracle needs, this module follows
`harness/import_driver.py`'s OWN pattern one level up: it renders its OWN small stdlib-only driver
(a mutable module-level `_CLOCK` holder + a `_now()` closure passed as the injected keyword, set
explicitly before every timeline call), launches it via the exact same audited sandboxed-subprocess
primitive `import_driver._launch_driver` already defines (scrubbed env, POSIX resource caps,
`server_oracle._kill_tree` teardown in a `finally` block), and reuses `import_driver`'s OWN
sentinel-line protocol and post-condition graders (`_parse_sentinels`/`_eval_check`) UNMODIFIED to
parse and grade the results -- so the only genuinely NEW code here is the driver template's clock-
mutation seam and this module's own declarative spec/plan rendering; every other moving part is
reused, not rebuilt.

**NEVER RAISES**, mirroring every sibling oracle in this substrate exactly: a malformed spec
(including a timeline whose `at` values go backward without `allow_backward`, or an `expect` that
is neither `returns` nor `raises`), a missing/uncallable entity, or a crashing/garbage fixture is
always an honest `accepted=False` with a diagnostic note -- never coerced to a pass, never an
uncaught exception.

**FOLLOW-UP (not built here):** a concurrent/interleaved-clock variant (two entities racing against
independently-driven clocks) and a service-based variant that drives calls over HTTP via
`harness/server_oracle.py`'s launch/request lifecycle, for time-dependent systems exposed as a web
API rather than an importable class.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from harness.import_driver import (
    DEFAULT_TIMEOUT_S,
    _cleanup,
    _eval_check,
    _launch_driver,
    _parse_sentinels,
    _tail,
)
from harness.server_oracle import _kill_tree

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CONSTRUCT_CALL_ID = "construct"


# The rendered driver is stdlib-only and NEVER `eval`/`exec`s any caller-supplied string -- the
# entity class name and every method name are validated safe by `_IDENT_RE` before rendering, and
# every argument is plain JSON data threaded straight through `json.dumps`/`json.loads`. Follows
# `harness/import_driver.py`'s own driver-template + sentinel-line-protocol pattern, reusing its
# parser/grader (`_parse_sentinels`/`_eval_check`) UNCHANGED -- see the module docstring for why a
# fresh (not reused) driver TEMPLATE is required here despite reusing everything else.
_CLOCK_DRIVER_TEMPLATE = r'''"""Auto-generated by harness.clock_oracle -- runs in a fresh sandboxed
subprocess. Stdlib only. Constructs the built entity with an injected clock callable, advances that
clock EXPLICITLY before every timeline call (never a real wall-clock sleep), and reports every
result via the exact sentinel-line protocol harness.import_driver defines; never trusts the built
module's own printing for anything but that protocol."""
import base64
import importlib
import json
import os
import sys

sys.path.insert(0, os.getcwd())

_PAYLOAD = json.loads(base64.b64decode("__PAYLOAD_B64__").decode("utf-8"))

_CLOCK = [0]


def _now():
    return _CLOCK[0]


def _report_result(call_id, result):
    try:
        payload_str = json.dumps(result)
    except TypeError:
        payload_str = json.dumps({"__unserializable__": repr(result)})
    print("__JAROS_RESULT__" + call_id + "__" + payload_str + "__END__", flush=True)


def _report_raised(call_id, exc):
    print("__JAROS_RAISED__" + call_id + "__" + type(exc).__name__ + "__END__", flush=True)


try:
    _mod = importlib.import_module(_PAYLOAD["module"])
except Exception as _exc:
    _msg = str(_exc).replace("\n", " ")
    print("__JAROS_IMPORT_ERROR__" + type(_exc).__name__ + "__" + _msg + "__END__", flush=True)
    sys.exit(1)

_entity = None
try:
    _entity_cls = getattr(_mod, _PAYLOAD["entity"])
    _construct_kwargs = dict(_PAYLOAD.get("construct_kwargs") or {})
    _construct_kwargs[_PAYLOAD["clock_param"]] = _now
    _entity = _entity_cls(*(_PAYLOAD.get("construct_args") or []), **_construct_kwargs)
    _report_result("__CONSTRUCT_ID__", None)
except Exception as _exc:
    _report_raised("__CONSTRUCT_ID__", _exc)

if _entity is not None:
    for _i, _step in enumerate(_PAYLOAD.get("timeline", [])):
        _CLOCK[0] = _step["at"]
        _call_id = "step" + str(_i)
        _args = _step.get("args") or []
        _kwargs = _step.get("kwargs") or {}
        try:
            _fn = getattr(_entity, _step["call"])
            _result = _fn(*_args, **_kwargs)
            _report_result(_call_id, _result)
        except Exception as _exc:
            _report_raised(_call_id, _exc)

    for _read in _PAYLOAD.get("final_reads", []):
        _rid = _read["id"]
        try:
            _fn = getattr(_entity, _read["target"])
            _result = _fn()
            _report_result(_rid, _result)
        except Exception as _exc:
            _report_raised(_rid, _exc)
'''


def _render_clock_driver_source(payload: dict) -> str:
    """Render the stdlib-only clock driver as a string, embedding ``payload`` as a base64-encoded
    JSON blob (avoids any quoting/escaping hazard), mirroring
    `harness.import_driver._render_driver_source`'s own encoding convention exactly."""
    payload_json = json.dumps(payload)
    payload_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
    source = _CLOCK_DRIVER_TEMPLATE.replace("__PAYLOAD_B64__", payload_b64)
    return source.replace("__CONSTRUCT_ID__", _CONSTRUCT_CALL_ID)


def validate_spec(spec: Any) -> "tuple[bool, str]":
    """Validate the declarative clock spec shape BEFORE anything is driven. Returns
    ``(True, "ok")`` when the spec is well-formed, else ``(False, <diagnostic reason>)``. Never
    raises -- any malformed input (wrong type, missing key, a timeline that silently goes
    backward, a malformed `expect`) is reported honestly rather than surfacing as an exception
    later during driving."""
    try:
        if not isinstance(spec, dict):
            return False, f"spec must be a dict, got {type(spec)!r}"

        clock_param = spec.get("clock_param")
        if not isinstance(clock_param, str) or not _IDENT_RE.match(clock_param):
            return False, f"spec['clock_param'] must be a valid identifier, got {clock_param!r}"

        construct_args = spec.get("construct_args")
        if construct_args is not None and not isinstance(construct_args, (list, tuple)):
            return False, "spec['construct_args'] must be a list when present"

        construct_kwargs = spec.get("construct_kwargs")
        if construct_kwargs is not None and not isinstance(construct_kwargs, dict):
            return False, "spec['construct_kwargs'] must be a dict when present"
        if construct_kwargs and clock_param in construct_kwargs:
            return False, (
                f"spec['construct_kwargs'] must not already define {clock_param!r} -- the oracle "
                f"injects the clock callable under that key itself"
            )

        timeline = spec.get("timeline")
        if not isinstance(timeline, (list, tuple)) or not timeline:
            return False, "spec['timeline'] must be a non-empty list of ordered timeline steps"

        prev_at = None
        for i, step in enumerate(timeline):
            if not isinstance(step, dict):
                return False, f"timeline[{i}] must be a dict, got {type(step)!r}"

            at = step.get("at")
            if not isinstance(at, int) or isinstance(at, bool):
                return False, f"timeline[{i}]['at'] must be an int (epoch seconds), got {at!r}"

            call = step.get("call")
            if not isinstance(call, str) or not _IDENT_RE.match(call):
                return False, f"timeline[{i}]['call'] must be a valid identifier, got {call!r}"

            if "args" in step and not isinstance(step["args"], (list, tuple)):
                return False, f"timeline[{i}]['args'] must be a list when present"
            if "kwargs" in step and not isinstance(step["kwargs"], dict):
                return False, f"timeline[{i}]['kwargs'] must be a dict when present"

            expect = step.get("expect")
            if not isinstance(expect, dict) or set(expect.keys()) not in ({"returns"}, {"raises"}):
                return False, (
                    f"timeline[{i}]['expect'] must be a dict with exactly one key, either "
                    f"'returns' (any JSON-serializable expected value) or 'raises' (an exception "
                    f"type name), got {expect!r}"
                )
            if "raises" in expect:
                exc_name = expect["raises"]
                if not isinstance(exc_name, str) or not _IDENT_RE.match(exc_name):
                    return False, (
                        f"timeline[{i}]['expect']['raises'] must be a valid identifier, got "
                        f"{exc_name!r}"
                    )

            allow_backward = step.get("allow_backward", False)
            if not isinstance(allow_backward, bool):
                return False, f"timeline[{i}]['allow_backward'] must be a bool when present"
            if prev_at is not None and at < prev_at and not allow_backward:
                return False, (
                    f"timeline[{i}]['at']={at!r} goes backward from the previous step's "
                    f"at={prev_at!r} without 'allow_backward': True -- a timeline must be "
                    f"non-decreasing unless a backward jump is explicitly declared"
                )
            prev_at = at

        expect_final = spec.get("expect_final")
        if expect_final is not None:
            if not isinstance(expect_final, dict) or not expect_final:
                return False, "spec['expect_final'] must be a non-empty dict when present"
            for key in expect_final:
                if not isinstance(key, str) or not _IDENT_RE.match(key):
                    return False, (
                        f"spec['expect_final'] key {key!r} must be a valid identifier (a "
                        f"zero-arg entity reader method name)"
                    )

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"validate_spec failed unexpectedly: {exc}"


def _build_payload_and_checks(module: str, entity: str, spec: dict) -> "tuple[dict, list]":
    """Render the driver ``payload`` and the ``checks`` list `_eval_check` grades against it: the
    entity is constructed once with the injected clock threaded into `spec['clock_param']`, then
    every `spec['timeline']` step is called in order (the driver sets the clock to that step's
    `at` immediately before the call), then every `spec['expect_final']` reader (if any) is called
    once more after the whole script."""
    expect_final = spec.get("expect_final") or {}

    payload = {
        "module": module,
        "entity": entity,
        "clock_param": spec["clock_param"],
        "construct_args": list(spec.get("construct_args") or []),
        "construct_kwargs": dict(spec.get("construct_kwargs") or {}),
        "timeline": [
            {
                "at": step["at"],
                "call": step["call"],
                "args": list(step.get("args") or []),
                "kwargs": dict(step.get("kwargs") or {}),
            }
            for step in spec["timeline"]
        ],
        "final_reads": [
            {"id": f"final_{name}", "target": name} for name in sorted(expect_final.keys())
        ],
    }

    checks: "list" = [
        {"kind": "returns_equals", "call_id": _CONSTRUCT_CALL_ID, "expected": None},
    ]
    for i, step in enumerate(spec["timeline"]):
        call_id = f"step{i}"
        expect = step["expect"]
        if "returns" in expect:
            checks.append({"kind": "returns_equals", "call_id": call_id, "expected": expect["returns"]})
        else:
            checks.append({"kind": "raises", "call_id": call_id, "exception": expect["raises"]})

    for name in sorted(expect_final.keys()):
        checks.append({
            "kind": "returns_equals", "call_id": f"final_{name}", "expected": expect_final[name],
        })

    return payload, checks


def _drive_clock(root: Any, payload: dict, checks: "list", *, timeout: float,
                  python_exe: "str | None", mem_mb: int) -> "tuple[bool, str]":
    """Render the clock driver, run it as a FRESH sandboxed subprocess (reusing
    `harness.import_driver._launch_driver` UNMODIFIED for the scrubbed-env/resource-capped launch
    and `harness.server_oracle._kill_tree` for unconditional teardown), then grade ``checks``
    against the driver's sentinel-reported behavior via `harness.import_driver._eval_check`
    UNMODIFIED. Mirrors `harness.import_driver.drive_import`'s own launch/teardown/grade shape."""
    try:
        root_path = Path(root)
    except (TypeError, ValueError) as exc:
        return False, f"invalid root: {root!r}: {exc}"
    if not root_path.exists() or not root_path.is_dir():
        return False, f"root does not exist: {root_path}"

    py_exe = python_exe or sys.executable or "python"

    try:
        driver_source = _render_clock_driver_source(payload)
    except Exception as exc:
        return False, f"failed to render clock driver script: {exc}"

    proc = None
    out_fh = err_fh = None
    out_path = err_path = driver_path = None
    try:
        fd_driver, driver_path_str = tempfile.mkstemp(prefix="jcode_clock_driver_", suffix=".py")
        os.close(fd_driver)
        driver_path = Path(driver_path_str)
        driver_path.write_text(driver_source, encoding="utf-8")

        fd_out, out_path = tempfile.mkstemp(prefix="jcode_clock_driver_out_")
        fd_err, err_path = tempfile.mkstemp(prefix="jcode_clock_driver_err_")
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
        return False, f"failed to launch clock driver: {exc}"

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
        note = f"clock driver timed out after {timeout}s; process tree killed"
        if tail_out or tail_err:
            note += f" -- stdout tail: {tail_out!r} stderr tail: {tail_err!r}"
        _cleanup(driver_path, out_path, err_path)
        return False, note

    stdout_text = _tail(out_path, limit=1_000_000)
    stderr_text = _tail(err_path, limit=1_000_000)
    _cleanup(driver_path, out_path, err_path)

    parsed = _parse_sentinels(stdout_text)

    if parsed["import_error"] is not None:
        exc_name, msg = parsed["import_error"]
        note = (
            f"module {payload['module']!r} failed to import in the sandboxed clock driver: "
            f"{exc_name}: {msg}"
        )
        if stderr_text.strip():
            note += f" -- stderr tail: {stderr_text[-400:]!r}"
        return False, note

    failures: "list" = []
    for i, check in enumerate(checks):
        ok, msg = _eval_check(parsed, check)
        if not ok:
            kind = check.get("kind") if isinstance(check, dict) else check
            failures.append(f"check[{i}] (kind={kind!r}) failed: {msg}")

    if failures:
        reason = "; ".join(failures)
        return False, f"clock check failed: {reason}"

    return True, (
        "ok: the entity constructed with the injected clock, every timeline step's expectation "
        "held at its injected 'at' value, and every expect_final reader matched"
    )


def grade_clock(root: Any, *, module: Any, entity: Any, spec: Any, python_exe: "str | None" = None,
                 timeout: float = DEFAULT_TIMEOUT_S, mem_mb: int = 512) -> "tuple[bool, str]":
    """The load-bearing oracle: validate ``spec``, render its timeline into a clock-driver
    payload, and drive a built ``entity`` class (importable from ``module`` under ``root``)
    through ``spec['timeline']`` in a fresh sandboxed subprocess, with an injected clock callable
    the driver advances EXPLICITLY before every call -- never a real wall-clock sleep.

    Returns ``(accepted, note)``. ``accepted`` is True only when the entity constructed
    successfully with the injected clock, EVERY timeline step's expectation held (a `'returns'`
    step returned exactly that value, a `'raises'` step raised exactly that exception) at the
    injected `at` value active for that call, and every `expect_final` reader (if declared)
    matched after the whole script. A build that derives its time decisions from the REAL wall
    clock instead of the injected one fails naturally: two calls declared seconds or hours apart
    in `at` execute within real milliseconds of each other, so an entity not actually consulting
    the injected clock cannot produce two different (correctly time-relative) answers -- this is
    the honesty core the class exists for.

    NEVER RAISES: a malformed ``spec`` (including a timeline that silently goes backward, or an
    `expect` that is neither `returns` nor `raises`), a missing or uncallable ``module``/
    ``entity``, or a crashing/garbage fixture is always an honest ``(False, <diagnostic note>)`` --
    never coerced to a pass, never an uncaught exception.
    """
    try:
        if not isinstance(module, str) or not module.strip():
            return False, f"module must be a non-empty string, got {module!r}"
        if not isinstance(entity, str) or not _IDENT_RE.match(entity):
            return False, f"entity must be a valid identifier, got {entity!r}"

        ok, note = validate_spec(spec)
        if not ok:
            return False, f"malformed clock spec: {note}"

        payload, checks = _build_payload_and_checks(module, entity, spec)

        return _drive_clock(root, payload, checks, timeout=timeout, python_exe=python_exe, mem_mb=mem_mb)
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"grade_clock failed unexpectedly: {exc}"
# #EXT-059-REQ-10 End
