"""EXT-033 — Routed-eval capstone: system-level multi-model lift measurement.

Validates the PRIME-001 multi-model claim end-to-end: does routing each problem
to its measured-best model (the multi-model harness) deliver a higher pass@1
than running everything on the default single model (gemma-4-e2b)?

Public API
----------
eval_routed(n, bar, registry, *, route_fn=None, solve_fn=None, _tasks=None) -> dict
    For the first n tasks of a benchmark, route each to its best-measured model
    (via the deterministic router), solve with that model's adaptation, and score
    with the honest pass@1 gate (task.test_cmd exit-code).

eval_single(n, bar, model, *, registry=None, solve_fn=None, _tasks=None) -> dict
    Baseline: solve all n tasks with ONE fixed model (default gemma-4-e2b).

compare_routed_vs_single(n, bar, ...) -> dict
    Run both on THE SAME n tasks and print a comparison table with honest
    Wilson95 CI (mirrors EXT-031/eval_strategy_easy convention).

All three callables accept injectable route_fn/solve_fn for OFFLINE tests —
no Jetson call is needed in tests.

Active-hours run command (Jetson must be running with gemma + qwen available):
    python -m harness.eval_routed --n 20 --bar humaneval

EXPECTED LIVE RESULT:
  standalone-fn-gen tasks -> qwen2.5-coder-3b (92% HumanEval measured)
  single-gemma baseline   -> gemma-4-e2b     (82% HumanEval measured)
  Expected lift: ~+10 pp.  Note: n=20 produces wide Wilson95 CIs; you may
  need n>=30 for CI separation. The per-task routing table always shows WHICH
  model handled each task (routing demonstration regardless of CI).

RESTORE GEMMA AFTER THE LIVE RUN:
  python -m harness.model_rewire gemma-4-e2b
  (or: ssh jetson "sudo systemctl restart gemma.service")

NOTE ON qwen3-4b-thinking:
  The hard-class / qwen3-4b-thinking escalation is a SEPARATELY VALIDATED path
  (solve_routed_escalating + test_fn gate, EXT-021 REQ-6). This capstone focuses
  on the tractable synthesis-class routing: gemma vs qwen2.5-coder-3b on
  standalone-fn-gen. Keep qwen3 OUT of the default capstone run (it is slow).

HONEST CI RULE (mirrors EXT-031):
  "lift?" = "yes (CI separates)" ONLY when the delta falls OUTSIDE the overlap
  of both Wilson95 intervals. Within-CI delta = "no (CI overlap)" — this IS a
  valid, reportable outcome (prior: retrieval was -5%, EXT-009). Small n
  produces wide CIs; that uncertainty is stated, not hidden (Tenet 3).
"""
from __future__ import annotations

import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Math helpers (same formulas as eval_strategy_easy; inline to avoid coupling)
# ---------------------------------------------------------------------------

def _wilson95(k: int, n: int) -> tuple[float, float]:
    """Wilson 95% CI for a proportion.  Width shrinks as n grows — honest."""
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


# ---------------------------------------------------------------------------
# Task loading (same _load_tasks logic as eval_strategy_easy)
# ---------------------------------------------------------------------------

def _load_tasks(bar: str, n: int) -> list:
    """Load first n tasks from HumanEval or MBPP.  Raises FileNotFoundError if absent.

    HONEST: if the dataset is absent the loader raises, never silently returns
    empty — Tenet 3.
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


# ---------------------------------------------------------------------------
# Honest pass@1 gate (same protocol as pass1_eval and eval_strategy_easy)
# ---------------------------------------------------------------------------

def _score_task(task: Any, code: str) -> bool:
    """Honest pass@1 gate: write code to solution.py, run task.test_cmd, check exit-code 0.

    Oracle is score-only — NEVER shown to any model during generation (Tenet 3).
    Same protocol as pass1_eval.run_pass1 and eval_strategy_easy._score_task.
    """
    from harness.eval_runner import setup_task          # noqa: PLC0415
    from harness.pass1_eval import _run_with_treekill  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as d:
        setup_task(task, Path(d))
        Path(d, "solution.py").write_text(code, encoding="utf-8", newline="\n")
        return _run_with_treekill(task.test_cmd, d, timeout=60)


# ---------------------------------------------------------------------------
# Problem dict builder for routing (deterministic feature extraction)
# ---------------------------------------------------------------------------

def _problem_dict_for_task(task: Any) -> dict:
    """Build a routing problem dict from a benchmark task.

    The deterministic router (model_router.route) extracts features from the
    stub source: ``>>>`` in the docstring -> ``standalone-fn-gen`` class.
    HumanEval stubs have docstring examples (``>>>``), so they classify as
    ``standalone-fn-gen`` and route to qwen2.5-coder-3b (92% HumanEval).
    MBPP stubs rarely have ``>>>`` so they classify as ``single-file-repair``.
    """
    stub: str = ""
    if hasattr(task, "files") and isinstance(task.files, dict):
        stub = task.files.get("solution.py", "")
    instruction: str = getattr(task, "instruction", "")
    return {
        "source": stub,
        "prompt": stub,   # legacy key some router paths expect
        "text": stub,
        "task": instruction,
    }


# ---------------------------------------------------------------------------
# Default live solve_fn factory (requires Jetson for live runs)
# ---------------------------------------------------------------------------

def _make_live_solve_fn(registry: Any) -> Callable:
    """Factory: returns a solve_fn that rewires to the routed model and generates code.

    Signature of the returned callable: ``solve_fn(task, decision) -> str``

    Adaptation dispatch (same as solve_routed's _default_solve_fn):
      qwen-instruct-direct  -> qwen_adapt.qwen_code
      gherkin-decompose     -> g_gherkin + g_code (Gemma path)
      unknown / missing     -> falls back to gherkin-decompose (DEFAULT)

    LIVE JETSON NOTES:
    - No rewire is triggered when the model is already active (idempotent).
    - Returns empty string on rewire failure; task scores as fail (Tenet 3).
    - After eval_routed returns, restore gemma:
        python -m harness.model_rewire gemma-4-e2b
    """
    def _solve(task: Any, decision: dict) -> str:
        from harness.model_rewire import rewire       # noqa: PLC0415
        from harness.adaptation import code_gen_for   # noqa: PLC0415

        model_id: str = decision.get("model_id", "")
        rw = rewire(model_id, registry)
        if not rw.get("ok"):
            # Honest: empty code on rewire failure -> gate scores it as fail
            return ""

        profile = registry.lookup_by_id(model_id)
        adaptation = profile.adaptation if profile is not None else {}
        code_gen = code_gen_for(adaptation)  # NEVER raises; defaults to gherkin

        stub: str = task.files.get("solution.py", "") if hasattr(task, "files") else ""
        m = re.search(r"def\s+(\w+)\(", stub)
        fn_name: str = m.group(1) if m else "solution"
        instruction: str = getattr(task, "instruction", "")
        return code_gen(instruction, fn_name, stub)

    return _solve


# ---------------------------------------------------------------------------
# #EXT-033-REQ-1 Start
# eval_routed: routed multi-model system evaluation
# ---------------------------------------------------------------------------

def eval_routed(
    n: int,
    bar: str,
    registry: Any,
    *,
    route_fn: Optional[Callable] = None,
    solve_fn: Optional[Callable] = None,
    _tasks=None,
) -> dict:
    """Evaluate the routed multi-model system on the first n tasks of a benchmark.

    For each task:
      1. Build a problem dict (stub source — carries docstring features for routing).
      2. Route deterministically: ``route_fn(problem_dict, registry) -> decision``.
      3. Solve with the routed model's adaptation: ``solve_fn(task, decision) -> str``.
      4. Score with the honest pass@1 gate: ``task.test_cmd`` exit-code 0 = pass.

    Parameters
    ----------
    n : int
        Number of tasks (first n from the benchmark).
    bar : str
        Benchmark: "humaneval" or "mbpp".
    registry : ModelRegistry
        Model registry used for routing (class -> model tally lookup).
    route_fn : callable | None
        Override: ``route_fn(problem_dict, registry) -> decision_dict``.
        When None, uses ``harness.model_router.route`` (deterministic classifier).
        Injected for offline tests — no Jetson needed.
    solve_fn : callable | None
        Override: ``solve_fn(task, decision) -> str`` (returns code string).
        When None, uses ``_make_live_solve_fn(registry)`` (requires Jetson).
        Injected for offline tests.
    _tasks : list | None
        Injectable task list for offline tests. Avoids disk loading.

    Returns
    -------
    dict ::

        {
          "n":             int,
          "bar":           str,
          "routed_passed": int,
          "routed_rate":   float,
          "wilson95":      [float, float],
          "per_task":      [
            {
              "task_id":       str,
              "routed_model":  str,
              "problem_class": str,
              "passed":        bool,
            },
            ...
          ],
        }

    Tenet guarantees
    ----------------
    - Tenet 1: ``route_fn`` is inert (Decision data only); ``solve_fn`` is the clerk.
    - Tenet 2: routing selects only Jetson-fitting models (tally invariant).
    - Tenet 3: honest gate (test_cmd exit-code); every failure surfaced in per_task.
    """
    from harness.model_router import route as _default_route  # noqa: PLC0415

    _route: Callable = route_fn if route_fn is not None else _default_route
    _solve: Callable = solve_fn if solve_fn is not None else _make_live_solve_fn(registry)

    tasks = _tasks if _tasks is not None else _load_tasks(bar, n)
    per_task: list[dict] = []
    routed_passed = 0

    for t in tasks:
        problem_dict = _problem_dict_for_task(t)
        decision: dict = _route(problem_dict, registry)
        model_id: str = decision.get("model_id", "unknown")
        problem_class: str = decision.get("problem_class", "unknown")

        code: str = _solve(t, decision)
        ok: bool = _score_task(t, code)
        routed_passed += int(ok)

        per_task.append({
            "task_id": t.id,
            "routed_model": model_id,
            "problem_class": problem_class,
            "passed": ok,
        })
        status = "PASS" if ok else "fail"
        print(f"  [{status}] {t.id}  routed_to={model_id}  class={problem_class}",
              flush=True)

    total = len(tasks)
    routed_rate = routed_passed / total if total else 0.0
    lo, hi = _wilson95(routed_passed, total)
    return {
        "n": total,
        "bar": bar,
        "routed_passed": routed_passed,
        "routed_rate": round(routed_rate, 4),
        "wilson95": [round(lo, 4), round(hi, 4)],
        "per_task": per_task,
    }

# #EXT-033-REQ-1 End


# #EXT-033-REQ-1 Start (eval_single)
def eval_single(
    n: int,
    bar: str,
    model: str,
    *,
    registry: Optional[Any] = None,
    solve_fn: Optional[Callable] = None,
    _tasks=None,
) -> dict:
    """Baseline: solve all n tasks with ONE fixed model.

    Parameters
    ----------
    n : int
        Number of tasks.
    bar : str
        Benchmark: "humaneval" or "mbpp".
    model : str
        Model id of the single model to use (e.g. "gemma-4-e2b").
    registry : ModelRegistry | None
        Unused by the default live solve_fn (which calls solve_gated directly);
        available for future adaptation-aware single-model baselines.
    solve_fn : callable | None
        Override: ``solve_fn(task) -> str``.
        When None, uses ``harness.pass1_eval.solve_gated`` (Gemma's honest gated
        baseline: self-gated thinking, temp=0, deterministic, requires Jetson).
        Injected for offline tests.
    _tasks : list | None
        Injectable task list for offline tests.

    Returns
    -------
    dict ::

        {
          "n":         int,
          "bar":       str,
          "model":     str,
          "passed":    int,
          "pass_rate": float,
          "wilson95":  [float, float],
          "per_task":  [{"task_id": str, "model": str, "passed": bool}, ...],
        }
    """
    if solve_fn is not None:
        _solve: Callable = solve_fn
    else:
        # Default live path: gemma's honest gated solve (temp=0, self-gated thinking).
        from harness.pass1_eval import solve_gated  # noqa: PLC0415
        _solve = solve_gated

    tasks = _tasks if _tasks is not None else _load_tasks(bar, n)
    per_task: list[dict] = []
    passed = 0

    for t in tasks:
        code: str = _solve(t)
        ok: bool = _score_task(t, code)
        passed += int(ok)
        per_task.append({"task_id": t.id, "model": model, "passed": ok})
        status = "PASS" if ok else "fail"
        print(f"  [{status}] {t.id}  model={model}", flush=True)

    total = len(tasks)
    pass_rate = passed / total if total else 0.0
    lo, hi = _wilson95(passed, total)
    return {
        "n": total,
        "bar": bar,
        "model": model,
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "wilson95": [round(lo, 4), round(hi, 4)],
        "per_task": per_task,
    }

# #EXT-033-REQ-1 End (eval_single)


# #EXT-033-REQ-1 Start (compare)
def compare_routed_vs_single(
    n: int,
    bar: str,
    *,
    registry: Optional[Any] = None,
    single_model: Optional[str] = None,
    route_fn: Optional[Callable] = None,
    routed_solve_fn: Optional[Callable] = None,
    single_solve_fn: Optional[Callable] = None,
    _tasks=None,
) -> dict:
    """Compare routed multi-model vs single-model baseline with honest Wilson95 CI.

    Runs both ``eval_routed`` and ``eval_single`` on THE SAME n tasks, then prints:
      1. A summary comparison table (routed vs single, delta, CI, lift?).
      2. A per-task routing table (shows WHICH model each task was routed to).

    HONEST CI RULE (mirrors EXT-031):
      "lift?" = "yes (CI separates)" ONLY when the delta falls OUTSIDE the overlap
      of both Wilson95 intervals. Within-CI = "no (CI overlap)" — a valid, honest,
      reportable outcome. Small n -> wide CIs; stated explicitly (Tenet 3).

    Parameters
    ----------
    n : int
        Number of tasks per approach (same list fed to both).
    bar : str
        Benchmark: "humaneval" or "mbpp".
    registry : ModelRegistry | None
        Model registry. Defaults to ``load_registry()`` (live). Inject for offline.
    single_model : str | None
        Model id for the baseline. Defaults to ``registry.default_model()`` (gemma).
    route_fn : callable | None
        Optional routing override for ``eval_routed``. Injected for offline tests.
    routed_solve_fn : callable | None
        Optional solve_fn for ``eval_routed``. Injected for offline tests.
        Signature: ``routed_solve_fn(task, decision) -> str``.
    single_solve_fn : callable | None
        Optional solve_fn for ``eval_single``. Injected for offline tests.
        Signature: ``single_solve_fn(task) -> str``.
    _tasks : list | None
        Injectable task list. Avoids disk loading. Same list fed to both evals.

    Returns
    -------
    dict ::

        {
          "bar":             str,
          "n":               int,
          "routed":          dict,     # full eval_routed result
          "single":          dict,     # full eval_single result
          "delta":           float,    # routed_rate - single_rate
          "significant_lift": bool,    # True only when delta outside CI overlap
          "lift_tag":        str,      # "yes (CI separates)" | "no (CI overlap)" | "NEGATIVE (CI separates)"
          "per_task_routing": [        # per-task routing summary (routing demonstration)
            {"task_id": str, "routed_model": str, "problem_class": str},
            ...
          ],
        }

    Tenet guarantees
    ----------------
    - Tenet 3: "no (CI overlap)" is NEVER hidden — small-n uncertainty printed
      explicitly. A negative result IS a valid honest outcome.
    """
    from harness.model_registry import load_registry  # noqa: PLC0415

    if registry is None:
        registry = load_registry()

    _single_model: str = (
        single_model if single_model is not None else registry.default_model()
    )
    tasks = _tasks if _tasks is not None else _load_tasks(bar, n)
    actual_n = len(tasks)

    print(f"\n>>> EXT-033 routed-eval capstone  bar={bar}  n={actual_n}", flush=True)
    print(">>> HONEST: CI overlap = no significant lift (valid, reportable outcome)",
          flush=True)
    print(f">>> Baseline: single-model={_single_model!r}", flush=True)

    # -- Single-model baseline (all tasks solved by one model) ----------------
    print(f"\n  Running single-model baseline: {_single_model}  n={actual_n}", flush=True)
    single_result = eval_single(
        actual_n, bar, _single_model,
        registry=registry,
        solve_fn=single_solve_fn,
        _tasks=tasks,
    )

    # -- Routed multi-model system (each task routed to its best model) --------
    print(f"\n  Running routed multi-model system  n={actual_n}", flush=True)
    routed_result = eval_routed(
        actual_n, bar, registry,
        route_fn=route_fn,
        solve_fn=routed_solve_fn,
        _tasks=tasks,
    )

    # -- Delta + CI -----------------------------------------------------------
    s_rate = single_result["pass_rate"]
    s_lo, s_hi = single_result["wilson95"]
    r_rate = routed_result["routed_rate"]
    r_lo, r_hi = routed_result["wilson95"]
    delta = round(r_rate - s_rate, 4)

    overlap = _ci_overlap(s_lo, s_hi, r_lo, r_hi)
    is_significant = (not overlap) and (delta != 0)
    sig_lift = is_significant and delta > 0

    if sig_lift:
        lift_tag = "yes (CI separates)"
    elif is_significant and delta < 0:
        lift_tag = "NEGATIVE (CI separates)"
    else:
        lift_tag = "no (CI overlap)"

    # -- Summary comparison table ---------------------------------------------
    print(f"\n{'=' * 76}", flush=True)
    print(
        f"  {'approach':<34}  {'pass_rate':>9}  {'wilson95':>20}  {'delta':>8}  lift?",
        flush=True,
    )
    print(f"  {'-' * 34}  {'-' * 9}  {'-' * 20}  {'-' * 8}  -----", flush=True)
    s_label = f"single-{_single_model} (baseline)"
    s_ci_str = f"[{s_lo:.3f}, {s_hi:.3f}]"
    r_ci_str = f"[{r_lo:.3f}, {r_hi:.3f}]"
    print(
        f"  {s_label:<34}  {s_rate:>9.3f}  {s_ci_str:>20}  {'---':>8}  ---",
        flush=True,
    )
    print(
        f"  {'routed':<34}  {r_rate:>9.3f}  {r_ci_str:>20}  {delta:>+8.3f}  {lift_tag}",
        flush=True,
    )
    print(f"\n{'=' * 76}", flush=True)
    print(f">>> n={actual_n} tasks — Wilson95 CI; narrow CI needs n>=30.", flush=True)
    print(">>> 'no (CI overlap)' IS a valid honest result (prior: retrieval was -5%).",
          flush=True)
    print(f"{'=' * 76}", flush=True)

    # -- Per-task routing table (shows routing actually happening) -------------
    print(f"\n  Per-task routing (routed system):", flush=True)
    print(
        f"  {'task_id':<26}  {'routed_to':<28}  {'class':<24}  passed",
        flush=True,
    )
    print(f"  {'-' * 26}  {'-' * 28}  {'-' * 24}  ------", flush=True)
    for pt in routed_result["per_task"]:
        status = "PASS" if pt["passed"] else "fail"
        print(
            f"  {pt['task_id']:<26}  {pt['routed_model']:<28}  "
            f"{pt['problem_class']:<24}  {status}",
            flush=True,
        )
    print(flush=True)

    per_task_routing = [
        {
            "task_id": pt["task_id"],
            "routed_model": pt["routed_model"],
            "problem_class": pt["problem_class"],
        }
        for pt in routed_result["per_task"]
    ]

    return {
        "bar": bar,
        "n": actual_n,
        "routed": routed_result,
        "single": single_result,
        "delta": delta,
        "significant_lift": sig_lift,
        "lift_tag": lift_tag,
        "per_task_routing": per_task_routing,
    }

# #EXT-033-REQ-1 End (compare)


# ---------------------------------------------------------------------------
# #EXT-033-REQ-2 Start
# Active-hours __main__ entry point (deferred; operator-invoked live run)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from harness.model_registry import load_registry  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description=(
            "EXT-033: Routed-eval capstone — system-level multi-model lift.\n\n"
            "Validates the PRIME-001 multi-model claim: routing each problem to\n"
            "its measured-best model beats running everything on the default model.\n\n"
            "ACTIVE-HOURS RUN (Jetson must be running; both gemma + qwen loaded):\n"
            "  python -m harness.eval_routed --n 20 --bar humaneval\n\n"
            "ROUTING EXPECTATION:\n"
            "  HumanEval tasks have '>>>' in docstrings -> standalone-fn-gen class\n"
            "  standalone-fn-gen -> qwen2.5-coder-3b (92% HumanEval measured)\n"
            "  Single-gemma baseline: gemma-4-e2b (82% HumanEval measured)\n"
            "  Expected lift: ~+10 pp. Note: n=20 gives wide CIs; n>=30 for separation.\n\n"
            "RESTORE GEMMA AFTER:\n"
            "  python -m harness.model_rewire gemma-4-e2b\n"
            "  (or: ssh jetson 'sudo systemctl restart gemma.service')\n\n"
            "NOTE: qwen3-4b-thinking escalation is a SEPARATE path (EXT-021 REQ-6).\n"
            "This capstone focuses on tractable gemma vs qwen synthesis routing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--n", type=int, default=20,
        help="Number of tasks per approach (default: 20; use >=30 for CI separation)",
    )
    parser.add_argument(
        "--bar", default="humaneval", choices=["humaneval", "mbpp"],
        help="Benchmark to evaluate (default: humaneval)",
    )
    parser.add_argument(
        "--single-model", default=None,
        help="Single-model baseline id (default: registry default = gemma-4-e2b)",
    )
    args = parser.parse_args()

    _registry = load_registry()
    compare_routed_vs_single(
        args.n, args.bar,
        registry=_registry,
        single_model=args.single_model,
    )

# #EXT-033-REQ-2 End
