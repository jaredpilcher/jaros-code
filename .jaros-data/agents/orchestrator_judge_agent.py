"""Single-purpose judge-agent ``orchestrator-judge`` (EXT-013 / REQ-3).

Given the current solve STATE — intent, function name, which artifacts exist
(spec/tests/code), last test feedback, and the step count — emits ONE inert
``orchestrate.next`` Decision naming the next action.  The action is chosen
from a CONSTRAINED set of proven layers only:

    code    — the implementation has a logic bug -> rewrite the code
    gherkin — the behavior spec misunderstood the intent -> rewrite the spec
    repair  — logic is right but code has broken indentation/syntax
    done    — stop (success OR budget exhausted)

This mirrors the ``_judge_revision`` logic in ``harness/behavioral_solve.py``:
the model makes ONE short call that must return one of the four tokens; any
unrecognised output falls back to the safe default ``"code"``.

Grounding rules (so the weak 2B cannot degenerate, as the smoke showed):
1. Mechanical steps (bootstrap: spec->tests->code) are handled OUTSIDE this
   agent by the deterministic orchestrator loop — this agent is ONLY called at
   the failure-revision decision point.
2. A step-budget guard forces ``"done"`` when ``step >= max_steps``, so the
   loop is unconditionally bounded regardless of model output.

Jaros-native (Tenet 1/3): emits an inert Decision; the Runtime gates + logs it;
the deterministic loop reads the payload and dispatches — the agent never
executes anything itself.
"""
from __future__ import annotations

# #EXT-013-REQ-3 Start
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "orchestrator-judge"

# The full action set — mirrors _REV in behavioral_solve.py exactly.
_ACTIONS = {"code", "gherkin", "repair", "done"}
_DEFAULT_ACTION = "code"

_REV_DESCRIPTIONS = {
    "code":    "the implementation has a LOGIC bug -> rewrite the code",
    "gherkin": "the behavior spec MISUNDERSTOOD the intent -> rewrite the spec (and its tests)",
    "repair":  "the logic is right but the code has broken indentation/syntax",
    "done":    "stop — it cannot be fixed",
}

_PROMPT = (
    "You are building the Python function `{name}`.\n"
    "GOAL: {intent}\n"
    "Its self-tests FAILED with:\n{feedback}\n\n"
    "Diagnose the cause and pick the SINGLE next action:\n"
    "{menu}\n"
    "Answer with ONLY one word."
)

DEFAULT_MAX_STEPS = 8


class OrchestratorJudgeBoundary:
    """Grounded judge: emit the next-action Decision for the behavioral-solve loop.

    Parameters
    ----------
    llm:
        LLM client (jaros.llm-compatible).
    max_steps:
        Hard budget.  When ``context["step"]`` >= this value the agent emits
        ``"done"`` unconditionally (no model call needed).
    """

    def __init__(self, llm, *, max_steps: int = DEFAULT_MAX_STEPS) -> None:
        self._llm = llm
        self._max_steps = max_steps

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = ctx.get("intent", "")
        name   = ctx.get("func") or ctx.get("name", "")
        step   = int(ctx.get("step", 0))
        feedback = str(ctx.get("feedback", ""))[:400]

        did = f"oj-{uuid.uuid4().hex}"

        # --- Step-budget guard (deterministic — no model call) ---
        if step >= self._max_steps:
            return [create_decision(
                id=did, source=NAME, type="orchestrate.next",
                payload={"action": "done",
                         "reason": f"step budget exhausted ({step}/{self._max_steps})"})]

        # --- Short LLM call: pick the revision layer ---
        menu = "\n".join(f"  {a} = {d}" for a, d in _REV_DESCRIPTIONS.items())
        prompt = _PROMPT.format(
            name=name, intent=intent, feedback=feedback, menu=menu)

        params: dict = {"temperature": 0.0, "max_tokens": 8}
        if "seed" in ctx:
            params["seed"] = ctx["seed"]
        if "temperature" in ctx:
            params["temperature"] = ctx["temperature"]

        raw = self._llm.complete(LlmRequest(prompt=prompt, params=params)).text
        token = raw.strip().lower()
        # Ground: pick the first recognised action token in the output;
        # fall back to the safe default if nothing matches.
        action = next((a for a in _ACTIONS if a in token), _DEFAULT_ACTION)

        return [create_decision(
            id=did, source=NAME, type="orchestrate.next",
            payload={"action": action, "reason": raw.strip()[:200]})]


def build(llm, *, max_steps: int = DEFAULT_MAX_STEPS) -> OrchestratorJudgeBoundary:
    """Factory — mirrors the ``build(llm)`` convention used by all agents in this package."""
    return OrchestratorJudgeBoundary(llm, max_steps=max_steps)
# #EXT-013-REQ-3 End
