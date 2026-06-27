"""Single-purpose agent ``planner`` (EXT-015 / plan-then-code decomposition).

The OPTIONAL PRE-GRAIN before code generation: given the commit intent, function
name, and module context, the 2B generates a CONCISE natural-language IMPLEMENTATION
STRATEGY — a short numbered list of concrete steps + edge cases to handle.

Research basis ('Strategic Decomposition & Filtering for SLMs'): a 1.5B model
gained +30% relative by first generating a strategy, then a DETERMINISTIC filter
cleaned it, then code was written FROM the filtered plan.  The deterministic filter
is the key insight — small models can't improve their own scaffold, so filtering
MUST be in the execution plane (two-plane, Tenet 1/2).

This agent makes ONE judgement (what are the steps?) and emits an inert
``code.write_file`` Decision, consistent with Tenet 1 and the agent/tool split
pattern established by gherkin_agent / code_agent.

NAME='planner', build(llm) mirrors gherkin_agent exactly.
"""
from __future__ import annotations

# #EXT-015-REQ-1 Start
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "planner"

_PROMPT = (
    "You are implementing the Python function `{name}`.\n"
    "COMMIT INTENT: {intent}\n"
    "{ctx}{cur}\n"
    "Write a CONCISE implementation strategy as a numbered list of concrete steps.\n"
    "Include: key algorithmic steps, edge cases to handle (empty input, None, zero, "
    "boundary values), and any important invariants to preserve.\n"
    "Do NOT write any code. Do NOT copy the existing function body. "
    "Do NOT include examples, sample inputs/outputs, or prose preamble.\n"
    "Output ONLY the numbered steps (e.g. '1. Check for ...')."
)


class PlannerBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = ctx.get("intent", "")
        name = ctx.get("func") or ctx.get("name", "")
        cur = (f"It currently is:\n{ctx['current_src']}\n" if ctx.get("current_src")
               else f"`{name}` does not exist yet.\n")
        module_ctx = f"Module context:\n{ctx['context']}\n" if ctx.get("context") else ""
        plan_path = ctx.get("plan_path", f".jcode/{name}.plan")
        params = {"temperature": 0.0, "max_tokens": 400}
        if "seed" in ctx:
            params["seed"] = ctx["seed"]
        reply = self._llm.complete(LlmRequest(
            prompt=_PROMPT.format(name=name, intent=intent, ctx=module_ctx, cur=cur),
            params=params,
        )).text
        # Strip any accidental code fences (same defensive pattern as gherkin_agent)
        strategy = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
        if not strategy:
            return [create_decision(
                id=f"pl-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"],
                         "note": "planner: no strategy produced"})]
        return [create_decision(
            id=f"pl-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": plan_path, "content": strategy + "\n",
                     "note": "implementation strategy (numbered steps + edge cases)"})]


def build(llm) -> PlannerBoundary:
    return PlannerBoundary(llm)
# #EXT-015-REQ-1 End
