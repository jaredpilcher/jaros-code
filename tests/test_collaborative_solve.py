"""Offline tests for EXT-029 harness/collaborative_solve.py.

All tests run WITHOUT the Jetson (no LLM calls, no Docker, no git clones).
Mock callables replace all live I/O.

Acceptance criteria covered
----------------------------
(a) draft passes  -> solved round 0; critique_fn and revise_fn NOT called.
(b) draft fails, revise (after critique) passes -> solved via collab; transcript
    records draft + critique + revised for the round.
(c) all rounds fail within max_rounds -> solved:False; all attempts recorded.
(d) test_fn is the sole arbiter — a mock where the model "claims" success but
    test_fn says fail -> NOT solved (model-as-judge is forbidden).
(e) max_rounds bounds the loop exactly — revise_fn called exactly max_rounds times.

Additional coverage
-------------------
(f) syntax smoke: collaborative_solve.py parses without SyntaxError.
(g) import smoke: top-level public symbols importable.
(h) winner field: "draft" / "collab" / None as appropriate.
(i) attempts list: empty on draft-pass; length = r on r-round collab win.
(j) multi-round collab: draft fails, round-1 fails, round-2 passes -> rounds==2.
(k) max_rounds=0: no critique/revise rounds; returns solved:False if draft fails.
(l) code field: returns the LAST revised code on all-fail, not the original draft.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.collaborative_solve import collaborative_solve


# ---------------------------------------------------------------------------
# (f) Syntax smoke
# ---------------------------------------------------------------------------

def test_collaborative_solve_parses():
    """collaborative_solve.py must parse without syntax errors."""
    src = (_REPO_ROOT / "harness" / "collaborative_solve.py").read_text(encoding="utf-8")
    ast.parse(src)


# ---------------------------------------------------------------------------
# (g) Import smoke
# ---------------------------------------------------------------------------

def test_collaborative_solve_imports():
    """Top-level public symbols importable — no heavy LLM imports at module scope."""
    from harness.collaborative_solve import (  # noqa: F401
        collaborative_solve,
        _make_jetson_fns,
        _build_critique_prompt,
        _build_revise_prompt,
        _http_swap,
        collab_probe,
        run_collab_probe,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fns(
    *,
    draft_code: str = "def f(): pass",
    pass_codes: set | None = None,
    critiques: list | None = None,
    revise_codes: list | None = None,
):
    """Build injectable mock callables for parametrized scenarios.

    pass_codes: set of code strings that test_fn should accept; default = all fail.
    revise_codes: list of revised code strings returned in order per revise call.
    """
    pass_set: set = pass_codes or set()
    critique_seq: list = critiques or ["critique text"]
    revise_seq: list = revise_codes or ["revised code"]

    critique_calls: list = []
    revise_calls: list = []

    def draft_fn(problem):
        return draft_code

    def critique_fn(problem, code, test_result):
        text = critique_seq[len(critique_calls) % len(critique_seq)]
        critique_calls.append((problem, code, test_result))
        return text

    def revise_fn(problem, code, critique):
        revised = revise_seq[len(revise_calls) % len(revise_seq)]
        revise_calls.append((problem, code, critique))
        return revised

    def test_fn(problem, code):
        return {"passed": code in pass_set}

    return draft_fn, critique_fn, revise_fn, test_fn, critique_calls, revise_calls


# ---------------------------------------------------------------------------
# (a) Draft passes -> round 0, critique/revise NOT called
# ---------------------------------------------------------------------------

def test_draft_passes_round0():
    """When draft_fn produces passing code, critique and revise are never called."""
    GOOD = "def f(): return 42"
    draft_fn, critique_fn, revise_fn, test_fn, crit_calls, rev_calls = _make_fns(
        draft_code=GOOD, pass_codes={GOOD}
    )

    result = collaborative_solve(
        "problem",
        draft_fn=draft_fn,
        critique_fn=critique_fn,
        revise_fn=revise_fn,
        test_fn=test_fn,
    )

    assert result["solved"] is True
    assert result["rounds"] == 0
    assert result["winner"] == "draft"
    assert result["code"] == GOOD
    assert len(crit_calls) == 0, "critique_fn must NOT be called when draft passes"
    assert len(rev_calls) == 0, "revise_fn must NOT be called when draft passes"
    assert result["attempts"] == []


# ---------------------------------------------------------------------------
# (b) Draft fails, revise (round 1) passes -> collab; transcript recorded
# ---------------------------------------------------------------------------

def test_draft_fails_revise_passes_round1():
    """Draft fails; first critique+revise produces passing code -> collab win at round 1."""
    DRAFT = "def f(): return 0"
    REVISED = "def f(): return 42"

    draft_fn, critique_fn, revise_fn, test_fn, crit_calls, rev_calls = _make_fns(
        draft_code=DRAFT,
        pass_codes={REVISED},
        critiques=["should return 42 not 0"],
        revise_codes=[REVISED],
    )

    result = collaborative_solve(
        "test problem",
        draft_fn=draft_fn,
        critique_fn=critique_fn,
        revise_fn=revise_fn,
        test_fn=test_fn,
        max_rounds=2,
    )

    assert result["solved"] is True
    assert result["rounds"] == 1
    assert result["winner"] == "collab"
    assert result["code"] == REVISED
    # Transcript
    assert len(result["attempts"]) == 1
    rec = result["attempts"][0]
    assert "draft" in rec, "transcript must record draft code per round"
    assert "critique" in rec, "transcript must record critique per round"
    assert "revised" in rec, "transcript must record revised code per round"
    assert rec["round"] == 1
    assert rec["draft"] == DRAFT
    assert rec["critique"] == "should return 42 not 0"
    assert rec["revised"] == REVISED
    # critique_fn and revise_fn each called exactly once
    assert len(crit_calls) == 1
    assert len(rev_calls) == 1


# ---------------------------------------------------------------------------
# (c) All rounds fail -> solved:False, all attempts recorded
# ---------------------------------------------------------------------------

def test_all_rounds_fail():
    """When every round produces failing code, solved=False and all attempts recorded."""
    draft_fn, critique_fn, revise_fn, test_fn, crit_calls, rev_calls = _make_fns(
        draft_code="def f(): pass",
        pass_codes=set(),  # nothing passes
        critiques=["critique A", "critique B"],
        revise_codes=["bad rev 1", "bad rev 2"],
    )

    result = collaborative_solve(
        "problem",
        draft_fn=draft_fn,
        critique_fn=critique_fn,
        revise_fn=revise_fn,
        test_fn=test_fn,
        max_rounds=2,
    )

    assert result["solved"] is False
    assert result["rounds"] == 2
    assert result["winner"] is None
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["round"] == 1
    assert result["attempts"][1]["round"] == 2


# ---------------------------------------------------------------------------
# (d) test_fn is the sole arbiter — model "claims" success but test_fn says fail
# ---------------------------------------------------------------------------

def test_test_fn_sole_arbiter():
    """test_fn is the only gate. Even if model says it fixed the issue, we follow test_fn."""
    # The model's revise_fn produces code that "looks" correct and the
    # critique says "I fixed it!" — but test_fn always returns passed=False.
    claim_calls: list = []

    def draft_fn(problem):
        return "def f(): return 0"  # clearly wrong

    def critique_fn(problem, code, test_result):
        return "I've identified the bug! Just return 42."

    def revise_fn(problem, code, critique):
        # Model emits a comment claiming the fix is perfect
        claim_calls.append(code)
        return "# MODEL CLAIMS THIS IS CORRECT\ndef f(): return 42"

    def test_fn(problem, code):
        # test_fn always fails regardless of what model produced
        return {"passed": False, "reason": "oracle says no"}

    result = collaborative_solve(
        "problem",
        draft_fn=draft_fn,
        critique_fn=critique_fn,
        revise_fn=revise_fn,
        test_fn=test_fn,
        max_rounds=3,
    )

    # test_fn returned False every time -> must be unsolved
    assert result["solved"] is False, (
        "test_fn is the sole arbiter; model 'claiming' success must not affect solved flag"
    )
    assert result["winner"] is None
    # revise_fn was called (model tried), but test_fn gate overrides
    assert len(claim_calls) == 3


# ---------------------------------------------------------------------------
# (e) max_rounds bounds the loop exactly
# ---------------------------------------------------------------------------

def test_max_rounds_bounds_loop():
    """revise_fn is called EXACTLY max_rounds times; never more."""
    revise_count: list[int] = [0]

    def draft_fn(problem): return "bad"
    def critique_fn(problem, code, tr): return "critique"
    def revise_fn(problem, code, crit):
        revise_count[0] += 1
        return f"attempt_{revise_count[0]}"
    def test_fn(problem, code): return {"passed": False}

    max_r = 4
    result = collaborative_solve(
        "p",
        draft_fn=draft_fn,
        critique_fn=critique_fn,
        revise_fn=revise_fn,
        test_fn=test_fn,
        max_rounds=max_r,
    )

    assert revise_count[0] == max_r, (
        f"revise_fn called {revise_count[0]} times but max_rounds={max_r}"
    )
    assert result["rounds"] == max_r
    assert result["solved"] is False


# ---------------------------------------------------------------------------
# (h) winner field correctness
# ---------------------------------------------------------------------------

def test_winner_draft():
    """winner='draft' when draft passes immediately."""
    GOOD = "def f(): return 1"
    result = collaborative_solve(
        "p",
        draft_fn=lambda p: GOOD,
        critique_fn=lambda p, c, t: "x",
        revise_fn=lambda p, c, r: "y",
        test_fn=lambda p, code: {"passed": code == GOOD},
    )
    assert result["winner"] == "draft"


def test_winner_collab():
    """winner='collab' when revise produces the passing candidate."""
    REVISED = "def f(): return 99"
    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "bad",
        critique_fn=lambda p, c, t: "try 99",
        revise_fn=lambda p, c, r: REVISED,
        test_fn=lambda p, code: {"passed": code == REVISED},
        max_rounds=1,
    )
    assert result["winner"] == "collab"


def test_winner_none_on_all_fail():
    """winner=None when all rounds exhaust without passing."""
    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "bad",
        critique_fn=lambda p, c, t: "try again",
        revise_fn=lambda p, c, r: "still bad",
        test_fn=lambda p, code: {"passed": False},
        max_rounds=2,
    )
    assert result["winner"] is None


# ---------------------------------------------------------------------------
# (i) attempts list structure
# ---------------------------------------------------------------------------

def test_attempts_empty_on_draft_pass():
    """attempts list is empty when draft passes immediately."""
    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "good",
        critique_fn=lambda p, c, t: "x",
        revise_fn=lambda p, c, r: "y",
        test_fn=lambda p, code: {"passed": True},
    )
    assert result["attempts"] == []


def test_attempts_length_matches_rounds():
    """len(attempts) == rounds for a collab win."""
    REVISED = "winning"
    call_count = [0]

    def revise_fn(p, c, r):
        call_count[0] += 1
        return REVISED if call_count[0] == 2 else "bad"

    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "bad",
        critique_fn=lambda p, c, t: "crit",
        revise_fn=revise_fn,
        test_fn=lambda p, code: {"passed": code == REVISED},
        max_rounds=3,
    )

    assert result["solved"] is True
    assert result["rounds"] == 2
    assert len(result["attempts"]) == 2


# ---------------------------------------------------------------------------
# (j) Multi-round collab: round-1 fails, round-2 passes -> rounds==2
# ---------------------------------------------------------------------------

def test_round2_collab_win():
    """Draft fails, round-1 revise fails, round-2 revise passes -> rounds==2."""
    GOOD = "def f(): return 42"
    revise_seq = ["bad", GOOD]
    rev_count = [0]

    def revise_fn(p, c, r):
        code = revise_seq[rev_count[0] % len(revise_seq)]
        rev_count[0] += 1
        return code

    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "bad draft",
        critique_fn=lambda p, c, t: "critique",
        revise_fn=revise_fn,
        test_fn=lambda p, code: {"passed": code == GOOD},
        max_rounds=3,
    )

    assert result["solved"] is True
    assert result["rounds"] == 2
    assert result["winner"] == "collab"
    assert result["code"] == GOOD


# ---------------------------------------------------------------------------
# (k) max_rounds=0: no critique/revise; solved:False if draft fails
# ---------------------------------------------------------------------------

def test_max_rounds_zero_no_revise():
    """With max_rounds=0 and a failing draft, solved=False immediately."""
    crit_calls: list = []
    rev_calls: list = []

    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "bad",
        critique_fn=lambda p, c, t: (crit_calls.append(1), "x")[1],
        revise_fn=lambda p, c, r: (rev_calls.append(1), "y")[1],
        test_fn=lambda p, code: {"passed": False},
        max_rounds=0,
    )

    assert result["solved"] is False
    assert result["rounds"] == 0
    assert result["attempts"] == []
    assert len(crit_calls) == 0
    assert len(rev_calls) == 0


# ---------------------------------------------------------------------------
# (l) code field: last revised code on all-fail (not original draft)
# ---------------------------------------------------------------------------

def test_code_field_is_last_revised_on_fail():
    """On all-fail, code field contains the LAST revised code, not the draft."""
    LAST = "def f(): return 'last attempt'"
    revise_seq = ["rev1", "rev2", LAST]
    rev_count = [0]

    def revise_fn(p, c, r):
        code = revise_seq[rev_count[0] % len(revise_seq)]
        rev_count[0] += 1
        return code

    result = collaborative_solve(
        "p",
        draft_fn=lambda p: "initial draft",
        critique_fn=lambda p, c, t: "crit",
        revise_fn=revise_fn,
        test_fn=lambda p, code: {"passed": False},
        max_rounds=3,
    )

    assert result["solved"] is False
    assert result["code"] == LAST, (
        "code field must be the last revised code on all-fail, not the original draft"
    )
