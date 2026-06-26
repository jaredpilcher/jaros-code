"""Single-purpose agent ``gherkin-writer`` (EXT-012 / Jaros-native behavioral solve).

The FIRST grain of the behavioral solve: turn an intent (+ the current code) into a behavior
specification — 3-6 Given/When/Then scenarios pinning what "correct" means AFTER the change.
It does NOT implement or test anything; it makes ONE judgement (the behavior) and hands a
``code.write_file`` Decision to the deterministic tool plane to persist the spec.

Jaros-native by construction (PRIME-001 Tenet 1/3): the model emits an inert Decision; the
Runtime gates + executes (write_file tool) + hash-chain logs it, so every solve is replayable.
The proven prompt is the same one that drove the held-out 6/37 behavioral-solve result; here it
lives behind the agent boundary instead of a raw harness function.
"""
from __future__ import annotations

# #EXT-013-REQ-1 Start
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "gherkin-writer"

_PROMPT = (
    "You are changing a Python library function `{name}`.\nCOMMIT INTENT: {intent}\n{ctx}{cur}\n"
    "Write the behavior specification for `{name}` AFTER the change as 3-6 numbered Given/When/Then "
    "scenarios. Include BOTH the NEW behavior the intent requires AND existing behavior that must "
    "stay the same. Output ONLY the numbered scenarios."
)


class GherkinWriterBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = ctx.get("intent", "")
        name = ctx.get("func") or ctx.get("name", "")
        cur = (f"It currently is:\n{ctx['current_src']}\n" if ctx.get("current_src")
               else f"`{name}` does not exist yet.\n")
        module_ctx = f"Module context:\n{ctx['context']}\n" if ctx.get("context") else ""
        spec_path = ctx.get("spec_path", f".jcode/{name}.gherkin")
        params = {"seed": ctx["seed"]} if "seed" in ctx else {}
        reply = self._llm.complete(LlmRequest(prompt=_PROMPT.format(
            name=name, intent=intent, ctx=module_ctx, cur=cur), params=params)).text
        spec = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
        if not spec:
            return [create_decision(
                id=f"gk-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"], "note": "gherkin-writer: no spec produced"})]
        return [create_decision(
            id=f"gk-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": spec_path, "content": spec + "\n",
                     "note": "gherkin behavior spec (Given/When/Then)"})]


def build(llm) -> GherkinWriterBoundary:
    return GherkinWriterBoundary(llm)
# #EXT-013-REQ-1 End
