"""Model-router judge for the multi-model routing harness (EXT-021, REQ-2).

``route(problem, registry) -> dict`` is the public entry point.

It returns an INERT decision dict::

    {
        "model_id":      "gemma-4-e2b",
        "problem_class": "standalone-fn-gen",
        "confidence":    0.9,
        "rationale":     "...",
    }

No side effects -- Tenet 1 requires the decision to be data only; the clerk
(model_rewire.rewire) acts on it later (TASK-3).

Classification strategy
-----------------------
1. Cheap DETERMINISTIC features are extracted first (no LLM, no network).
2. If the problem carries a Python failure signal (traceback / failing test),
   that signal is parsed deterministically and maps to a richer Python class
   prior (e.g. ``missing-method-or-attr``, ``logic-or-assertion``).  These
   are PRIORs -- the test gate (REQ-6) is the real judge; a mis-class merely
   costs one extra escalation attempt (self-correcting).  They accumulate in
   ``new_classes.jsonl`` for later profiling (REQ-7 DISCOVER).
3. When no failure signal is present, structural features determine the class
   (multi-file/repo > has-examples > single-file-repair).
4. The resolved class is mapped to a model via the registry tally; ties are
   broken by the default model, then roster order.
5. If no profile covers the class, the registry default is used and the
   rationale marks this as a HARNESS-GAP -- never a model limit (PRIME-001).

NOTE: The LLM-classification path has been removed (REQ-2 criterion closed,
TASK-27).  Classification is DETERMINISTIC end-to-end -- no model is ever
consulted to route or to choose between models (model-as-judge is forbidden
per the external-review correction).
"""
from __future__ import annotations

# #EXT-021-REQ-2 Start
import re
from typing import Any

# ---------------------------------------------------------------------------
# Known problem classes (aligned with registry class names)
# ---------------------------------------------------------------------------
_KNOWN_CLASSES: list[str] = [
    "standalone-fn-gen",   # standalone function / HumanEval-style
    "single-file-repair",  # repair or edit of a single existing file
    "multi-file-edit",     # edit spanning multiple files, no repo context
    "multi-step-repo",     # multi-step tasks rooted in a real repository
]

# Richer Python-error-derived classes (PRIORS; accumulate for later profiling)
# These are HYPOTHESES validated by the test gate (REQ-6).  Won't have tally
# coverage yet, so route() will default-fallback + record them as new/unhandled
# classes (REQ-7 DISCOVER) -- that is CORRECT; they accumulate for profiling.
_FAILURE_CLASSES: list[str] = [
    "missing-method-or-attr",   # AttributeError / 'has no attribute'
    "logic-or-assertion",       # AssertionError / ValueError
    "signature-or-type",        # TypeError on call/arg
    "missing-import",           # ImportError / ModuleNotFoundError
    "undefined-name",           # NameError
    "bounds-or-key",            # IndexError / KeyError
]

# Mapping: Python error_type -> richer problem class (deterministic prior)
_FAILURE_CLASS_MAP: dict[str, str] = {
    "AttributeError":       "missing-method-or-attr",
    "AssertionError":       "logic-or-assertion",
    "ValueError":           "logic-or-assertion",
    "TypeError":            "signature-or-type",
    "ImportError":          "missing-import",
    "ModuleNotFoundError":  "missing-import",
    "NameError":            "undefined-name",
    "IndexError":           "bounds-or-key",
    "KeyError":             "bounds-or-key",
}

# Confidence thresholds
_HIGH_CONFIDENCE: float = 0.9
_MED_CONFIDENCE: float = 0.65
_FALLBACK_CONFIDENCE: float = 0.2   # assigned when no profile covers the class


# ---------------------------------------------------------------------------
# Feature extraction (purely deterministic)
# ---------------------------------------------------------------------------

def _to_dict(problem: Any) -> dict:
    """Normalise *problem* to a plain dict.  Never raises."""
    if isinstance(problem, dict):
        return problem
    try:
        return vars(problem)
    except TypeError:
        return {}


def _extract_features(problem: dict) -> dict[str, Any]:
    """Extract cheap, deterministic classification features.

    Accepts a normalised problem dict.  All field lookups are defensive;
    missing or wrong-typed fields produce safe defaults.

    Recognised keys
    ---------------
    source / prompt / text : str
        The code or task description.
    has_examples : bool
        Explicit flag (overrides heuristic).  If absent, heuristic checks
        for ``>>>`` in *source* (docstring-example style).
    is_repo_task : bool
        Explicit flag.  If absent, presence of ``repo_root``, ``repo_path``,
        or ``task_type == "repo"`` implies a repo task.
    is_multi_file : bool
        Explicit flag.  If absent, derived from ``files`` list length.
    files : list or dict
        Collection of file paths/dicts; length > 1 implies multi-file.
    task_type : str
        ``"repo"`` implies ``is_repo_task``.
    repo_root / repo_path : any
        Presence implies ``is_repo_task``.
    """
    source: str = str(
        problem.get("source", problem.get("prompt", problem.get("text", "")))
    )

    # -- has_examples --------------------------------------------------------
    has_examples_flag = problem.get("has_examples")
    if has_examples_flag is None:
        has_examples: bool = ">>>" in source
    else:
        has_examples = bool(has_examples_flag)

    # -- is_repo_task --------------------------------------------------------
    is_repo_flag = problem.get("is_repo_task")
    if is_repo_flag is None:
        is_repo_task: bool = bool(
            problem.get("repo_root")
            or problem.get("repo_path")
            or problem.get("task_type") == "repo"
        )
    else:
        is_repo_task = bool(is_repo_flag)

    # -- is_multi_file -------------------------------------------------------
    is_multi_flag = problem.get("is_multi_file")
    if is_multi_flag is None:
        files = problem.get("files", [])
        is_multi_file: bool = bool(
            (isinstance(files, (list, tuple)) and len(files) > 1)
            or (isinstance(files, dict) and len(files) > 1)
        )
    else:
        is_multi_file = bool(is_multi_flag)

    # -- fn_len (proxy for complexity) ---------------------------------------
    fn_len: int = len(source.splitlines()) if source else 0

    return {
        "has_examples": has_examples,
        "is_repo_task": is_repo_task,
        "is_multi_file": is_multi_file,
        "fn_len": fn_len,
        "source_len": len(source),
    }


# ---------------------------------------------------------------------------
# Python failure-signal parser (deterministic prior for richer classes)
# ---------------------------------------------------------------------------

def _failure_signal(problem: dict) -> dict[str, Any] | None:
    """Parse a Python failure signal from the problem dict.

    Checks several plausible fields for a failing test / traceback text,
    then deterministically extracts:

    * ``error_type`` -- e.g. ``AttributeError``, ``TypeError``, etc.
    * ``symbol``     -- the touched symbol or abbreviated error detail (optional).

    Returns ``None`` when no Python failure signal is found.

    These are DETERMINISTIC PRIORS that seed the richer class ontology.
    The test gate (REQ-6) is the real judge -- a mis-class merely costs
    one extra escalation attempt (self-correcting, by design).  The richer
    classes won't have tally coverage yet; route() records them as
    new/unhandled (REQ-7 DISCOVER) so the roster can be re-profiled.
    """
    # Collect candidate strings that may carry a traceback / error
    candidates: list[str] = []
    for key in ("traceback", "test_output", "error", "failing_test"):
        val = problem.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val)
    # context/task fields may embed a traceback inline
    for key in ("context", "task"):
        val = problem.get(key)
        if isinstance(val, str) and "Traceback" in val:
            candidates.append(val)

    if not candidates:
        return None

    text = "\n".join(candidates)

    # Check known error types (more-specific before aliases)
    _ORDERED_ERRORS: list[str] = [
        "ModuleNotFoundError",   # before ImportError (it is a subclass)
        "ImportError",
        "AttributeError",
        "TypeError",
        "AssertionError",
        "NameError",
        "IndexError",
        "KeyError",
        "ValueError",
    ]
    error_type: str | None = None
    for et in _ORDERED_ERRORS:
        if et in text:
            error_type = et
            break

    if error_type is None:
        return None

    # Try to extract the touched symbol for richer context
    symbol: str | None = None

    # "AttributeError: 'Foo' has no attribute 'bar'" -> symbol = 'bar'
    m = re.search(r"has no attribute '([^']+)'", text)
    if m:
        symbol = m.group(1)

    if symbol is None:
        # "NameError: name 'foo' is not defined" -> symbol = 'foo'
        m = re.search(r"name '([^']+)' is not defined", text)
        if m:
            symbol = m.group(1)

    if symbol is None:
        # Fall back to the error detail on the same line as the error type
        m = re.search(rf"{re.escape(error_type)}: (.{{0,80}})", text)
        if m:
            symbol = m.group(1).strip()

    result: dict[str, Any] = {"error_type": error_type}
    if symbol:
        result["symbol"] = symbol
    return result


# ---------------------------------------------------------------------------
# Classification (structural + failure-signal paths, both deterministic)
# ---------------------------------------------------------------------------

def _classify_deterministic(features: dict[str, Any]) -> tuple[str, float]:
    """Map extracted structural features to ``(problem_class, confidence)``.

    Priority: multi-file / repo tasks are harder and need a stronger model;
    docstring examples signal a standalone-fn-gen style; everything else leans
    toward single-file-repair at medium confidence.
    """
    is_multi = features["is_multi_file"]
    is_repo = features["is_repo_task"]
    has_ex = features["has_examples"]

    if is_multi or is_repo:
        return "multi-step-repo", _HIGH_CONFIDENCE

    if has_ex:
        return "standalone-fn-gen", _HIGH_CONFIDENCE

    # No strong distinguishing signal
    return "single-file-repair", _MED_CONFIDENCE


def _classify(problem_dict: dict, features: dict[str, Any]) -> tuple[str, float, str]:
    """Classify a problem to ``(problem_class, confidence, method)``.

    When the problem carries a Python failure signal (traceback / failing test),
    that signal maps to a richer class (deterministic PRIOR; REQ-7).  Otherwise
    the structural feature mapping is used.  ``method`` is a short label for
    the rationale (``"failure-signal"`` or ``"structural"``).

    The richer failure-signal classes are HYPOTHESES -- the test gate (REQ-6)
    validates predictiveness, and they accumulate in new_class_log for
    later roster re-profiling (REQ-7 DISCOVER).
    """
    signal = _failure_signal(problem_dict)
    if signal is not None:
        error_type = signal["error_type"]
        mapped_class = _FAILURE_CLASS_MAP.get(error_type)
        if mapped_class is not None:
            return mapped_class, _HIGH_CONFIDENCE, "failure-signal"

    problem_class, confidence = _classify_deterministic(features)
    return problem_class, confidence, "structural"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def route(
    problem: Any,
    registry: Any,
    *,
    tally: Any = None,
    record: bool = True,
) -> dict[str, Any]:
    """Classify *problem* and select the best-matching registry model.

    Parameters
    ----------
    problem:
        A dict (or object with ``__dict__``) describing the coding task.
        Recognised keys: ``source``/``prompt``/``text``, ``has_examples``,
        ``is_repo_task``/``repo_root``/``repo_path``, ``is_multi_file``,
        ``files``, ``task_type``, ``traceback``, ``test_output``, ``error``,
        ``failing_test``, ``context``, ``task``.
    registry:
        A ``ModelRegistry`` instance (``harness.model_registry``).
    tally:
        Optional ``CoverageTally`` (``harness.model_tally``).  When ``None``
        (the default), a tally is built on-the-fly from *registry*.  Inject
        a pre-built tally in tests for full offline isolation.  The tally is
        the sole mechanism for model selection (deterministic argmax -- no
        model-as-judge, REQ-5).
    record:
        When ``True`` (the default), a HARNESS-GAP result appends one record
        to the new-class log via ``harness.new_class_log.record_unhandled``.
        Set to ``False`` in unit tests to keep them side-effect-free.

    Returns
    -------
    dict
        Inert decision with keys ``model_id``, ``problem_class``,
        ``confidence`` (float 0.0-1.0), and ``rationale`` (str).

        Never raises.  Always returns a valid model_id (worst-case: the
        registry default).

    Tenet 1 note
        The routing decision itself has NO side effects.  When ``record=True``
        a HARNESS-GAP triggers a best-effort JSONL append (new_class_log);
        that append is the honest observation that a class is unhandled, and
        it never mutates routing state.  Pass ``record=False`` when callers
        need a fully pure read (e.g. unit tests, replay).

    REQ-2 note
        Classification is DETERMINISTIC end-to-end.  No model is ever
        consulted to route or to choose between models (model-as-judge is
        forbidden per the external-review correction in REQ-2/REQ-7).  The
        optional LLM-classification path present in earlier versions has been
        removed (TASK-27).
    """
    # 1. Normalise problem representation
    problem_dict = _to_dict(problem)

    # 2. Cheap, deterministic feature extraction
    features = _extract_features(problem_dict)

    # 3. Deterministic classification: failure-signal PRIOR when available,
    #    else structural features (REQ-2 + REQ-7)
    problem_class, confidence, method = _classify(problem_dict, features)
    rationale_parts: list[str] = [
        "features={"
        f"has_examples:{features['has_examples']}, "
        f"is_repo_task:{features['is_repo_task']}, "
        f"is_multi_file:{features['is_multi_file']}, "
        f"fn_len:{features['fn_len']}"
        f"}} method={method}"
    ]

    # #EXT-021-REQ-5 Start
    # 4. Tally argmax: deterministic best-model-per-class (REQ-5)
    #    Build from registry on demand if no pre-built tally was injected.
    #    NOTE: the tally is a pure deterministic table lookup -- no model judges
    #    between models here (model-as-judge is forbidden, REQ-2 / REQ-5).
    default_id: str = registry.default_model()
    _active_tally = tally
    if _active_tally is None:
        from harness.model_tally import CoverageTally  # lazy: avoids import at module load
        _active_tally = CoverageTally(registry)

    best_id: str | None = _active_tally.best_model_for(problem_class)

    is_gap: bool = False
    if best_id is not None:
        model_id: str = best_id
        rationale_parts.append(
            f"routed to '{model_id}' (tally argmax for '{problem_class}')"
        )
    else:
        # No profile has evidence for this class -> deterministic default fallback
        model_id = default_id
        confidence = _FALLBACK_CONFIDENCE
        rationale_parts.append(
            f"HARNESS-GAP: no profile has measured coverage for class '{problem_class}'; "
            f"routed to default '{model_id}' -- "
            "add held-out evidence to a profile to close this gap (not a model limit)"
        )
        is_gap = True
    # #EXT-021-REQ-5 End

    decision: dict[str, Any] = {
        "model_id": model_id,
        "problem_class": problem_class,
        "confidence": float(confidence),
        "rationale": "; ".join(rationale_parts),
    }

    # #EXT-021-REQ-7 Start
    # DISCOVER: record unhandled problems so the class ontology can evolve.
    # Only fires on HARNESS-GAP (no measured coverage); never blocks the return.
    if record and is_gap:
        try:
            from harness.new_class_log import record_unhandled  # lazy to avoid circ-import
            record_unhandled(problem_dict, decision)
        except Exception:
            pass  # best-effort; routing decision is unaffected
    # #EXT-021-REQ-7 End

    return decision


# #EXT-021-REQ-2 Start (route_native — Jaros-native routing, TASK-25)
def route_native(
    problem: Any,
    registry: Any,
    runtime: Any,
    *,
    tally: Any = None,
    record: bool = False,
) -> "dict[str, Any]":
    """Like route() but emits the routing Decision through Runtime.apply for Jaros-native logging.

    The routing logic is UNCHANGED (deterministic classification + tally argmax,
    same as route()).  This function wraps the inert routing dict as a real Jaros
    Decision (type ``'model.route'``), applies it through Runtime.apply
    (gate -> executor -> DecisionLog), and returns the routing dict for the caller.

    Parameters
    ----------
    problem : the coding task (same as route())
    registry : ModelRegistry (same as route())
    runtime : a Runtime instance; the Decision is applied through it and hash-chain logged.
    tally : optional CoverageTally (same as route())
    record : bool, default False — offline-safe; same semantics as route(record=)

    Returns
    -------
    dict : the inert routing dict (model_id, problem_class, confidence, rationale)
    """
    import uuid
    from jaros.core import create_decision

    decision_data = route(problem, registry, tally=tally, record=record)

    jaros_decision = create_decision(
        id=f"route-{uuid.uuid4().hex}",
        source="model-router",
        type="model.route",
        payload=decision_data,
    )
    runtime.apply(jaros_decision)
    return decision_data
# #EXT-021-REQ-2 End (route_native)
