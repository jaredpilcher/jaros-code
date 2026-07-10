# #EXT-059-REQ-9 Start
"""EXT-059 REQ-9: the DOUBLE-ENTRY-BALANCE INVARIANT ORACLE -- a deterministic, model-free verifier
that grades whether a built accounting system preserves the double-entry invariant under a driven
sequence of journal-entry postings.

**The gap this closes (Tenet 3), and why it is the #4 (last) of the atlas's top-four highest-leverage
oracles:** ledgers, journals, general-ledger accounts, wallets, escrow accounts, and statements
(roughly 16 real-world fintech/accounting classes) all share one honesty core that no existing oracle
in this substrate checks: an accounting entry whose debit legs and credit legs do not sum to the same
total (an UNBALANCED entry) must be REJECTED, not silently posted -- and every account's running
balance must always equal exactly the sum of the postings actually applied to it (`balance ==
Sigma(postings)`). A build that only ever exercises the *legal* path (always-balanced entries) can
look correct while quietly accepting nonsense (an unbalanced entry that creates or destroys money out
of nowhere) the moment it is pushed past that path -- this module closes that gap by driving BOTH the
legal path (a balanced entry must be accepted and every touched account's balance must land exactly
where the entry's own legs predict) and the illegal path (an unbalanced entry must be refused, with
every account balance left UNCHANGED) through the same script, and asserting each independently.

**The pinned contract (mirrors `harness/conservation_oracle.py` exactly -- class-based, driven via
`harness.import_driver.drive_import`):** the built module exposes a ledger/account entity CLASS with

  - one POSTING method (named by `spec['post_method']`, e.g. `post()`) that takes a single
    positional argument -- a list of "legs", each a plain dict `{"account": <name>, "debit": <cents>}`
    or `{"account": <name>, "credit": <cents>}` -- and applies (or refuses) the entry,
  - one ZERO-ARGUMENT method per account name in `spec['accounts']` (e.g. `cash()`, `revenue()`) that
    returns that account's CURRENT signed balance, in exact integer CENTS.

**Why integer cents, never float (Tenet 3 -- money must be exact):** every numeric value this module
puts INTO a spec (`initial`, leg `debit`/`credit` amounts, `expect_final`) must be a plain Python
`int` (`validate_spec` rejects `float`/`bool` outright) -- so every expected value the oracle compares
against the driven entity's own reported balance is an EXACT integer. If the built entity's own
internals use `float` cents/dollars internally, floating-point drift (e.g. repeated `0.1 + 0.2`-style
addition landing on `9999.999999999998` instead of `10000`) fails the resulting exact-equality
`returns_equals` check the same way a genuinely wrong balance would -- no float-tolerant "close
enough" comparison is ever used, so a build silently going through `float` is caught exactly where its
sum first diverges from the integer-cents shadow, not just eventually.

**How the double-entry LAW is encoded (the structural trick, mirroring `conservation_oracle`'s
`deltas`-sum-to-zero law exactly, restated in accounting vocabulary):** every posting op declares
`legs` -- the debit/credit lines that make up that journal entry. Each leg is translated to a SIGNED
per-account delta: a debit leg on account A contributes `+amount` to A, a credit leg contributes
`-amount` (a uniform debit-positive/credit-negative sign convention applied to every account, exactly
as `conservation_oracle` applies its `deltas`). Because `Sigma(debit legs) == Sigma(credit legs)` for a
balanced entry is ALGEBRAICALLY IDENTICAL to "that entry's signed per-account deltas sum to zero",
`validate_spec` REQUIRES every `expect:"accept"` op's legs to sum to zero once translated to signed
deltas (an unbalanced entry, by construction, does NOT sum to zero) -- so a spec that would itself
create or destroy money is rejected before anything is ever driven, exactly mirroring
`conservation_oracle`'s own structural law. Because this holds for every accepted entry, it holds
CUMULATIVELY across the whole driven script: `Sigma` over every account's final balance always equals
`Sigma` over every account's initial balance -- i.e. `Sigma(all debit legs across every accepted
entry) == Sigma(all credit legs across every accepted entry)`, the ledger-wide double-entry invariant,
holds STRUCTURALLY whenever every individual entry balances. The oracle then walks the script
maintaining a Python-side "shadow" per-account balance dict (starting from `spec['initial']`, updated
by each accepted op's signed deltas) and asserts, after EVERY op, that the driven entity's own account
readers agree with the shadow -- so a build that applies the wrong side (credits an account a debit
leg should have credited), drops a leg, or double-posts a leg is caught exactly where it diverges from
that structural law, not just at the end. (Follow-up, not built here: an explicit running
`total_debits()`/`total_credits()` reader pair on the entity itself, for entities that track raw
lifetime totals independently of derived account balances.)

On an `expect:"reject"` op (one that is DELIBERATELY UNBALANCED -- `Sigma(debit legs) !=
Sigma(credit legs)`, the flagship honesty case this oracle exists for), the posting method must raise
(`spec.get('reject_exception', 'ValueError')` by default, override per-spec), and EVERY account reader
must read back the shadow value from BEFORE the op (unchanged -- no partial/silent posting of some legs
before the raise). A build that lets an unbalanced entry post (no raise, or a partial post of only some
of its legs) FAILS this check even if every balanced entry also works correctly -- this is the honesty
core the class exists for.

**How this reuses `import_driver` (no reimplementation):** this module renders exactly one
`api_calls` plan -- construct the entity once, then for every op call the posting method with its
`legs` and read every account back, then one final independent read of every account -- and one
`checks` list (`returns_equals` per account per step, `raises` for a rejected op's posting call), then
hands both to `harness.import_driver.drive_import` UNMODIFIED. `drive_import` already does everything
this oracle needs: the fresh sandboxed subprocess, the sentinel protocol (never trusts the built
module's own printing), and the conjunctive checks gate (`ok=True` only when every check held).

**NEVER RAISES**, mirroring `harness/conservation_oracle.py` exactly: a malformed spec (including one
whose declared legs do not balance for an `accept` op, or DO balance for a `reject` op -- a
`reject` op must be genuinely unbalanced, the only rejection reason this oracle models), a missing/
uncallable entity, or a crashing/garbage fixture is always an honest `accepted=False` with a
diagnostic note -- never coerced to a pass, never an uncaught exception.

**FOLLOW-UP (not built here):** a running `total_debits()`/`total_credits()` reader-pair variant (for
entities that track raw lifetime posting totals independently of derived account balances), a
multi-currency variant, and a service-based variant that drives postings over HTTP via
`harness/server_oracle.py`'s launch/request lifecycle instead of `import_driver`.
"""

from __future__ import annotations

import re
from typing import Any

from harness.import_driver import DEFAULT_TIMEOUT_S, drive_import

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_money_int(value: Any) -> bool:
    """Money must be exact -- an integer number of cents. ``bool`` is a subclass of ``int`` in
    Python, and ``float`` is never exact for money, so both are excluded explicitly."""
    return isinstance(value, int) and not isinstance(value, bool)


_ENTITY_CALL_ID = "entity"
_DEFAULT_POST_METHOD = "post"


def _leg_signed_delta(leg: Any) -> "tuple[str, int, str] | None":
    """Validate ONE leg dict and return ``(account, signed_delta, side)`` where ``side`` is
    ``"debit"`` or ``"credit"`` and ``signed_delta`` is ``+amount`` for a debit leg, ``-amount``
    for a credit leg. Returns ``None`` if the leg is malformed (not a dict, unknown/missing keys,
    both or neither of ``debit``/``credit`` present, or a non-positive/non-integer amount)."""
    if not isinstance(leg, dict):
        return None
    account = leg.get("account")
    if not isinstance(account, str) or not _IDENT_RE.match(account):
        return None
    has_debit = "debit" in leg
    has_credit = "credit" in leg
    if has_debit == has_credit:  # both or neither -- exactly one side is required
        return None
    if has_debit:
        amount = leg.get("debit")
        side = "debit"
        sign = 1
    else:
        amount = leg.get("credit")
        side = "credit"
        sign = -1
    if not _is_money_int(amount) or amount <= 0:
        return None
    return account, sign * amount, side


def validate_spec(spec: Any) -> "tuple[bool, str]":
    """Validate the declarative double-entry spec shape BEFORE anything is driven. Returns
    ``(True, "ok")`` when the spec is well-formed, else ``(False, <diagnostic reason>)``. Never
    raises -- any malformed input (wrong type, missing key, an `accept` entry whose legs do not
    balance, a `reject` entry whose legs actually DO balance) is reported honestly rather than
    surfacing as an exception later during driving."""
    try:
        if not isinstance(spec, dict):
            return False, f"spec must be a dict, got {type(spec)!r}"

        accounts = spec.get("accounts")
        if not isinstance(accounts, (list, tuple)) or not accounts or not all(
            isinstance(a, str) and _IDENT_RE.match(a) for a in accounts
        ):
            return False, "spec['accounts'] must be a non-empty list of valid identifier strings"
        if len(set(accounts)) != len(accounts):
            return False, "spec['accounts'] must not contain duplicate names"
        accounts_set = set(accounts)

        initial = spec.get("initial")
        if not isinstance(initial, dict) or set(initial.keys()) != accounts_set:
            return False, (
                "spec['initial'] must be a dict with exactly the keys in spec['accounts'], "
                f"got {initial!r}"
            )
        if not all(_is_money_int(v) for v in initial.values()):
            return False, (
                f"spec['initial'] values must all be exact integer cents (no float), got {initial!r}"
            )

        post_method = spec.get("post_method", _DEFAULT_POST_METHOD)
        if not isinstance(post_method, str) or not _IDENT_RE.match(post_method):
            return False, f"spec['post_method'] must be a valid identifier, got {post_method!r}"

        drive = spec.get("drive")
        if not isinstance(drive, (list, tuple)) or not drive:
            return False, "spec['drive'] must be a non-empty list of journal-entry ops"

        for i, op in enumerate(drive):
            if not isinstance(op, dict):
                return False, f"drive[{i}] must be a dict, got {type(op)!r}"
            if op.get("expect") not in ("accept", "reject"):
                return False, f"drive[{i}]['expect'] must be 'accept' or 'reject', got {op.get('expect')!r}"
            if "args" in op and not isinstance(op["args"], (list, tuple)):
                return False, f"drive[{i}]['args'] must be a list when present"
            if "kwargs" in op and not isinstance(op["kwargs"], dict):
                return False, f"drive[{i}]['kwargs'] must be a dict when present"

            legs = op.get("legs")
            if not isinstance(legs, (list, tuple)) or len(legs) < 2:
                return False, (
                    f"drive[{i}]['legs'] must be a list of at least 2 legs (a double-entry "
                    f"posting needs at least one debit and one credit leg)"
                )

            deltas: "dict[str, int]" = {}
            for j, leg in enumerate(legs):
                parsed = _leg_signed_delta(leg)
                if parsed is None:
                    return False, (
                        f"drive[{i}]['legs'][{j}] is malformed -- must be a dict with 'account' "
                        f"(one of {sorted(accounts_set)!r}) and exactly one of 'debit'/'credit' "
                        f"as a positive integer number of cents, got {leg!r}"
                    )
                account, delta, _side = parsed
                if account not in accounts_set:
                    return False, (
                        f"drive[{i}]['legs'][{j}] references unknown account {account!r} -- must "
                        f"be one of {sorted(accounts_set)!r}"
                    )
                deltas[account] = deltas.get(account, 0) + delta

            total = sum(deltas.values())
            if op["expect"] == "accept":
                if total != 0:
                    return False, (
                        f"drive[{i}] has expect='accept' but its legs do not balance (signed "
                        f"total {total!r} cents, must be 0 -- Sigma(debits) must equal "
                        f"Sigma(credits)) -- the spec itself would create or destroy money"
                    )
            else:  # "reject", already validated by the expect check above
                if total == 0:
                    return False, (
                        f"drive[{i}] has expect='reject' but its legs actually DO balance "
                        f"(signed total 0) -- this oracle only models rejection of a genuinely "
                        f"UNBALANCED entry, so a 'reject' op's legs must NOT balance"
                    )

        expect_final = spec.get("expect_final")
        if not isinstance(expect_final, dict) or set(expect_final.keys()) != accounts_set:
            return False, (
                "spec['expect_final'] must be a dict with exactly the keys in spec['accounts'], "
                f"got {expect_final!r}"
            )
        if not all(_is_money_int(v) for v in expect_final.values()):
            return False, (
                f"spec['expect_final'] values must all be exact integer cents (no float), "
                f"got {expect_final!r}"
            )

        reject_exception = spec.get("reject_exception", "ValueError")
        if not isinstance(reject_exception, str) or not _IDENT_RE.match(reject_exception):
            return False, f"spec['reject_exception'] must be a valid identifier, got {reject_exception!r}"

        return True, "ok"
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"validate_spec failed unexpectedly: {exc}"


def _build_drive_plan(entity: str, spec: dict) -> "tuple[list | None, list | None, str | None]":
    """Render the ONE `api_calls`/`checks` plan `drive_import` needs to walk the whole `drive`
    script: construct the entity once, then for every op post its `legs` (as one plain JSON-list
    argument) and read every account back, threading a Python-side "shadow" per-account balance
    dict forward from `spec['initial']` via each accepted op's signed leg deltas. Returns
    ``(api_calls, checks, None)`` on success, or ``(None, None, <reason>)`` if the script and its
    own declared legs disagree with `spec['expect_final']` (an inconsistent SPEC, caught before
    any subprocess is ever launched)."""
    accounts = list(spec["accounts"])
    post_method = spec.get("post_method", _DEFAULT_POST_METHOD)
    reject_exception = spec.get("reject_exception", "ValueError")

    api_calls = [{
        "id": _ENTITY_CALL_ID,
        "target": entity,
        "args": list(spec.get("construct_args") or []),
        "kwargs": dict(spec.get("construct_kwargs") or {}),
    }]
    checks: "list" = []

    def _reader_target(account: str) -> str:
        return f"{_ENTITY_CALL_ID}.{account}"

    shadow = dict(spec["initial"])
    for i, op in enumerate(spec["drive"]):
        legs = list(op["legs"])
        args = [legs] + list(op.get("args") or [])
        kwargs = dict(op.get("kwargs") or {})
        expect = op["expect"]
        call_id = f"op{i}"

        api_calls.append({
            "id": call_id, "target": f"{_ENTITY_CALL_ID}.{post_method}", "args": args, "kwargs": kwargs,
        })

        reader_ids = {}
        for a in accounts:
            rid = f"op{i}_{a}"
            reader_ids[a] = rid
            api_calls.append({"id": rid, "target": _reader_target(a), "args": [], "kwargs": {}})

        deltas: "dict[str, int]" = {}
        for leg in legs:
            account, delta, _side = _leg_signed_delta(leg)
            deltas[account] = deltas.get(account, 0) + delta

        if expect == "accept":
            new_shadow = {a: shadow[a] + deltas.get(a, 0) for a in accounts}
            for a in accounts:
                checks.append({
                    "kind": "returns_equals", "call_id": reader_ids[a], "expected": new_shadow[a],
                })
            shadow = new_shadow
        else:  # "reject", already validated by validate_spec
            checks.append({"kind": "raises", "call_id": call_id, "exception": reject_exception})
            for a in accounts:
                checks.append({
                    "kind": "returns_equals", "call_id": reader_ids[a], "expected": shadow[a],
                })

    expect_final = spec["expect_final"]
    for a in accounts:
        if shadow[a] != expect_final[a]:
            return None, None, (
                f"spec inconsistency: walking spec['drive'] through each op's legs lands "
                f"account {a!r} on {shadow[a]!r} cents, but spec['expect_final'][{a!r}] is "
                f"{expect_final[a]!r} cents"
            )

    # One more explicit, independent read of every account after the whole script -- redundant
    # with the last op's own post-state checks but keeps "the final balances match expect_final"
    # its own visible assertion rather than an implicit side effect of however the script ends.
    for a in accounts:
        rid = f"final_{a}"
        api_calls.append({"id": rid, "target": _reader_target(a), "args": [], "kwargs": {}})
        checks.append({"kind": "returns_equals", "call_id": rid, "expected": expect_final[a]})

    return api_calls, checks, None


def grade_double_entry(root: Any, *, module: Any, entity: Any, spec: Any,
                        python_exe: "str | None" = None, timeout: float = DEFAULT_TIMEOUT_S,
                        mem_mb: int = 512) -> "tuple[bool, str]":
    """The load-bearing oracle: validate ``spec``, render its drive plan, and hand it to
    ``harness.import_driver.drive_import`` UNMODIFIED to actually drive a built ledger/account
    ``entity`` class (importable from ``module`` under ``root``) through ``spec['drive']`` in a
    fresh sandboxed subprocess.

    Returns ``(accepted, note)``. ``accepted`` is True only when EVERY balanced (`'accept'`)
    journal entry posted without raising and left EVERY account in ``spec['accounts']`` at the
    exact integer-cents balance its legs predict, EVERY unbalanced (`'reject'`) entry (Sigma(debit
    legs) != Sigma(credit legs) -- the honesty core this oracle exists for) raised
    ``spec.get('reject_exception', 'ValueError')`` and left EVERY account balance unchanged, and
    the final balances after the whole script match ``spec['expect_final']``. Because every
    accepted entry's legs are required to balance, the ledger-wide double-entry invariant
    (Sigma of all debit legs across the whole script equals Sigma of all credit legs) holds
    structurally and is verified dynamically the same way -- via each account's own balance
    reader, never a value the built module merely claims. A build that allows even one unbalanced
    entry to post, or that posts a balanced entry to the wrong side of an account, FAILS -- this is
    the honesty core the class exists for.

    NEVER RAISES: a malformed ``spec`` (including one whose declared legs do not balance for an
    `'accept'` op, or DO balance for a `'reject'` op), an inconsistent script/legs/`expect_final`
    pairing, a missing or uncallable ``module``/``entity``, or a crashing/garbage fixture is
    always an honest ``(False, <diagnostic note>)`` -- never coerced to a pass, never an
    uncaught exception.
    """
    try:
        if not isinstance(module, str) or not module.strip():
            return False, f"module must be a non-empty string, got {module!r}"
        if not isinstance(entity, str) or not _IDENT_RE.match(entity):
            return False, f"entity must be a valid identifier, got {entity!r}"

        ok, note = validate_spec(spec)
        if not ok:
            return False, f"malformed double-entry spec: {note}"

        api_calls, checks, err = _build_drive_plan(entity, spec)
        if err is not None:
            return False, err

        result = drive_import(
            root, module, api_calls, checks,
            timeout=timeout, python_exe=python_exe, mem_mb=mem_mb,
        )
        if not result.ok:
            reason = "; ".join(result.failures) if result.failures else result.note
            return False, f"double-entry check failed: {reason}"

        return True, (
            "ok: every balanced entry posted and left every account at its declared exact-cents "
            "balance, every unbalanced entry was rejected with every account balance unchanged, "
            "and the final balances matched expect_final"
        )
    except Exception as exc:  # never raise -- an honest diagnostic result instead
        return False, f"grade_double_entry failed unexpectedly: {exc}"
# #EXT-059-REQ-9 End
