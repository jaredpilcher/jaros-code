"""harness/judgment_eval.py — Tool-use-judgment eval for the 2B orchestrator judge.

Scores the 2B judge (_judge_revision in behavioral_solve.py) DIRECTLY on a held-out set
of realistic FAILED-solve states. This is a DIAGNOSTIC — it tells us which failure classes
the judge gets right/wrong, feeding the grounding work (task #12 after #21).

Real action space (from behavioral_solve._REV, verbatim):
  code    — the implementation has a LOGIC bug -> rewrite the code
  gherkin — the behavior spec MISUNDERSTOOD the intent -> rewrite the spec (and its tests)
  repair  — the logic is right but the code has broken indentation/syntax
  done    — stop — it cannot be fixed

Run against the live Jetson 2B:
    python -m harness.judgment_eval

For offline / unit-test use, inject a stub judge:
    from harness.judgment_eval import run_eval
    results = run_eval(judge_fn=lambda intent, name, fb, temp: "code")

EXT-016 / REQ-2
"""
# #EXT-016-REQ-2 Start
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

# The real action space — must stay in sync with behavioral_solve._REV keys.
VALID_ACTIONS = frozenset({"code", "gherkin", "repair", "done"})

_SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "evals" / "judgment" / "scenarios.json"


def _load_scenarios(path: Path = _SCENARIOS_PATH) -> list[dict]:
    """Load and return the scenarios list from JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _default_judge(intent: str, name: str, fb: str, temp: float) -> str:
    """The real 2B judge — imported lazily so unit tests never trigger an LLM import."""
    from harness.behavioral_solve import _judge_revision
    return _judge_revision(intent, name, fb, temp)


def _parse_action(raw: str) -> str:
    """Mirror behavioral_solve's parse logic: find first matching action key in output.

    Falls back to 'code' when no known action word appears — identical to the real caller.
    """
    lowered = raw.strip().lower()
    return next((a for a in VALID_ACTIONS if a in lowered), "code")


def run_eval(
    judge_fn: Callable[[str, str, str, float], str] | None = None,
    scenarios_path: Path = _SCENARIOS_PATH,
    temp: float = 0.0,
    silent: bool = False,
) -> list[dict]:
    """Run the judgment eval.

    Parameters
    ----------
    judge_fn : optional callable (intent, name, fb, temp) -> str
        If None, uses the real _judge_revision (requires Jetson).
        Pass a stub for offline testing.
    scenarios_path : path to scenarios.json (defaults to evals/judgment/scenarios.json)
    temp : temperature passed to the judge (0.0 = deterministic)
    silent : if True, suppress all printed output (used in unit tests that capture output)

    Returns
    -------
    List of per-scenario result dicts:
        {id, failure_class, expected, got, ok}
    """
    judge = judge_fn if judge_fn is not None else _default_judge
    scenarios = _load_scenarios(scenarios_path)

    results: list[dict] = []
    for sc in scenarios:
        raw_out = judge(sc["intent"], sc["name"], sc["feedback"], temp)
        got = _parse_action(raw_out)
        expected = sc["expected_action"]
        ok = got == expected
        results.append({
            "id": sc["id"],
            "failure_class": sc["failure_class"],
            "expected": expected,
            "got": got,
            "ok": ok,
        })

    if not silent:
        _print_report(results)

    return results


def _print_report(results: list[dict]) -> None:
    """Print the per-scenario table, overall accuracy, and per-class breakdown."""
    # Header
    col = 22
    print(f"\n{'Scenario':<{col}} {'Class':<18} {'Expected':<10} {'Got':<10} {'OK'}")
    print("-" * (col + 18 + 10 + 10 + 6))

    for r in results:
        tick = "YES" if r["ok"] else "NO "
        print(f"{r['id']:<{col}} {r['failure_class']:<18} {r['expected']:<10} {r['got']:<10} {tick}")

    n_ok = sum(1 for r in results if r["ok"])
    n_total = len(results)
    pct = 100.0 * n_ok / n_total if n_total else 0.0
    print(f"\nOverall accuracy: {n_ok}/{n_total} correct ({pct:.1f}%)")

    # Per-class breakdown
    class_correct: dict[str, int] = defaultdict(int)
    class_total: dict[str, int] = defaultdict(int)
    for r in results:
        fc = r["failure_class"]
        class_total[fc] += 1
        if r["ok"]:
            class_correct[fc] += 1

    print("\nPer-class breakdown:")
    for fc in sorted(class_total):
        c, t = class_correct[fc], class_total[fc]
        bar = "YES" if c == t else ("PARTIAL" if c > 0 else "NONE")
        print(f"  {fc:<20} {c}/{t}  [{bar}]")
    print()
# #EXT-016-REQ-2 End


def main() -> None:
    """Entry point: python -m harness.judgment_eval"""
    print("=== Judgment Eval — 2B judge diagnostic (EXT-016) ===")
    print(f"Scenarios: {_SCENARIOS_PATH}")
    print("Calling live 2B judge (_judge_revision, temp=0.0) ...")
    results = run_eval()
    n_ok = sum(1 for r in results if r["ok"])
    # Exit non-zero if judge is below 50% — not a hard gate, just a signal.
    sys.exit(0 if n_ok >= len(results) / 2 else 1)


if __name__ == "__main__":
    main()
