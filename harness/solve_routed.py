"""End-to-end route -> rewire -> solve entry point (EXT-021, REQ-2/REQ-3/REQ-4).

``solve_routed`` is the public entry point that wires the full multi-model routing
loop: route (inert Decision) -> rewire (deterministic clerk) -> solve (existing
behavioral/orchestrator solve, now activated under the chosen model's adaptation).

PLACEMENT RATIONALE
-------------------
``solve_routed`` lives in a dedicated ``harness/solve_routed.py`` rather than
extending ``harness/model_router.py`` because:

1. It is a higher-level orchestration entry that COMPOSES ``model_router``,
   ``model_rewire``, and ``model_registry`` — keeping them in separate files avoids
   circular imports and preserves each component at a single level of abstraction.
2. ``model_router`` is a pure reasoning-plane module (Tenet 1: no side effects).
   Adding rewire calls to it would violate that constraint.

NOTE — STUB 2-PROFILE REGISTRY IN TESTS
-----------------------------------------
A real second model is not yet profiled (only gemma-4-e2b has measured held-out
evidence from TASK-1/TASK-4).  The end-to-end two-class / two-model demonstration
in ``tests/test_solve_routed.py`` therefore uses a STUB 2-profile registry — that is
CORRECT and SUFFICIENT for TASK-5.  The real second-model profiling run will happen
after the profiler (harness/model_profiler.py) serves and profiles a candidate from
the roster (design.md APPENDIX), then writes its measured class evidence to a profile
JSON under .jaros-data/config/models/.

PUBLIC API
----------
::

    result = solve_routed(
        problem,
        registry=None,
        *,
        route_fn=None,
        rewire_fn=None,
        solve_fn=None,
    )
    # Returns:
    # {
    #     "decision": {...},         # inert routing Decision
    #     "rewire":   {...},         # rewire result record
    #     "solve":    {...} | None,  # solve result (None on rewire / solve failure)
    #     "ok":       bool,
    #     "error":    str | None,
    # }

All three inner callables are INJECTABLE so the whole path is OFFLINE-testable.
"""
from __future__ import annotations

# #EXT-021-REQ-2 Start
# #EXT-021-REQ-3 Start
# #EXT-021-REQ-4 Start
from typing import Any, Callable, Optional

from harness.model_registry import load_registry
from harness.model_router import route
from harness.model_rewire import rewire


# ---------------------------------------------------------------------------
# Default solve adapter — thin bridge to the existing behavioral solve
# ---------------------------------------------------------------------------

def _default_solve_fn(
    problem: Any,
    decision: dict,
    rewire_result: dict,
) -> dict:
    """Thin adapter: extract problem fields and call ``behavioral_solve``.

    This is the DEFAULT solve path when no ``solve_fn`` is injected into
    ``solve_routed``.  It maps the generic ``problem`` dict / object to the
    ``behavioral_solve`` signature.

    Required problem keys
    ---------------------
    intent    : str      — the change to make (commit message / user request)
    name      : str      — the function to write/repair
    run_tests : callable — env adapter ``(code, test_code) -> (passed, feedback)``

    Optional
    --------
    current_src : str | None — existing source (None if new function)
    context     : str        — module preamble (imports/sentinels)
    pkg         : str        — import package for self-tests
    max_fix     : int        — fix iterations (default 2)

    Raises ``KeyError`` with a descriptive message if required keys are missing.
    """
    # Late import: avoids pulling in the full behavioral_solve dependency chain
    # when solve_routed is used with an injected solve_fn (e.g. in tests).
    from harness.behavioral_solve import behavioral_solve  # noqa: PLC0415

    p: dict = problem if isinstance(problem, dict) else (
        vars(problem) if hasattr(problem, "__dict__") else {}
    )

    _required = ("intent", "name", "run_tests")
    _missing = [k for k in _required if k not in p]
    if _missing:
        raise KeyError(
            f"Default solve_fn requires problem dict keys: {_required}; "
            f"missing: {_missing}.  "
            "Inject a custom solve_fn or include these fields in the problem dict."
        )

    return behavioral_solve(
        intent=p["intent"],
        name=p["name"],
        current_src=p.get("current_src"),
        context=p.get("context", ""),
        pkg=p.get("pkg", ""),
        run_tests=p["run_tests"],
        max_fix=p.get("max_fix", 2),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def solve_routed(
    problem: Any,
    registry: Optional[Any] = None,
    *,
    route_fn: Optional[Callable] = None,
    rewire_fn: Optional[Callable] = None,
    solve_fn: Optional[Callable] = None,
) -> dict:
    """Route, rewire, and solve *problem* using the best-matching registered model.

    Parameters
    ----------
    problem :
        A dict (or object with ``__dict__``) describing the coding task.
        Recognised routing keys: ``source``/``prompt``/``text``, ``has_examples``,
        ``is_repo_task``/``repo_root``/``repo_path``, ``is_multi_file``, ``files``,
        ``task_type``.  Solve keys depend on the active ``solve_fn``.
    registry :
        A ``ModelRegistry`` instance.  Defaults to ``load_registry()`` (loads from
        ``.jaros-data/config/models/``).
    route_fn :
        Optional replacement for ``route(problem, registry) -> dict``.  Injected
        in tests to control routing without a live model.  Defaults to ``route``.
    rewire_fn :
        Optional replacement for ``rewire(model_id, registry) -> dict``.  Injected
        in tests to avoid Jetson SSH calls.  Defaults to ``rewire``.
    solve_fn :
        Optional replacement for the inner solve.  Signature::

            solve_fn(problem, decision, rewire_result) -> dict

        Defaults to ``_default_solve_fn`` (thin adapter to ``behavioral_solve``).

    Returns
    -------
    dict
        ``{decision, rewire, solve, ok, error}``

        The full path is inspectable:
        - ``decision`` -- the inert routing Decision dict
        - ``rewire``   -- the rewire result record
        - ``solve``    -- the solve result (any shape), or ``None`` on failure
        - ``ok``       -- ``False`` if rewire failed or solve raised
        - ``error``    -- honest error string, or ``None`` on success (Tenet 3)

    Tenet guarantees
    ----------------
    - **Tenet 1**: ``route_fn`` is inert (no side effects); rewire is the clerk.
    - **Tenet 2**: rewire is scoped to the known Jetson; never off-device.
    - **Tenet 3**: a rewire failure short-circuits HONESTLY -- ``solve_fn`` is
      NEVER called when the rewire failed (i.e. the wrong model would be active).
      Every failure path is surfaced in the return dict; none are hidden.
    - **Inspectability**: the full route -> rewire -> solve path is recorded in the
      return dict (native Jaros spirit: inert Decision -> clerk -> logged).
    """
    # 1. Registry: default to the real registry if not provided ---------------
    if registry is None:
        registry = load_registry()

    # 2. Resolve injectable callables -----------------------------------------
    _route: Callable = route_fn if route_fn is not None else route
    _rewire: Callable = rewire_fn if rewire_fn is not None else rewire
    _solve: Callable = solve_fn if solve_fn is not None else _default_solve_fn

    # 3. Route: produce an INERT Decision (Tenet 1 -- no side effects here) ---
    decision: dict = _route(problem, registry)

    # 4. Rewire: the clerk that acts on the Decision (deterministic, guarded) --
    rewire_result: dict = _rewire(decision["model_id"], registry)

    # 5. Honesty gate (Tenet 3): NEVER solve on a failed / wrong rewire -------
    #    The rewire failed means we cannot guarantee the correct model is active;
    #    solving now would produce a result on the wrong model -- forbidden.
    if not rewire_result.get("ok"):
        return {
            "decision": decision,
            "rewire": rewire_result,
            "solve": None,
            "ok": False,
            "error": (
                "solve_routed short-circuited: rewire failed -- "
                + str(rewire_result.get("error", "unknown rewire error"))
            ),
        }

    # 6. Solve with the active model's adaptation (solve_fn is the inner solve)-
    try:
        solve_result = _solve(problem, decision, rewire_result)
    except Exception as exc:
        return {
            "decision": decision,
            "rewire": rewire_result,
            "solve": None,
            "ok": False,
            "error": f"solve_fn raised: {exc}",
        }

    return {
        "decision": decision,
        "rewire": rewire_result,
        "solve": solve_result,
        "ok": True,
        "error": None,
    }
# #EXT-021-REQ-2 End
# #EXT-021-REQ-3 End
# #EXT-021-REQ-4 End
