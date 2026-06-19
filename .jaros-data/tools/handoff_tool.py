"""Custom tool ``swarm.handoff`` — the reviewer accepting a worker's draft.

Deterministic Execution-Plane handler for the worker -> reviewer handoff. A
handoff with ``ok: false`` is structurally valid data (so it passes the gate and
is recorded) but is **rejected on execution** — modelling a bad handoff one
member passed to another. Because it is recorded then fails deterministically,
``jaros replay`` reproduces the swarm byte-identically AND attributes the failure
to the exact worker + decision that produced it (EXT-015 / REQ-3).
"""

from __future__ import annotations

from jaros.core.decision_gate import ValidationResult


class HandoffTool:
    NAME = "swarm.handoff"

    def validate(self, decision) -> ValidationResult:
        if not isinstance(decision.payload, dict):
            return ValidationResult.reject("handoff payload must be a JSON object")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        draft = payload.get("draft", "")
        if not payload.get("ok", False):
            raise RuntimeError(f"reviewer rejected the handoff draft: {draft[:40]!r}")
        return {"tool": self.NAME, "accepted": True, "chars": len(draft)}
