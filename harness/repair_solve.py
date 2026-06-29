"""EXT-032: Test-feedback repair scaffold.

repair_solve() is a bounded test-feedback repair loop designed for slow, strong
reasoning models (e.g. qwen3-4b-thinking).  The core insight: seeing the ACTUAL
test failure output — information the model cannot get by pure thinking alone —
helps it crack hard tasks it failed single-shot.  Bounded to max_retries=2 (cost
guard for slow models at ~10 tok/s + long <think> traces).

HONESTY: the repair loop sees only the VISIBLE failing test's output (the spec the
developer is given).  test_fn is the SOLE arbiter; gen_fn never sees the oracle's
pass/fail directly — only via the deterministic failure_text that test_fn returns
from the visible test.  Tenet 3 preserved.

Cell #35: scaffold x strong base x right class.
The cheapest multi-call scaffold for a slow reasoner:
    attempt -> run visible failing test -> on fail, re-solve given real traceback
    -> retest.  1-2 retries (cost bound).

Ref: EXT-031 MEASURED RESULT #2 — the #36 reframe: "a scaffold multiplies WITHIN
its class."  The one promising untested cell is scaffold x qwen3-4b-thinking x
hard-repo-repair class.  This module is that scaffold.
"""
from __future__ import annotations

# #EXT-032-REQ-1 Start


def repair_solve(
    spec: str,
    name: str,
    context: str,
    *,
    gen_fn,
    test_fn,
    max_retries: int = 2,
) -> dict:
    """Bounded test-feedback repair loop.

    Parameters
    ----------
    spec : str
        The visible task spec / commit intent shown to gen_fn.
    name : str
        The Python function name to implement.
    context : str
        Context block (current source, failing test, module context).  The original
        context is preserved; each retry augments it with the failure text and the
        previous code attempt so the model always has full repair context.
    gen_fn : callable(spec, name, context) -> str
        Code generator.  Called with augmented context on each retry.  Signature
        matches ``r1_code(task_or_spec, name, context)`` from harness.r1_adapt.
    test_fn : callable(code: str) -> dict
        Visible-test runner.  Returns ``{"passed": bool, "failure_text": str}``.
        **test_fn is the SOLE arbiter** — gen_fn only observes failure_text, never
        the oracle's raw pass/fail signal.  Tenet 3: never leak the oracle result
        into the generation loop.
    max_retries : int
        Maximum repair iterations after the initial attempt (default 2 ->
        at most 3 total LLM calls).  Hard bound on cost for slow reasoners.

    Returns
    -------
    dict
        ``{"solved": bool, "code": str, "retries": int, "attempts": list[str]}``.
        ``retries`` is the number of repair iterations used (0 = first attempt
        passed).  ``attempts`` lists every generated code string in order.
    """
    attempts: list[str] = []

    # --- Initial attempt ---
    attempt = gen_fn(spec, name, context)
    attempts.append(attempt)
    result = test_fn(attempt)
    if result["passed"]:
        return {"solved": True, "code": attempt, "retries": 0, "attempts": attempts}

    # --- Repair loop (bounded by max_retries) ---
    for retry in range(max_retries):
        failure_text = result.get("failure_text", "")
        # Augment the ORIGINAL context with the most-recent failure info.
        # Using the original context (not accumulated) avoids unbounded context
        # blowup across retries while still giving the model the full task spec.
        repair_context = (
            context
            + f"\n\nYour previous attempt:\n{attempt}\n"
            + f"The test FAILED with:\n{failure_text}\nFix it."
        )
        attempt = gen_fn(spec, name, repair_context)
        attempts.append(attempt)
        result = test_fn(attempt)
        if result["passed"]:
            return {
                "solved": True,
                "code": attempt,
                "retries": retry + 1,
                "attempts": attempts,
            }

    return {
        "solved": False,
        "code": attempt,
        "retries": max_retries,
        "attempts": attempts,
    }


# #EXT-032-REQ-1 End


# #EXT-032-REQ-2 Start


def make_r1_gen_fn():
    """Return r1_code from harness.r1_adapt as a gen_fn for repair_solve.

    ``r1_code`` already has the signature ``(task_or_spec, name, context) -> str``
    which matches repair_solve's gen_fn contract exactly.  The import is deferred
    so this module is importable offline without a live Jetson.

    The returned callable handles qwen3-4b-thinking's ``<think>...</think>``
    reasoning traces, extracts the LAST fenced code block, and applies the
    proven parse-gated indentation-repair layer.

    Usage::

        gen_fn = make_r1_gen_fn()
        result = repair_solve(spec, name, ctx, gen_fn=gen_fn, test_fn=my_test_fn)
    """
    from harness.r1_adapt import r1_code  # deferred: no Jetson needed at import
    return r1_code


# #EXT-032-REQ-2 End
