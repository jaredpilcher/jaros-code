"""EXT-031 — Strategy-vs-Easier-Tasks eval harness.

MOTIVATION: the 6 solve strategies (decomposition, experiment-to-understand, collaboration,
maximal-help, verified-solution-memory, pass@k) were built and measured ONLY on the HARD
class (bigbar tasks — all returned 0/N).  Their effect on EASIER tasks (HumanEval/MBPP) is
UNTESTED.  A scaffold is a MULTIPLIER — on easier tasks the base model HAS capability to
amplify, so a lift IS plausible.  But a non-result is ALSO plausible (retrieval was a prior
negative on this codebase).

HONEST: the CI is mandatory.  A strategy whose Wilson95 CI overlaps bare IS a valid,
reportable outcome ("no significant lift").  We report it plainly, not as a failure.  Small n
produces wide CIs; that uncertainty is stated, not hidden.

Three strategies wired (reuse existing modules — no reimplementation):
  bare                 -> pass1_eval.solve_gated  (the established honest baseline)
  decomposition        -> decomp_probe._g_plan + _g_code_from_plan (EXT-020)
  experiment-to-understand -> experiment_solve.experiment_solve (EXT-030)

Scoring gate: same as pass1_eval — write solution.py, run task.test_cmd, check exit-code 0.
Oracle is score-only; never shown to any strategy during generation (Tenet 3).

Active-hours invocation (Jetson must be running):
    python -m harness.eval_strategy_easy --n 20 --bar humaneval
    python -m harness.eval_strategy_easy --n 20 --bar mbpp
    python -m harness.eval_strategy_easy --strategy decomposition --n 10 --bar humaneval
"""
from __future__ import annotations

import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shared helpers (no LLM, no I/O)
# ---------------------------------------------------------------------------

def _wilson95(k: int, n: int) -> tuple[float, float]:
    """Wilson 95% CI for a proportion.  Width shrinks as n grows — honest small-n interval."""
    if n == 0:
        return (0.0, 1.0)
    z = 1.96
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _ci_overlap(lo1: float, hi1: float, lo2: float, hi2: float) -> bool:
    """True if two Wilson95 CIs share any point (intervals overlap)."""
    return not (hi1 < lo2 or hi2 < lo1)


def _extract_fn_name(task) -> str:
    """Best-effort: extract the primary function name from the task's solution stub."""
    stub = task.files.get("solution.py", "") if hasattr(task, "files") else ""
    m = re.search(r"def\s+(\w+)\(", stub)
    return m.group(1) if m else "f"


def _load_tasks(bar: str, n: int) -> list:
    """Load the first n tasks from HumanEval or MBPP.  Both datasets must be on disk.

    HONEST: if the dataset is absent the loader raises FileNotFoundError (says so, never
    silently returns empty — Tenet 3).
    """
    if bar == "humaneval":
        from harness.humaneval import _read_problems, problem_to_task  # noqa: PLC0415
        problems = _read_problems()[:n]
        return [problem_to_task(p) for p in problems]
    if bar == "mbpp":
        from harness.mbpp import _read_problems, problem_to_task  # noqa: PLC0415
        problems = _read_problems()[:n]
        tasks = [problem_to_task(p) for p in problems]
        return [t for t in tasks if t is not None][:n]
    raise ValueError(f"Unknown bar {bar!r}. Use 'humaneval' or 'mbpp'.")


def _score_task(task, code: str) -> bool:
    """Honest pass@1 gate (same protocol as pass1_eval).

    Writes code to solution.py in an isolated temp dir, materialises all task support
    files, runs task.test_cmd, returns True iff exit-code 0.

    Oracle is score-only — never shown to any strategy during generation (Tenet 3).
    """
    from harness.eval_runner import setup_task          # noqa: PLC0415
    from harness.pass1_eval import _run_with_treekill  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as d:
        setup_task(task, Path(d))
        Path(d, "solution.py").write_text(code, encoding="utf-8", newline="\n")
        return _run_with_treekill(task.test_cmd, d, timeout=60)


# ---------------------------------------------------------------------------
# #EXT-031-REQ-1 Start
# Core evaluation function
# ---------------------------------------------------------------------------

def eval_strategy_on_easy(
    strategy: str,
    *,
    n: int,
    bar: str,
    solve_fn: "Callable | None" = None,
    model: "str | None" = None,
    _tasks=None,
) -> dict:
    """Run a strategy's solve over the first n HumanEval/MBPP tasks; score pass@1.

    HONEST: the hidden test (task.test_cmd exit code) is the sole gate — same as
    pass1_eval.  A non-result (no lift vs bare) is a valid, reportable outcome.

    Parameters
    ----------
    strategy : str
        Strategy name from STRATEGY_REGISTRY (e.g. "bare", "decomposition",
        "experiment-to-understand").
    n : int
        Number of tasks to evaluate (first n tasks from the chosen bar).
    bar : str
        Benchmark: "humaneval" or "mbpp".
    solve_fn : callable | None
        Optional override: ``solve_fn(task) -> code_str``.  Injected for offline tests.
        When None, the registry's callable for *strategy* is used (requires Jetson).
    model : str | None
        Model id for strategies that need it (e.g. "qwen2.5-coder-3b").  Passed to
        strategies that accept it; unused by "bare".
    _tasks : list | None
        Injectable task list for offline tests.  When provided, skips disk loading.

    Returns
    -------
    dict
        ``{strategy, n, passed, pass_rate, wilson95: [lo, hi], per_task: [...]}``

        per_task entries: ``{id, passed, strategy}``
    """
    if strategy not in STRATEGY_REGISTRY and solve_fn is None:
        raise KeyError(
            f"Unknown strategy {strategy!r}. Known: {list(STRATEGY_REGISTRY)}"
        )

    _solve = solve_fn if solve_fn is not None else STRATEGY_REGISTRY[strategy]
    tasks = _tasks if _tasks is not None else _load_tasks(bar, n)

    per_task: list[dict] = []
    passed = 0
    for t in tasks:
        code: str = _solve(t)
        ok: bool = _score_task(t, code)
        per_task.append({"id": t.id, "passed": ok, "strategy": strategy})
        passed += int(ok)
        status = "PASS" if ok else "fail"
        print(f"  [{status}] {t.id}", flush=True)

    total = len(tasks)
    pass_rate = passed / total if total else 0.0
    lo, hi = _wilson95(passed, total)
    return {
        "strategy": strategy,
        "n": total,
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "wilson95": [round(lo, 4), round(hi, 4)],
        "per_task": per_task,
    }

# #EXT-031-REQ-1 End


# ---------------------------------------------------------------------------
# #EXT-031-REQ-2 Start
# Strategy Registry — name -> (task -> code) callable
# ---------------------------------------------------------------------------

def _bare_solve(task) -> str:
    """Bare solve: one greedy body completion (temp=0, no strategy scaffolding).

    Uses pass1_eval.solve_gated — the established honest baseline: self-gated thinking
    that only activates when the direct solve demonstrably fails visible docstring examples.
    This IS the baseline every other strategy is compared against.

    Requires: Jetson llama.cpp server running.
    """
    from harness.pass1_eval import solve_gated  # noqa: PLC0415
    return solve_gated(task)


def _decomp_solve(task) -> str:
    """Decomposition solve: generate a numbered plan, then implement following it.

    Reuses decomp_probe._g_plan (EXT-020) to author a granular numbered
    implementation plan from the task stub + instruction, then _g_code_from_plan to
    implement following that plan (with indentation-repair applied internally).

    For HumanEval/MBPP tasks the stub serves as context; the instruction is the subject.
    Falls back to bare solve if plan-guided generation produces empty output.

    Requires: Jetson llama.cpp server running.
    """
    from harness.decomp_probe import _g_plan, _g_code_from_plan  # noqa: PLC0415

    stub = task.files.get("solution.py", "") if hasattr(task, "files") else ""
    name = _extract_fn_name(task)
    subject = task.instruction if hasattr(task, "instruction") else ""

    # Plan: stub is the context; instruction doubles as the "gherkin" (simpler task format)
    plan = _g_plan(subject, name, None, stub, subject)
    code = _g_code_from_plan(subject, name, None, stub, subject, plan)

    if not code:
        # Fallback: bare solve when plan-guided generation produces empty output
        return _bare_solve(task)
    return code


def _experiment_solve_for_task(task) -> str:
    """Experiment-to-understand solve: bounded exploration before writing the fix.

    Wraps experiment_solve (EXT-030) adapted for HumanEval/MBPP tasks.  The problem
    dict is built from the task stub.  Experiments are lightweight (read the stub,
    docstring examples) since we cannot run the hidden test node during experiments —
    bounded to max_experiments=2.  After observation the model writes the final code.

    Falls back to bare solve if experiment_solve produces empty output.

    TWO-PLANE: propose_fn returns an inert Decision dict (judgement only);
    run_exp_fn executes the bounded observation (no arbitrary code — reads stub only);
    test_fn is the sole oracle and NEVER feeds back to propose_fn or solve_fn.

    Requires: Jetson llama.cpp server running (gemma-4-e2b via manager or direct).
    """
    from harness.experiment_solve import experiment_solve, _make_jetson_fns  # noqa: PLC0415

    stub = task.files.get("solution.py", "") if hasattr(task, "files") else ""
    name = _extract_fn_name(task)
    subject = task.instruction if hasattr(task, "instruction") else ""

    problem = {
        "subject": subject,
        "name": name,
        "parent_src": stub,
        "context": "",
    }

    manager_url = "http://192.168.1.183:8001"
    active_model = "gemma-4-e2b"
    propose_fn, jetson_solve_fn = _make_jetson_fns(active_model, manager_url)

    def run_exp_fn(prob, decision) -> str:
        """Bounded experiment for HumanEval/MBPP — reads the stub (E3-style).

        We cannot run the hidden test nodes during exploration (they require the correct
        solution to exist, which we haven't written yet).  Instead:
          E3 -> read function source from the stub
          E1/E2 -> return the stub docstring as context (informative without execution)
        BOUNDED: no arbitrary code execution; only the literal stub text is returned.
        """
        exp_type = (decision.get("type", "E1") if isinstance(decision, dict) else "E1")
        if exp_type == "E3":
            fn = ((decision.get("params") or {}).get("fn_name", name)
                  if isinstance(decision, dict) else name)
            if fn in stub:
                return f"E3 — source of `{fn}` in stub:\n{stub[:600]}"
            return f"E3: `{fn}` not found in stub; showing full stub:\n{stub[:600]}"
        # E1/E2 fallback: return stub context (no live process — HumanEval task context)
        return (
            f"Task stub for `{name}` ({exp_type}):\n{stub[:600]}\n\n"
            f"Instruction: {subject[:200]}"
        )

    def test_fn(prob, code) -> dict:
        """Oracle: score-only.  NEVER shown to propose_fn or solve_fn."""
        ok = _score_task(task, code)
        return {"passed": ok}

    result = experiment_solve(
        problem,
        propose_fn=propose_fn,
        run_experiment_fn=run_exp_fn,
        solve_fn=jetson_solve_fn,
        test_fn=test_fn,
        max_experiments=2,
    )
    code: str = result.get("code", "")
    if not code:
        return _bare_solve(task)
    return code


#: Strategy registry: name -> solve callable (task) -> code str.
#: All callables require the Jetson running for live runs; for offline tests inject
#: solve_fn into eval_strategy_on_easy (the registry callable is never called).
STRATEGY_REGISTRY: dict[str, Callable] = {
    "bare": _bare_solve,
    "decomposition": _decomp_solve,
    "experiment-to-understand": _experiment_solve_for_task,
}

# #EXT-031-REQ-2 End


# ---------------------------------------------------------------------------
# #EXT-031-REQ-3 Start
# Compare function with honest Wilson95 CI
# ---------------------------------------------------------------------------

def compare(
    n: int,
    bar: str,
    *,
    _tasks=None,
    _solve_fns: "dict | None" = None,
) -> dict:
    """Compare "bare" vs each strategy on the SAME n tasks with honest Wilson95 CI.

    HONEST CI RULE: a delta outside CI overlap counts as a real lift.  A delta WITHIN
    CI overlap = "no significant lift" — this IS a valid outcome, printed plainly.
    Small n means wide CIs; the report says so explicitly, not quietly.

    Prior negative (retrieval-fewshot, EXT-009): retrieval did NOT lift the 2B
    (67->62%).  A non-result here is not surprising and is just as informative.

    Parameters
    ----------
    n : int
        Number of tasks per strategy.  All strategies run on THE SAME task list.
    bar : str
        Benchmark: "humaneval" or "mbpp".
    _tasks : list | None
        Injectable task list (offline tests).  Avoids loading the dataset from disk.
    _solve_fns : dict | None
        Optional ``{strategy_name: solve_fn}`` overrides (offline tests).
        Missing keys fall back to the registry.

    Returns
    -------
    dict
        ``{bar, n, bare_rate, results: {strategy: {...}}, summary: [...]}``

        summary entries:
        ``{strategy, pass_rate, wilson95, delta, significant_lift, lift_tag}``
    """
    _solve_fns = _solve_fns or {}
    tasks = _tasks if _tasks is not None else _load_tasks(bar, n)
    actual_n = len(tasks)

    # -- Bare baseline (run first; same task list fed to every other strategy) -----------
    bare_sfn = _solve_fns.get("bare")
    print(f"\n>>> EXT-031 strategy comparison  bar={bar}  n={actual_n}", flush=True)
    print(">>> HONEST: CI overlap = no significant lift (valid, reportable outcome)",
          flush=True)
    print(f"\n  Running strategy: bare (baseline)  n={actual_n}", flush=True)

    bare_result = eval_strategy_on_easy(
        "bare", n=actual_n, bar=bar, solve_fn=bare_sfn, _tasks=tasks
    )
    bare_rate = bare_result["pass_rate"]
    bare_lo, bare_hi = bare_result["wilson95"]

    results: dict = {"bare": bare_result}
    summary: list[dict] = []

    header_row = (
        f"\n{'=' * 72}\n"
        f"  {'strategy':<28}  {'pass_rate':>9}  {'wilson95':>20}  {'delta':>8}  lift?"
    )
    print(header_row, flush=True)
    print(f"  {'-' * 28}  {'-' * 9}  {'-' * 20}  {'-' * 8}  -----", flush=True)
    bare_ci_str = f"[{bare_lo:.3f}, {bare_hi:.3f}]"
    print(f"  {'bare (baseline)':<28}  {bare_rate:>9.3f}  {bare_ci_str:>20}"
          f"  {'---':>8}  ---", flush=True)

    # -- Non-bare strategies -----------------------------------------------------------
    for strat in STRATEGY_REGISTRY:
        if strat == "bare":
            continue
        sfn = _solve_fns.get(strat)
        print(f"\n  Running strategy: {strat}  n={actual_n}", flush=True)
        res = eval_strategy_on_easy(strat, n=actual_n, bar=bar, solve_fn=sfn, _tasks=tasks)
        results[strat] = res

        s_rate = res["pass_rate"]
        s_lo, s_hi = res["wilson95"]
        delta = round(s_rate - bare_rate, 4)

        overlap = _ci_overlap(bare_lo, bare_hi, s_lo, s_hi)
        is_significant = (not overlap) and (delta != 0)
        sig_lift = is_significant and delta > 0

        if sig_lift:
            lift_tag = "LIFT *"
        elif is_significant and delta < 0:
            lift_tag = "NEGATIVE *"
        else:
            lift_tag = "no (CI overlap)"

        res["delta"] = delta
        res["significant_lift"] = sig_lift

        ci_str = f"[{s_lo:.3f}, {s_hi:.3f}]"
        print(f"  {strat:<28}  {s_rate:>9.3f}  {ci_str:>20}  {delta:>+8.3f}"
              f"  {lift_tag}", flush=True)

        summary.append({
            "strategy": strat,
            "pass_rate": s_rate,
            "wilson95": [s_lo, s_hi],
            "delta": delta,
            "significant_lift": sig_lift,
            "lift_tag": lift_tag,
        })

    print(f"\n{'=' * 72}", flush=True)
    print(f">>> n={actual_n} tasks — Wilson95 CI; narrow CI needs n>=30.", flush=True)
    print(f">>> 'no (CI overlap)' IS a valid honest result (prior: retrieval was -5%).",
          flush=True)
    print(f"{'=' * 72}\n", flush=True)

    return {
        "bar": bar,
        "n": actual_n,
        "bare_rate": bare_rate,
        "results": results,
        "summary": summary,
    }

# #EXT-031-REQ-3 End


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "EXT-031: strategy-vs-easier-tasks eval harness.\n"
            "Compares solve strategies on HumanEval/MBPP tasks with honest Wilson95 CI.\n"
            "HONEST: 'no significant lift' is a valid, reportable outcome.\n\n"
            "Active-hours invocation (Jetson must be running):\n"
            "  python -m harness.eval_strategy_easy --n 20 --bar humaneval\n"
            "  python -m harness.eval_strategy_easy --n 20 --bar mbpp\n"
            "  python -m harness.eval_strategy_easy --strategy decomposition "
            "--n 10 --bar humaneval"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--n", type=int, default=20,
        help="Number of tasks per strategy (default: 20)"
    )
    parser.add_argument(
        "--bar", default="humaneval", choices=["humaneval", "mbpp"],
        help="Benchmark to evaluate on (default: humaneval)"
    )
    parser.add_argument(
        "--strategy", default=None,
        help=(
            "Run ONE strategy and exit (default: all via compare()).\n"
            f"Known: {', '.join(STRATEGY_REGISTRY)}"
        ),
    )
    args = parser.parse_args()

    if args.strategy:
        if args.strategy not in STRATEGY_REGISTRY:
            print(
                f"ERROR: unknown strategy {args.strategy!r}. "
                f"Known: {list(STRATEGY_REGISTRY)}",
                file=sys.stderr,
            )
            sys.exit(1)
        result = eval_strategy_on_easy(args.strategy, n=args.n, bar=args.bar)
        passed = result["passed"]
        total = result["n"]
        lo, hi = result["wilson95"]
        print(
            f"\n>>> {args.strategy}  {passed}/{total} = {result['pass_rate']:.3f}"
            f"  Wilson95 [{lo:.3f}, {hi:.3f}]"
        )
    else:
        compare(args.n, args.bar)
