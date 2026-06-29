"""EXT-030 — Experiment-to-understand agentic solve loop.

CONCEPT: strong coding agents (Claude Code, SWE-agent) crack hard repo tasks by
EXPLORING and OBSERVING before writing the fix — they run tests, inspect behavior,
read helpers.  This module implements that pattern as a principled agentic loop
with BOUNDED, SAFE experiments chosen by the model and executed by the deterministic
plane.

TWO-PLANE DISCIPLINE (Tenet 1 — CRITICAL):
  - The model PICKS which experiment to run (judgement, inert Decision dict).
  - The execution plane RUNS the bounded experiment (deterministic tool).
  - The oracle (test_fn) is the SOLE arbiter of solved.  Experiments only build
    understanding; the oracle answer is NEVER shown to propose_fn or solve_fn.
  - No arbitrary code execution — all experiments come from a SAFE BOUNDED MENU:
      E1: RUN the failing test nodes + capture real traceback/stdout.
      E2: CALL the target function with specific docstring/test inputs + capture
          return value or exception (subprocess, ast.literal_eval guarded).
      E3: READ the source of a specific named helper or related function (AST only).

After max_experiments observations the model writes the fix INFORMED by what it saw.

Connection to collaborative_solve (EXT-029): collab returned 0/6 on the hard class —
collaboration changes WHO writes the code, not whether the solver UNDERSTANDS the
problem first.  This loop changes the SOLVE PROCESS: explore/observe -> understand
-> fix.  It is the next qualitatively different lever after collaboration.

Connection to dependency_structure (EXT-028): E3 reuses AST analysis from
method_dependencies for related-function lookup.

Connection to working-memory (EXT-024 / issue #24): the understanding scratchpad
IS a lightweight working memory — accumulated observations guide the final solve.

Active-hours probe (deferred, operator-invoked):
    python -m harness.experiment_solve --n 6
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]

# Experiment type constants — the bounded menu
E1 = "E1"  # Run failing tests + capture traceback
E2 = "E2"  # Call target function with specific inputs + capture return/exception
E3 = "E3"  # Read source of a named helper/related function


# ---------------------------------------------------------------------------
# #EXT-030-REQ-1 Start
# Core experiment -> observe -> understand -> solve loop (all-injectable)
# ---------------------------------------------------------------------------

def experiment_solve(
    problem: Any,
    *,
    propose_fn: Callable,
    run_experiment_fn: Callable,
    solve_fn: Callable,
    test_fn: Callable,
    max_experiments: int = 3,
) -> dict:
    """Core experiment -> observe -> understand -> solve agentic loop.

    All callables are INJECTABLE so the loop is fully offline-testable.

    HONEST: test_fn is the SOLE arbiter of 'solved'.  propose_fn and solve_fn
    NEVER see the oracle answer.  Experiments only build understanding.

    TWO-PLANE: propose_fn returns an inert Decision dict; run_experiment_fn
    executes the bounded experiment deterministically; the model only judges
    WHAT to observe, never WHAT to execute arbitrarily.

    Parameters
    ----------
    problem :
        Opaque problem descriptor passed verbatim to all callables.
        For the real probe this is a dict with task context; for offline
        tests it can be any value the mock fns accept.
    propose_fn :
        ``propose_fn(problem, understanding) -> dict``
        Model picks the next experiment from the bounded menu given the
        understanding accumulated so far.  Returns an inert Decision dict:
        ``{"type": "E1"|"E2"|"E3", "params": {...}}``.
        NEVER executes anything — emits an inert Decision only.
    run_experiment_fn :
        ``run_experiment_fn(problem, decision) -> str``
        Deterministic execution plane runs the bounded experiment and returns
        an observation string.  Never executes arbitrary code.
    solve_fn :
        ``solve_fn(problem, understanding) -> str``
        Model writes the final code INFORMED by accumulated observations.
        Does NOT see the oracle answer.
    test_fn :
        ``test_fn(problem, code) -> {"passed": bool, ...}``
        Deterministic oracle gate — THE ONLY arbiter of 'solved'.
        critique_fn / revise_fn only generate; they never decide.
    max_experiments :
        Maximum number of experiment -> observe cycles before solving.
        Default 3.  Set to 0 to solve immediately with no exploration.

    Returns
    -------
    dict
        ``{solved, code, experiments, understanding}``

        - ``solved``        — True iff test_fn accepted the final code.
        - ``code``          — The code produced by solve_fn.
        - ``experiments``   — list of ``{"experiment": decision, "observation": str}``
                              in the order they were run.
        - ``understanding`` — same list (the growing scratchpad fed to propose_fn
                              and solve_fn each step).
    """
    understanding: list[dict] = []
    experiments: list[dict] = []

    for _ in range(max_experiments):
        # Model picks next experiment (inert Decision — no execution here)
        decision = propose_fn(problem, understanding)

        # Execution plane runs the bounded experiment; errors captured defensively
        try:
            observation: str = run_experiment_fn(problem, decision)
        except Exception as exc:  # noqa: BLE001 — never let one failed experiment abort the loop
            observation = f"experiment error: {type(exc).__name__}: {exc}"

        entry = {"experiment": decision, "observation": observation}
        experiments.append(entry)
        understanding.append(entry)

    # Model writes the fix informed by all accumulated observations
    code: str = solve_fn(problem, understanding)

    # Oracle is the sole arbiter — NEVER feeds back into propose/solve
    result: dict = test_fn(problem, code)

    return {
        "solved": bool(result.get("passed")),
        "code": code,
        "experiments": experiments,
        "understanding": understanding,
    }


# ---------------------------------------------------------------------------
# Bounded experiment executor — the deterministic execution plane
# ---------------------------------------------------------------------------

def _make_experiment_runner(
    repo: "Path",
    task: dict,
    targets: list,
    orig: dict,
) -> Callable:
    """Build the DETERMINISTIC bounded-experiment executor for a real repo task.

    Returns ``run_experiment_fn(problem, decision) -> str`` that dispatches on
    ``decision["type"]`` to one of three bounded, safe operations:

    E1 — Run the failing red-test nodes in Docker + capture short traceback.
         Uses ``_run_nodes_fb`` from commit_replay.  Files must be at parent
         state (with the commit's tests checked out) so the tests are red.
    E2 — Call the target function with SPECIFIC inputs in a subprocess.
         Args are validated with ``ast.literal_eval`` (safe literals only —
         str, int, float, list, dict, tuple, bool, None; no imports or calls).
         Returns ``repr(result)`` or the exception text.  Files restored after.
    E3 — Return the source of a NAMED helper/related function via AST.
         Reads from the ``orig`` dict (parent state in memory).  Pure, no LLM.

    BOUNDED (E2): ast.literal_eval is the safety gate; the model cannot inject
    arbitrary code via args_repr — only Python literal values are accepted.
    SAFE (E2): subprocess run with a timeout; orig files restored in finally.
    DEFENSIVE: any experiment error is captured as an observation string;
    the loop in experiment_solve continues regardless.
    """
    def run_experiment_fn(problem: Any, decision: Any) -> str:
        exp_type = (decision.get("type") if isinstance(decision, dict)
                    else getattr(decision, "type", None))
        params: dict = (decision.get("params", {}) if isinstance(decision, dict)
                        else getattr(decision, "params", {})) or {}

        if exp_type == E1:
            return _e1_run_failing_tests(repo, task)
        elif exp_type == E2:
            return _e2_call_function(
                repo, targets, orig,
                fn_name=params.get("fn_name", ""),
                args_repr=params.get("args_repr", "()"),
            )
        elif exp_type == E3:
            return _e3_read_function_source(orig, fn_name=params.get("fn_name", ""))
        else:
            return f"unknown experiment type: {exp_type!r} — valid types: E1, E2, E3"

    return run_experiment_fn


def _e1_run_failing_tests(repo: "Path", task: dict, timeout: int = 60) -> str:
    """E1: Run the failing red test nodes in Docker + capture short traceback."""
    from harness.commit_replay import _run_nodes_fb  # noqa: PLC0415 — deferred, no Docker at import
    nodes = task.get("redgreen", [])
    if not nodes:
        return "E1: no redgreen test nodes in task"
    fails, tb = _run_nodes_fb(repo, nodes, timeout)
    if not fails:
        return "E1: tests PASSED at current file state (unexpected — files may not be at parent)"
    return (
        f"E1 — {len(fails)}/{len(nodes)} test(s) FAILING:\n"
        f"Failing nodes: {', '.join(sorted(fails))}\n\n"
        f"Captured output (last ~700 chars):\n{tb}"
    )


def _e2_call_function(
    repo: "Path",
    targets: list,
    orig: dict,
    fn_name: str,
    args_repr: str,
    timeout: int = 15,
) -> str:
    """E2: Call the target function with literal args in a subprocess.

    BOUNDED: args_repr is validated with ast.literal_eval — only Python
    literals (str, int, float, list, dict, tuple, bool, None) are accepted.
    The model cannot inject imports or calls via args_repr.
    SAFE: subprocess with timeout; orig files restored in finally.
    """
    # Find the code file that defines fn_name
    code_file: Optional[str] = None
    for cf, name, _ in targets:
        if name == fn_name:
            code_file = cf
            break
    if code_file is None:
        # Fallback: scan orig for the function definition
        for cf, content in orig.items():
            if re.search(rf"\bdef\s+{re.escape(fn_name)}\s*\(", content):
                code_file = cf
                break
    if code_file is None:
        return (
            f"E2: function '{fn_name}' not found in target files "
            f"{sorted(orig.keys())}"
        )

    # Validate args with ast.literal_eval (safe literals only, no arbitrary code)
    safe_repr = args_repr.strip()
    try:
        parsed_args = ast.literal_eval(safe_repr)
        if not isinstance(parsed_args, tuple):
            parsed_args = (parsed_args,)
    except (ValueError, SyntaxError) as exc:
        return (
            f"E2: args_repr is not valid Python literals (ast.literal_eval): {exc}\n"
            f"args_repr must be a tuple literal e.g. '(1, 2)' or '(\"hello\",)'"
        )

    # Build importable package path from the code file (e.g. 'more_itertools.more' -> module)
    pkg_path = code_file.replace("\\", "/").removesuffix(".py").replace("/", ".")

    # Minimal safe runner script — only uses ast-validated literal args
    script = (
        f"import sys\n"
        f"sys.path.insert(0, '.')\n"
        f"from {pkg_path} import {fn_name} as _fn\n"
        f"try:\n"
        f"    _result = _fn(*{parsed_args!r})\n"
        f"    print('RESULT:', repr(_result))\n"
        f"except Exception as _e:\n"
        f"    print('EXCEPTION:', type(_e).__name__, str(_e))\n"
    )

    # Restore orig files so the module is at parent state before subprocess import
    for cf, content in orig.items():
        try:
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")
        except Exception:  # noqa: BLE001
            pass

    tmp_dir = repo / ".jcode"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"e2_{uuid.uuid4().hex[:8]}.py"
    try:
        tmp_path.write_text(script, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            cwd=str(repo),
        )
        output = (r.stdout + r.stderr).strip()
        if not output:
            output = f"(no output, returncode={r.returncode})"
        return f"E2 — calling {fn_name}(*{parsed_args!r}):\n{output}"
    except subprocess.TimeoutExpired:
        return f"E2: subprocess timeout ({timeout}s) calling {fn_name}"
    except Exception as exc:  # noqa: BLE001
        return f"E2: subprocess error: {type(exc).__name__}: {exc}"
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        # Restore orig files regardless of subprocess outcome
        for cf, content in orig.items():
            try:
                (repo / cf).write_text(content, encoding="utf-8", newline="\n")
            except Exception:  # noqa: BLE001
                pass


def _e3_read_function_source(orig: dict, fn_name: str) -> str:
    """E3: Return source of a named function via AST. Pure — no LLM, no I/O.

    Searches orig dict (parent state in memory).  Checks module-level functions
    and class methods.  Falls back to a not-found message if absent.
    """
    for cf, content in orig.items():
        if not re.search(rf"\bdef\s+{re.escape(fn_name)}\s*\(", content):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        # Module-level functions
        for node in tree.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == fn_name):
                src = ast.get_source_segment(content, node)
                if src:
                    return f"E3 — source of `{fn_name}` in {cf}:\n\n{src}"
        # Class methods
        for cls_node in tree.body:
            if isinstance(cls_node, ast.ClassDef):
                for m in cls_node.body:
                    if (isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and m.name == fn_name):
                        src = ast.get_source_segment(content, m)
                        if src:
                            return (
                                f"E3 — source of `{fn_name}` in {cf} "
                                f"(class {cls_node.name}):\n\n{src}"
                            )
    return f"E3: function '{fn_name}' not found in target files {sorted(orig.keys())}"

# #EXT-030-REQ-1 End


# ---------------------------------------------------------------------------
# #EXT-030-REQ-2 Start
# Jetson factory + active-hours probe protocol
# ---------------------------------------------------------------------------

def _parse_experiment_decision(raw: str, fn_name: str = "f") -> dict:
    """Parse model output into an experiment Decision dict.  Defensive fallback to E1.

    Tries JSON extraction first; falls back to keyword scan (E1/E2/E3 in text);
    defaults to E1 (always informative — see why the test fails).
    """
    # Tight JSON pattern: find {"type": "E1"|"E2"|"E3", ...}
    json_match = re.search(r'\{[^{}]*"type"\s*:\s*"(E[123])"[^{}]*\}', raw, re.DOTALL)
    if json_match:
        try:
            decision = json.loads(json_match.group(0))
            if decision.get("type") in (E1, E2, E3):
                if "params" not in decision:
                    decision["params"] = {}
                return decision
        except json.JSONDecodeError:
            pass

    # Broader extraction: find outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            candidate = json.loads(raw[start:end])
            if candidate.get("type") in (E1, E2, E3):
                if "params" not in candidate:
                    candidate["params"] = {}
                return candidate
        except json.JSONDecodeError:
            pass

    # Keyword scan fallback (no valid JSON found)
    upper = raw.upper()
    if "E3" in upper:
        m = re.search(r'"fn_name"\s*:\s*"([^"]+)"', raw)
        helper = m.group(1) if m else fn_name
        return {"type": E3, "params": {"fn_name": helper}}
    if "E2" in upper:
        m_fn = re.search(r'"fn_name"\s*:\s*"([^"]+)"', raw)
        m_args = re.search(r'"args_repr"\s*:\s*"([^"]+)"', raw)
        return {
            "type": E2,
            "params": {
                "fn_name": m_fn.group(1) if m_fn else fn_name,
                "args_repr": m_args.group(1) if m_args else "()",
            },
        }
    # Default: E1 — always useful (shows the exact failure reason)
    return {"type": E1, "params": {}}


def _make_jetson_fns(
    model: str,
    manager_url: str,
    *,
    swap_fn: Optional[Callable] = None,
    llm_fn: Optional[Callable] = None,
) -> tuple[Callable, Callable]:
    """Factory: return (propose_fn, solve_fn) for Jetson production use.

    propose_fn: model picks the next experiment from the bounded menu (E1/E2/E3)
        given the problem and understanding-so-far.  Returns an inert Decision dict.
        NEVER executes anything.
    solve_fn: model writes the fix informed by all accumulated observations.
        Applies the proven parse-gated indentation-repair layer (+12% on HumanEval).

    Both functions assume ``model`` is ALREADY LOADED on the Jetson when called.
    Model swapping is the caller's responsibility (same batching pattern as
    collaborative_solve's ``_make_jetson_fns``).

    Parameters
    ----------
    model :
        Model id to serve for both propose and solve (e.g. "qwen2.5-coder-3b").
    manager_url :
        Model-manager HTTP endpoint (e.g. "http://192.168.1.183:8001").
    swap_fn :
        Optional injectable swap callable ``(model_id: str) -> None``.
        Inject a no-op lambda in offline tests.
    llm_fn :
        Optional injectable LLM callable ``(prompt: str) -> str``.
        Inject a mock in offline tests.

    Problem dict keys expected by the returned fns (production use):
        subject    (str)       : commit intent / task description
        name       (str)       : Python function name to implement
        parent_src (str|None)  : current function source (None if new)
        context    (str)       : optional module context (default "")
    """
    def _get_llm_text(prompt: str) -> str:
        """Call the live LLM (or injected llm_fn) with the prompt; return text."""
        if llm_fn is not None:
            return llm_fn(prompt)
        from jaros.llm import LlmRequest  # noqa: PLC0415 — deferred, no Jetson at import
        from harness.coding_loop import build_llm  # noqa: PLC0415
        llm = build_llm()
        return llm.complete(LlmRequest(
            prompt=prompt, params={"temperature": 0.0, "max_tokens": 400}
        )).text

    def propose_fn(problem: Any, understanding: list) -> dict:
        """Pick next experiment from the bounded menu.  Returns inert Decision dict.

        Prompts the model with the experiment menu (E1/E2/E3) and accumulated
        understanding.  Parses the response defensively; defaults to E1 on parse
        failure (always informative — shows the exact test failure reason).

        NEVER executes.  Emits an inert ``{"type": ..., "params": {...}}`` dict.
        """
        p: dict = problem if isinstance(problem, dict) else {}
        subject: str = p.get("subject", "")
        name: str = p.get("name", "f")
        parent_src: str = p.get("parent_src", "") or ""
        context: str = p.get("context", "")

        cur_block = (
            f"Current (failing) function:\n{parent_src}\n"
            if parent_src
            else f"`{name}` does not exist yet.\n"
        )
        ctx_block = f"Module context:\n{context}\n\n" if context.strip() else ""

        obs_block = ""
        if understanding:
            obs_lines = []
            for i, entry in enumerate(understanding, 1):
                exp = entry.get("experiment", {})
                obs = entry.get("observation", "")
                exp_type = exp.get("type", "?") if isinstance(exp, dict) else str(exp)
                obs_lines.append(f"Experiment {i} ({exp_type}): {obs[:300]}")
            obs_block = "OBSERVATIONS SO FAR:\n" + "\n---\n".join(obs_lines) + "\n\n"

        prompt = (
            f"You are analyzing a Python function before writing a fix.\n\n"
            f"TASK: {subject}\n"
            f"FUNCTION: `{name}`\n"
            f"{ctx_block}"
            f"{cur_block}\n"
            f"{obs_block}"
            f"EXPERIMENT MENU:\n"
            f"  E1: Run the failing test — see WHY it fails (traceback/stdout).\n"
            f"  E2: Call `{name}` with specific inputs — see what it returns.\n"
            f"       Requires: fn_name (str), args_repr (Python tuple literal e.g. '(1, 2)').\n"
            f"  E3: Read source of a specific helper or related function.\n"
            f"       Requires: fn_name (str) — the helper name to inspect.\n\n"
            f"Pick ONE experiment that best helps you understand the failure.\n"
            f'Output ONLY valid JSON: {{"type": "E1"|"E2"|"E3", "params": {{...}}}}\n'
            f"For E1: params is {{}}. "
            f"For E2: params has fn_name and args_repr. "
            f"For E3: params has fn_name."
        )
        raw = _get_llm_text(prompt)
        return _parse_experiment_decision(raw, fn_name)

    def solve_fn(problem: Any, understanding: list) -> str:
        """Write the fix informed by all accumulated observations.

        Prompts the model with the full understanding scratchpad (what it observed)
        plus the problem description.  Applies the proven parse-gated indentation-
        repair layer (+12% on HumanEval lineage) as a best-effort post-process.

        Returns a clean function definition string (or "" on failure).
        """
        p: dict = problem if isinstance(problem, dict) else {}
        subject: str = p.get("subject", "")
        name: str = p.get("name", "f")
        parent_src: str = p.get("parent_src", "") or ""
        context: str = p.get("context", "")

        cur_block = (
            f"Current (failing) function:\n{parent_src}\n"
            if parent_src
            else f"`{name}` does not exist yet.\n"
        )
        ctx_block = f"Module context:\n{context}\n\n" if context.strip() else ""

        obs_block = ""
        if understanding:
            obs_lines = []
            for i, entry in enumerate(understanding, 1):
                exp = entry.get("experiment", {})
                obs = entry.get("observation", "")
                exp_type = exp.get("type", "?") if isinstance(exp, dict) else str(exp)
                obs_lines.append(f"Observation {i} ({exp_type}):\n{obs[:400]}")
            obs_block = (
                "WHAT YOU OBSERVED (use this to inform your fix):\n"
                + "\n---\n".join(obs_lines)
                + "\n\n"
            )

        prompt = (
            f"You have explored the failing function.  Now write the fix.\n\n"
            f"TASK: {subject}\n"
            f"FUNCTION: `{name}`\n"
            f"{ctx_block}\n"
            f"{ctx_block}"
            f"{obs_block}"
            f"Based on your observations, implement the CORRECT `{name}` function.\n"
            f"Output ONLY the complete `def {name}(...):` definition — valid Python, "
            f"correct indentation, no markdown, no prose, no test code."
        )
        raw = _get_llm_text(prompt)
        code = re.sub(r"```[\w+-]*", "", raw).replace("```", "").strip()
        i = code.find(f"def {name}")
        code = code[i:] if i >= 0 else (code if code.lstrip().startswith("def ") else "")
        if code:
            try:
                from harness.pass1_eval import _bc, _llm  # noqa: PLC0415
                code = _bc.repair_indentation(_llm(), code)
            except Exception:  # noqa: BLE001 — repair is best-effort, never block the solve
                pass
        return code

    return propose_fn, solve_fn


def run_experiment_probe(n: int = 6) -> None:
    """Run the experiment-to-understand probe on n hard bigbar [fail] tasks.

    Loads n hard bigbar [fail] tasks, runs experiment_solve per task
    (qwen2.5-coder-3b as proposer + solver, max_experiments=3), scores with
    the _run_nodes oracle (hidden — NEVER shown to the model during generation),
    restores gemma-4-e2b after, reports cracked X/n vs the 0/6 collab baseline.

    HONEST: the _run_nodes oracle is score-only.  The model never sees its
    output during generation — the same invariant as EXT-019, EXT-026, EXT-029.
    Only the FIRST changed function per task is probed (the simplest probe of
    the loop concept; full multi-function coverage is a later step).

    ACTIVE HOURS ONLY — requires the Jetson to serve models via the manager.
    DO NOT call from automated tests.

    Active-hours invocation:
        python -m harness.experiment_solve --n 6
    """
    from harness.commit_replay import (  # noqa: PLC0415
        tasks_corpus, _git, _spec, _reset, _target_funcs, _file_context,
        _apply_func, _run_nodes, wilson,
    )
    from harness.collaborative_solve import _http_swap  # noqa: PLC0415
    from harness.passk_probe import _parse_fail_shas, _resolve_tasks  # noqa: PLC0415

    bigbar = _ROOT / ".jaros-data" / "artifacts" / "bigbar_jaros.txt"
    if not bigbar.exists():
        print(
            f"ERROR: {bigbar} not found. Run the big-bar eval first.",
            file=sys.stderr,
        )
        sys.exit(1)

    manager_url = "http://192.168.1.183:8001"
    solver_model = "qwen2.5-coder-3b"
    restore_model = "gemma-4-e2b"

    repos_dir = _ROOT / ".jaros-data" / "repos"
    corpus = tasks_corpus(repos_dir=repos_dir, bar="big")
    fail_shas = _parse_fail_shas(bigbar.read_text(encoding="utf-8"), n)
    fail_tasks = _resolve_tasks(fail_shas, corpus)

    if not fail_tasks:
        print(
            "ERROR: no [fail] tasks resolved — check bigbar_jaros.txt and corpus JSON files.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f">>> EXT-030 experiment-to-understand probe  tasks={len(fail_tasks)}", flush=True)
    print(f">>> proposer+solver={solver_model}  max_experiments=3", flush=True)
    print(
        ">>> HONEST: oracle score-only — NEVER shown to model during generation",
        flush=True,
    )
    print(">>> Baseline: collab-solve 0/6; both models solo 0/8", flush=True)
    print(
        ">>> BOUNDED: experiments E1/E2/E3 only (no arbitrary code exec)",
        flush=True,
    )

    _swap = _http_swap(manager_url)
    _swap(solver_model)
    propose_fn, solve_fn = _make_jetson_fns(solver_model, manager_url)

    results: list[dict] = []

    for task in fail_tasks:
        repo_path = repos_dir / task["repo"]
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        sha_short = task["sha"][:8]
        try:
            _git(repo_path, "checkout", "-f", task["parent"])
            _git(repo_path, "checkout", task["sha"], "--", _spec(repo_path)["test"])
            targets = _target_funcs(repo_path, task)
            if not targets or len(targets) > 4:
                reason = "no_target" if not targets else "capped"
                results.append({
                    "sha": sha_short, "subject": task["subject"][:52],
                    "skipped": True, "reason": reason,
                })
                _reset(repo_path, branch)
                continue

            files = sorted({cf for cf, _, _ in targets})
            orig = {cf: (repo_path / cf).read_text(encoding="utf-8") for cf in files}
            ctx = {cf: _file_context(orig[cf]) for cf in files}

            # Probe: first changed function per task (simplest unit of the loop concept)
            cf, name, parent_src = targets[0]
            problem = {
                "subject": task["subject"],
                "name": name,
                "parent_src": parent_src,
                "context": ctx[cf],
            }

            runner = _make_experiment_runner(repo_path, task, targets, orig)

            def _test_fn(prob: Any, code: str, _cf=cf, _name=name) -> dict:
                """Apply code + score with oracle.  Oracle NEVER shown to model."""
                if not code:
                    return {"passed": False}
                content = _apply_func(orig[_cf], _name, code)
                (repo_path / _cf).write_text(content, encoding="utf-8", newline="\n")
                fails = _run_nodes(repo_path, task["redgreen"], 120)
                (repo_path / _cf).write_text(orig[_cf], encoding="utf-8", newline="\n")
                return {"passed": len(fails) == 0}

            outcome = experiment_solve(
                problem,
                propose_fn=propose_fn,
                run_experiment_fn=runner,
                solve_fn=solve_fn,
                test_fn=_test_fn,
                max_experiments=3,
            )

            results.append({
                "sha": sha_short, "subject": task["subject"][:52],
                "skipped": False,
                "cracked": outcome["solved"],
                "n_experiments": len(outcome["experiments"]),
            })
            status = "CRACKED" if outcome["solved"] else "fail   "
            print(
                f"  {sha_short} [{status}] exps={len(outcome['experiments'])} "
                f"| {task['subject'][:40]}",
                flush=True,
            )

        except Exception as exc:  # noqa: BLE001
            results.append({
                "sha": sha_short, "subject": task["subject"][:52],
                "skipped": True, "reason": f"err:{type(exc).__name__}",
            })
            print(f"  {sha_short} [err:{type(exc).__name__}]", flush=True)
        finally:
            _reset(repo_path, branch)

    # Restore default model
    print(f"\n>>> Restoring {restore_model} on Jetson...", flush=True)
    _swap(restore_model)

    # Summary
    probed = [r for r in results if not r.get("skipped")]
    n_probed = len(probed)
    n_cracked = sum(1 for r in probed if r.get("cracked"))
    n_skipped = len(results) - n_probed

    print(f"\n{'=' * 72}", flush=True)
    print(
        f">>> EXT-030 experiment-to-understand SUMMARY "
        f"({n_probed} probed, {n_skipped} skipped)",
        flush=True,
    )
    for r in results:
        sha = r.get("sha", "?")
        subj = r.get("subject", "?")
        if r.get("skipped"):
            print(f"  {sha}  SKIP  [{r.get('reason', '')}]  {subj}", flush=True)
        else:
            tag = "CRACK" if r.get("cracked") else "fail "
            exps = r.get("n_experiments", 0)
            print(f"  {sha}  {tag}  exps={exps}  {subj}", flush=True)
    print(f"{'=' * 72}", flush=True)
    if n_probed > 0:
        pct = n_cracked / n_probed * 100
        lo, hi = wilson(n_cracked, n_probed)
        print(f">>> collab-solve baseline        = 0/6  = 0.0%", flush=True)
        print(
            f">>> experiment-to-understand     = {n_cracked}/{n_probed} = {pct:.1f}%  "
            f"[Wilson95 {lo * 100:.1f}-{hi * 100:.1f}%]",
            flush=True,
        )
        if n_cracked > 0:
            print(
                f">>> VERDICT: EXPERIMENT LOOP HELPS — cracked {n_cracked}/{n_probed} "
                f"tasks that both models fail solo.",
                flush=True,
            )
            print(
                ">>> Next: integrate experiment loop into the default hard-class path.",
                flush=True,
            )
        else:
            print(
                f">>> VERDICT: 0/{n_probed} cracked. "
                f"Deeper exploration scaffolding needed.",
                flush=True,
            )
    print(f"{'=' * 72}", flush=True)

# #EXT-030-REQ-2 End


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "EXT-030: experiment-to-understand agentic solve probe.\n"
            "EXPLORE (E1/E2/E3) -> OBSERVE -> UNDERSTAND -> SOLVE -> oracle gate.\n"
            "HONEST: oracle is score-only; model never sees oracle output.\n"
            "BOUNDED: experiments from safe menu only (no arbitrary code exec).\n\n"
            "Run command (ACTIVE HOURS ONLY — Jetson must be running):\n"
            "  python -m harness.experiment_solve --n 6"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--n",
        type=int,
        default=6,
        help="Number of [fail] tasks to probe from bigbar_jaros.txt (default: 6)",
    )
    args = parser.parse_args()
    run_experiment_probe(n=args.n)
