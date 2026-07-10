# #EXT-059-REQ-8 Start
"""EXT-059 REQ-8: the CONSERVATION / NO-OVERSELL INVARIANT ORACLE -- a deterministic, model-free
verifier that grades whether a built system preserves a CONSERVED quantity under a driven
operation sequence.

**The gap this closes (Tenet 3):** conservation-shaped systems (inventory stock reservation, WMS
bin transfers, returns/refund balances, loyalty points, escrow, wallet balances -- roughly 17 real-
world classes) all share one honesty core that no existing oracle in this substrate checks: an
operation that would VIOLATE conservation (oversell more units than are available, overdraw a
balance, double-spend a point/credit) must be REJECTED, not silently allowed. A build that only
ever exercises the *legal* path (reserve within stock, spend within balance) can look correct while
quietly accepting nonsense (negative inventory, manufactured balance) the moment it is pushed past
its limit -- this module closes that gap by driving BOTH the legal path (must succeed and leave the
conserved quantities exactly where the spec's declared deltas say they land) and the illegal path
(must be refused, with every conserved quantity left UNCHANGED) through the same script, and
asserting each independently.

**The pinned contract (mirrors `harness/state_machine_oracle.py`'s first rung exactly: class-based,
driven via `harness.import_driver.drive_import`):** the built module exposes an entity CLASS with

  - one method per action (e.g. `reserve()`, `release()`, `withdraw()`, `deposit()`) that mutates
    the entity's internal conserved quantities,
  - one ZERO-ARGUMENT method per named quantity in `spec['quantities']` (e.g. `available()`,
    `reserved()`) that returns the quantity's CURRENT value.

Unlike `state_machine_oracle`'s single `@property` read (a single symbolic state), conservation
needs to read back SEVERAL independently-tracked numeric quantities (e.g. `available` AND
`reserved`) whose SUM is what must never drift. Rather than trust the built entity to compute that
sum itself (which would let a broken entity grade itself), each quantity is read back as a PLAIN
method call -- `import_driver`'s existing "resolve a dotted target, then call it" convention applies
completely unmodified, with no `@property`/`.fget` trick needed at all.

**How the conservation LAW is encoded (the structural trick, mirroring `state_machine_oracle`'s
`transitions` table):** every `expect:"accept"` op in the driven script declares a `deltas` dict --
the expected per-quantity change that op causes (e.g. `reserve(30)` declares
`{"available": -30, "reserved": +30}`). `validate_spec` REQUIRES every op's `deltas` to sum to zero
across `spec['quantities']` -- this is the conservation law itself, encoded structurally in the spec
so an inconsistent spec (one that would create or destroy units by its own arithmetic) is rejected
before anything is ever driven. The oracle then walks the script maintaining a Python-side "shadow"
quantities dict (starting from `spec['initial']`, updated by each accept op's `deltas`) and asserts,
after EVERY op, that the driven entity's own readers agree with the shadow -- so a build that applies
the wrong delta (decrements `available` without incrementing `reserved`, i.e. silently loses units;
or the reverse, silently creates them) is caught exactly where it diverges, not just at the end.

On a `expect:"reject"` op (one that WOULD violate conservation -- e.g. reserving more than is
available), the action method must raise (`spec.get('reject_exception', 'ValueError')` by default,
override per-spec), and EVERY quantity reader must read back the shadow value from BEFORE the op
(unchanged -- no partial/silent mutation before the raise). A build that lets an oversell/overdraw/
double-spend op succeed (no raise) FAILS this check even if every legal op also works -- this is the
honesty core the class exists for.

**How this reuses `import_driver` (no reimplementation):** this module renders exactly one
`api_calls` plan -- construct the entity once, then for every op call its action and read every
quantity back, then one final independent read of every quantity -- and one `checks` list
(`returns_equals` per quantity per step, `raises` for a rejected op's action call), then hands both
to `harness.import_driver.drive_import` UNMODIFIED. `drive_import` already does everything this
oracle needs: the fresh sandboxed subprocess, the sentinel protocol (never trusts the built module's
own printing), and the conjunctive checks gate (`ok=True` only when every check held).

**NEVER RAISES**, mirroring `harness/state_machine_oracle.py`/`harness/import_driver.py` exactly: a
malformed spec (including one whose declared deltas do not sum to zero), a missing/uncallable
entity, or a crashing/garbage fixture is always an honest `accepted=False` with a diagnostic note --
never coerced to a pass, never an uncaught exception.

**FOLLOW-UP (not built here):** a concurrent/interleaved-ops variant (conservation under racing
operations) and a service-based variant that drives ops over HTTP via `harness/server_oracle.py`'s
launch/request lifecycle instead of `import_driver`, for conservation systems exposed as a web API
rather than an importable class.
"""

from __future__ import annotations

import re
from typing import Any

from harness.import_driver import DEFAULT_TIMEOUT_S, drive_import

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMERIC_TYPES = (int, float)


def _is_numeric(value: Any) -> bool:
    """``bool`` is a subclass of ``int`` in Python -- exclude it so a spec accidentally writing
    ``True``/``False`` for a quantity is caught as malformed rather than silently treated as 1/0."""
    return isinstance(value, _NUMERIC_TYPES) and not isinstance(value, bool)


_ENTITY_CALL_ID = "entity"


def validate_spec(spec: Any) -> "tuple[bool, str]":
    """Validate the declarative conservation spec shape BEFORE anything is driven. Returns
    ``(True, "ok")`` when the spec is well-formed, else ``(False, <diagnostic reason>)``. Never
    raises -- any malformed input (wrong type, missing key, non-conserving deltas) is reported
    honestly rather than surfacing as an exception later during driving."""
    try:
        if not isinstance(spec, dict):
            return False, f"spec must be a dict, got {type(spec)!r}"

        quantities = spec.get("quantities")
        if not isinstance(quantities, (list, tuple)) or not quantities or not all(
            isinstance(q, str) and _IDENT_RE.match(q) for q in quantities
        ):
            return False, "spec['quantities'] must be a non-empty list of valid identifier strings"
        if len(set(quantities)) != len(quantities):
            return False, "spec['quantities'] must not contain duplicate names"
        quantities_set = set(quantities)

        initial = spec.get("initial")
        if not isinstance(initial, dict) or set(initial.keys()) != quantities_set:
            return False, (
                "spec['initial'] must be a dict with exactly the keys in spec['quantities'], "
                f"got {initial!r}"
            )
        if not all(_is_numeric(v) for v in initial.values()):
            return False, f"spec['initial'] values must all be numeric, got {initial!r}"

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

            if op["expect"] == "accept":
                deltas = op.get("deltas")
                if not isinstance(deltas, dict) or not deltas:
                    return False, (
                        f"drive[{i}] has expect='accept' but no non-empty 'deltas' dict -- every "
                        f"accepted op must declare the per-quantity change it causes"
                    )
                for key, val in deltas.items():
                    if key not in quantities_set:
                        return False, (
                            f"drive[{i}]['deltas'] references unknown quantity {key!r} -- must be "
                            f"one of {sorted(quantities_set)!r}"
                        )
                    if not _is_numeric(val):
                        return False, f"drive[{i}]['deltas'][{key!r}] must be numeric, got {val!r}"
                total = sum(deltas.get(q, 0) for q in quantities)
                if total != 0:
                    return False, (
                        f"drive[{i}]['deltas'] does not conserve the total (sums to {total!r}, "
                        f"must sum to 0 across spec['quantities']) -- the spec itself would "
                        f"create or destroy units"
                    )
            else:  # "reject", already validated by the expect check above
                if "deltas" in op:
                    return False, (
                        f"drive[{i}] has expect='reject' but declares 'deltas' -- a rejected op "
                        f"must leave every quantity unchanged, so it must not declare a delta"
                    )

        expect_final = spec.get("expect_final")
        if not isinstance(expect_final, dict) or set(expect_final.keys()) != quantities_set:
            return False, (
                "spec['expect_final'] must be a dict with exactly the keys in spec['quantities'], "
                f"got {expect_final!r}"
            )
        if not all(_is_numeric(v) for v in expect_final.values()):
            return False, f"spec['expect_final'] values must all be numeric, got {expect_final!r}"

        reject_exception = spec.get("reject_exception", "ValueError")
        if not isinstance(reject_exception, str) or not _IDENT_RE.match(reject_exception):
            return False, f"spec['reject_exception'] must be a valid identifier, got {reject_exception!r}"

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"validate_spec failed unexpectedly: {exc}"


def _build_drive_plan(entity: str, spec: dict) -> "tuple[list | None, list | None, str | None]":
    """Render the ONE `api_calls`/`checks` plan `drive_import` needs to walk the whole `drive`
    script: construct the entity once, then for every op call the action and read every quantity
    back, threading a Python-side "shadow" quantities dict forward from `spec['initial']` via each
    accept op's `deltas`. Returns ``(api_calls, checks, None)`` on success, or
    ``(None, None, <reason>)`` if the script and its own declared `deltas` disagree with
    `spec['expect_final']` (an inconsistent SPEC, caught before any subprocess is ever launched)."""
    quantities = list(spec["quantities"])
    reject_exception = spec.get("reject_exception", "ValueError")

    api_calls = [{
        "id": _ENTITY_CALL_ID,
        "target": entity,
        "args": list(spec.get("construct_args") or []),
        "kwargs": dict(spec.get("construct_kwargs") or {}),
    }]
    checks: "list" = []

    def _reader_target(q: str) -> str:
        return f"{_ENTITY_CALL_ID}.{q}"

    shadow = dict(spec["initial"])
    for i, op in enumerate(spec["drive"]):
        action = op["action"]
        args = list(op.get("args") or [])
        kwargs = dict(op.get("kwargs") or {})
        expect = op["expect"]
        call_id = f"op{i}"

        api_calls.append({
            "id": call_id, "target": f"{_ENTITY_CALL_ID}.{action}", "args": args, "kwargs": kwargs,
        })

        reader_ids = {}
        for q in quantities:
            rid = f"op{i}_{q}"
            reader_ids[q] = rid
            api_calls.append({"id": rid, "target": _reader_target(q), "args": [], "kwargs": {}})

        if expect == "accept":
            deltas = op.get("deltas") or {}
            new_shadow = {q: shadow[q] + deltas.get(q, 0) for q in quantities}
            for q in quantities:
                checks.append({
                    "kind": "returns_equals", "call_id": reader_ids[q], "expected": new_shadow[q],
                })
            shadow = new_shadow
        else:  # "reject", already validated by validate_spec
            checks.append({"kind": "raises", "call_id": call_id, "exception": reject_exception})
            for q in quantities:
                checks.append({
                    "kind": "returns_equals", "call_id": reader_ids[q], "expected": shadow[q],
                })

    expect_final = spec["expect_final"]
    for q in quantities:
        if shadow[q] != expect_final[q]:
            return None, None, (
                f"spec inconsistency: walking spec['drive'] through each op's declared 'deltas' "
                f"lands quantity {q!r} on {shadow[q]!r}, but spec['expect_final'][{q!r}] is "
                f"{expect_final[q]!r}"
            )

    # One more explicit, independent read of every quantity after the whole script -- redundant
    # with the last op's own post-state checks but keeps "the final quantities match expect_final"
    # its own visible assertion rather than an implicit side effect of however the script ends.
    for q in quantities:
        rid = f"final_{q}"
        api_calls.append({"id": rid, "target": _reader_target(q), "args": [], "kwargs": {}})
        checks.append({"kind": "returns_equals", "call_id": rid, "expected": expect_final[q]})

    return api_calls, checks, None


def grade_conservation(root: Any, *, module: Any, entity: Any, spec: Any,
                        python_exe: "str | None" = None, timeout: float = DEFAULT_TIMEOUT_S,
                        mem_mb: int = 512) -> "tuple[bool, str]":
    """The load-bearing oracle: validate ``spec``, render its drive plan, and hand it to
    ``harness.import_driver.drive_import`` UNMODIFIED to actually drive a built ``entity`` class
    (importable from ``module`` under ``root``) through ``spec['drive']`` in a fresh sandboxed
    subprocess.

    Returns ``(accepted, note)``. ``accepted`` is True only when EVERY legal (`'accept'`) op
    completed without raising and left EVERY quantity in ``spec['quantities']`` at the value the
    op's declared ``deltas`` predict, EVERY illegal (`'reject'`) op (one that would oversell/
    overdraw/double-spend) raised ``spec.get('reject_exception', 'ValueError')`` and left EVERY
    quantity unchanged, and the final quantities after the whole script match
    ``spec['expect_final']``. A build that allows even one conservation-violating op, or that
    silently loses/creates units on a legal op, FAILS -- this is the honesty core the class exists
    for.

    NEVER RAISES: a malformed ``spec`` (including one whose declared deltas do not sum to zero), an
    inconsistent script/deltas/`expect_final` pairing, a missing or uncallable ``module``/``entity``,
    or a crashing/garbage fixture is always an honest ``(False, <diagnostic note>)`` -- never
    coerced to a pass, never an uncaught exception.
    """
    try:
        if not isinstance(module, str) or not module.strip():
            return False, f"module must be a non-empty string, got {module!r}"
        if not isinstance(entity, str) or not _IDENT_RE.match(entity):
            return False, f"entity must be a valid identifier, got {entity!r}"

        ok, note = validate_spec(spec)
        if not ok:
            return False, f"malformed conservation spec: {note}"

        api_calls, checks, err = _build_drive_plan(entity, spec)
        if err is not None:
            return False, err

        result = drive_import(
            root, module, api_calls, checks,
            timeout=timeout, python_exe=python_exe, mem_mb=mem_mb,
        )
        if not result.ok:
            reason = "; ".join(result.failures) if result.failures else result.note
            return False, f"conservation check failed: {reason}"

        return True, (
            "ok: every legal op succeeded and left every quantity at its declared delta value, "
            "every illegal (conservation-violating) op was rejected with every quantity "
            "unchanged, and the final quantities matched expect_final"
        )
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"grade_conservation failed unexpectedly: {exc}"
# #EXT-059-REQ-8 End
