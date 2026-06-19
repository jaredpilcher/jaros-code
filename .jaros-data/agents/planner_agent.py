"""Swarm member: ``planner`` — an LLM triage gate that ACCEPTS or REJECTS a ticket.

The model's verdict **drives the decision**, not just a note: an ACCEPT advances
the job to ``DONE``; a REJECT drives it to ``FAILED``. The chosen events are baked
into the recorded ``Decision``, so replay reconstructs the same outcome with no
model call — the LLM decided *what* (accept vs reject), the deterministic executor
did *how* (the transitions). Part of the EXT-015 support-triage swarm demo.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "planner"


def _accepts(text: str) -> bool:
    """Parse the model's one-word verdict; default to ACCEPT when ambiguous/echo."""
    u = text.strip().upper()
    first = u.split()[0].strip(".,!:'\"") if u.split() else ""
    if first == "REJECT" or ("REJECT" in u and "ACCEPT" not in u):
        return False
    return True


class PlannerBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ticket = context.get("ticket", "") if isinstance(context, dict) else str(context)
        verdict = self._llm.complete(LlmRequest(prompt=(
            "You are a support-ticket triage gate. Reply with ONLY one word: "
            "ACCEPT if this is a genuine support request, or REJECT if it is spam or abuse.\n\n"
            f"Ticket: {ticket}"
        ))).text
        accepted = _accepts(verdict)
        # The model's verdict selects the events -> the reconstructed final state.
        events = ["start", "complete"] if accepted else ["start", "fail"]
        return [create_decision(
            id=f"plan-{uuid.uuid4().hex}",
            source=NAME,
            type="advance",
            payload={
                "events": events,
                "verdict": "accept" if accepted else "reject",
                "note": f"triage: {verdict.strip()[:60]}",
            },
        )]


def build(llm) -> PlannerBoundary:
    return PlannerBoundary(llm)
