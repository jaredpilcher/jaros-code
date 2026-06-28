"""EXT-020 — Decomposition probe.

KEY QUESTION: is the bottleneck in greedy-fail tasks the 2B's REASONING/planning
(which decomposition offloads) or its CODING itself (which decomposition can't fix)?

Pass@k (EXT-019) showed 0/7 hard tasks cracked even with k=20 blind samples at
fair temperature — the 2B cannot generate these functions whole.  This probe tests
the last structural lever: give the 2B an explicit, granular step-by-step
IMPLEMENTATION PLAN and have it implement step by step.

Two-phase flow (both temp=0, oracle never shown to model):
  1. DECOMPOSE: prompt the 2B to write a DETAILED numbered implementation plan
     (concrete internal steps — parse, iterate, edge cases, return) far more
     granular than the behavior gherkin.
  2. IMPLEMENT: prompt the 2B to write the function FOLLOWING that explicit plan
     (plan as scaffolding in the prompt), piped through the proven indentation-repair.
  3. SCORE: oracle (_run_nodes red->green) — HONEST, score-only, never shown to model.

Compares decomposition against monolithic greedy (same implement prompt, no plan)
to isolate the plan's contribution.

Usage (Jetson must be running):
    python -m harness.decomp_probe --tasks 8

Estimated runtime: ~8 tasks * ~3 LLM calls (gherkin+plan+implement) * ~30s/call
                 = ~12 minutes.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# #EXT-020-REQ-1 Start
# Pure helpers — no I/O, fully testable offline
# ---------------------------------------------------------------------------

def _g_plan(subject: str, name: str, parent_src: str | None,
            context: str, gherkin: str) -> str:
    """DECOMPOSE: prompt the 2B (temp=0) for a granular numbered implementation plan.

    The plan captures concrete internal steps (parse args, initialize data
    structures, iterate, handle edge cases, return) — far more granular than the
    behavior gherkin alone.  This offloads the reasoning/planning burden from the
    subsequent implement call so the model only needs to TRANSLATE each step to code.

    HONEST: the hidden oracle is never consulted here.
    """
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm

    cur = (f"The current version of `{name}` is:\n{parent_src}\n"
           if parent_src else f"`{name}` does not exist yet.\n")
    ctx = (f"Module context (imports + module-level names available):\n{context}\n"
           if context else "")
    gk = f"Behavior scenarios to satisfy:\n{gherkin}\n" if gherkin else ""
    prompt = (
        f"You need to implement the Python function `{name}`.\n"
        f"COMMIT INTENT: {subject}\n"
        f"{ctx}{cur}{gk}\n"
        f"Write a DETAILED NUMBERED IMPLEMENTATION PLAN for `{name}`.\n"
        f"Be concrete and granular — describe each internal step:\n"
        f"  - What arguments to parse / validate\n"
        f"  - What data structures to initialize\n"
        f"  - How to iterate or process the input step by step\n"
        f"  - Each edge case to handle (empty input, None, zero, exhausted iterator, etc.)\n"
        f"  - Exactly what to compute and return\n\n"
        f"Output ONLY a numbered list of concrete implementation steps.\n"
        f"No code, no prose explanation — just the numbered steps."
    )
    reply = _llm().complete(LlmRequest(prompt=prompt, params={
        "temperature": 0.0, "max_tokens": 600})).text
    return reply.strip()


def _g_code_from_plan(subject: str, name: str, parent_src: str | None,
                      context: str, gherkin: str, plan: str) -> str:
    """IMPLEMENT: prompt the 2B (temp=0) to write the function following the explicit plan.

    The plan is included as scaffolding in the prompt.  When plan is empty string
    this degrades to the monolithic greedy baseline (no plan scaffolding) — used by
    ``_core_decomp_probe`` for the apples-to-apples greedy comparison.

    Output is piped through the proven parse-gated indentation-repair layer
    (same as g_code in commit_replay — the +12% HumanEval layer).

    HONEST: the hidden oracle is never consulted here.
    """
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm, _bc

    cur = f"Current version:\n{parent_src}\n" if parent_src else ""
    ctx = f"Module context:\n{context}\n" if context else ""
    plan_block = (
        f"Follow this step-by-step implementation plan:\n\n{plan}\n\n"
        if plan else ""
    )
    prompt = (
        f"Implement the Python function `{name}`.\n"
        f"{plan_block}"
        f"Behavior scenarios to satisfy:\n{gherkin}\n\n"
        f"{ctx}{cur}COMMIT INTENT: {subject}\n"
        f"Output ONLY the complete `def {name}(...):` definition — valid Python, "
        f"correct indentation, no markdown, no prose, no test code."
    )
    reply = _llm().complete(LlmRequest(prompt=prompt, params={
        "temperature": 0.0, "max_tokens": 900})).text
    s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    i = s.find(f"def {name}")
    code = s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")
    if code:
        try:
            code = _bc.repair_indentation(_llm(), code)
        except Exception:  # noqa: BLE001 — repair is best-effort, never block
            pass
    return code


def _core_decomp_probe(
    *,
    targets: list[tuple[str, str, str | None]],   # (code_file, func_name, parent_src_or_None)
    orig: dict[str, str],                           # {code_file: parent file content}
    gherkins: dict[tuple[str, str], str],           # {(cf, name): gherkin spec}
    task: dict,
    repo: Path,
    timeout: int,
    plan_fn: Callable,      # (subject, name, parent_src, context, gherkin) -> plan_str
    implement_fn: Callable,  # (subject, name, parent_src, context, gherkin, plan) -> code_str
    oracle_fn: Callable,    # (repo, nodes, timeout) -> set[str]  (empty = pass)
) -> dict:
    """Pure decompose-implement-score inner loop — no git setup/teardown.

    HONEST: oracle_fn is called ONLY to SCORE a candidate AFTER both the plan
    and the implementation have been generated.  The model never receives oracle
    feedback during decompose or implement steps.

    Also scores the monolithic greedy baseline (implement_fn with empty plan) so
    the comparison is apples-to-apples.  The greedy call comes first (call index 0)
    so oracle stubs can distinguish greedy vs decomp by call order.

    Returns:
        greedy_pass:  bool — did the monolithic (no-plan) attempt pass?
        decomp_pass:  bool — did the decomposition attempt (plan -> implement) pass?
        per_target:   list of {name, plan, code} for each target function
        skipped:      always False (caller sets True on error)
    """
    from harness.commit_replay import _apply_func, _file_context  # deferred

    files = sorted({cf for cf, _, _ in targets})
    ctxs = {cf: _file_context(orig.get(cf, "")) for cf in files}

    def _apply_and_score(codes: dict[tuple[str, str], str]) -> bool:
        """Apply all target codes to their files, score with oracle, then restore."""
        for cf in files:
            content = orig[cf]
            for (cf2, name2), code in codes.items():
                if cf2 == cf and code:
                    content = _apply_func(content, name2, code)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # ORACLE: score-only — never used to guide plan or implement generation
        fails = oracle_fn(repo, task["redgreen"], timeout)
        passed = len(fails) == 0

        # Restore files to parent state for the next attempt
        for cf in files:
            (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")

        return passed

    # --- Monolithic greedy baseline (implement_fn with empty plan) ---
    # Empty plan → no plan scaffolding in the prompt (same as the failing greedy
    # that produced the bigbar [fail] entries this probe targets).
    greedy_codes = {
        (cf, name): implement_fn(
            task["subject"], name, parent_src, ctxs[cf], gherkins[(cf, name)], ""
        )
        for cf, name, parent_src in targets
    }
    greedy_pass = _apply_and_score(greedy_codes)

    # --- Decomposition: plan then implement ---
    per_target: list[dict] = []
    decomp_codes: dict[tuple[str, str], str] = {}
    for cf, name, parent_src in targets:
        plan = plan_fn(
            task["subject"], name, parent_src, ctxs[cf], gherkins[(cf, name)]
        )
        code = implement_fn(
            task["subject"], name, parent_src, ctxs[cf], gherkins[(cf, name)], plan
        )
        decomp_codes[(cf, name)] = code
        per_target.append({"name": name, "plan": plan, "code": code})

    decomp_pass = _apply_and_score(decomp_codes)

    return {
        "greedy_pass": greedy_pass,
        "decomp_pass": decomp_pass,
        "per_target": per_target,
    }

# #EXT-020-REQ-1 End


# ---------------------------------------------------------------------------
# #EXT-020-REQ-2 Start
# Task-level probe with git setup/teardown + top-level entry point
# ---------------------------------------------------------------------------

def probe_task_decomp(
    repo: Path,
    task: dict,
    branch: str,
    timeout: int = 120,
    _plan_fn: Callable | None = None,
    _implement_fn: Callable | None = None,
    _oracle_fn: Callable | None = None,
) -> dict:
    """Probe one task with the decompose-then-implement strategy.

    Mirrors ``probe_task`` from EXT-019 (passk_probe):  sets up git state
    (checkout parent + commit tests), builds the gherkin spec for each target
    function via ``g_gherkin``, then delegates to ``_core_decomp_probe`` for
    the pure plan->implement->score inner loop.

    HONEST: the hidden oracle is score-only; it is never shown to the model
    during the decompose or implement steps.

    Args:
        repo:         path to the repo checkout.
        task:         corpus task dict (sha, parent, subject, redgreen, code_files, ...).
        branch:       current branch name (for _reset cleanup).
        timeout:      oracle Docker timeout (seconds).
        _plan_fn:     optional override for plan generation (offline tests).
                      Signature: (subject, name, parent_src, context, gherkin) -> str
        _implement_fn: optional override for implementation (offline tests).
                      Signature: (subject, name, parent_src, context, gherkin, plan) -> str
        _oracle_fn:   optional override for the hidden oracle (offline tests).
                      Signature: (repo, nodes, timeout) -> set[str]  (empty = pass)

    Returns dict with keys:
        skipped:      bool
        reason:       str (present when skipped)
        greedy_pass:  bool — monolithic (no-plan) baseline
        decomp_pass:  bool — decomposition (plan -> implement) result
        per_target:   list of {name, plan, code}
    """
    from harness.commit_replay import (
        _target_funcs, _file_context, g_gherkin,
        _run_nodes, _git, _spec, _reset,
    )

    plan_fn = _plan_fn if _plan_fn is not None else _g_plan
    implement_fn = _implement_fn if _implement_fn is not None else _g_code_from_plan
    oracle_fn = _oracle_fn if _oracle_fn is not None else _run_nodes

    targets = _target_funcs(repo, task)
    if not targets:
        return {"skipped": True, "reason": "no_target",
                "decomp_pass": False, "greedy_pass": False, "per_target": []}
    if len(targets) > 4:
        return {"skipped": True, "reason": "capped",
                "decomp_pass": False, "greedy_pass": False, "per_target": []}

    files = sorted({cf for cf, _, _ in targets})
    try:
        # Setup: mirror attempt_gherkin_jaros up to g_gherkin
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", _spec(repo)["test"])

        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}

        # Build gherkin spec ONCE per target at temp=0 (stable, same as EXT-019)
        gherkins: dict[tuple[str, str], str] = {}
        for cf, name, parent_src in targets:
            gherkins[(cf, name)] = g_gherkin(task["subject"], name, parent_src, ctx[cf])

        result = _core_decomp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            timeout=timeout,
            plan_fn=plan_fn,
            implement_fn=implement_fn,
            oracle_fn=oracle_fn,
        )
        result["skipped"] = False
        return result

    except Exception as e:  # noqa: BLE001
        return {"skipped": True, "reason": f"err:{type(e).__name__}",
                "decomp_pass": False, "greedy_pass": False, "per_target": []}
    finally:
        _reset(repo, branch)


def run_decomp_probe(n: int = 8) -> None:
    """Run the decomposition probe on the first n [fail] tasks from bigbar_jaros.txt.

    THE DECISIVE QUESTION: does explicit plan scaffolding crack tasks that greedy
    generation and k=20 blind sampling both failed?

    HONEST: the hidden oracle is score-only. The model never sees oracle output
    during the decompose or implement steps.
    """
    from harness.commit_replay import tasks_corpus, _git, wilson
    from harness.passk_probe import _parse_fail_shas, _resolve_tasks

    bigbar = _ROOT / ".jaros-data" / "artifacts" / "bigbar_jaros.txt"
    if not bigbar.exists():
        print(f"ERROR: {bigbar} not found. Run the big-bar eval first to get bigbar_jaros.txt.",
              file=sys.stderr)
        sys.exit(1)

    repos_dir = _ROOT / ".jaros-data" / "repos"
    corpus = tasks_corpus(repos_dir=repos_dir, bar="big")
    fail_shas = _parse_fail_shas(bigbar.read_text(encoding="utf-8"), n)
    fail_tasks = _resolve_tasks(fail_shas, corpus)

    if not fail_tasks:
        print("ERROR: no [fail] tasks resolved — check bigbar_jaros.txt and corpus JSON files.",
              file=sys.stderr)
        sys.exit(1)

    print(f">>> EXT-020 decomposition probe  tasks={len(fail_tasks)}", flush=True)
    print(f">>> HONEST: oracle score-only — NEVER shown to model during decompose/implement",
          flush=True)
    print(f">>> KEY QUESTION: does explicit step-by-step plan scaffolding crack tasks that",
          flush=True)
    print(f">>>              greedy generation AND k=20 sampling both could not?", flush=True)
    print(f">>> Probing tasks: {[t['sha'][:8] for t in fail_tasks]}", flush=True)

    results: list[dict] = []
    for i, task in enumerate(fail_tasks):
        repo_path = repos_dir / task["repo"]
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        print(f"\n  task {i + 1}/{len(fail_tasks)} [{task['repo']}] {task['sha'][:8]}"
              f" | {task['subject'][:52]}", flush=True)
        result = probe_task_decomp(repo_path, task, branch)
        result["sha"] = task["sha"][:8]
        result["subject"] = task["subject"][:52]
        result["repo"] = task["repo"]
        results.append(result)

        if result["skipped"]:
            print(f"  => SKIP ({result.get('reason', '?')})", flush=True)
        else:
            decomp_s = "CRACKED" if result["decomp_pass"] else "fail   "
            greedy_s = "PASS" if result["greedy_pass"] else "fail"
            print(f"  => decomp={decomp_s}  greedy={greedy_s}", flush=True)
            # Show a brief plan preview for cracked tasks (informational)
            if result["decomp_pass"]:
                for pt in result.get("per_target", []):
                    plan_preview = pt["plan"][:200].replace("\n", " | ")
                    print(f"  [plan] {plan_preview}", flush=True)

    # --- Summary table ---
    probed = [r for r in results if not r["skipped"]]
    n_tasks = len(probed)
    n_skipped = len(results) - n_tasks
    n_decomp = sum(1 for r in probed if r["decomp_pass"])
    n_greedy = sum(1 for r in probed if r.get("greedy_pass"))

    print(f"\n{'=' * 72}", flush=True)
    print(f">>> EXT-020 decomposition SUMMARY  ({n_tasks} tasks probed, {n_skipped} skipped)",
          flush=True)
    print(flush=True)
    header = f"{'SHA':>8}  {'decomp':>6}  {'greedy':>6}  subject"
    print(header, flush=True)
    print("-" * 72, flush=True)
    for r in results:
        sha = r.get("sha", "?")
        subj = r.get("subject", "?")
        if r["skipped"]:
            print(f"{sha:>8}  {'SKIP':>6}  {'':>6}  {subj} [{r.get('reason', '')}]",
                  flush=True)
        else:
            decomp_s = "CRACK" if r["decomp_pass"] else "no"
            greedy_s = "PASS" if r.get("greedy_pass") else "fail"
            print(f"{sha:>8}  {decomp_s:>6}  {greedy_s:>6}  {subj}", flush=True)

    print("-" * 72, flush=True)
    print(f">>> greedy  (monolithic, no plan)                 = {n_greedy}/{n_tasks}"
          f" = {n_greedy / n_tasks * 100:.1f}%"
          f"  (baseline: all sourced from bigbar [fail])", flush=True)
    print(f">>> decomp  (plan -> implement, temp=0, 1-shot)   = {n_decomp}/{n_tasks}"
          f" = {n_decomp / n_tasks * 100:.1f}%", flush=True)

    if n_tasks > 0:
        lo, hi = wilson(n_decomp, n_tasks)
        print(f">>> Wilson95: [{lo * 100:.1f}%, {hi * 100:.1f}%]", flush=True)

    print(flush=True)
    if n_tasks > 0:
        if n_decomp > n_greedy:
            print(f">>> VERDICT: DECOMPOSITION HELPS — decomp={n_decomp}/{n_tasks} >"
                  f" greedy={n_greedy}/{n_tasks}", flush=True)
            print(f">>> Bottleneck was REASONING/PLANNING (which the plan offloads).",
                  flush=True)
            print(f">>> Next: productionize decompose->implement as a default harness path.",
                  flush=True)
        elif n_decomp == 0 and n_greedy == 0:
            print(f">>> VERDICT: DECOMPOSITION DOES NOT HELP — both decomp and greedy"
                  f" = 0/{n_tasks}", flush=True)
            print(f">>> Bottleneck is CODING ITSELF (plan scaffolding cannot fix it).",
                  flush=True)
            print(f">>> These tasks may need retrieval, execution-plane tools, or a stronger"
                  f" on-device model.", flush=True)
        elif n_decomp >= n_greedy:
            print(f">>> VERDICT: PARTIAL GAIN — decomp={n_decomp}/{n_tasks}"
                  f" greedy={n_greedy}/{n_tasks}", flush=True)
        else:
            print(f">>> VERDICT: NO GAIN — greedy={n_greedy}/{n_tasks}"
                  f" decomp={n_decomp}/{n_tasks}", flush=True)
    print(f"{'=' * 72}", flush=True)

# #EXT-020-REQ-2 End


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "EXT-020: decomposition probe.\n"
            "For each hard greedy-fail task: DECOMPOSE (2B writes a granular numbered\n"
            "implementation plan), then IMPLEMENT following that plan (temp=0), scored\n"
            "by the hidden oracle (_run_nodes red->green).\n"
            "HONEST: oracle is score-only; model never sees oracle output."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tasks", type=int, default=8,
        help="Number of [fail] tasks to probe from bigbar_jaros.txt (default: 8)",
    )
    args = parser.parse_args()
    run_decomp_probe(n=args.tasks)
