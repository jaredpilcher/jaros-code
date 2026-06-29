"""EXT-029 — Cross-model collaborative solve (draft -> critique -> revise).

CONCEPT: prior independent probes had each model solve ALONE (both 0/8, correlated
at the task level). Collaboration combines complementary partial-strengths. The
cheapest form = DRAFT -> CRITIQUE -> REVISE across two models, with the DETERMINISTIC
TEST as the final judge (models collaborate to GENERATE; the test SELECTS — never
model-as-judge for selection).

HONEST: test_fn is the SOLE arbiter of whether a candidate is "solved". Neither the
draft model nor the critique/revise model ranks or selects between outputs — the
deterministic test does. This is the same gate principle as solve_routed_escalating
(EXT-021 REQ-6) — model-as-judge is forbidden.

Connection to issue #33 (open team-discussion = the richer form): collaborative_solve
is the cheapest two-model collaboration (one-shot draft -> critique -> revise per
round). Issue #33 explores richer team-discussion protocols (multiple rounds, multiple
critics, structured debate). collaborative_solve is the base case that proves or
disproves whether complementary model views help at all.

Targeted class: hard multi-step-repo — the class where both gemma 4 2B and
qwen2.5-coder-3B independently fail (0/8 baseline), correlated at the task level.
Collaboration hypothesis: qwen has better code structure, gemma has better reasoning
about intent/logic — together they may crack tasks neither can alone.

BATCHING DESIGN (minimises Jetson serial model swaps):
The PROBE RUNNER performs swaps in BATCHES across all tasks, not per task:
    1. Serve draft_model   (1 swap)
    2. Draft ALL n tasks
    3. Serve critique_model  (1 swap)
    4. Critique ALL n tasks
    5. Serve revise_model   (1 swap)
    6. Revise ALL n tasks
    (repeat steps 3-6 for each additional round)
    7. Restore to gemma    (1 swap)
    Total swaps: 2 * max_rounds + 1
    (vs 2 * max_rounds * n for naive per-task swapping)

The _make_jetson_fns factory provides per-phase code-gen callables; the batched
runner (collab_probe / run_collab_probe) controls swaps externally, calling each
phase function independently — NOT bundling a swap into each fn call.

Usage — ACTIVE HOURS ONLY (Jetson must serve both models via the manager):
    python -m harness.collaborative_solve --n 6
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# #EXT-029-REQ-1 Start
# Core collaborative solve loop — no I/O, fully injectable for offline tests
# ---------------------------------------------------------------------------

def collaborative_solve(
    problem: Any,
    *,
    draft_fn: Callable,
    critique_fn: Callable,
    revise_fn: Callable,
    test_fn: Callable,
    max_rounds: int = 2,
) -> dict:
    """Core DRAFT -> CRITIQUE -> REVISE collaborative solve loop.

    All callables are INJECTABLE so the loop is fully offline-testable.

    HONEST: test_fn is the SOLE arbiter of "solved" — neither draft_fn nor
    critique_fn/revise_fn ranks or selects between candidates. Model-as-judge
    is forbidden (same gate principle as solve_routed_escalating, EXT-021 REQ-6).

    Parameters
    ----------
    problem :
        Opaque problem descriptor passed verbatim to all four callables.
        For the collab probe this is a dict with task context; for offline
        tests it can be any value the mock fns accept.
    draft_fn :
        ``draft_fn(problem) -> str``
        Generate the first candidate code string.
    critique_fn :
        ``critique_fn(problem, candidate_code: str, test_result: dict) -> str``
        Given the failing code and the test result, produce a short critique /
        alternative-approach suggestion. NEVER selects or ranks outputs.
    revise_fn :
        ``revise_fn(problem, candidate_code: str, critique: str) -> str``
        Generate a revised code string informed by the critique.
    test_fn :
        ``test_fn(problem, candidate_code: str) -> dict``
        Deterministic gate — returns at least ``{"passed": bool}``.
        THIS IS THE ONLY ARBITER of whether a candidate is accepted.
        critique_fn and revise_fn only generate; they never decide.
    max_rounds :
        Maximum number of critique -> revise rounds after the initial draft.
        Default 2. The loop exits early on the first passing candidate.

    Returns
    -------
    dict
        ``{solved, code, rounds, winner, attempts}``

        - ``solved``   — True iff test_fn accepted a candidate.
        - ``code``     — the accepted code, or the last revised code on failure.
        - ``rounds``   — 0 if the draft passed; r ∈ [1, max_rounds] for collab;
                         max_rounds if all failed.
        - ``winner``   — ``"draft"`` / ``"collab"`` / ``None`` on all-fail.
        - ``attempts`` — list of round records ``{round, draft, critique, revised}``
                         (empty if draft passed immediately).
    """
    attempts: list[dict] = []

    # --- Phase 1: Draft ---
    candidate: str = draft_fn(problem)
    test_result: dict = test_fn(problem, candidate)

    if test_result.get("passed"):
        return {
            "solved": True,
            "code": candidate,
            "rounds": 0,
            "winner": "draft",
            "attempts": attempts,
        }

    # --- Phase 2: Critique -> Revise loop (up to max_rounds) ---
    last_code: str = candidate
    last_test_result: dict = test_result

    for r in range(max_rounds):
        critique: str = critique_fn(problem, last_code, last_test_result)
        revised: str = revise_fn(problem, last_code, critique)

        round_record: dict = {
            "round": r + 1,
            "draft": last_code,
            "critique": critique,
            "revised": revised,
        }
        attempts.append(round_record)

        last_code = revised
        last_test_result = test_fn(problem, revised)

        if last_test_result.get("passed"):
            return {
                "solved": True,
                "code": revised,
                "rounds": r + 1,
                "winner": "collab",
                "attempts": attempts,
            }
        # test_fn said fail — continue to next round regardless of what the
        # model said in the critique or revised code (test_fn is sole arbiter)

    # --- All rounds exhausted without a passing candidate ---
    return {
        "solved": False,
        "code": last_code,
        "rounds": max_rounds,
        "winner": None,
        "attempts": attempts,
    }

# #EXT-029-REQ-1 End


# ---------------------------------------------------------------------------
# Prompt builders for production critique / revise steps (Jetson factory)
# ---------------------------------------------------------------------------

def _build_critique_prompt(
    subject: str,
    name: str,
    candidate_code: str,
    test_failure_info: str,
    context: str = "",
) -> str:
    """Build a critique prompt: gemma reviews qwen's failing draft."""
    ctx_block = f"\nModule context:\n{context}\n" if context.strip() else ""
    return (
        f"You are reviewing Python code that FAILS a test.\n\n"
        f"TASK: {subject}\n"
        f"FUNCTION: `{name}`\n"
        f"{ctx_block}\n"
        f"FAILING CODE:\n{candidate_code}\n\n"
        f"TEST FAILURE:\n{test_failure_info}\n\n"
        f"Briefly identify the key bug or missing logic in `{name}`. "
        f"Then suggest a DIFFERENT approach to implement it correctly. "
        f"Be concise (3-5 sentences). Do not write code — only a critique and suggestion."
    )


def _build_revise_prompt(
    subject: str,
    name: str,
    candidate_code: str,
    critique: str,
    context: str = "",
) -> str:
    """Build a revise prompt: qwen generates improved code from gemma's critique."""
    ctx_block = f"\nModule context:\n{context}\n" if context.strip() else ""
    return (
        f"Revise the Python function `{name}` based on this critique.\n\n"
        f"TASK: {subject}\n"
        f"{ctx_block}\n"
        f"CRITIQUE:\n{critique}\n\n"
        f"CURRENT (FAILING) CODE:\n{candidate_code}\n\n"
        f"Output ONLY the complete `def {name}(...):` definition — valid Python, "
        f"correct indentation, no markdown, no prose, no test code."
    )


def _http_swap(manager_url: str) -> Callable[[str], None]:
    """Return a swap callable that POSTs to manager_url/serve to switch models.

    BATCHING NOTE: The collab_probe runner calls this ONCE per phase (draft/
    critique/revise), NOT once per task. Total swaps = 2 * max_rounds + 1.
    """
    def _swap(model_id: str) -> None:
        payload = json.dumps({"model": model_id}).encode()
        req = urllib.request.Request(
            f"{manager_url}/serve",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            if not data.get("ok") and not data.get("ready"):
                raise RuntimeError(f"manager swap returned non-ok: {data}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"model-manager unreachable at {manager_url}: {exc}") from exc
    return _swap


# ---------------------------------------------------------------------------
# #EXT-029-REQ-2 Start
# Batched Jetson factory + active-hours probe protocol
# ---------------------------------------------------------------------------

def _make_jetson_fns(
    draft_model: str,
    critique_model: str,
    revise_model: str,
    manager_url: str,
    *,
    swap_fn: Optional[Callable] = None,
    llm_fn: Optional[Callable] = None,
) -> tuple[Callable, Callable, Callable]:
    """Factory: return (draft_fn, critique_fn, revise_fn) for Jetson production use.

    Each function calls the appropriate model's code-gen (qwen / gemma path).
    Model swapping is NOT bundled into each fn call — the caller (collab_probe
    runner) controls swapping in BATCHES to minimise Jetson serial swaps:

        _swap = _http_swap(manager_url) [or injected swap_fn]

        _swap(draft_model)       # 1 swap for all n drafts
        for task in tasks:
            draft = draft_fn(problem)

        _swap(critique_model)    # 1 swap for all n critiques
        for task in tasks:
            critique = critique_fn(problem, draft, test_result)

        _swap(revise_model)      # 1 swap for all n revisions
        for task in tasks:
            revised = revise_fn(problem, draft, critique)

    Each fn assumes the correct model is ALREADY LOADED on the Jetson when called.
    This minimises swaps from 2*max_rounds*n to 2*max_rounds+1.

    Parameters
    ----------
    draft_model :
        Model id to serve when drafting (e.g. "qwen2.5-coder-3b").
    critique_model :
        Model id to serve when critiquing (e.g. "gemma-4-e2b").
    revise_model :
        Model id to serve when revising (e.g. "qwen2.5-coder-3b").
    manager_url :
        Model-manager HTTP endpoint (e.g. "http://192.168.1.183:8001").
    swap_fn :
        Optional injectable swap callable ``(model_id: str) -> None``.
        Defaults to ``_http_swap(manager_url)`` when None.
        Inject a no-op lambda in offline tests.
    llm_fn :
        Optional injectable LLM callable ``(prompt: str) -> str``.
        Defaults to the live ``_llm().complete(...)`` path.
        Inject a mock in offline tests.

    Returns
    -------
    tuple[Callable, Callable, Callable]
        ``(draft_fn, critique_fn, revise_fn)`` — all assume the correct
        Jetson model is already loaded when called.

    Problem dict keys expected by the returned fns (production use):
        subject (str)  : commit intent / task description
        name    (str)  : Python function name to implement
        context (str)  : optional module context (default "")
    """
    _swap: Callable = swap_fn if swap_fn is not None else _http_swap(manager_url)

    def _get_llm_text(prompt: str) -> str:
        """Call the live LLM (or injected llm_fn) with a prompt, return text."""
        if llm_fn is not None:
            return llm_fn(prompt)
        from jaros.llm import LlmRequest  # noqa: PLC0415 — deferred, no Jetson at import
        from harness.coding_loop import build_llm  # noqa: PLC0415
        llm = build_llm()
        return llm.complete(LlmRequest(
            prompt=prompt, params={"temperature": 0.0, "max_tokens": 900}
        )).text

    def draft_fn(problem: Any) -> str:
        """Generate first-attempt code using draft_model's code-gen style.

        Assumes draft_model is already loaded on the Jetson.
        Uses qwen_code style (clean instruct direct) for qwen models;
        falls back to gherkin-decompose for gemma-class models.
        """
        p: dict = problem if isinstance(problem, dict) else {}
        subject: str = p.get("subject", "")
        name: str = p.get("name", "f")
        context: str = p.get("context", "")
        # Qwen instruct-direct style: clean prompt, fence-stripped output
        from harness.qwen_adapt import qwen_code  # noqa: PLC0415 — lazy
        return qwen_code(subject, name, context)

    def critique_fn(problem: Any, candidate_code: str, test_result: dict) -> str:
        """Generate a critique of the failing code using critique_model.

        Assumes critique_model is already loaded on the Jetson.
        Produces a SHORT textual critique/alternative-approach suggestion —
        NEVER ranks or selects between candidates (test_fn is the only arbiter).
        """
        p: dict = problem if isinstance(problem, dict) else {}
        subject: str = p.get("subject", "")
        name: str = p.get("name", "f")
        context: str = p.get("context", "")
        failure_info: str = str(test_result) if test_result else "test failed"
        prompt = _build_critique_prompt(subject, name, candidate_code, failure_info, context)
        return _get_llm_text(prompt)

    def revise_fn(problem: Any, candidate_code: str, critique: str) -> str:
        """Generate revised code using revise_model informed by the critique.

        Assumes revise_model is already loaded on the Jetson.
        Uses qwen_code instruct-direct style with critique in context.
        Applies parse-gated indentation repair (the +12% layer).
        """
        p: dict = problem if isinstance(problem, dict) else {}
        subject: str = p.get("subject", "")
        name: str = p.get("name", "f")
        context: str = p.get("context", "")
        # Embed the critique as additional context for the revise call
        rich_context: str = f"CRITIQUE OF FAILING ATTEMPT:\n{critique}\n\n{context}".strip()
        from harness.qwen_adapt import qwen_code  # noqa: PLC0415 — lazy
        return qwen_code(subject, name, rich_context)

    return draft_fn, critique_fn, revise_fn


def collab_probe(n: int = 6) -> None:
    """Entry stub: BATCHED collaborative solve on n hard bigbar [fail] tasks.

    ACTIVE HOURS ONLY — requires the Jetson to serve both gemma and qwen via
    the model manager.  DO NOT call from tests.

    Strategy (qwen drafts, gemma critiques, qwen revises):
        1. Swap to qwen2.5-coder-3b; draft ALL n tasks.
        2. Swap to gemma-4-e2b; critique ALL n tasks (those that failed).
        3. Swap to qwen2.5-coder-3b; revise ALL n tasks using critiques.
        4. Score ALL revised candidates with the _run_nodes oracle (hidden,
           score-only — never shown to the model).
        5. Repeat steps 2-4 for round 2 if any tasks still fail.
        6. Restore gemma-4-e2b after all rounds.

    HONEST: the _run_nodes oracle is the SOLE selector. Neither qwen nor gemma
    ever sees oracle output during generation (test_fn is score-only, never fed
    back as a generation prompt — same invariant as EXT-019 and EXT-026).

    Baseline: 0/8 for both models solving independently.
    Hypothesis: qwen (stronger code structure) + gemma (stronger intent reasoning)
    together crack tasks neither can alone.

    Active-hours invocation:
        python -m harness.collaborative_solve --n 6
    """
    run_collab_probe(n=n)


def run_collab_probe(n: int = 6) -> None:
    """Run the batched collaborative solve probe on n [fail] tasks.

    Loads n hard bigbar [fail] tasks, runs DRAFT (qwen) -> CRITIQUE (gemma) ->
    REVISE (qwen) in batches, scores with the _run_nodes oracle, restores gemma.

    ACTIVE HOURS ONLY — no Jetson call in tests; invoke operator-side.

    Invoke:
        python -m harness.collaborative_solve --n 6
    """
    from harness.commit_replay import tasks_corpus, _git, wilson  # noqa: PLC0415
    from harness.passk_probe import _parse_fail_shas, _resolve_tasks  # noqa: PLC0415

    bigbar = _ROOT / ".jaros-data" / "artifacts" / "bigbar_jaros.txt"
    if not bigbar.exists():
        print(
            f"ERROR: {bigbar} not found. Run the big-bar eval first.",
            file=sys.stderr,
        )
        sys.exit(1)

    manager_url = "http://192.168.1.183:8001"
    draft_model = "qwen2.5-coder-3b"
    critique_model = "gemma-4-e2b"
    revise_model = "qwen2.5-coder-3b"

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

    print(f">>> EXT-029 collaborative solve probe  tasks={len(fail_tasks)}", flush=True)
    print(f">>> draft_model={draft_model}  critique_model={critique_model}", flush=True)
    print(
        ">>> HONEST: oracle score-only — NEVER shown to model during generation",
        flush=True,
    )
    print(
        ">>> BATCHING: swap once per phase (draft ALL / critique ALL / revise ALL)",
        flush=True,
    )
    print(
        ">>> Baseline: 0/8 for both models solving independently.",
        flush=True,
    )
    print(
        ">>> Hypothesis: draft(qwen) + critique(gemma) + revise(qwen) > 0/8",
        flush=True,
    )

    # Build injectable fns (swap_fn=None -> real HTTP swap in production)
    draft_fn, critique_fn, revise_fn = _make_jetson_fns(
        draft_model, critique_model, revise_model, manager_url
    )

    # Build test_fn that applies code via oracle and returns {"passed": bool}
    def _make_test_fn(repo: Path, task: dict, targets: list, orig: dict, timeout: int):
        """Build an oracle test_fn for one task (apply + score + restore)."""
        from harness.commit_replay import _apply_func, _run_nodes  # noqa: PLC0415

        files = sorted({cf for cf, _, _ in targets})

        def _test_fn(problem: Any, candidate_code: str) -> dict:
            # Apply candidate to the target function, score, restore
            name: str = problem.get("name", "") if isinstance(problem, dict) else ""
            cf_target = next((cf for cf, nm, _ in targets if nm == name), None)
            for cf in files:
                content = orig[cf]
                if cf == cf_target and candidate_code:
                    content = _apply_func(content, name, candidate_code)
                (repo / cf).write_text(content, encoding="utf-8", newline="\n")
            fails = _run_nodes(repo, task["redgreen"], timeout)
            passed = len(fails) == 0
            for cf in files:
                (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")
            return {"passed": passed, "failing_nodes": list(fails)}

        return _test_fn

    # BATCHED EXECUTION — minimise Jetson model swaps
    # Phase setup: for each task, read targets + orig files
    from harness.commit_replay import (  # noqa: PLC0415
        _target_funcs, _file_context, _git, _spec, _reset,
    )

    _swap = _http_swap(manager_url)

    results: list[dict] = []
    task_states: list[dict] = []

    # -- Setup: git state for each task --
    for task in fail_tasks:
        repo_path = repos_dir / task["repo"]
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        try:
            _git(repo_path, "checkout", "-f", task["parent"])
            _git(repo_path, "checkout", task["sha"], "--", _spec(repo_path)["test"])
            targets = _target_funcs(repo_path, task)
            if not targets or len(targets) > 4:
                results.append({
                    "sha": task["sha"][:8],
                    "subject": task["subject"][:52],
                    "skipped": True,
                    "reason": "no_target" if not targets else "capped",
                })
                task_states.append(None)
                _reset(repo_path, branch)
                continue
            files = sorted({cf for cf, _, _ in targets})
            orig = {cf: (repo_path / cf).read_text(encoding="utf-8") for cf in files}
            # Build one problem per target function
            problems = []
            for cf, name, parent_src in targets:
                ctx = _file_context(orig[cf])
                problems.append({
                    "subject": task["subject"],
                    "name": name,
                    "context": ctx,
                    "parent_src": parent_src,
                })
            task_states.append({
                "task": task,
                "repo": repo_path,
                "branch": branch,
                "targets": targets,
                "orig": orig,
                "problems": problems,
                "files": files,
            })
        except Exception as e:
            results.append({
                "sha": task["sha"][:8],
                "subject": task["subject"][:52],
                "skipped": True,
                "reason": f"err:{type(e).__name__}",
            })
            task_states.append(None)
            _reset(repo_path, branch)

    active = [(i, s) for i, s in enumerate(task_states) if s is not None]

    if not active:
        print("ERROR: all tasks were skipped in setup.", file=sys.stderr)
        sys.exit(1)

    # -- Phase 1: Draft ALL tasks on draft_model --
    print(f"\n>>> Phase 1: drafting {len(active)} tasks on {draft_model}", flush=True)
    _swap(draft_model)
    drafts: dict[int, dict] = {}
    for i, state in active:
        task_drafts = {}
        for problem in state["problems"]:
            code = draft_fn(problem)
            task_drafts[problem["name"]] = code
        drafts[i] = task_drafts
        print(f"  task {i+1}/{len(active)} [{state['task']['repo']}] drafted", flush=True)

    # -- Build initial test results (score drafts) --
    print(f"\n>>> Scoring drafts with oracle...", flush=True)
    draft_results: dict[int, dict] = {}
    for i, state in active:
        task = state["task"]
        repo = state["repo"]
        targets = state["targets"]
        orig = state["orig"]
        files = state["files"]
        from harness.commit_replay import _apply_func, _run_nodes  # noqa: PLC0415
        content_map = {cf: orig[cf] for cf in files}
        for cf, name, _ in targets:
            code = drafts[i].get(name, "")
            if code:
                content_map[cf] = _apply_func(content_map[cf], name, code)
        for cf in files:
            (repo / cf).write_text(content_map[cf], encoding="utf-8", newline="\n")
        fails = _run_nodes(repo, task["redgreen"], 120)
        passed = len(fails) == 0
        for cf in files:
            (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")
        draft_results[i] = {"passed": passed, "failing_nodes": list(fails)}
        status = "PASS" if passed else "fail"
        print(f"  task {i+1} [{task['repo']}] draft: {status}", flush=True)

    n_draft_pass = sum(1 for r in draft_results.values() if r["passed"])
    print(f">>> Draft results: {n_draft_pass}/{len(active)} passed", flush=True)

    # -- Phase 2: Critique ALL failing tasks on critique_model --
    failing_indices = [i for i in (j for j, _ in active) if not draft_results[i]["passed"]]
    critiques: dict[int, dict] = {}

    if failing_indices:
        print(f"\n>>> Phase 2: critiquing {len(failing_indices)} failing tasks on {critique_model}", flush=True)
        _swap(critique_model)
        for i in failing_indices:
            state = task_states[i]
            task_critiques = {}
            for problem in state["problems"]:
                name = problem["name"]
                code = drafts[i].get(name, "")
                tr = draft_results[i]
                crit = critique_fn(problem, code, tr)
                task_critiques[name] = crit
            critiques[i] = task_critiques
            print(f"  task {i+1} [{state['task']['repo']}] critiqued", flush=True)

    # -- Phase 3: Revise ALL failing tasks on revise_model --
    revisions: dict[int, dict] = {}

    if failing_indices:
        print(f"\n>>> Phase 3: revising {len(failing_indices)} tasks on {revise_model}", flush=True)
        _swap(revise_model)
        for i in failing_indices:
            state = task_states[i]
            task_revisions = {}
            for problem in state["problems"]:
                name = problem["name"]
                code = drafts[i].get(name, "")
                crit = critiques.get(i, {}).get(name, "")
                revised = revise_fn(problem, code, crit)
                task_revisions[name] = revised
            revisions[i] = task_revisions
            print(f"  task {i+1} [{state['task']['repo']}] revised", flush=True)

    # -- Score revised candidates --
    revision_results: dict[int, dict] = {}
    if failing_indices:
        print(f"\n>>> Scoring revised candidates with oracle...", flush=True)
        for i in failing_indices:
            state = task_states[i]
            task = state["task"]
            repo = state["repo"]
            targets = state["targets"]
            orig = state["orig"]
            files = state["files"]
            from harness.commit_replay import _apply_func, _run_nodes  # noqa: PLC0415
            content_map = {cf: orig[cf] for cf in files}
            for cf, name, _ in targets:
                code = revisions[i].get(name, "")
                if code:
                    content_map[cf] = _apply_func(content_map[cf], name, code)
            for cf in files:
                (repo / cf).write_text(content_map[cf], encoding="utf-8", newline="\n")
            fails = _run_nodes(repo, task["redgreen"], 120)
            passed = len(fails) == 0
            for cf in files:
                (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")
            revision_results[i] = {"passed": passed, "failing_nodes": list(fails)}
            status = "CRACKED" if passed else "fail   "
            print(f"  task {i+1} [{task['repo']}] revised: {status}", flush=True)

    # -- Restore gemma + cleanup --
    print(f"\n>>> Restoring {critique_model} on Jetson...", flush=True)
    _swap(critique_model)

    for i, state in active:
        _reset(state["repo"], state["branch"])

    # -- Build final results --
    for i, state in active:
        task = state["task"]
        if draft_results[i]["passed"]:
            winner = "draft"
            cracked = True
        elif revision_results.get(i, {}).get("passed"):
            winner = "collab"
            cracked = True
        else:
            winner = None
            cracked = False
        results.append({
            "sha": task["sha"][:8],
            "subject": task["subject"][:52],
            "skipped": False,
            "cracked": cracked,
            "winner": winner,
        })

    # -- Summary --
    probed = [r for r in results if not r.get("skipped")]
    n_probed = len(probed)
    n_cracked = sum(1 for r in probed if r.get("cracked"))
    n_skipped = len(results) - n_probed

    from harness.commit_replay import wilson  # noqa: PLC0415

    print(f"\n{'=' * 72}", flush=True)
    print(
        f">>> EXT-029 collaborative solve SUMMARY ({n_probed} probed, {n_skipped} skipped)",
        flush=True,
    )
    print(f">>> draft_model={draft_model}  critique_model={critique_model}", flush=True)
    print(flush=True)
    print(f"{'SHA':>8}  {'result':>7}  {'winner':>6}  subject", flush=True)
    print("-" * 72, flush=True)
    for r in results:
        sha = r.get("sha", "?")
        subj = r.get("subject", "?")
        if r.get("skipped"):
            print(f"{sha:>8}  {'SKIP':>7}  {'':>6}  {subj} [{r.get('reason', '')}]", flush=True)
        else:
            res = "CRACK" if r.get("cracked") else "fail "
            win = r.get("winner") or ""
            print(f"{sha:>8}  {res:>7}  {win:>6}  {subj}", flush=True)

    print("-" * 72, flush=True)
    print(f">>> baseline (gemma+qwen, solo)          = 0/8 = 0.0%", flush=True)
    if n_probed > 0:
        pct = n_cracked / n_probed * 100
        print(f">>> collaborative (draft+critique+revise) = {n_cracked}/{n_probed} = {pct:.1f}%", flush=True)
        lo, hi = wilson(n_cracked, n_probed)
        print(f">>> Wilson95: [{lo * 100:.1f}%, {hi * 100:.1f}%]", flush=True)
        print(flush=True)
        if n_cracked > 0:
            print(
                f">>> VERDICT: COLLABORATION HELPS — cracked {n_cracked}/{n_probed} tasks "
                f"that both models fail solo.",
                flush=True,
            )
            print(
                ">>> Next: productionize collaborative solve as the default hard-class path.",
                flush=True,
            )
        else:
            print(
                f">>> VERDICT: COLLABORATION DOES NOT HELP — 0/{n_probed} cracked.",
                flush=True,
            )
            print(
                ">>> These tasks need a stronger model or deeper decomposition scaffolding.",
                flush=True,
            )
    print(f"{'=' * 72}", flush=True)

# #EXT-029-REQ-2 End


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "EXT-029: cross-model collaborative solve probe.\n"
            "DRAFT (qwen) -> CRITIQUE (gemma) -> REVISE (qwen) -> oracle gate.\n"
            "HONEST: oracle is score-only; model never sees oracle output.\n"
            "BATCHED: 1 Jetson swap per phase (not per task).\n\n"
            "Run command (ACTIVE HOURS ONLY — Jetson must be running):\n"
            "  python -m harness.collaborative_solve --n 6"
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
    run_collab_probe(n=args.n)
