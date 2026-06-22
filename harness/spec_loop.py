"""Spec-driven loop (EXT-009): the jarify-FLOW alternative to the free-form agent loop.

The agentic-eval finding: a 2B free-form planner is FLAKY — it sometimes never even plans the
`fix` step, so the run fails for no good reason. The jarify methodology fixes this by removing the
open-ended judgement entirely: decompose intent into checkable REQUIREMENTS, then run a
DETERMINISTIC flow (verify -> implement -> verify) where the model only fills CONSTRAINED
sub-tasks (write a test, write code) — never "what steps?". This is the decomposition principle at
the WORKFLOW level; the owner has seen this structure converge low-reasoning models on intent.

Two flows, chosen deterministically (not by the model):
  * FIX  — a failing test already encodes the requirement ("the suite passes"); run the structured
           localize->fix->gate pipeline (multi_file_fix). The model only writes the fix.
  * BUILD — no failing test: the requirement is the intent; the test-writer turns it into checkable
           tests, then implement against them (build_in_dir). The model only writes tests + code.
"""
from __future__ import annotations

import re
from pathlib import Path

from harness.multi_file import _run, multi_file_fix

_TEST_CMD = "python -m pytest -q"


def _find_test(cwd: str) -> str:
    for p in Path(cwd).rglob("*.py"):
        if p.name.startswith("test"):
            return str(p)
    return ""


def spec_driven_loop(intent: str, cwd: str, *, max_iters: int = 3, verbose: bool = False) -> dict:
    """Structured (jarify-flow) loop. The FLOW is deterministic; the 2B never chooses the steps —
    it only fills the constrained sub-task (the fix / the code). Returns {solved, flow, note}."""
    green, _ = _run(cwd, _TEST_CMD)
    if green:
        return {"solved": True, "flow": "already-green", "note": "requirement already met"}

    test_file = _find_test(cwd)
    if test_file:
        # FIX flow — the failing test IS the requirement; run the structured repair pipeline.
        res = multi_file_fix(cwd, _TEST_CMD, intent, test_file, max_iters=max_iters, verbose=verbose)
        green, _ = _run(cwd, _TEST_CMD)
        return {"solved": green, "flow": "fix", "note": res.get("note", "")}

    # BUILD flow — no test yet: DECOMPOSE the intent into requirements, a test per requirement,
    # then implement against all (the richer jarify-flow). Single-function falls back to build_in_dir.
    return _decompose_build(intent, cwd, max_iters=max_iters, verbose=verbose)


def _decompose(intent: str, max_reqs: int = 5) -> list[tuple[str, str]]:
    """jarify-flow: ONE constrained model call -> a list of (func_name, behavior) requirements.
    The 2B only does this bounded sub-task (list functions), never open-ended planning."""
    from harness.coding_loop import build_llm
    from jaros.llm import LlmRequest
    prompt = ("Decompose this build request into the Python functions it needs. Output ONLY lines "
              f"of the form 'func_name: one-line behavior', at most {max_reqs} lines, no prose.\n\n"
              f"Request: {intent}")
    reply = build_llm().complete(LlmRequest(prompt=prompt, params={"max_tokens": 200})).text
    return _parse_reqs(reply, max_reqs)


def _parse_reqs(reply: str, max_reqs: int = 5) -> list[tuple[str, str]]:
    """Parse 'func_name: behavior' lines into (name, behavior) requirements — pure + testable."""
    reqs = []
    for line in reply.splitlines():
        line = line.strip().lstrip("-*0123456789.) ").strip()
        if ":" in line:
            name, beh = line.split(":", 1)
            name = name.strip().split("(")[0].split()[0] if name.strip() else ""
            if name.isidentifier() and beh.strip():
                reqs.append((name, beh.strip()))
    return reqs[:max_reqs]


_SIG_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(([^)]*)\)")
_SIG_STOP = {"a", "an", "the", "module", "function", "def", "list", "str", "int"}


def _extract_signatures(intent: str) -> list[tuple[str, str]]:
    """DETERMINISTIC: pull explicit `name(params)` function signatures from the intent. Reliable
    (no 2B naming/param errors) when the intent names functions, which is the common case; the
    2B `_decompose` is only the fallback. De-duped, order-preserving."""
    out, seen = [], set()
    for m in _SIG_RE.finditer(intent):
        name, params = m.group(1), m.group(2).strip()
        if name.isidentifier() and name not in _SIG_STOP and not name.startswith("_") and name not in seen:
            seen.add(name)
            out.append((name, params))
    return out


def _decompose_build(intent: str, cwd: str, *, max_iters: int = 3, verbose: bool = False) -> dict:
    sigs = _extract_signatures(intent)                  # deterministic signatures beat 2B params
    reqs = sigs if len(sigs) >= 2 else [(n, "") for n, _ in _decompose(intent)]
    from harness.intent_loop import build_in_dir
    if len(reqs) <= 1:                                   # single-function: the existing spine
        func = reqs[0][0] if reqs else next(
            (w for w in intent.replace("(", " ").split() if w.isidentifier()), "solution")
        r = build_in_dir(cwd, intent, f"{func}.py", func, max_iters=max_iters, verbose=verbose)
        return {"solved": bool(r.get("self_pass")), "flow": "build", "requirements": len(reqs),
                "note": r.get("note", "")}
    # multi-requirement: one module, a stub + a test per requirement (with the REAL signature),
    # implement against all. The stubs use *args so fix_loop routes to the WHOLE-FILE rewriter
    # (which implements ALL functions); the test-writer gets the real signature so the tests — and
    # therefore the rewrite — use the correct params (the 0/3 lesson: concrete stubs broke routing).
    from harness.coding_loop import Runtime, build_llm, _load_agent, fix_loop
    module = "solution"
    (Path(cwd) / f"{module}.py").write_text(
        "".join(f"def {n}(*args, **kwargs):\n    raise NotImplementedError\n\n" for n, _ in reqs),
        encoding="utf-8", newline="\n")
    rt, writer = Runtime(), _load_agent("test_writer_agent.py", build_llm())
    for func, params in reqs:
        [tw] = writer.decide({"intent": intent, "module": module, "func": func,
                              "signature": f"def {func}({params})",
                              "test_path": str(Path(cwd) / f"test_{func}.py"), "seed": 1})
        if tw.type == "code.write_file":
            rt.apply(tw)
    fix_loop(str(Path(cwd) / f"{module}.py"), intent, _TEST_CMD, max_iters=max_iters,
             cwd=cwd, verbose=verbose)
    green, _ = _run(cwd, _TEST_CMD)
    return {"solved": green, "flow": "build-decomposed", "requirements": len(reqs),
            "note": f"{len(reqs)} requirements"}
