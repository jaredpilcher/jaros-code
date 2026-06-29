"""Execution-plane tool ``model.route`` (EXT-021, TASK-25).

Pass-through logging tool that lets the routing Decision flow through
Runtime.apply (gate -> executor -> DecisionLog) so the routing choice is
hash-chain logged and byte-identically replayable — no side effects.

Decision payload:
  model_id       (str)   — the selected model registry id
  problem_class  (str)   — the classified problem class
  confidence     (float) — 0.0-1.0
  rationale      (str)   — classification rationale (optional)

Returns a record of the routed model and class (pure data, no host effects).

Tenet guarantees
----------------
Tenet 1: no side effects — this tool records the inert Decision only.
Tenet 3: the routing choice is hash-chain logged for honest, replayable audit.
"""
from __future__ import annotations

from jaros.core.decision_gate import ValidationResult


# #EXT-021-REQ-2 Start
class ModelRouteTool:
    NAME = "model.route"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        model_id = payload.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            return ValidationResult.reject(
                "model.route: payload must have a non-empty 'model_id' string"
            )
        problem_class = payload.get("problem_class")
        if not isinstance(problem_class, str) or not problem_class.strip():
            return ValidationResult.reject(
                "model.route: payload must have a non-empty 'problem_class' string"
            )
        confidence = payload.get("confidence")
        if not isinstance(confidence, (int, float)):
            return ValidationResult.reject(
                "model.route: payload must have a numeric 'confidence' field"
            )
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        """Pass-through: record the routing Decision (no side effects)."""
        payload = decision.payload
        return {
            "tool": self.NAME,
            "model_id": payload.get("model_id"),
            "problem_class": payload.get("problem_class"),
            "confidence": payload.get("confidence"),
        }
# #EXT-021-REQ-2 End
