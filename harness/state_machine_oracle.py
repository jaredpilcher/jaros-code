# #EXT-059-REQ-7 Start
"""EXT-059 REQ-7: the STATE-MACHINE / LIFECYCLE ORACLE -- a deterministic, model-free verifier
that grades whether a built system enforces a legal state machine.

**The gap this closes (Tenet 3):** lifecycle-shaped systems (order/shipment/fulfillment/RMA/
prescription/claim/dispute/moderation/appointment/subscription -- roughly 18-20 real-world
classes) all share one honesty core that no existing oracle in this substrate checks: an ILLEGAL
transition must be REJECTED, not silently allowed (you can't ship an unpaid order, can't cancel a
delivered one). A build that only ever exercises the *legal* path can look correct while quietly
accepting nonsense -- this module closes that gap by driving BOTH the legal path (must succeed,
must land on the modeled next state) and the illegal path (must be refused) through the same
script, and asserting each independently.

**The pinned contract (first rung: class-based, driven via `harness.import_driver.drive_import`):**
the built module exposes an entity CLASS with

  - one method per action (e.g. `pay()`, `ship()`, `deliver()`, `cancel()`) that mutates the
    entity's internal state,
  - a real Python `@property` named `state` that reads the current state.

On a LEGAL transition the action method must complete without raising, and the `state` property
must read back the spec's modeled next state. On an ILLEGAL transition the action method must
raise (by default `ValueError` -- override per-spec via `reject_exception` -- a standard, widely
used Python idiom for "invalid transition/invalid state"), and the `state` property must read back
UNCHANGED (no partial/silent mutation before the raise).

**How this reuses `import_driver` (no reimplementation):** this module renders exactly one
`api_calls` plan -- construct the entity once, call every action in the driven script's order,
and read the `state` property after every op -- and one `checks` list (`returns_equals` for a
legal op's post-state, `raises` for an illegal op's action call, `returns_equals` again for an
illegal op's UNCHANGED post-state), then hands both to `harness.import_driver.drive_import`
UNMODIFIED. `drive_import` already does everything this oracle needs: the fresh sandboxed
subprocess, the sentinel protocol (never trusts the built module's own printing), and the
conjunctive checks gate (`ok=True` only when every check held). The property is read via
`f"{entity}.__class__.state.fget"` bound to `{"__jaros_ref__": entity_call_id}` -- accessing a
`property` object through the CLASS (not the instance) returns the descriptor itself rather than
invoking it, so its `.fget` (the underlying getter function) is directly callable by
`import_driver`'s existing "resolve a dotted target, then call it" convention, with the instance
threaded in as the getter's `self` argument via `import_driver`'s own injected-reference marker --
no change to `import_driver.py` itself.

**NEVER RAISES**, mirroring `harness/import_driver.py`/`harness/fs_oracle.py` exactly: a malformed
spec, a missing/uncallable entity, or a crashing/garbage fixture is always an honest
`accepted=False` with a diagnostic note -- never coerced to a pass, never an uncaught exception.

**FOLLOW-UP (not built here):** a service-based variant that drives transitions over HTTP via
`harness/server_oracle.py`'s launch/request lifecycle instead of `import_driver`, for lifecycle
systems exposed as a web API rather than an importable class.
"""

from __future__ import annotations

import re
from typing import Any

from harness.import_driver import DEFAULT_TIMEOUT_S, drive_import

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The generic "read the state property back" call/target convention every op reuses -- see the
# module docstring for why `.fget` bound to the instance via an injected reference is the correct,
# `import_driver`-native way to invoke a real Python `@property`'s getter without modifying
# `import_driver.py`'s "resolve a dotted target, then call it" convention.
_ENTITY_CALL_ID = "entity"
_STATE_PROPERTY_TARGET = f"{_ENTITY_CALL_ID}.__class__.state.fget"


def validate_spec(spec: Any) -> "tuple[bool, str]":
    """Validate the declarative state-machine spec shape BEFORE anything is driven. Returns
    ``(True, "ok")`` when the spec is well-formed, else ``(False, <diagnostic reason>)``. Never
    raises -- any malformed input (wrong type, missing key, dangling reference) is reported
    honestly rather than surfacing as an exception later during driving."""
    try:
        if not isinstance(spec, dict):
            return False, f"spec must be a dict, got {type(spec)!r}"

        states = spec.get("states")
        if not isinstance(states, (list, tuple)) or not states or not all(
            isinstance(s, str) and s for s in states
        ):
            return False, "spec['states'] must be a non-empty list of non-empty strings"
        states_set = set(states)

        initial = spec.get("initial")
        if initial not in states_set:
            return False, f"spec['initial'] {initial!r} is not one of spec['states']"

        transitions = spec.get("transitions")
        if not isinstance(transitions, dict) or not transitions:
            return False, "spec['transitions'] must be a non-empty dict"
        for key, to_state in transitions.items():
            if not isinstance(key, str) or ":" not in key:
                return False, f"transitions key {key!r} must be formatted 'from_state:action'"
            from_state = key.split(":", 1)[0]
            if from_state not in states_set:
                return False, f"transitions key {key!r} references unknown from_state {from_state!r}"
            if to_state not in states_set:
                return False, f"transitions[{key!r}] targets unknown state {to_state!r}"

        drive = spec.get("drive")
        if not isinstance(drive, (list, tuple)) or not drive:
            return False, "spec['drive'] must be a non-empty list of ops"
        for i, op in enumerate(drive):
            if not isinstance(op, dict):
                return False, f"drive[{i}] must be a dict, got {type(op)!r}"
            action = op.get("action")
            if not isinstance(action, str) or not _IDENT_RE.match(action):
                return False, f"drive[{i}]['action'] must be a valid identifier, got {action!r}"
            if op.get("expect") not in ("accept", "reject"):
                return False, f"drive[{i}]['expect'] must be 'accept' or 'reject', got {op.get('expect')!r}"
            if "args" in op and not isinstance(op["args"], (list, tuple)):
                return False, f"drive[{i}]['args'] must be a list when present"
            if "kwargs" in op and not isinstance(op["kwargs"], dict):
                return False, f"drive[{i}]['kwargs'] must be a dict when present"

        expect_final = spec.get("expect_final")
        if expect_final not in states_set:
            return False, f"spec['expect_final'] {expect_final!r} is not one of spec['states']"

        reject_exception = spec.get("reject_exception", "ValueError")
        if not isinstance(reject_exception, str) or not _IDENT_RE.match(reject_exception):
            return False, f"spec['reject_exception'] must be a valid identifier, got {reject_exception!r}"

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"validate_spec failed unexpectedly: {exc}"


def _build_drive_plan(entity: str, spec: dict) -> "tuple[list | None, list | None, str | None]":
    """Render the ONE `api_calls`/`checks` plan `drive_import` needs to walk the whole `drive`
    script: construct the entity once, then for every op call the action and read the `state`
    property back, threading a Python-side "shadow" expected state forward from `spec['initial']`
    via `spec['transitions']`. Returns ``(api_calls, checks, None)`` on success, or
    ``(None, None, <reason>)`` if the script and `transitions` table disagree with each other
    (an inconsistent SPEC, caught before any subprocess is ever launched)."""
    transitions = spec["transitions"]
    reject_exception = spec.get("reject_exception", "ValueError")

    api_calls = [{
        "id": _ENTITY_CALL_ID,
        "target": entity,
        "args": list(spec.get("construct_args") or []),
        "kwargs": dict(spec.get("construct_kwargs") or {}),
    }]
    checks: "list" = []

    shadow = spec["initial"]
    for i, op in enumerate(spec["drive"]):
        action = op["action"]
        args = list(op.get("args") or [])
        kwargs = dict(op.get("kwargs") or {})
        expect = op["expect"]
        call_id = f"op{i}"
        state_call_id = f"op{i}_state"
        key = f"{shadow}:{action}"

        api_calls.append({
            "id": call_id, "target": f"{_ENTITY_CALL_ID}.{action}", "args": args, "kwargs": kwargs,
        })
        api_calls.append({
            "id": state_call_id, "target": _STATE_PROPERTY_TARGET,
            "args": [{"__jaros_ref__": _ENTITY_CALL_ID}], "kwargs": {},
        })

        if expect == "accept":
            if key not in transitions:
                return None, None, (
                    f"drive[{i}] expects 'accept' for {key!r} but spec['transitions'] declares no "
                    f"such transition -- the spec itself is inconsistent"
                )
            next_state = transitions[key]
            checks.append({"kind": "returns_equals", "call_id": state_call_id, "expected": next_state})
            shadow = next_state
        else:  # "reject", already validated by validate_spec
            if key in transitions:
                return None, None, (
                    f"drive[{i}] expects 'reject' for {key!r} but spec['transitions'] declares it "
                    f"legal -- the spec itself is inconsistent"
                )
            checks.append({"kind": "raises", "call_id": call_id, "exception": reject_exception})
            checks.append({"kind": "returns_equals", "call_id": state_call_id, "expected": shadow})

    expect_final = spec["expect_final"]
    if shadow != expect_final:
        return None, None, (
            f"spec inconsistency: walking spec['drive'] through spec['transitions'] lands on "
            f"{shadow!r}, but spec['expect_final'] is {expect_final!r}"
        )

    # One more explicit, independent read after the whole script -- redundant with the last op's
    # own post-state check but keeps "the final state matches expect_final" its own visible
    # assertion rather than an implicit side effect of however the script happens to end.
    api_calls.append({
        "id": "final_state", "target": _STATE_PROPERTY_TARGET,
        "args": [{"__jaros_ref__": _ENTITY_CALL_ID}], "kwargs": {},
    })
    checks.append({"kind": "returns_equals", "call_id": "final_state", "expected": expect_final})

    return api_calls, checks, None


def grade_state_machine(root: Any, *, module: Any, entity: Any, spec: Any,
                         python_exe: "str | None" = None, timeout: float = DEFAULT_TIMEOUT_S,
                         mem_mb: int = 512) -> "tuple[bool, str]":
    """The load-bearing oracle: validate ``spec``, render its drive plan, and hand it to
    ``harness.import_driver.drive_import`` UNMODIFIED to actually drive a built ``entity`` class
    (importable from ``module`` under ``root``) through ``spec['drive']`` in a fresh sandboxed
    subprocess.

    Returns ``(accepted, note)``. ``accepted`` is True only when EVERY legal ('accept') op
    completed without raising and landed the ``state`` property on the spec's modeled next state,
    EVERY illegal ('reject') op raised ``spec.get('reject_exception', 'ValueError')`` and left
    ``state`` unchanged, and the final ``state`` after the whole script matches
    ``spec['expect_final']``. A build that allows even one illegal transition, or that silently
    mutates state on a rejected op, FAILS -- this is the honesty core the class exists for.

    NEVER RAISES: a malformed ``spec``, an inconsistent script/transitions pairing, a missing or
    uncallable ``module``/``entity``, or a crashing/garbage fixture is always an honest
    ``(False, <diagnostic note>)`` -- never coerced to a pass, never an uncaught exception.
    """
    try:
        if not isinstance(module, str) or not module.strip():
            return False, f"module must be a non-empty string, got {module!r}"
        if not isinstance(entity, str) or not _IDENT_RE.match(entity):
            return False, f"entity must be a valid identifier, got {entity!r}"

        ok, note = validate_spec(spec)
        if not ok:
            return False, f"malformed state-machine spec: {note}"

        api_calls, checks, err = _build_drive_plan(entity, spec)
        if err is not None:
            return False, err

        result = drive_import(
            root, module, api_calls, checks,
            timeout=timeout, python_exe=python_exe, mem_mb=mem_mb,
        )
        if not result.ok:
            reason = "; ".join(result.failures) if result.failures else result.note
            return False, f"state-machine check failed: {reason}"

        return True, (
            "ok: every legal transition succeeded and landed on the modeled next state, every "
            "illegal transition was rejected with state unchanged, and the final state matched "
            "expect_final"
        )
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"grade_state_machine failed unexpectedly: {exc}"
# #EXT-059-REQ-7 End
