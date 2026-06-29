"""Coverage tally for the multi-model routing harness (EXT-021, REQ-5).

The ``CoverageTally`` is the DETERMINISTIC source of truth for "which model is
best for each problem class."  It is built from a ``ModelRegistry``'s measured
profile data — only entries that appear in a profile (with held-out evidence)
become cells in the matrix.  An empty cell (not present in the dict) means
"not yet measured."

``best_model_for(class_name)`` is a pure deterministic argmax over the class's
column: no model is ever asked to choose between models (model-as-judge is
forbidden here, per REQ-2 and owner directive 2026-06-28).

Public API
----------
CoverageTally(registry, roster_order=None)
    Build the tally from *registry*.  *roster_order* overrides the registry's
    own ``roster_order()`` when provided (useful for injection in tests).

.best_model_for(class_name) -> str | None
    Deterministic argmax: highest-scored model for *class_name*; ties broken by
    roster order, then default model preference, then alphabetical id.
    Returns ``None`` when no model has measured coverage (caller should
    default-fallback + record as unhandled class).

.ranked_models_for(class_name) -> list[str]
    All model ids with measured coverage, best-score-first.  REQ-6 will use
    this list as the escalation order.

.as_matrix() -> dict
    Full model x class score matrix, plus a ``coverage_gaps()`` summary.

.coverage_gaps() -> dict
    Classes with no real coverage (all scores unparseable) and per-model gaps
    (known classes a model has not been measured on).  Drives REQ-5 roster
    progression.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# #EXT-021-REQ-5 Start

# ---------------------------------------------------------------------------
# Score parsing — purely deterministic, no model judge
# ---------------------------------------------------------------------------


def _parse_score(score: Any) -> float:
    """Convert a raw profile score value to a comparable float in [0, 1].

    Matching rules (first-wins, documented):

    1. ``int`` / ``float``: used directly; values > 1 treated as a percentage
       value (divided by 100 to normalise to [0, 1]).
    2. Explicit fraction string ``"num/den"`` (e.g. ``"~18/101"``): evaluated
       as ``num / den``.  Fraction chars must be adjacent to the ``/`` with
       only optional whitespace — so ``"82% HumanEval / ~48% MBPP"`` does NOT
       match here (the ``%`` and letters break adjacency).
    3. Percentage string ``"N%"`` (e.g. ``"~82% HumanEval"``): first ``%``
       occurrence; value divided by 100.
    4. Plain numeric string ``"N"`` (e.g. ``"82"`` or ``"0.82"``): value
       divided by 100 when > 1, else used as-is.
    5. Anything else / unparseable: ``-1.0`` (treated as lowest — sorts below
       any real score so it never wins a tie against measured evidence).

    The function is deterministic: same input → same output, always.
    """
    if isinstance(score, (int, float)):
        v = float(score)
        return v / 100.0 if v > 1.0 else v

    if not isinstance(score, str):
        return -1.0

    # 1. Explicit fraction: digits + optional-whitespace + "/" + optional-whitespace + digits
    #    "~18/101" → 18/101 ≈ 0.178
    #    "82% HumanEval / ~48% MBPP" does NOT match because "%" prevents adjacency.
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", score)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        if den > 0:
            return num / den

    # 2. Percentage: "82%" (may be preceded by "~" or spaces)
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", score)
    if m:
        return float(m.group(1)) / 100.0

    # 3. Plain number
    m = re.search(r"(\d+(?:\.\d+)?)", score)
    if m:
        v = float(m.group(1))
        return v / 100.0 if v > 1.0 else v

    return -1.0  # unparseable → lowest


# ---------------------------------------------------------------------------
# CoverageTally
# ---------------------------------------------------------------------------


class CoverageTally:
    """Deterministic model x class coverage matrix.

    Each cell ``(model_id, class_name)`` holds the parsed score from the
    model's measured profile entry.  A missing cell means "not yet measured"
    (Tenet 3 — honest: we never fabricate coverage).

    ``best_model_for`` is a pure function: same registry → same answer every
    time.  No LLM, no network, no randomness.

    Parameters
    ----------
    registry:
        A ``ModelRegistry`` instance.
    roster_order:
        Explicit tie-break order (list of model ids, best first).  When
        ``None``, ``registry.roster_order()`` is called; if that is also empty
        or the method is absent, ties fall through to the ``default_model``
        preference, then alphabetical id.
    """

    def __init__(self, registry: Any, roster_order: Optional[list[str]] = None) -> None:
        self._registry = registry

        # Resolve roster order for tie-breaking
        if roster_order is not None:
            self._roster_order: list[str] = list(roster_order)
        else:
            try:
                self._roster_order = list(registry.roster_order())
            except AttributeError:
                self._roster_order = []

        # Populate cells from every profile
        # Key: (model_id, class_name) → cell dict
        self._cells: dict[tuple[str, str], dict[str, Any]] = {}
        for profile in registry.all_profiles():
            for cls_entry in profile.classes:
                name = cls_entry.get("name")
                if not name:
                    continue  # skip malformed entries
                raw_score = cls_entry.get("score", -1.0)
                self._cells[(profile.id, name)] = {
                    "model_id": profile.id,
                    "class": name,
                    "score_raw": raw_score,
                    "score": _parse_score(raw_score),
                    "bar": cls_entry.get("bar", ""),
                    "date": cls_entry.get("date", ""),
                }

    # ------------------------------------------------------------------
    # Internal helpers (deterministic)
    # ------------------------------------------------------------------

    def _roster_rank(self, model_id: str) -> int:
        """Return the roster rank for *model_id* (lower = better, for ascending sort).

        Models absent from the roster list get rank ``len(roster)`` — they sort
        after all explicitly ranked models.
        """
        try:
            return self._roster_order.index(model_id)
        except ValueError:
            return len(self._roster_order)

    def _default_rank(self, model_id: str) -> int:
        """Return 0 when *model_id* is the registry default (preferred), else 1."""
        try:
            return 0 if model_id == self._registry.default_model() else 1
        except Exception:
            return 1

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def best_model_for(self, class_name: str) -> Optional[str]:
        """Return the deterministic best model id for *class_name*.

        "Best" = highest parsed score.  On ties:
          1. Lower roster order index (best-first in ``_roster.json``) wins.
          2. Registry ``default_model`` wins over non-default.
          3. Alphabetical model id for full determinism.

        Returns ``None`` when no model has any measured coverage for
        *class_name* (caller should default-fallback + log as unhandled).
        """
        candidates = [
            cell
            for (mid, cls), cell in self._cells.items()
            if cls == class_name
        ]
        if not candidates:
            return None

        def _key(cell: dict) -> tuple:
            mid = cell["model_id"]
            return (
                -cell["score"],            # highest score first (negate for ascending)
                self._roster_rank(mid),    # lower rank = better
                self._default_rank(mid),   # default preferred on equal rank
                mid,                       # alphabetical for full determinism
            )

        candidates.sort(key=_key)
        return candidates[0]["model_id"]

    def ranked_models_for(self, class_name: str) -> list[str]:
        """Return ALL model ids with measured coverage for *class_name*, best-first.

        The ranking follows the same sort key as ``best_model_for``.  REQ-6
        (test-gated escalation) will use this ordered list to try models in
        sequence: best tally first, escalate on test-gate failure.

        Returns an empty list when no model has measured coverage.
        """
        candidates = [
            cell
            for (mid, cls), cell in self._cells.items()
            if cls == class_name
        ]
        if not candidates:
            return []

        def _key(cell: dict) -> tuple:
            mid = cell["model_id"]
            return (
                -cell["score"],
                self._roster_rank(mid),
                self._default_rank(mid),
                mid,
            )

        candidates.sort(key=_key)
        return [c["model_id"] for c in candidates]

    def as_matrix(self) -> dict:
        """Return the full model x class score matrix for inspection.

        Structure::

            {
              "classes": ["standalone-fn-gen", ...],   # sorted
              "models":  ["gemma-4-e2b", ...],          # sorted
              "cells": {
                  "<model_id>": {
                      "<class_name>": {
                          "score": 0.82,
                          "score_raw": "~82% HumanEval",
                          "bar": "...",
                          "date": "...",
                      }
                      | None   # not measured
                  }
              }
            }
        """
        all_classes = sorted({cls for (_, cls) in self._cells})
        all_models = sorted({mid for (mid, _) in self._cells})

        cells_matrix: dict[str, dict] = {}
        for mid in all_models:
            cells_matrix[mid] = {
                cls: (self._cells[(mid, cls)] if (mid, cls) in self._cells else None)
                for cls in all_classes
            }

        return {
            "classes": all_classes,
            "models": all_models,
            "cells": cells_matrix,
        }

    def coverage_gaps(self) -> dict:
        """Return a summary of coverage gaps to drive REQ-5 roster progression.

        Returns::

            {
              "uncovered_classes": [...],   # classes whose only scores are -1.0
                                            # (no real measured coverage)
              "partial_models": {           # per model: known classes not yet measured
                  "<model_id>": ["class-a", "class-b"],
              }
            }

        "Known classes" = all classes appearing in ANY loaded profile.
        A partial-model gap is any (model, class) pair where the model has no
        cell for a class that other models DO have cells for.

        This output drives the roster-progression rule (REQ-5): measure the
        current model across all known classes before admitting the next model,
        and re-profile all roster models whenever a new class is discovered.
        """
        all_classes = sorted({cls for (_, cls) in self._cells})
        all_models = sorted({mid for (mid, _) in self._cells})

        # Classes with no genuine measured coverage (all scores <= 0 i.e. -1.0)
        uncovered: list[str] = [
            cls for cls in all_classes
            if not any(
                self._cells.get((mid, cls), {}).get("score", -1.0) >= 0.0
                for mid in all_models
            )
        ]

        # Per-model gaps: known classes the model has NO cell for
        partial: dict[str, list[str]] = {}
        for mid in all_models:
            missing = [
                cls for cls in all_classes if (mid, cls) not in self._cells
            ]
            if missing:
                partial[mid] = missing

        return {
            "uncovered_classes": uncovered,
            "partial_models": partial,
        }

# #EXT-021-REQ-5 End
