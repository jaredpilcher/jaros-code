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
