"""Execution-plane tool ``model.rewire`` (EXT-021, TASK-25).

Makes the harness BECOME the routed model: validates the model_id resolves in
the registry and targets an on-device (fits_jetson=True) model (Tenet 1/2),
then executes the manager HTTP swap + adaptation activation via
harness.model_rewire.rewire().

Decision payload:
  model_id (str) — the registry id to rewire to

Injectable state (via harness._rewire_config — the stable singleton)
--------------------------------------------------------------------
The registry and optional callables (swap_fn, serving_state, activate_fn) are
provided via harness._rewire_config rather than the Decision payload (which must
be inert JSON).  callers set state with set_registry() / set_swap_fn() etc.
BEFORE applying the Decision, and call reset_all() afterwards for isolation.

Why harness._rewire_config and not module-level globals here?
-------------------------------------------------------------
load_custom_tools() imports each tool with a FRESH importlib module object NOT
registered in sys.modules.  Any setter targeted at ``import model_rewire_tool``
from the normal sys.path would hit a DIFFERENT module object than the one the
executor has bound.  harness._rewire_config is a stable harness package module
with ONE copy in sys.modules — setters and lazy getters always share the same state.

Returns the rewire() result dict (ok, model_id, swapped, served_before,
served_after, adaptation_active, error) extended with {"tool": "model.rewire"}.

Tenet guarantees
----------------
Tenet 1: validate() runs and resolves the profile BEFORE execute() swaps.
Tenet 2: only models with fits_jetson=True (on-device) pass validate().
Tenet 3: every failure is surfaced honestly in the return dict; nothing hidden.
"""
from __future__ import annotations

import os
import sys

from jaros.core.decision_gate import ValidationResult

# Resolve repo root so harness package is importable from the tools dir.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# #EXT-021-REQ-3 Start
class ModelRewireTool:
    NAME = "model.rewire"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            return ValidationResult.reject(
                "model.rewire: payload must have a non-empty 'model_id' string"
            )

        # Lazy import: read current registry at call time from the stable singleton.
        # (Tenet 1: validate resolves the profile BEFORE the swap executes.)
        from harness._rewire_config import get_registry  # noqa: PLC0415
        registry = get_registry()
        if registry is not None:
            profile = registry.lookup_by_id(model_id)
            if profile is None:
                return ValidationResult.reject(
                    f"model.rewire: unknown model_id '{model_id}' — not in registry "
                    "(Tenet 1: profile must resolve before swap is attempted)"
                )
            # Tenet 2: only on-device (Jetson-fitting) models are allowed.
            serve = profile.serve if isinstance(profile.serve, dict) else {}
            if not serve.get("fits_jetson", True):
                return ValidationResult.reject(
                    f"model.rewire: model '{model_id}' is not on-device "
                    "(fits_jetson=False) — Tenet 2 forbids off-device escalation"
                )

        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        model_id = payload["model_id"]

        # Lazy imports: read current config values from the stable singleton at call time.
        from harness._rewire_config import (  # noqa: PLC0415
            get_registry,
            get_swap_fn,
            get_serving_state_fn,
            get_activate_fn,
        )
        from harness.model_rewire import rewire  # noqa: PLC0415

        registry = get_registry()
        if registry is None:
            return {
                "tool": self.NAME,
                "model_id": model_id,
                "ok": False,
                "error": (
                    "model.rewire: no registry set — call "
                    "harness._rewire_config.set_registry() before applying this Decision"
                ),
            }

        kwargs: dict = {}
        swap_fn = get_swap_fn()
        serving_state = get_serving_state_fn()
        activate_fn = get_activate_fn()
        if swap_fn is not None:
            kwargs["swap_fn"] = swap_fn
        if serving_state is not None:
            kwargs["serving_state"] = serving_state
        if activate_fn is not None:
            kwargs["activate_fn"] = activate_fn

        result = dict(rewire(model_id, registry, **kwargs))
        result["tool"] = self.NAME
        return result
# #EXT-021-REQ-3 End
