"""Spec-driven loop (EXT-009): the jarify-FLOW alternative to the free-form agent loop.

The agentic-eval finding: a 2B free-form planner is FLAKY — it sometimes never even plans the
`fix` step, so the run fails for no good reason. The jarify methodology fixes this by removing the
open-ended judgement entirely: decompose intent into checkable REQUIREMENTS, then run a
DETERMINISTIC flow (verify -> implement -> verify) where the model only fills CONSTRAINED
sub-tasks (write a test, write code) — never "what steps?". This is the decomposition principle at
the WORKFLOW level; the owner has seen this structure converge low-reasoning models on intent.

Two flows, chosen deterministically (not by the model):
  * FIX  — a failing test already encodes the requirement ("the suite passes"); run the structured
           localize->fix->gate pipeline (multi_file_fix). The model only writes the fix.
  * BUILD — no failing test: the requirement is the intent; the test-writer turns it into checkable
           tests, then implement against them (build_in_dir). The model only writes tests + code.
"""
from __future__ import annotations

from pathlib import Path

from harness.multi_file import _run, multi_file_fix

_TEST_CMD = "python -m pytest -q"


def _find_test(cwd: str) -> str:
    for p in Path(cwd).rglob("*.py"):
        if p.name.startswith("test"):
            return str(p)
    return ""


def spec_driven_loop(intent: str, cwd: str, *, max_iters: int = 3, verbose: bool = False) -> dict:
    """Structured (jarify-flow) loop. The FLOW is deterministic; the 2B never chooses the steps —
    it only fills the constrained sub-task (the fix / the code). Returns {solved, flow, note}."""
    green, _ = _run(cwd, _TEST_CMD)
    if green:
        return {"solved": True, "flow": "already-green", "note": "requirement already met"}

    test_file = _find_test(cwd)
    if test_file:
        # FIX flow — the failing test IS the requirement; run the structured repair pipeline.
        res = multi_file_fix(cwd, _TEST_CMD, intent, test_file, max_iters=max_iters, verbose=verbose)
        green, _ = _run(cwd, _TEST_CMD)
        return {"solved": green, "flow": "fix", "note": res.get("note", "")}

    # BUILD flow — no test yet: turn the intent into tests, then implement against them.
    from harness.intent_loop import build_in_dir
    func = next((w for w in intent.replace("(", " ").split() if w.isidentifier()), "solution")
    r = build_in_dir(cwd, intent, f"{func}.py", func, max_iters=max_iters, verbose=verbose)
    return {"solved": bool(r.get("self_pass")), "flow": "build", "note": r.get("note", "")}
