"""Per-model profiling loop — multi-model routing harness (EXT-021, REQ-4).

The profiling loop earns each model's class profile **honestly**: for every
candidate Jetson-fitting model, serve it, run the held-out class evals, and
record ONLY the classes whose bar was cleared — with score/bar/date evidence
(Tenet 3: never claim a class without measured proof).

Public API
----------
profile_model(model_id, classes, registry, *, eval_fn, serve_fn=None, now=None, models_dir=None)
    -> {"model_id", "added": [...], "rejected": [...]}

    Run held-out evals for each class and update the profile JSON.
    Classes that clear the bar are written with evidence; below-bar classes
    are NOT added — honest failure (Tenet 3).

fits_jetson(profile_or_serve) -> bool
    Admission check: True iff the model fits the Jetson ~8 GB VRAM budget.

roster_order(registry, models_dir=None) -> list[str]
    Best-first exploration list from ``_roster.json``; only Jetson-fitting
    models should appear.

Honesty guarantee (Tenet 3)
---------------------------
A class entry is appended to the profile ONLY when eval_fn returns
``passed=True``.  Every other path (failure, below-bar, already recorded)
leaves the profile unchanged for that class.  A failed class is listed
in ``rejected`` — visible in the return dict, never hidden.
"""
from __future__ import annotations

# #EXT-021-REQ-4 Start
import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Default config path — mirrors model_registry._DEFAULT_MODELS_DIR
# ---------------------------------------------------------------------------
_DEFAULT_MODELS_DIR: Path = (
    Path(os.environ.get("JAROS_DATA_DIR", str(Path(__file__).parent.parent / ".jaros-data")))
    / "config"
    / "models"
)

_ROSTER_FILE = "_roster.json"

# Jetson Orin Nano effective VRAM budget
_JETSON_VRAM_GB: float = 8.0


# ---------------------------------------------------------------------------
# fits_jetson — Jetson admission check
# ---------------------------------------------------------------------------

def fits_jetson(profile_or_serve: Any) -> bool:
    """Return True iff the model fits within the Jetson's ~8 GB VRAM budget.

    Accepts a ``ModelProfile`` instance (has a ``.serve`` attribute) or a
    raw serve-params ``dict``.

    Check order
    -----------
    1. Explicit size field (``size_gb``, ``vram_gb``, ``model_size_gb``) —
       numeric comparison against :data:`_JETSON_VRAM_GB` (8.0 GB).
    2. Explicit ``fits_jetson`` boolean flag in the serve params.

    Admission is **opt-in**: a model with no size info and no explicit
    ``fits_jetson: true`` flag is **rejected** (Tenet 3 — honest by default;
    we never assume a model fits if we have no evidence).

    Parameters
    ----------
    profile_or_serve :
        Either a ``ModelProfile`` instance (``harness.model_registry``) or a
        plain ``dict`` (serve-params block from a profile JSON).

    Returns
    -------
    bool
        ``True`` if the model is judged to fit the Jetson budget.
    """
    # Accept ModelProfile (has .serve) or a raw serve-params dict
    if hasattr(profile_or_serve, "serve"):
        serve: dict = profile_or_serve.serve or {}
    elif isinstance(profile_or_serve, dict):
        serve = profile_or_serve
    else:
        return False

    if not isinstance(serve, dict):
        return False

    # 1. Numeric size check — explicit measurement takes priority
    for key in ("size_gb", "vram_gb", "model_size_gb"):
        val = serve.get(key)
        if val is not None:
            try:
                return float(val) <= _JETSON_VRAM_GB
            except (TypeError, ValueError):
                pass  # malformed value — fall through

    # 2. Explicit admission flag (opt-in; absent defaults to False)
    return bool(serve.get("fits_jetson", False))


# ---------------------------------------------------------------------------
# roster_order — best-first exploration order
# ---------------------------------------------------------------------------

def roster_order(
    registry: Any,
    models_dir: Optional[str | Path] = None,
) -> list[str]:
    """Return model ids in best-first order from ``_roster.json``.

    The order is the ``"order"`` array in ``_roster.json``, listing models
    from strongest-Jetson-fitting first.  If the roster file is absent or
    malformed, falls back to: default model first, then remaining profiles
    in load order.

    Parameters
    ----------
    registry :
        A ``ModelRegistry`` instance.  Used only as a fallback source of
        model ids when the roster file is absent.
    models_dir : str | Path, optional
        Directory containing ``_roster.json``.  Defaults to the standard
        ``.jaros-data/config/models/``.  Override with ``tmp_path`` in tests
        (no env-var pollution needed).

    Returns
    -------
    list[str]
        Model ids, best-first (strongest Jetson-fitting model first).
    """
    if models_dir is None:
        models_dir = _DEFAULT_MODELS_DIR
    models_dir = Path(models_dir)

    roster_path = models_dir / _ROSTER_FILE
    if roster_path.is_file():
        try:
            roster: dict = json.loads(roster_path.read_text(encoding="utf-8"))
            order: list = roster.get("order", [])
            if order:
                return list(order)
        except (json.JSONDecodeError, OSError):
            pass  # malformed roster — fall through to fallback

    # Fallback: default model first, then remaining profiles in load order
    default_id: str = registry.default_model()
    all_ids: list[str] = [p.id for p in registry.all_profiles()]
    if default_id in all_ids:
        all_ids.remove(default_id)
        all_ids.insert(0, default_id)
    elif default_id:
        all_ids.insert(0, default_id)
    return all_ids


# ---------------------------------------------------------------------------
# profile_model — the honesty backbone of the profiling loop
# ---------------------------------------------------------------------------

def profile_model(
    model_id: str,
    classes: list[dict],
    registry: Any,
    *,
    eval_fn: Callable[[str, dict], dict],
    serve_fn: Optional[Callable[[str], None]] = None,
    now: Optional[Callable[[], str]] = None,
    models_dir: Optional[str | Path] = None,
) -> dict:
    """Run held-out class evals for *model_id* and update its profile JSON.

    For each class descriptor in *classes*:

    * If ``eval_fn`` reports ``passed=True`` **and** the class is not already
      recorded in the profile, append the evidence ``{name, bar, score, date}``
      to the profile's ``classes`` list and persist the JSON.
      **Earned, with recorded proof — Tenet 3.**
    * If ``passed=False``, the class is listed in ``rejected`` and NOT added
      to the profile — **honest failure**.
    * If the class is already present in the profile (prior run), it is
      **skipped entirely** — eval_fn is NOT called, no duplicate written
      (**idempotent**: multiple runs converge to the same profile).

    Parameters
    ----------
    model_id : str
        Registry id of the model to profile.
    classes : list[dict]
        Class descriptors.  Each must have at minimum a ``"name"`` key; any
        extra keys (``"bar"``, ``"eval_key"``, …) are forwarded to *eval_fn*.
    registry :
        A ``ModelRegistry`` instance.  Used to resolve the profile; the JSON
        file on disk is the canonical truth for idempotency (not the in-memory
        registry, which may be stale from a previous session).
    eval_fn : callable
        ``(model_id: str, class_def: dict) -> {"score": Any, "passed": bool, "bar": str}``

        **The sole gate**: a class is written ONLY when this returns
        ``passed=True``.  Inject a stub in tests (no live eval calls).
        The real implementation wires to existing class eval harnesses
        (HumanEval/MBPP for ``standalone-fn-gen``, 101-task repo suite for
        repo classes, etc.).
    serve_fn : callable, optional
        ``(model_id: str) -> None`` — ensure the model is loaded on the Jetson
        before evals begin.  Default is a no-op (``None``).  Inject a stub in
        tests; inject the real ``rewire`` clerk in production.
    now : callable, optional
        ``() -> str`` returning an ISO date string for the evidence record.
        Default: ``datetime.date.today().isoformat()``.  Injectable for
        deterministic test assertions.
    models_dir : str | Path, optional
        Directory where ``<model_id>.json`` profile files live.  Defaults to
        ``.jaros-data/config/models/``.  Pass ``tmp_path`` in tests so no
        real profile is modified.

    Returns
    -------
    dict
        ``{"model_id": str, "added": [name, ...], "rejected": [name, ...]}``

        ``added``    — class names written to the profile (bar cleared).
        ``rejected`` — class names NOT added (bar not cleared — honest).

        On I/O errors an additional ``"error"`` key is present.

    Tenet 3 guarantee
    -----------------
    A class is appended to ``profile["classes"]`` ONLY when *eval_fn*
    returns ``passed=True``.  Every other path (failure, below-bar, already
    recorded, I/O error) leaves the profile unchanged for that class.
    """
    # -- resolve defaults --------------------------------------------------------
    if models_dir is None:
        models_dir = _DEFAULT_MODELS_DIR
    models_dir = Path(models_dir)

    _now: Callable[[], str] = (
        now if now is not None else (lambda: datetime.date.today().isoformat())
    )

    # -- serve the model before evals (injectable; skipped when serve_fn=None) --
    if serve_fn is not None:
        serve_fn(model_id)

    # -- load profile JSON from disk (canonical source of truth) ----------------
    profile_path = models_dir / f"{model_id}.json"
    if not profile_path.is_file():
        return {
            "model_id": model_id,
            "added": [],
            "rejected": [],
            "error": f"Profile JSON not found: {profile_path}",
        }

    try:
        profile_data: dict = json.loads(profile_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "model_id": model_id,
            "added": [],
            "rejected": [],
            "error": f"Failed to read profile JSON: {exc}",
        }

    existing_classes: list[dict] = profile_data.get("classes", [])
    # Build a fast lookup of already-recorded class names for idempotency
    existing_names: set[str] = {
        c["name"]
        for c in existing_classes
        if isinstance(c, dict) and "name" in c
    }

    added: list[str] = []
    rejected: list[str] = []

    for class_def in classes:
        if not isinstance(class_def, dict):
            continue
        name: str = class_def.get("name", "").strip()
        if not name:
            continue

        # Idempotency guard: skip if already recorded in the profile JSON
        if name in existing_names:
            continue

        # Run the held-out eval (injectable — no live calls in tests)
        try:
            result: dict = eval_fn(model_id, class_def)
        except Exception:
            # eval failure → treat as not-passed (honest)
            rejected.append(name)
            continue

        passed: bool = bool(result.get("passed", False))
        score: Any = result.get("score")
        bar: str = str(result.get("bar", class_def.get("bar", "")))

        if passed:
            # Tenet 3: append evidence ONLY when the bar is cleared
            entry: dict[str, Any] = {
                "name": name,
                "bar": bar,
                "score": score,
                "date": _now(),
            }
            existing_classes.append(entry)
            existing_names.add(name)
            added.append(name)
        else:
            # Honest failure — NOT added to the profile
            rejected.append(name)

    # -- persist the updated profile JSON ---------------------------------------
    profile_data["classes"] = existing_classes
    try:
        profile_path.write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
    except OSError as exc:
        return {
            "model_id": model_id,
            "added": added,
            "rejected": rejected,
            "error": f"Failed to persist profile JSON: {exc}",
        }

    return {"model_id": model_id, "added": added, "rejected": rejected}
# #EXT-021-REQ-4 End
