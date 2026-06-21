"""Tiny single-purpose agent ``planner`` (EXT-004 multi-step): given a natural-language dev
request, emit an INERT ordered PLAN — a list of {action, arg} steps drawn from a fixed verb
set. The model only proposes the plan (a judgement it does reliably, verified on gemma-4-e2b);
a deterministic executor runs each step. Two-plane discipline: no side effects here.

The 2B's step ARGS are often vague ("the identified bug"); that's fine — the executor grounds
them (run -> the project's test command, fix -> multi_file_fix which locates the file, etc.).
What must be reliable is the STRUCTURE (valid verbs, sensible order), which it is.
"""
from __future__ import annotations

import json
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "planner"
VERBS = ("find", "read", "fix", "run")

_PROMPT = (
    "You are a coding-assistant planner. Output ONLY a JSON list of steps to carry out the "
    "request. Each step is {\"action\": one of [find, read, fix, run], \"arg\": \"...\"}. "
    "Keep it short (2-5 steps), in a sensible order. No prose, just the JSON list.\n\n"
    "REQUEST: {request}\nSTEPS:"
)


def parse_plan(raw: str) -> list[dict]:
    """Pull the JSON step list out of the model text and keep only well-formed steps whose
    action is a known verb. Robust to fences / trailing prose."""
    raw = re.sub(r"```[\w+-]*", "", raw).replace("```", "")
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    plan = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            action = str(it.get("action", "")).strip().lower()
            if action in VERBS:
                plan.append({"action": action, "arg": str(it.get("arg", "")).strip()})
    return plan


class PlannerBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        request = ctx.get("request", "")
        reply = self._llm.complete(LlmRequest(
            prompt=_PROMPT.replace("{request}", request), params={"max_tokens": 220})).text
        plan = parse_plan(reply)
        return [create_decision(id=f"plan-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "complete"], "plan": plan,
                         "note": f"planner: {len(plan)} steps"})]


def build(llm) -> PlannerBoundary:
    return PlannerBoundary(llm)
