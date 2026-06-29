"""Label store for class-evolution machinery (EXT-021, REQ-7 SPLIT + VALIDATE).

Every test-gated solve in ``solve_routed_escalating`` appends a
``(problem-signature, model, pass/fail)`` label here via ``record_outcome``.
Those accumulated labels power two class-evolution operations:

- **SPLIT**: ``split_candidates`` flags classes whose most-measured model has
  an inconsistent outcome (pass_rate in a middle band) — they are too coarse
  and should be split along a separating structural feature, then re-profiled.

- **VALIDATE**: ``validate_classes`` partitions classes into *predictive* (the
  best model wins >= min_winrate across >= min_n samples) and *non_predictive*
  (below bar — flag for re-examination or dissolution).

The store is a JSONL file (``.jaros-data/artifacts/solve_labels.jsonl``).
Writes are best-effort: ``record_outcome`` never raises into the caller so the
solve path is never blocked by a logging failure (Tenet 1).  Reads are pure.

Signature format (shared with new_class_log for consistency)
------------------------------------------------------------
Each JSONL record contains:

    {
      "ts":            "2026-06-29T00:00:00.000000Z",   # UTC ISO-8601
      "signature":     {                                 # deterministic features
          "language":          "python",
          "is_repo_task":      false,
          "is_multi_file":     false,
          "has_examples":      true,
          "fn_len_bucket":     "small",
          "source_len_bucket": "short",
          "error_signal":      ""
      },
      "problem_class": "standalone-fn-gen",
      "model_id":      "gemma-4-e2b",
      "passed":        true
    }

Split-candidate heuristic (documented)
---------------------------------------
A class is a SPLIT candidate when, for its most-measured model:

    variance_threshold <= pass_rate <= 1.0 - variance_threshold
    AND total_samples >= min_n

With the default threshold of 0.35 this flags classes in the band [0.35, 0.65]:
a pass_rate near 0 or 1 is *consistent* (the model reliably fails or passes);
a middle-band rate reveals that the class is heterogeneous — split it.

Validate heuristic (documented)
--------------------------------
A class is PREDICTIVE when its most-measured model achieves:

    pass_rate >= min_winrate   (default 0.5)
    AND total_samples >= min_n (default 4)

Below either bar the class goes to *non_predictive* (flagged for re-examination).
"""
from __future__ import annotations

# #EXT-021-REQ-7 Start
import datetime
import json
from pathlib import Path
from typing import Any

# Reuse the deterministic signature helpers from new_class_log so every
# label record uses the same feature schema.  These are internal helpers —
# the import is intentional and co-located within the harness package.
from harness.new_class_log import _build_signature, _normalise  # noqa: PLC2701

_DEFAULT_LABEL_PATH = Path(".jaros-data/artifacts/solve_labels.jsonl")


# ---------------------------------------------------------------------------
# record_outcome — best-effort write, never raises
# ---------------------------------------------------------------------------


def record_outcome(
    problem: Any,
    model_id: str,
    problem_class: str,
    passed: bool,
    *,
    path: "str | Path | None" = None,
) -> None:
    """Append one ``(problem-signature, model, outcome)`` label to the JSONL store.

    Parameters
    ----------
    problem:
        The raw problem dict (or object with ``__dict__``) from the solve loop.
        Missing or wrong-typed fields are handled defensively.
    model_id:
        The model that produced the solve attempt (e.g. ``"gemma-4-e2b"``).
    problem_class:
        The class string from the routing Decision (e.g. ``"standalone-fn-gen"``).
    passed:
        ``True`` when the deterministic test gate accepted the solve result.
    path:
        Override the output path.  Defaults to
        ``.jaros-data/artifacts/solve_labels.jsonl``.

    Notes
    -----
    Never raises.  All exceptions are silently swallowed so the routing /
    solve path is never blocked by a logging failure (best-effort, Tenet 1).
    """
    label_path = Path(path) if path is not None else _DEFAULT_LABEL_PATH
    try:
        p = _normalise(problem)
        sig = _build_signature(p)
        record: dict = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "signature": sig,
            "problem_class": str(problem_class),
            "model_id": str(model_id),
            "passed": bool(passed),
        }
        label_path.parent.mkdir(parents=True, exist_ok=True)
        with label_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # best-effort; never block the caller


# ---------------------------------------------------------------------------
# class_outcome_stats — pure read, no side effects
# ---------------------------------------------------------------------------


def class_outcome_stats(
    *,
    path: "str | Path | None" = None,
) -> dict:
    """Read the label store and return per-``(class, model)`` statistics.

    Returns
    -------
    dict
        Keys are ``(problem_class, model_id)`` tuples; values are::

            {"pass_count": int, "total": int, "pass_rate": float}

        Empty dict when the store does not exist or contains no valid records.
    """
    label_path = Path(path) if path is not None else _DEFAULT_LABEL_PATH

    # Accumulators: (class, model) -> [pass_count, total]
    acc: dict[tuple[str, str], list[int]] = {}

    if label_path.exists():
        try:
            with label_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = (
                        str(rec.get("problem_class", "")),
                        str(rec.get("model_id", "")),
                    )
                    if key not in acc:
                        acc[key] = [0, 0]
                    acc[key][1] += 1
                    if rec.get("passed", False):
                        acc[key][0] += 1
        except Exception:
            pass  # corrupt file — return what was successfully parsed

    stats: dict = {}
    for (cls, mid), (pass_count, total) in acc.items():
        pass_rate = pass_count / total if total > 0 else 0.0
        stats[(cls, mid)] = {
            "pass_count": pass_count,
            "total": total,
            "pass_rate": pass_rate,
        }
    return stats


# ---------------------------------------------------------------------------
# split_candidates — deterministic SPLIT heuristic
# ---------------------------------------------------------------------------


def split_candidates(
    *,
    variance_threshold: float = 0.35,
    min_n: int = 4,
    path: "str | Path | None" = None,
) -> list:
    """Return classes flagged as too coarse (SPLIT candidates).

    A class is a split candidate when its most-measured model's ``pass_rate``
    sits in the middle band ``[variance_threshold, 1 - variance_threshold]``
    with at least *min_n* samples.

    "Most-measured" = the model with the highest ``total`` count for that
    class (ties broken alphabetically by model_id for full determinism).

    Heuristic rationale
    -------------------
    - ``pass_rate ~= 0`` or ``~= 1`` → consistent; no split needed.
    - ``variance_threshold <= pass_rate <= 1 - variance_threshold`` → the model
      wins some and loses others — the class is heterogeneous; split it along a
      separating structural feature, then re-profile each sub-class.

    Parameters
    ----------
    variance_threshold:
        One-sided band width.  Default 0.35 (flags rates in [0.35, 0.65]).
    min_n:
        Minimum sample count for the most-measured model.  Classes below this
        threshold are skipped (insufficient data to decide).
    path:
        Override the label store path.

    Returns
    -------
    list
        List of ``{class, model, pass_rate, n}`` dicts for each flagged class.
        Deterministic: same label store → same output.
    """
    stats = class_outcome_stats(path=path)

    # Group by class → list of (model_id, pass_rate, total)
    by_class: dict[str, list[tuple[str, float, int]]] = {}
    for (cls, mid), entry in stats.items():
        by_class.setdefault(cls, []).append((mid, entry["pass_rate"], entry["total"]))

    candidates: list[dict] = []
    for cls, model_entries in sorted(by_class.items()):  # sorted for determinism
        # Most-measured model first; alphabetical tie-break
        model_entries.sort(key=lambda t: (-t[2], t[0]))
        best_model, best_rate, best_n = model_entries[0]

        if best_n < min_n:
            continue  # not enough data

        lo = variance_threshold
        hi = 1.0 - variance_threshold
        if lo <= best_rate <= hi:
            candidates.append({
                "class": cls,
                "model": best_model,
                "pass_rate": best_rate,
                "n": best_n,
            })

    return candidates


# ---------------------------------------------------------------------------
# validate_classes — deterministic VALIDATE heuristic
# ---------------------------------------------------------------------------


def validate_classes(
    *,
    min_winrate: float = 0.5,
    min_n: int = 4,
    path: "str | Path | None" = None,
) -> dict:
    """Partition classes into *predictive* and *non_predictive*.

    A class is **PREDICTIVE** when its most-measured model achieves::

        pass_rate >= min_winrate   AND   total_samples >= min_n

    Classes that fail either condition go into ``non_predictive`` and are
    flagged for re-examination (the class may need splitting, dissolution, or
    additional profiling data before it can guide routing).

    "Most-measured" = the model with the highest ``total`` count for that
    class (ties broken alphabetically by model_id for full determinism).

    Parameters
    ----------
    min_winrate:
        Minimum ``pass_rate`` for the most-measured model.  Default 0.5
        (the model wins at least as often as it loses — a minimal bar).
    min_n:
        Minimum sample count.  Classes with fewer samples are non_predictive
        (insufficient evidence to classify as predictive).
    path:
        Override the label store path.

    Returns
    -------
    dict
        ``{"predictive": [...], "non_predictive": [...]}``

        Each entry is ``{class, model, pass_rate, n}``.  Both lists are
        sorted by class name for deterministic output.
    """
    stats = class_outcome_stats(path=path)

    by_class: dict[str, list[tuple[str, float, int]]] = {}
    for (cls, mid), entry in stats.items():
        by_class.setdefault(cls, []).append((mid, entry["pass_rate"], entry["total"]))

    predictive: list[dict] = []
    non_predictive: list[dict] = []

    for cls in sorted(by_class):  # sorted for deterministic output
        model_entries = by_class[cls]
        model_entries.sort(key=lambda t: (-t[2], t[0]))
        best_model, best_rate, best_n = model_entries[0]

        entry_dict = {
            "class": cls,
            "model": best_model,
            "pass_rate": best_rate,
            "n": best_n,
        }

        if best_n >= min_n and best_rate >= min_winrate:
            predictive.append(entry_dict)
        else:
            non_predictive.append(entry_dict)

    return {"predictive": predictive, "non_predictive": non_predictive}

# #EXT-021-REQ-7 End
