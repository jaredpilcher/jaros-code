"""Swarm member: ``worker`` — drafts a reply; the LLM decides if it's a clean handoff.

The model **drives the handoff**: it drafts a reply, then judges whether it can
confidently resolve the ticket. A confident YES hands the draft off cleanly; an
unsure NO produces a bad handoff that the reviewer tool rejects on execution — so
swarm replay attributes that failure to the exact worker that produced it
(EXT-015 / REQ-3). Submitting ``{"bad": true}`` forces a bad handoff for the demo.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "worker"


def _confident(text: str) -> bool:
    """Parse the model's YES/NO self-assessment; default to YES when ambiguous/echo."""
    words = text.strip().upper().split()
    first = words[0].strip(".,!:'\"") if words else ""
    if first == "NO" or ("NO" in words and "YES" not in words):
        return False
    return True


class WorkerBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        ticket = ctx.get("ticket", "")
        draft = self._llm.complete(LlmRequest(prompt=f"Draft a one-sentence support reply to: {ticket}")).text
        # The model judges whether the draft is a confident, complete resolution.
        verdict = self._llm.complete(LlmRequest(prompt=(
            "Can you confidently and completely resolve this ticket with the reply below? "
            "Reply with ONLY one word: YES or NO.\n\n"
            f"Ticket: {ticket}\nReply: {draft[:120]}"
        ))).text
        confident = _confident(verdict)
        # A bad handoff happens when the model is unsure — or when the demo seeds it.
        ok = confident and not bool(ctx.get("bad", False))
        return [create_decision(
            id=f"work-{uuid.uuid4().hex}",
            source=NAME,
            type="swarm.handoff",
            payload={"draft": draft[:80], "ok": ok, "confidence": "yes" if confident else "no"},
        )]


def build(llm) -> WorkerBoundary:
    return WorkerBoundary(llm)
