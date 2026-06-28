"""Model registry for the multi-model routing harness (EXT-021, REQ-1).

Each Jetson-fitting model is described by a ``ModelProfile`` stored as a JSON file
under ``.jaros-data/config/models/<id>.json``.  Files starting with ``_`` (e.g.
``_roster.json``) are meta-files (default/order) and are NOT loaded as profiles.

The ``ModelRegistry`` loads all profiles at start-up and exposes:
  - ``lookup_by_id(id)``       -> ``ModelProfile | None``
  - ``lookup_by_class(name)``  -> ``list[str]`` (ids with MEASURED coverage)
  - ``default_model()``        -> ``str`` (id of the designated default model)
  - ``all_profiles()``         -> ``list[ModelProfile]``

Tenet 3 (honest): a model is never returned by ``lookup_by_class`` unless its
profile actually lists that class with recorded held-out evidence.
"""
from __future__ import annotations

# #EXT-021-REQ-1 Start
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Default config path — overridable via JAROS_DATA_DIR env var
# ---------------------------------------------------------------------------
_DEFAULT_MODELS_DIR = (
    Path(os.environ.get("JAROS_DATA_DIR", Path(__file__).parent.parent / ".jaros-data"))
    / "config"
    / "models"
)

_ROSTER_FILE = "_roster.json"


@dataclass
class ModelProfile:
    """A single Jetson-fitting model's complete description.

    Attributes
    ----------
    id : str
        Stable key (matches the JSON filename without ``.json``).
    alias : str
        The llama.cpp ``--alias`` the model is served under; used to identify
        the currently-served model and to point the LLM client at it.
    serve : dict
        llama.cpp serving parameters::

            {
              "gguf": "<path on Jetson | placeholder>",
              "ctx":  4096,
              "ngl":  99,
              "fits_jetson": true
            }

    classes : list[dict]
        The problem classes this model is MEASURED to handle.  Each entry must
        carry held-out evidence::

            {"name": "standalone-fn-gen",
             "bar":  "HumanEval/MBPP pass@1 (gated)",
             "score": "~82% HumanEval / ~48% MBPP",
             "date": "2026-06-25"}

        A class entry is added ONLY after it clears the bar on held-out tasks
        (Tenet 3 — honest profiling).

    adaptation : dict
        The harness pieces to activate for this model::

            {
              "tools":   [...],
              "agents":  [...],
              "config":  {...},
              "prompts": {...}
            }
    """

    id: str
    alias: str
    serve: dict[str, Any] = field(default_factory=dict)
    classes: list[dict[str, Any]] = field(default_factory=list)
    adaptation: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def handled_class_names(self) -> list[str]:
        """Return the names of all classes this profile has measured coverage for."""
        return [c["name"] for c in self.classes if "name" in c]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelProfile":
        return cls(
            id=data["id"],
            alias=data.get("alias", data["id"]),
            serve=data.get("serve", {}),
            classes=data.get("classes", []),
            adaptation=data.get("adaptation", {}),
        )


class ModelRegistry:
    """Registry of all Jetson-fitting model profiles.

    Loaded from ``.jaros-data/config/models/`` (or a custom ``models_dir``).
    Files beginning with ``_`` are meta-files and are ignored as profiles.
    """

    def __init__(self, profiles: list[ModelProfile], default_id: str) -> None:
        self._profiles: dict[str, ModelProfile] = {p.id: p for p in profiles}
        self._default_id = default_id

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def lookup_by_id(self, model_id: str) -> Optional[ModelProfile]:
        """Return the profile for *model_id*, or ``None`` if unknown."""
        return self._profiles.get(model_id)

    def lookup_by_class(self, class_name: str) -> list[str]:
        """Return ids of models whose profiles include MEASURED coverage of *class_name*.

        Honest (Tenet 3): a model that has no recorded held-out evidence for
        *class_name* is NEVER returned, even if the name looks related.
        """
        return [
            profile.id
            for profile in self._profiles.values()
            if class_name in profile.handled_class_names()
        ]

    def default_model(self) -> str:
        """Return the id of the designated default model.

        Read from ``_roster.json`` ``default`` field at load time.  Falls back
        to the founding Gemma id if the roster is absent or malformed.
        """
        return self._default_id

    def all_profiles(self) -> list[ModelProfile]:
        """Return every loaded profile (order not guaranteed)."""
        return list(self._profiles.values())


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

_FALLBACK_DEFAULT = "gemma-4-e2b"


def from_dir(models_dir: str | Path) -> ModelRegistry:
    """Load a ``ModelRegistry`` from *models_dir*.

    Every ``*.json`` file NOT starting with ``_`` is treated as a model profile.
    ``_roster.json`` supplies the ``default`` model id and ``order``.
    """
    models_dir = Path(models_dir)

    # -- read roster meta-file (optional) -----------------------------------
    roster_path = models_dir / _ROSTER_FILE
    default_id = _FALLBACK_DEFAULT
    if roster_path.is_file():
        try:
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
            default_id = roster.get("default", _FALLBACK_DEFAULT)
        except (json.JSONDecodeError, OSError):
            pass  # malformed roster — keep fallback

    # -- load profile files -------------------------------------------------
    profiles: list[ModelProfile] = []
    if models_dir.is_dir():
        for json_file in sorted(models_dir.glob("*.json")):
            if json_file.name.startswith("_"):
                continue  # skip meta-files
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                profiles.append(ModelProfile.from_dict(data))
            except (json.JSONDecodeError, KeyError, OSError):
                # Skip malformed files — don't crash the registry
                pass

    return ModelRegistry(profiles=profiles, default_id=default_id)


def load_registry() -> ModelRegistry:
    """Load the registry from the default ``.jaros-data/config/models/`` directory."""
    return from_dir(_DEFAULT_MODELS_DIR)
# #EXT-021-REQ-1 End
