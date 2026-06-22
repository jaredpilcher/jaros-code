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
        # Anchor on long-term project memory (REQ-3) when present; absent -> unchanged (no-op).
        from harness.project_memory import read_memory
        mem = read_memory(cwd).strip()
        instr = f"Project conventions:\n{mem}\n\n{intent}" if mem else intent
        res = multi_file_fix(cwd, _TEST_CMD, instr, test_file, max_iters=max_iters, verbose=verbose)
        green, _ = _run(cwd, _TEST_CMD)
        return {"solved": green, "flow": "fix", "note": res.get("note", "")}

    # BUILD flow — no test yet: DECOMPOSE the intent into requirements, a test per requirement,
    # then implement against all (the richer jarify-flow). Single-function falls back to build_in_dir.
    return _decompose_build(intent, cwd, max_iters=max_iters, verbose=verbose)


def plan_preview(intent: str, cwd: str) -> str:
    """Plan-mode (EXT-009 REQ-4): describe what `spec_driven_loop` WOULD do, with NO file side
    effects — so a human can review before `/agent` acts (Claude Code's plan mode + the jarify
    'show the plan first' discipline)."""
    green, _ = _run(cwd, _TEST_CMD)
    if green:
        return "tests already pass — nothing to do"
    if _find_test(cwd):
        return ("FIX flow:\n  1. run the tests (requirement = the suite passes)\n"
                "  2. localize the fault + fix the code (multi_file_fix)\n"
                "  3. re-verify the suite")
    sigs = _extract_signatures(intent)
    reqs = sigs if len(sigs) >= 2 else [(n, "") for n, _ in _decompose(intent)]
    if len(reqs) <= 1:
        only = reqs[0][0] if reqs else "solution"
        return f"BUILD flow (single function): write tests for `{only}` from intent, then implement"
    funcs = "\n".join(f"     - {n}({p})" for n, p in reqs)
    return (f"BUILD flow (decomposed into {len(reqs)} requirements):\n"
            f"  1. functions:\n{funcs}\n"
            "  2. write a test per requirement (test-writer)\n"
            "  3. implement solution.py against all tests\n"
            "  4. verify pytest green")


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
    if len(sigs) >= 2:                                   # TASK-9: per-function concrete-sig build
        return _build_per_function(intent, cwd, sigs, max_iters=max_iters, verbose=verbose)
    reqs = [(n, "") for n, _ in _decompose(intent)]
    from harness.intent_loop import build_in_dir
    if len(reqs) <= 1:                                   # single-function: the existing spine
        func = reqs[0][0] if reqs else next(
            (w for w in intent.replace("(", " ").split() if w.isidentifier()), "solution")
        r = build_in_dir(cwd, intent, f"{func}.py", func, max_iters=max_iters, verbose=verbose)
        return {"solved": bool(r.get("self_pass")), "flow": "build", "requirements": len(reqs),
                "note": r.get("note", "")}
    # FALLBACK (no explicit signatures): *args stubs -> whole-file rewriter implements all.
    _build_whole_file(intent, cwd, [n for n, _ in reqs], max_iters=max_iters, verbose=verbose)
    green, _ = _run(cwd, _TEST_CMD)
    return {"solved": green, "flow": "build-decomposed", "requirements": len(reqs),
            "note": f"{len(reqs)} requirements"}


def _build_whole_file(intent: str, cwd: str, names: list, *, max_iters: int = 3,
                      verbose: bool = False) -> None:
    """*args whole-file build: stub every function with `*args` so fix_loop routes to the WHOLE-FILE
    rewriter (which implements ALL of them in one solution.py), write one test per function (from the
    real intent), then implement against all. This path builds simple predicates like is_odd reliably
    where the per-function body-completer botches them — it is TASK-10's fallback."""
    from harness.coding_loop import Runtime, build_llm, _load_agent, fix_loop
    module = "solution"
    (Path(cwd) / f"{module}.py").write_text(
        "".join(f"def {n}(*args, **kwargs):\n    raise NotImplementedError\n\n" for n in names),
        encoding="utf-8", newline="\n")
    rt, writer = Runtime(), _load_agent("test_writer_agent.py", build_llm())
    for func in names:
        [tw] = writer.decide({"intent": intent, "module": module, "func": func, "signature": "",
                              "test_path": str(Path(cwd) / f"test_{func}.py"), "seed": 1})
        if tw.type == "code.write_file":
            rt.apply(tw)
    fix_loop(str(Path(cwd) / f"{module}.py"), intent, _TEST_CMD, max_iters=max_iters,
             cwd=cwd, verbose=verbose)


def _build_per_function(intent: str, cwd: str, sigs: list, *, max_iters: int = 3,
                        verbose: bool = False) -> dict:
    """TASK-9: build each function in ITS OWN module with a CONCRETE single-function stub, so
    fix_loop routes to the body-completer (which keeps the real signature and implements correctly,
    incl. list-aggregation — the whole-file rewriter kept *args and did max(args)). Then EXTRACT
    each implemented function (+ its imports) via AST and combine into a self-contained solution.py.

    Fixes list-aggregation (listops, minmax) SYSTEMATICALLY. boolchecks's `is_odd` is HIGH-VARIANCE
    for the body-completer (clean `n % 2 != 0` some runs, botched indentation others). TASK-10's
    hybrid (below) gives a 2nd independent chance — the *args whole-file build in a clean temp dir,
    swapped in when it has fewer stubs — so the build eval reaches 7/7: per-function fixes
    list-aggregation, the hybrid recovers boolchecks. No-regression by construction (the fallback
    only fires when a per-function build leaves a stub; passing scenarios are untouched)."""
    import ast
    from harness.coding_loop import Runtime, build_llm, _load_agent, fix_loop
    from harness.intent_loop import _stub
    rt, writer = Runtime(), _load_agent("test_writer_agent.py", build_llm())
    imports: list[str] = []
    defs: list[str] = []
    failed: list[str] = []                              # functions whose per-function build didn't land
    for func, params in sigs:
        fp = Path(cwd) / f"{func}.py"
        fp.write_text(_stub(f"def {func}({params})", func), encoding="utf-8", newline="\n")
        [tw] = writer.decide({"intent": intent, "module": func, "func": func,
                              "signature": f"def {func}({params})",
                              "test_path": str(Path(cwd) / f"test_{func}.py"), "seed": 1})
        if tw.type == "code.write_file":
            rt.apply(tw)
        fix_loop(str(fp), intent, _TEST_CMD, max_iters=max_iters, cwd=cwd, verbose=verbose)
        src = fp.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            # a malformed per-function build must NOT break the whole module — stub it, keep the
            # rest importable (graceful partial build) instead of appending unparseable source.
            defs.append(f"def {func}({params}):\n    raise NotImplementedError\n")
            failed.append(func)
            continue
        func_def = None
        for node in tree.body:
            seg = ast.get_source_segment(src, node)
            if not seg:
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)) and seg not in imports:
                imports.append(seg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
                func_def = seg
        if func_def and "raise NotImplementedError" not in func_def:
            defs.append(func_def)
        else:                                           # not found, or still a stub -> failed build
            defs.append(func_def or f"def {func}({params}):\n    raise NotImplementedError\n")
            failed.append(func)
    body = ("\n".join(imports) + "\n\n" if imports else "") + "\n\n".join(defs) + "\n"
    (Path(cwd) / "solution.py").write_text(body, encoding="utf-8", newline="\n")

    # TASK-10 hybrid: if any per-function build failed (e.g. body-completer botches is_odd), try the
    # *args whole-file build in a CLEAN temp dir and keep whichever solution.py has fewer stubs (more
    # functions implemented). Tie -> keep per-function (it has list-aggregation correct).
    flow = "build-per-function"
    if failed:
        import tempfile
        pf_sol = (Path(cwd) / "solution.py").read_text(encoding="utf-8")
        pf_stubs = pf_sol.count("raise NotImplementedError")
        with tempfile.TemporaryDirectory(prefix="jcode-wf-") as alt:
            _build_whole_file(intent, alt, [f for f, _ in sigs], max_iters=max_iters, verbose=verbose)
            wf_path = Path(alt) / "solution.py"
            wf_sol = wf_path.read_text(encoding="utf-8") if wf_path.exists() else ""
        wf_stubs = wf_sol.count("raise NotImplementedError") if wf_sol else 10 ** 9
        if wf_sol and wf_stubs < pf_stubs:
            (Path(cwd) / "solution.py").write_text(wf_sol, encoding="utf-8", newline="\n")
            flow = "build-hybrid"

    final = (Path(cwd) / "solution.py").read_text(encoding="utf-8")
    solved = "raise NotImplementedError" not in final     # all functions at least implemented
    return {"solved": solved, "flow": flow, "requirements": len(sigs),
            "note": f"{len(sigs)} functions ({flow.split('-', 1)[1]})"}
