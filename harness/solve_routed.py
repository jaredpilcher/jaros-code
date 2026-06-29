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
    registry: Optional[Any] = None,
) -> dict:
    """Adaptation-aware adapter: dispatch to the active model's code-gen then solve.

    This is the DEFAULT solve path when no ``solve_fn`` is injected into
    ``solve_routed``.  When *registry* is supplied (by ``solve_routed``'s closure),
    the routed model's adaptation is resolved and its code-gen callable is used
    as the code-generation step:

    - ``qwen-instruct-direct``  →  ``harness.qwen_adapt.qwen_code``
    - ``gherkin-decompose``     →  ``g_gherkin`` + ``g_code`` wrapper (Gemma)
    - unknown / missing label   →  DEFAULT fallback to ``gherkin-decompose``

    When no *registry* is available (or the model_id is not found in the registry),
    the function falls back to the legacy ``behavioral_solve`` path — keeping
    backward compatibility for all existing call sites.

    Adaptation path (registry provided and profile found)
    -----------------------------------------------------
    Required problem keys : intent, name
    Optional problem keys : context, run_tests, max_fix

    Legacy fallback path (no registry / profile)
    --------------------------------------------
    Required problem keys : intent, name, run_tests
    Optional problem keys : current_src, context, pkg, max_fix

    Raises ``KeyError`` with a descriptive message if required keys are missing.
    """
    # #EXT-021-REQ-3 Start
    p: dict = problem if isinstance(problem, dict) else (
        vars(problem) if hasattr(problem, "__dict__") else {}
    )

    # -- Adaptation-aware dispatch ------------------------------------------
    # Resolve the routed model's profile and look up its code-gen callable.
    # ``registry`` is injected by solve_routed / solve_routed_escalating as a
    # closure so the adaptation fires automatically for every non-injected solve.
    _code_gen = None
    if registry is not None:
        _model_id: str = decision.get("model_id", "")
        _profile = registry.lookup_by_id(_model_id)
        if _profile is not None:
            from harness.adaptation import code_gen_for  # noqa: PLC0415
            _code_gen = code_gen_for(_profile.adaptation)

    if _code_gen is not None:
        # Adaptation path: call the model's code-gen, then optionally run tests.
        _adapt_required = ("intent", "name")
        _adapt_missing = [k for k in _adapt_required if k not in p]
        if _adapt_missing:
            raise KeyError(
                f"Default solve_fn (adaptation path) requires problem dict keys: "
                f"{_adapt_required}; missing: {_adapt_missing}.  "
                "Inject a custom solve_fn or include these fields in the problem dict."
            )
        intent: str = p["intent"]
        name: str = p["name"]
        context: str = p.get("context", "")
        run_tests = p.get("run_tests")   # optional for the adaptation path
        max_fix: int = p.get("max_fix", 2)

        code: str = _code_gen(intent, name, context)
        self_pass = False
        if run_tests is not None and code:
            for _attempt in range(max_fix + 1):
                self_pass, _fb = run_tests(code, "")
                if self_pass:
                    break
                if _attempt < max_fix:
                    # Re-generate; code_gen owns the feedback channel (e.g. qwen
                    # keeps temperature=0 so additional calls are deterministic).
                    code = _code_gen(intent, name, context)
        return {"code": code, "self_pass": self_pass}
    # #EXT-021-REQ-3 End

    # -- Legacy fallback: no adaptation info → behavioral_solve ---------------
    # Late import: avoids pulling in the full behavioral_solve dependency chain
    # when solve_routed is used with an injected solve_fn (e.g. in tests).
    from harness.behavioral_solve import behavioral_solve  # noqa: PLC0415

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
    if solve_fn is not None:
        _solve: Callable = solve_fn
    else:
        # Capture registry in a closure so _default_solve_fn can resolve the
        # active model's adaptation without changing the (problem, decision,
        # rewire_result) call signature used throughout the rest of the pipeline.
        _reg = registry
        def _solve(problem, decision, rewire_result):  # type: ignore[misc]
            return _default_solve_fn(problem, decision, rewire_result, registry=_reg)

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

# #EXT-021-REQ-6 Start

def solve_routed_escalating(
    problem: Any,
    registry: Optional[Any] = None,
    *,
    route_fn: Optional[Callable] = None,
    rewire_fn: Optional[Callable] = None,
    solve_fn: Optional[Callable] = None,
    test_fn: Optional[Callable] = None,
    tally: Optional[Any] = None,
    max_models: int = 3,
    record: bool = True,
    label_path: "Optional[Any]" = None,
) -> dict:
    """Route and escalate through ranked-tally candidates; test_fn picks the winner.

    REQ-6: the deterministic ``test_fn`` is the SOLE judge between candidate
    model outputs — no model ranks or picks between outputs (model-as-judge
    forbidden, REQ-2 / REQ-6).  Escalation stays entirely on LOCAL
    Jetson-fitting models; cloud/paid is never a tier (Tenet 2).  All failure
    paths are surfaced honestly (Tenet 3).

    Parameters
    ----------
    problem :
        A dict (or object with ``__dict__``) describing the coding task.
    registry :
        A ``ModelRegistry`` instance.  Defaults to ``load_registry()``.
    route_fn :
        Optional replacement for ``route(problem, registry) -> dict``.
        Injected in tests for deterministic offline routing.
    rewire_fn :
        Optional replacement for ``rewire(model_id, registry) -> dict``.
        Injected in tests to avoid Jetson SSH/HTTP calls.
    solve_fn :
        Optional replacement for the inner solve.  Signature::

            solve_fn(problem, decision, rewire_result) -> dict

        Defaults to ``_default_solve_fn``.
    test_fn :
        Callable ``(problem, solve_result) -> dict`` that runs the
        given/visible test (the task's own failing test or docstring examples)
        and returns at least ``{"passed": bool}``.  This is the DETERMINISTIC
        GATE — never a model.  Required for meaningful escalation; callers
        should always inject a real test_fn.  The default always returns
        ``passed=False`` (honest: without a test we cannot pick a winner).
    tally :
        Optional pre-built ``CoverageTally`` for offline injection in tests.
        When ``None``, built on-the-fly from *registry*.
    max_models :
        Maximum number of candidate models to try (escalation budget).
        Default 3.  Models beyond this cap are never tried (Tenet 2 /
        cost-safety).
    record :
        When ``True`` (default), each test-gated outcome is appended to the
        label store via ``label_store.record_outcome`` (best-effort, never
        raises).  Pass ``False`` in tests that want isolation from the store,
        or inject a *label_path* pointing at a temp file instead.
    label_path :
        Override the label store path for ``record_outcome``.  ``None`` uses
        the default ``.jaros-data/artifacts/solve_labels.jsonl`` path.
        Inject a ``tmp_path``-based path in tests to avoid polluting the
        real runtime store.

    Returns
    -------
    dict
        ``{decision, winner_model_id, attempts, solve, test_gated, ok, error}``

        - ``decision``        -- the inert routing Decision dict
        - ``winner_model_id`` -- model id of the passing candidate, or ``None``
        - ``attempts``        -- ``[{model, rewire_ok, passed, ...}, ...]``
        - ``solve``           -- winning solve result, or last attempt on
                                 all-fail (``None`` if every solve raised)
        - ``test_gated``      -- always ``True`` (REQ-6 contract)
        - ``ok``              -- ``True`` only when a candidate passed the test
        - ``error``           -- ``None`` on success; honest message on all-fail

    Escalation rules (REQ-6)
    ------------------------
    1. ``ranked_models_for(problem_class)`` is the escalation ORDER — best
       tally score first, then roster order, then deterministic tiebreak.
    2. Empty tally -> single-candidate fallback to the registry default model.
    3. Budget capped at *max_models*; models beyond the budget are NEVER tried.
    4. First candidate whose output passes ``test_fn`` is the winner; returned
       immediately — remaining candidates are NOT tried (early-exit efficiency).
    5. If NO candidate passes within budget, returns honest
       ``"no candidate passed the test within budget"`` status (Tenet 3).
    6. ALL candidates are LOCAL Jetson-fitting (the tally only records local
       models; cloud/paid has no tally entry — Tenet 2 guarantee).

    Tenet guarantees
    ----------------
    - **Tenet 1**: route_fn is inert; rewire_fn is the clerk.
    - **Tenet 2**: escalation is bounded to LOCAL models only; cloud/paid is
      never a tier — the tally invariant enforces this.
    - **Tenet 3**: all failure paths are surfaced explicitly; "no candidate
      passed" is never silently hidden.
    - **Model-as-judge forbidden**: ``test_fn`` is the SOLE arbiter; no model
      is called to compare or rank outputs between candidates (REQ-6 / REQ-2).
    """
    # 1. Registry default -------------------------------------------------------
    if registry is None:
        registry = load_registry()

    # 2. Resolve injectable callables -------------------------------------------
    _route: Callable = route_fn if route_fn is not None else route
    _rewire: Callable = rewire_fn if rewire_fn is not None else rewire
    if solve_fn is not None:
        _solve: Callable = solve_fn
    else:
        # Same registry-capturing closure as solve_routed: adaptation fires
        # automatically for every non-injected solve across the escalation loop.
        _reg_esc = registry
        def _solve(problem, decision, rewire_result):  # type: ignore[misc]
            return _default_solve_fn(problem, decision, rewire_result, registry=_reg_esc)
    # test_fn must be provided for real use; default is honest pass=False
    _test: Callable = test_fn if test_fn is not None else (
        lambda _prob, _sol: {"passed": False, "reason": "no test_fn provided"}
    )

    # 3. Route: produce an INERT Decision (Tenet 1 -- no side effects here) -----
    decision: dict = _route(problem, registry)
    problem_class: str = decision.get("problem_class", "")

    # 4. Tally: build from registry on demand; injectable for offline tests ------
    _active_tally = tally
    if _active_tally is None:
        from harness.model_tally import CoverageTally  # lazy: avoid circ-import
        _active_tally = CoverageTally(registry)

    # 5. Escalation order: best-measured-first candidates for this class --------
    #    Empty tally -> single-candidate fallback to the registry default.
    #    ALL candidates are LOCAL/Jetson-fitting (tally invariant, Tenet 2).
    candidates: list[str] = _active_tally.ranked_models_for(problem_class)
    if not candidates:
        candidates = [registry.default_model()]

    # Budget cap: never exceed max_models attempts (Tenet 2 / cost-safety)
    candidates = candidates[:max_models]

    # 6. Escalation loop --------------------------------------------------------
    #    test_fn is the SOLE judge; no model is ever asked to rank outputs.
    attempts: list[dict] = []
    last_solve_result: Optional[dict] = None

    for model_id in candidates:
        # 6a. Rewire to this candidate (deterministic clerk, guarded)
        rewire_result: dict = _rewire(model_id, registry)
        if not rewire_result.get("ok"):
            attempts.append({
                "model": model_id,
                "rewire_ok": False,
                "passed": False,
                "error": rewire_result.get("error", "rewire failed"),
            })
            continue  # escalate to next candidate (not a model limit — harness gap)

        # 6b. Derive candidate-scoped decision.
        #     Inherits class/confidence/rationale from the router Decision;
        #     overrides model_id so the solve_fn sees the correct active model.
        candidate_decision: dict = {**decision, "model_id": model_id}

        # 6c. Solve under this candidate's adaptation
        try:
            solve_result: dict = _solve(problem, candidate_decision, rewire_result)
        except Exception as exc:
            attempts.append({
                "model": model_id,
                "rewire_ok": True,
                "passed": False,
                "error": f"solve_fn raised: {exc}",
            })
            continue  # escalate

        last_solve_result = solve_result

        # 6d. DETERMINISTIC TEST GATE — test_fn picks the winner.
        #     NO model is consulted here; model-as-judge is forbidden (REQ-6).
        try:
            test_result: dict = _test(problem, solve_result)
        except Exception as exc:
            test_result = {"passed": False, "error": f"test_fn raised: {exc}"}

        passed: bool = bool(test_result.get("passed", False))

        # #EXT-021-REQ-7 Start
        # Label recording: every test-gated outcome is a free (problem, model,
        # pass/fail) label that drives class evolution (SPLIT + VALIDATE).
        # Best-effort only — record_outcome never raises (Tenet 1).
        if record:
            from harness.label_store import record_outcome  # lazy; avoids circ-import
            record_outcome(
                problem,
                model_id,
                problem_class,
                passed,
                path=label_path,
            )
        # #EXT-021-REQ-7 End

        attempts.append({
            "model": model_id,
            "rewire_ok": True,
            "passed": passed,
            "test_result": test_result,
        })

        if passed:
            # Winner found — return immediately; remaining candidates NOT tried
            return {
                "decision": decision,
                "winner_model_id": model_id,
                "attempts": attempts,
                "solve": solve_result,
                "test_gated": True,
                "ok": True,
                "error": None,
            }
        # passed=False -> escalate to next candidate

    # 7. No candidate passed within budget — honest failure status (Tenet 3) ----
    return {
        "decision": decision,
        "winner_model_id": None,
        "attempts": attempts,
        "solve": last_solve_result,
        "test_gated": True,
        "ok": False,
        "error": "no candidate passed the test within budget",
    }

# #EXT-021-REQ-6 End
