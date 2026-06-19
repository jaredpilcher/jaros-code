"""Swarm member: ``reviewer`` — an LLM that APPROVES the reply or sends it back.

The model's verdict **drives the decision**: APPROVE advances the job to ``DONE``;
REVISE drives it to ``BLOCKED`` (needs revision). The chosen events are baked into
the recorded ``Decision``, so replay reconstructs the same outcome with no model
call. Part of the EXT-015 support-triage swarm demo.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "reviewer"


def _approves(text: str) -> bool:
    """Parse the model's one-word verdict; default to APPROVE when ambiguous/echo."""
    u = text.strip().upper()
    first = u.split()[0].strip(".,!:'\"") if u.split() else ""
    if first == "REVISE" or ("REVISE" in u and "APPROVE" not in u):
        return False
    return True


class ReviewerBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ticket = context.get("ticket", "") if isinstance(context, dict) else str(context)
        verdict = self._llm.complete(LlmRequest(prompt=(
            "You are a reply reviewer. Reply with ONLY one word: APPROVE to publish the reply, "
            "or REVISE if it needs changes.\n\n"
            f"Ticket: {ticket}"
        ))).text
        approved = _approves(verdict)
        # The model's verdict selects the events -> the reconstructed final state.
        events = ["start", "complete"] if approved else ["start", "block"]
        return [create_decision(
            id=f"rev-{uuid.uuid4().hex}",
            source=NAME,
            type="advance",
            payload={
                "events": events,
                "verdict": "approve" if approved else "revise",
                "note": f"review: {verdict.strip()[:60]}",
            },
        )]


def build(llm) -> ReviewerBoundary:
    return ReviewerBoundary(llm)
