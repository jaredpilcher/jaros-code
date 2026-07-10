"""EXT-059 REQ-9: offline tests for the deterministic double-entry-balance invariant oracle.

Every fixture here is a small, hand-written Python module written to a temp directory -- never a
live ``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this
pytest suite). No external service, no network, no model call anywhere: stdlib only. These tests
are pure execution-plane verification of a deterministic module and must never reach the Jetson.

Run in isolation: ``python -m pytest tests/test_ext059_double_entry_oracle.py -q``.
"""

# #EXT-059-REQ-9 Start
# TASK-7
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.double_entry_oracle import grade_double_entry, validate_spec

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# A correctly-implemented two-account ledger: `post(legs)` sums debit legs positive / credit legs
# negative, refuses (ValueError) an unbalanced entry, and otherwise applies every leg's exact
# integer-cents delta to the named account. Balances are exact int cents -- never float.
CORRECT_LEDGER = """
    class Ledger:
        def __init__(self):
            self._balances = {"cash": 0, "revenue": 0}

        def cash(self):
            return self._balances["cash"]

        def revenue(self):
            return self._balances["revenue"]

        def post(self, legs):
            total = 0
            for leg in legs:
                if "debit" in leg:
                    total += leg["debit"]
                else:
                    total -= leg["credit"]
            if total != 0:
                raise ValueError(f"unbalanced entry: signed total {total} cents")
            for leg in legs:
                account = leg["account"]
                if "debit" in leg:
                    self._balances[account] += leg["debit"]
                else:
                    self._balances[account] -= leg["credit"]
"""

# The flagship honesty bug: `post()` has NO balance guard at all -- it happily posts an
# unbalanced entry (debits != credits), creating money out of nowhere.
BROKEN_ACCEPTS_UNBALANCED_LEDGER = """
    class Ledger:
        def __init__(self):
            self._balances = {"cash": 0, "revenue": 0}

        def cash(self):
            return self._balances["cash"]

        def revenue(self):
            return self._balances["revenue"]

        def post(self, legs):
            # BUG: no balance check at all -- posts unbalanced entries too.
            for leg in legs:
                account = leg["account"]
                if "debit" in leg:
                    self._balances[account] += leg["debit"]
                else:
                    self._balances[account] -= leg["credit"]
"""

# The balance guard is correct (unbalanced entries ARE rejected), but a copy/paste mistake applies
# every leg's delta TWICE -- wrong balance math that lands on the wrong final balances even though
# every individual entry was itself balanced.
BROKEN_DOUBLE_APPLIES_LEDGER = """
    class Ledger:
        def __init__(self):
            self._balances = {"cash": 0, "revenue": 0}

        def cash(self):
            return self._balances["cash"]

        def revenue(self):
            return self._balances["revenue"]

        def post(self, legs):
            total = 0
            for leg in legs:
                if "debit" in leg:
                    total += leg["debit"]
                else:
                    total -= leg["credit"]
            if total != 0:
                raise ValueError(f"unbalanced entry: signed total {total} cents")
            # BUG: applies every leg's delta TWICE (duplicate-loop copy/paste mistake).
            for _ in range(2):
                for leg in legs:
                    account = leg["account"]
                    if "debit" in leg:
                        self._balances[account] += leg["debit"]
                    else:
                        self._balances[account] -= leg["credit"]
"""

# The balance guard is correct, but applying an accepted (balanced) entry silently DROPS every
# credit leg -- only debit legs are ever posted. Money is created out of nowhere: the ledger-wide
# debits==credits invariant is broken even though every individual entry passed the balance check.
BROKEN_DROPS_CREDIT_LEGS_LEDGER = """
    class Ledger:
        def __init__(self):
            self._balances = {"cash": 0, "revenue": 0}

        def cash(self):
            return self._balances["cash"]

        def revenue(self):
            return self._balances["revenue"]

        def post(self, legs):
            total = 0
            for leg in legs:
                if "debit" in leg:
                    total += leg["debit"]
                else:
                    total -= leg["credit"]
            if total != 0:
                raise ValueError(f"unbalanced entry: signed total {total} cents")
            for leg in legs:
                if "debit" in leg:
                    self._balances[leg["account"]] += leg["debit"]
                # BUG: credit legs are silently dropped -- money is created, not moved.
"""

# A garbage fixture: raises at IMPORT time, before any entity could ever be constructed.
CRASHING_MODULE = """
    raise RuntimeError("boom -- this module is broken at import time")
"""

# `accounts`/`initial`/`drive`/`expect_final` for a two-account ledger: post a balanced $100.00
# entry (debit cash, credit revenue), then attempt a genuinely UNBALANCED $50.00-debit/$40.00-credit
# entry (must be rejected), then post a balanced $50.00 reversal (debit revenue, credit cash) --
# landing on cash=5000 cents, revenue=-5000 cents.
LEDGER_SPEC = {
    "accounts": ["cash", "revenue"],
    "initial": {"cash": 0, "revenue": 0},
    "drive": [
        {"legs": [{"account": "cash", "debit": 10000}, {"account": "revenue", "credit": 10000}],
         "expect": "accept"},
        {"legs": [{"account": "cash", "debit": 5000}, {"account": "revenue", "credit": 4000}],
         "expect": "reject"},
        {"legs": [{"account": "revenue", "debit": 5000}, {"account": "cash", "credit": 5000}],
         "expect": "accept"},
    ],
    "expect_final": {"cash": 5000, "revenue": -5000},
}


def test_validate_spec_accepts_well_formed_ledger_spec():
    ok, note = validate_spec(LEDGER_SPEC)
    assert ok, note


def test_validate_spec_rejects_malformed_specs():
    ok, note = validate_spec({"accounts": ["cash"]})  # missing initial/drive/expect_final
    assert not ok
    assert note

    ok, note = validate_spec("not a dict")
    assert not ok

    bad = dict(LEDGER_SPEC)
    bad["initial"] = {"cash": 0}  # missing 'revenue' key
    ok, note = validate_spec(bad)
    assert not ok
    assert "initial" in note


def test_validate_spec_rejects_float_money_values():
    """Money must be exact integer cents -- a spec declaring a float anywhere in initial/legs/
    expect_final is malformed, never silently coerced."""
    bad = dict(LEDGER_SPEC)
    bad["initial"] = {"cash": 0.0, "revenue": 0}
    ok, note = validate_spec(bad)
    assert not ok
    assert "integer" in note.lower() or "float" in note.lower()


def test_validate_spec_rejects_unbalanced_accept_op():
    """The double-entry law itself is enforced structurally: an 'accept' op whose legs don't sum
    to zero (debits != credits) describes a spec that would itself create or destroy money."""
    bad = dict(LEDGER_SPEC)
    bad["drive"] = [
        {"legs": [{"account": "cash", "debit": 100}, {"account": "revenue", "credit": 90}],
         "expect": "accept"},
    ]
    bad["expect_final"] = {"cash": 100, "revenue": -90}
    ok, note = validate_spec(bad)
    assert not ok
    assert "balance" in note.lower()


def test_validate_spec_rejects_balanced_reject_op():
    """A 'reject' op must be genuinely unbalanced -- this oracle only models rejection of the
    unbalanced-entry honesty case, so a 'reject' op whose legs DO balance is a malformed spec."""
    bad = dict(LEDGER_SPEC)
    bad["drive"] = [
        {"legs": [{"account": "cash", "debit": 100}, {"account": "revenue", "credit": 100}],
         "expect": "reject"},
    ]
    ok, note = validate_spec(bad)
    assert not ok
    assert "balance" in note.lower()


def test_validate_spec_rejects_malformed_leg():
    bad = dict(LEDGER_SPEC)
    bad["drive"] = [
        {"legs": [{"account": "cash", "debit": 100, "credit": 100}, {"account": "revenue", "credit": 100}],
         "expect": "accept"},  # both debit and credit on one leg
    ]
    ok, note = validate_spec(bad)
    assert not ok
    assert note


def test_correct_ledger_passes(tmp_path):
    _write(tmp_path, "ledger.py", CORRECT_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert accepted, note
    assert "ok" in note.lower()


def test_unbalanced_entry_accepted_bug_is_caught(tmp_path):
    """The flagship honesty test: a build that ACCEPTS an unbalanced entry (debits != credits)
    must be caught, not silently passed just because the legal path also happens to work."""
    _write(tmp_path, "ledger.py", BROKEN_ACCEPTS_UNBALANCED_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_wrong_balance_math_bug_is_caught(tmp_path):
    """The balance guard is correct, but a copy/paste bug double-applies every leg's delta --
    wrong balance math must be caught even though every individual entry was itself balanced."""
    _write(tmp_path, "ledger.py", BROKEN_DOUBLE_APPLIES_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_ledger_wide_invariant_violation_is_caught(tmp_path):
    """The balance guard is correct, but applying an accepted entry silently drops every credit
    leg -- money is created, breaking the ledger-wide debits==credits invariant, must be caught."""
    _write(tmp_path, "ledger.py", BROKEN_DROPS_CREDIT_LEGS_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert not accepted
    assert note


def test_never_raises_on_crashing_module(tmp_path):
    _write(tmp_path, "ledger.py", CRASHING_MODULE)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_module(tmp_path):
    accepted, note = grade_double_entry(
        tmp_path, module="does_not_exist_at_all", entity="Ledger", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_missing_entity(tmp_path):
    _write(tmp_path, "ledger.py", CORRECT_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="NoSuchClass", spec=LEDGER_SPEC, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_malformed_spec(tmp_path):
    _write(tmp_path, "ledger.py", CORRECT_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec={"garbage": True}, python_exe=PY,
    )
    assert accepted is False
    assert note


def test_never_raises_on_inconsistent_spec(tmp_path):
    """A spec whose `drive` script's own legs disagree with its own `expect_final` is caught
    BEFORE any subprocess is launched."""
    _write(tmp_path, "ledger.py", CORRECT_LEDGER)

    inconsistent = dict(LEDGER_SPEC)
    inconsistent["drive"] = [
        {"legs": [{"account": "cash", "debit": 100}, {"account": "revenue", "credit": 100}],
         "expect": "accept"},
    ]
    inconsistent["expect_final"] = {"cash": 999, "revenue": 999}  # disagrees with the shadow

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=inconsistent, python_exe=PY,
    )
    assert accepted is False
    assert "inconsistency" in note


def test_never_raises_on_garbage_spec_type(tmp_path):
    _write(tmp_path, "ledger.py", CORRECT_LEDGER)

    accepted, note = grade_double_entry(
        tmp_path, module="ledger", entity="Ledger", spec=None, python_exe=PY,
    )
    assert accepted is False
    assert note
# #EXT-059-REQ-9 End
