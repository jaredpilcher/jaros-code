"""harness/behavioral_solve.py — THE canonical behavioral solve (EXT-012 system).

The local 2B authors a Gherkin behavior spec (with a COMPREHENSION step that pins the exact case the
intent names, read literally), derives its OWN tests from that spec, implements the function, and fixes
the code against those tests. This is jaros-code's DEFAULT solve path — the integrated stack of the
mechanisms proven on held-out real commits:

  multi-function localize (caller's job) -> Gherkin + comprehension -> self-tests -> code -> fix.

Proven (intent-only, hidden-oracle, no leakage): more-itertools held-out 6/37 = 16.2% vs the
multi-function baseline 4/37 = 10.8%; cross-repo combined 7/48 vs 5/48 (see .jarify/EXT-012).

It is ENVIRONMENT-AGNOSTIC: `run_tests(code, test_code) -> (passed, feedback)` adapts it to the eval
(Docker on a repo checkout) or the product (`jcode` -> local pytest), so the evaluation harness and the
real product share exactly ONE solve. New mechanisms (retrieval, etc.) enter here as layers, measured
then kept or pruned — the system only moves forward.
"""
from __future__ import annotations

from typing import Callable

# The proven Gherkin grains currently live in commit_replay (the eval's first home); the eval will be
# refactored to import them from here. Reusing them keeps ONE implementation feeding both clients.
from harness.commit_replay import g_gherkin, g_selftests, g_code   # noqa: E402


def behavioral_solve(intent: str, name: str, current_src: str | None, context: str, pkg: str,
                     run_tests: Callable[[str, str], tuple[bool, str]],
                     max_fix: int = 2) -> dict:
    """Canonical behavioral solve. Returns {code, gherkin, tests, self_pass}.

    intent       : the change to make (commit message / user request).
    name         : the function to write/repair.
    current_src  : its current source, or None if new.
    context      : module preamble (imports/sentinels) the model can use.
    pkg          : import package for the self-tests (`from <pkg> import <name>`).
    run_tests    : env adapter: (candidate_code, test_code) -> (passed, short_feedback).
    """
    gherkin = g_gherkin(intent, name, current_src, context)          # behavior spec (+comprehension)
    tests = g_selftests(name, gherkin, pkg)                          # the model's OWN tests, from spec
    code = g_code(intent, name, current_src, context, gherkin)       # first implementation
    self_pass = False
    for _ in range(max_fix + 1):                                     # fix against its own tests
        if not code:
            break
        self_pass, feedback = run_tests(code, tests)
        if self_pass:
            break
        code = g_code(intent, name, current_src, context, gherkin, feedback)
    return {"code": code, "gherkin": gherkin, "tests": tests, "self_pass": self_pass}


# --- Agentic variant: bootstrap, then the 2B JUDGES the revision layer at each failure -------------
# Smoke finding: a free 2B-judge collapses to "code" — it won't even pick "run" among 2 options. So a
# small model can't run the mechanical control flow. Ground it: bootstrap (spec->tests->code) and the
# RUN are deterministic; the 2B's judgement goes where it adds value — when the self-tests FAIL,
# diagnose WHICH layer is wrong and revise it (emergent revision path, any layer revisited).
_REV = {"code": "the implementation has a LOGIC bug -> rewrite the code",
        "gherkin": "the behavior spec MISUNDERSTOOD the intent -> rewrite the spec (and its tests)",
        "repair": "the logic is right but the code has broken indentation/syntax",
        "done": "stop — it cannot be fixed"}


def _judge_revision(intent: str, name: str, fb: str, temp: float) -> str:
    """The 2B as a judge AT THE FAILURE: diagnose which layer to revise. One short call."""
    from harness.pass1_eval import _llm
    from jaros.llm import LlmRequest
    menu = "\n".join(f"  {a} = {d}" for a, d in _REV.items())
    prompt = (f"You are building the Python function `{name}`.\nGOAL: {intent}\n"
              f"Its self-tests FAILED with:\n{str(fb)[:400]}\n\n"
              f"Diagnose the cause and pick the SINGLE next action:\n{menu}\nAnswer with ONLY one word.")
    out = _llm().complete(LlmRequest(prompt=prompt,
                                     params={"temperature": temp, "max_tokens": 8})).text.strip().lower()
    return next((a for a in _REV if a in out), "code")


def behavioral_solve_agentic(intent: str, name: str, current_src: str | None, context: str, pkg: str,
                             run_tests: Callable[[str, str], tuple[bool, str]],
                             max_rounds: int = 4, temp: float = 0.0) -> dict:
    """Agentic behavioral solve: bootstrap (spec->tests->code), then auto-run + the 2B judges the
    REVISION layer at each failure (code / gherkin / repair / done) — emergent, layers revisited.
    temp>0 -> non-deterministic. Honest: self-tests scaffold; the hidden oracle scores (caller).
    Returns {code, gherkin, tests, self_pass, trace}."""
    from harness.commit_replay import g_gherkin as _gk, g_selftests as _gt, g_code as _gc
    gherkin = _gk(intent, name, current_src, context)
    tests = _gt(name, gherkin, pkg)
    code = _gc(intent, name, current_src, context, gherkin)
    trace = ["spec", "tests", "code"]
    passed = False
    for _ in range(max_rounds):
        passed, fb = run_tests(code, tests)
        trace.append("run")
        if passed:
            break
        a = _judge_revision(intent, name, str(fb), temp)
        trace.append(a)
        if a == "done":
            break
        if a == "gherkin":                                   # spec was wrong -> re-spec, re-test, re-code
            gherkin = _gk(intent, name, current_src, context)
            tests = _gt(name, gherkin, pkg)
            code = _gc(intent, name, current_src, context, gherkin, str(fb)[:400])
        elif a == "repair":
            from harness.pass1_eval import _bc, _llm
            code = _bc.repair_indentation(_llm(), code)
        else:                                                # "code": logic bug -> revise the code
            code = _gc(intent, name, current_src, context, gherkin, str(fb)[:400])
    return {"code": code, "gherkin": gherkin, "tests": tests, "self_pass": passed, "trace": trace}
