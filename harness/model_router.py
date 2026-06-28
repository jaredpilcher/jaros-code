"""Model-router judge for the multi-model routing harness (EXT-021, REQ-2).

``route(problem, registry, llm=None) -> dict`` is the public entry point.

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
2. If an *llm* callable is provided AND the deterministic confidence falls
   below ``_AMBIGUITY_THRESHOLD``, we ask the LLM for a class label.
3. The resolved class is mapped to a model via the registry; ties (multiple
   covering models) are broken by preferring the default model, then roster
   order.
4. If no profile covers the class, the registry default is used and the
   rationale marks this as a HARNESS-GAP -- never a model limit (PRIME-001).
"""
from __future__ import annotations

# #EXT-021-REQ-2 Start
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

# Confidence thresholds
_HIGH_CONFIDENCE: float = 0.9
_MED_CONFIDENCE: float = 0.65
_AMBIGUITY_THRESHOLD: float = 0.7   # below this -> may consult LLM
_LLM_CONFIDENCE: float = 0.75       # assigned when LLM supplied a valid label
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
# Deterministic class classification
# ---------------------------------------------------------------------------

def _classify_deterministic(features: dict[str, Any]) -> tuple[str, float]:
    """Map extracted features to ``(problem_class, confidence)``.

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


# ---------------------------------------------------------------------------
# Optional LLM label (stub-friendly)
# ---------------------------------------------------------------------------

def _ask_llm(llm: Any, problem: dict, current_class: str) -> str | None:
    """Ask *llm* for a problem-class label.

    *llm* must be callable as ``llm(prompt: str) -> str``.  Returns one of
    ``_KNOWN_CLASSES`` or ``None`` (bad reply, unknown label, or exception).
    Never propagates an exception to the caller.
    """
    source_snippet: str = str(
        problem.get("source", problem.get("prompt", problem.get("text", "")))
    )[:500]
    prompt = (
        "Classify this coding problem into exactly one of these classes:\n"
        f"  {', '.join(_KNOWN_CLASSES)}\n\n"
        "Reply with ONLY the class name, nothing else.\n\n"
        f"Problem:\n{source_snippet}"
    )
    try:
        result = llm(prompt)
        if isinstance(result, str):
            label = result.strip()
            if label in _KNOWN_CLASSES:
                return label
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def route(
    problem: Any,
    registry: Any,
    llm: Any = None,
) -> dict[str, Any]:
    """Classify *problem* and select the best-matching registry model.

    Parameters
    ----------
    problem:
        A dict (or object with ``__dict__``) describing the coding task.
        Recognised keys: ``source``/``prompt``/``text``, ``has_examples``,
        ``is_repo_task``/``repo_root``/``repo_path``, ``is_multi_file``,
        ``files``, ``task_type``.
    registry:
        A ``ModelRegistry`` instance (``harness.model_registry``).
    llm:
        Optional callable ``(prompt: str) -> str``.  When provided AND
        deterministic confidence < ``_AMBIGUITY_THRESHOLD``, the LLM is
        asked to supply a class label.  The deterministic path is fully
        self-contained when ``llm=None``.

    Returns
    -------
    dict
        Inert decision with keys ``model_id``, ``problem_class``,
        ``confidence`` (float 0.0-1.0), and ``rationale`` (str).

        Never raises.  Always returns a valid model_id (worst-case: the
        registry default).

    Tenet 1 guarantee
        This function has NO side effects.  It reads ``registry`` and
        optionally calls ``llm``; it does not write files, serve models,
        modify environment state, or perform I/O beyond those calls.
    """
    # 1. Normalise problem representation
    problem_dict = _to_dict(problem)

    # 2. Cheap, deterministic feature extraction
    features = _extract_features(problem_dict)

    # 3. Deterministic classification
    problem_class, confidence = _classify_deterministic(features)
    rationale_parts: list[str] = [
        "features={"
        f"has_examples:{features['has_examples']}, "
        f"is_repo_task:{features['is_repo_task']}, "
        f"is_multi_file:{features['is_multi_file']}, "
        f"fn_len:{features['fn_len']}"
        "}"
    ]

    # 4. Optional LLM refinement when features are ambiguous
    if llm is not None and confidence < _AMBIGUITY_THRESHOLD:
        llm_label = _ask_llm(llm, problem_dict, problem_class)
        if llm_label is not None:
            problem_class = llm_label
            confidence = _LLM_CONFIDENCE
            rationale_parts.append(f"LLM labelled as '{llm_label}'")
        else:
            rationale_parts.append(
                "LLM returned no usable label; kept deterministic class"
            )

    # 5. Registry lookup: find which models have measured coverage
    default_id: str = registry.default_model()
    covering_ids: list[str] = registry.lookup_by_class(problem_class)

    if covering_ids:
        # Prefer the default model if it also covers the class (roster preference)
        if default_id in covering_ids:
            model_id: str = default_id
        else:
            model_id = covering_ids[0]
        rationale_parts.append(
            f"routed to '{model_id}' (measured coverage for '{problem_class}')"
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

    return {
        "model_id": model_id,
        "problem_class": problem_class,
        "confidence": float(confidence),
        "rationale": "; ".join(rationale_parts),
    }
# #EXT-021-REQ-2 End
