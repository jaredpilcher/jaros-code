"""Generate-and-test solve helper (EXT-012 / REQ-12).

HONESTY NOTE: Candidate selection is ONLY by the model's own self-tests (derived
from the visible spec/intent), NEVER by the hidden oracle.  The hidden oracle is
never exposed to the model or to this module.

NOT YET wired into the default solve path — must be measured on held-out commits
(integrate-or-prune gate, EXT-012 REQ-7 / design.md "integrate-or-prune by
measurement") before any default use.

Public API
----------
generate_and_test_solve(
    intent, name, current_src, context, pkg, runtime,
    run_selftests, n=4, base_seed=0
) -> dict

    Uses the code-writer agent to generate *n* candidate implementations (one per
    varied seed), runs each through the provided *run_selftests* callable to obtain
    a self-test pass-count, then applies the ``code.generate_and_test`` tool to
    pick the best deterministically.

    Parameters
    ----------
    intent       : str  — Commit intent / task description (visible spec only).
    name         : str  — Target function name.
    current_src  : str | None — Existing implementation (may be None).
    context      : str  — Module-level context snippet (imports, neighbours).
    pkg          : str  — Package name (for test imports).
    runtime      : Runtime — Jaros Runtime instance (for Decision logging).
    run_selftests: callable(code: str) -> int
                          Caller-supplied function that takes a candidate source
                          string, runs the model's self-tests against it, and
                          returns the number of tests that pass (int >= 0).
                          This callable MUST use the model's own self-tests derived
                          from the visible spec — NEVER the hidden oracle.
    n            : int  — Number of candidates to generate (default 4).
    base_seed    : int  — Starting seed; candidate i uses seed base_seed+i
                          (reproducible, deterministic).

    Returns
    -------
    {
      "chosen":     <str>,   # best candidate source
      "index":      <int>,   # 0-based candidate index chosen
      "pass_count": <int>,   # self-test pass-count of the chosen candidate
      "candidates": [...],   # all N candidate sources (for debugging)
      "results":    [...],   # parallel pass-counts (for debugging)
    }
"""

from __future__ import annotations

import os
import sys
import uuid

# #EXT-012-REQ-12 Start

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_DIR = os.path.join(_REPO_ROOT, ".jaros-data", "tools")
_AGENTS_DIR = os.path.join(_REPO_ROOT, ".jaros-data", "agents")

for _d in (_REPO_ROOT, _TOOLS_DIR, _AGENTS_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)


def _load_code_agent(llm, seed: int):
    """Load the code-writer agent boundary with *llm* and the given *seed* baked in.

    Returns an object whose ``.decide(context)`` emits inert Decisions.
    """
    import importlib.util as _ilu

    agent_path = os.path.join(_AGENTS_DIR, "code_agent.py")
    spec = _ilu.spec_from_file_location("_code_agent_mod", agent_path)
    mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.build(llm)


def _apply_generate_and_test(runtime, candidates: list[str], results: list[int]) -> dict:
    """Apply the generate_and_test tool Decision through Runtime.apply."""
    from jaros.core import create_decision

    # Import the tool registration or instantiate directly
    import importlib.util as _ilu

    tool_path = os.path.join(_TOOLS_DIR, "generate_and_test_tool.py")
    spec = _ilu.spec_from_file_location("_gat_tool_mod", tool_path)
    mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    tool = mod.GenerateAndTestTool()

    decision = create_decision(
        id=f"gat-{uuid.uuid4().hex}",
        source="generate-and-test-solve",
        type="code.generate_and_test",
        payload={"candidates": candidates, "results": results},
    )

    # Validate manually since runtime may not have this tool registered yet.
    validation = tool.validate(decision)
    if not validation.ok:
        raise RuntimeError(
            f"generate_and_test tool rejected decision: {validation.reason}"
        )

    # Execute directly (deterministic — no side effects, no LLM call).
    return tool.execute(decision)


def generate_and_test_solve(
    intent: str,
    name: str,
    current_src: str | None,
    context: str,
    pkg: str,
    runtime,
    run_selftests,
    n: int = 4,
    base_seed: int = 0,
    *,
    llm=None,
    gherkin: str = "",
) -> dict:
    """Generate *n* candidate implementations and return the best by self-tests.

    See module docstring for full parameter and return-value specification.

    HONESTY: *run_selftests* MUST use only the model's own spec-derived self-tests.
    The hidden oracle is never touched here.
    """
    candidates: list[str] = []
    results: list[int] = []

    for i in range(n):
        seed = base_seed + i

        # If no LLM provided, we cannot generate; skip.
        if llm is None:
            candidates.append("")
            results.append(0)
            continue

        agent = _load_code_agent(llm, seed=seed)

        context_dict: dict = {
            "intent": intent,
            "name": name,
            "func": name,
            "current_src": current_src,
            "context": context,
            "pkg": pkg,
            "gherkin": gherkin,
            "seed": seed,
        }

        # The agent emits an inert Decision (two-plane discipline).
        decisions = agent.decide(context_dict)

        candidate_code = ""
        for dec in decisions:
            payload = dec.payload if isinstance(dec.payload, dict) else {}
            if dec.type == "code.write_file" and "content" in payload:
                candidate_code = payload["content"]
                break

        candidates.append(candidate_code)

        # Run self-tests (caller-supplied, must be spec-derived, not oracle).
        pass_count = run_selftests(candidate_code) if candidate_code else 0
        results.append(int(pass_count))

    # Apply the selection tool deterministically.
    selection = _apply_generate_and_test(runtime, candidates, results)

    return {
        "chosen": selection["chosen"],
        "index": selection["index"],
        "pass_count": selection["pass_count"],
        "candidates": candidates,
        "results": results,
    }

# #EXT-012-REQ-12 End
