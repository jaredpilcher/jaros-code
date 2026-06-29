"""EXT-026 — Maximal-Help Ceiling Probe.

KEY QUESTION (cheapest-first): can HARNESS-DEEPENING crack the hard multi-step-repo
class that gemma+qwen both fail (0/8) raw — before committing to a new roster model?

Give the model MAXIMAL HELP: the right context + a worked example from a DIFFERENT
task + an explicit decomposition plan, then see if it cracks tasks it fails raw.

If ANY tasks crack -> harness-deepening is the lever (no new model needed).
If 0/N cracked -> confirms the hard class needs a DECORRELATED model (EXT-021 router).

Three deepening layers (all HONEST — no oracle leakage into the prompt):
  1. RETRIEVED CONTEXT: enriched_file_context (direct-dependency signatures + small
     bodies of helpers the target calls), not the whole file.
  2. WORKED EXAMPLE: ONE solved example from a DIFFERENT corpus task — its
     (parent version -> committed fixed version) before/after + commit intent.
     HONEST: always a different sha from the target; target's answer is NEVER shown.
  3. DECOMPOSITION: an explicit numbered step plan from _g_plan (EXT-020).

Scoring: _run_nodes oracle (red->green) — score-only, never shown to model.

Usage (Jetson must be running):
    python -m harness.maximal_help_probe --n 6

Estimated runtime: ~6 tasks * ~3 LLM calls (gherkin+plan+code) * ~30s/call = ~9 min.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# #EXT-026-REQ-1 Start
# Pure helpers — no I/O, fully testable offline
# ---------------------------------------------------------------------------

def _build_maxhelp_prompt(
    subject: str,
    name: str,
    parent_src: str | None,
    enriched_ctx: str,
    gherkin: str,
    worked_example: dict | None,
    plan: str,
    failing_test_src: str = "",
) -> str:
    """Build the MAXIMAL-HELP prompt combining three deepening layers.

    Layer 1: RETRIEVED CONTEXT — enriched_file_context (direct-dep helpers).
    Layer 2: WORKED EXAMPLE — from a DIFFERENT corpus task (never the target's answer).
    Layer 3: DECOMPOSITION — explicit numbered implementation plan from _g_plan.

    HONEST: the worked_example is always from a different sha than the target.
    The target's hidden oracle (task['redgreen'] answer / committed solution) is
    NEVER included here. The visible failing test IS included — it is the public
    spec, checked out at setup, not the hidden scoring answer.
    """
    cur = (f"Current version of `{name}`:\n{parent_src}\n"
           if parent_src else f"`{name}` does not exist yet.\n")

    # Layer 1: retrieved context
    ctx_block = (
        f"=== RETRIEVED CONTEXT: helper functions `{name}` directly calls ===\n"
        f"{enriched_ctx}\n"
        f"=== END CONTEXT ===\n\n"
    ) if enriched_ctx else ""

    # Layer 2: worked example from a different task
    if worked_example:
        ex = worked_example
        ex_block = (
            f"=== WORKED EXAMPLE (from a DIFFERENT repository task — not this task's answer) ===\n"
            f"Task intent: {ex.get('subject', '')}\n"
            f"Function being fixed: `{ex.get('func_name', 'unknown')}`\n"
            f"Before (current version):\n{ex.get('parent_src', '')}\n"
            f"After (committed fix):\n{ex.get('fixed_src', '')}\n"
            f"=== END EXAMPLE ===\n\n"
        )
    else:
        ex_block = ""

    # Layer 3: decomposition plan
    plan_block = (
        f"=== STEP-BY-STEP IMPLEMENTATION PLAN for `{name}` ===\n"
        f"{plan}\n"
        f"=== END PLAN ===\n\n"
    ) if plan else ""

    # Visible failing test (the spec — safe to include)
    test_block = (
        f"FAILING TEST (visible spec — this test must turn green):\n"
        f"{failing_test_src}\n\n"
    ) if failing_test_src else ""

    # Gherkin behavior scenarios
    gk_block = (
        f"Behavior scenarios for `{name}`:\n{gherkin}\n\n"
    ) if gherkin else ""

    return (
        f"You are fixing a Python function in a repository.\n"
        f"COMMIT INTENT: {subject}\n\n"
        f"{test_block}"
        f"{gk_block}"
        f"{ctx_block}"
        f"{ex_block}"
        f"{plan_block}"
        f"{cur}\n"
        f"Following the implementation plan above, implement the corrected `{name}` function.\n"
        f"Output ONLY the complete `def {name}(...):` definition — valid Python, correct "
        f"indentation, no markdown, no prose, no test code."
    )


def _g_code_maxhelp(
    subject: str,
    name: str,
    parent_src: str | None,
    enriched_ctx: str,
    gherkin: str,
    worked_example: dict | None,
    plan: str,
    failing_test_src: str = "",
) -> str:
    """Generate code using the maximal-help prompt (all three layers, temp=0).

    Pipes output through the proven parse-gated indentation-repair layer
    (same as g_code in commit_replay — the +12% HumanEval layer).

    HONEST: the worked_example is always from a DIFFERENT task; the target's
    hidden oracle answer is never in this prompt. The visible failing test
    (failing_test_src) is the public spec and is always safe to include.
    """
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm, _bc

    prompt = _build_maxhelp_prompt(
        subject, name, parent_src, enriched_ctx, gherkin,
        worked_example, plan, failing_test_src,
    )
    reply = _llm().complete(LlmRequest(
        prompt=prompt, params={"temperature": 0.0, "max_tokens": 900}
    )).text
    s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    i = s.find(f"def {name}")
    code = s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")
    if code:
        try:
            code = _bc.repair_indentation(_llm(), code)
        except Exception:  # noqa: BLE001 — repair is best-effort, never block
            pass
    return code


def _build_worked_example(
    corpus: list[dict],
    target_sha: str,
    repos_dir: Path,
) -> dict | None:
    """Extract a worked example from a DIFFERENT corpus task.

    Picks the first corpus task whose sha[:8] differs from target_sha AND has exactly
    one cleanly changed function we can retrieve (parent + committed versions differ).

    HONEST: the sha[:8] check ensures the example is always from a different commit.
    The target task's own committed code is NEVER returned here.

    Returns:
        dict with keys: subject, func_name, parent_src, fixed_src
        or None if no suitable example found.
    """
    from harness.commit_replay import _code_funcs, _git

    for task in corpus:
        if task["sha"][:8] == target_sha[:8]:
            continue  # NEVER use the target task
        try:
            repo_path = repos_dir / task["repo"]
            for cf in task.get("code_files", []):
                c_f = _code_funcs(_git(repo_path, "show", f"{task['sha']}:{cf}"))
                p_f = _code_funcs(_git(repo_path, "show", f"{task['parent']}:{cf}"))
                changed = [
                    (fn, csrc)
                    for fn, csrc in c_f.items()
                    if p_f.get(fn) != csrc and p_f.get(fn)
                ]
                if len(changed) == 1:
                    func_name, fixed_src = changed[0]
                    parent_src_ex = p_f[func_name]
                    if fixed_src.strip() != parent_src_ex.strip():
                        return {
                            "subject": task["subject"],
                            "func_name": func_name,
                            "parent_src": parent_src_ex,
                            "fixed_src": fixed_src,
                        }
        except Exception:  # noqa: BLE001 — skip tasks with broken git state
            continue
    return None


def _core_maxhelp_probe(
    *,
    targets: list[tuple[str, str, str | None]],
    orig: dict[str, str],
    gherkins: dict[tuple[str, str], str],
    failing_tests: dict[tuple[str, str], str],
    enriched_ctxs: dict[tuple[str, str], str],
    worked_example: dict | None,
    plans: dict[tuple[str, str], str],
    task: dict,
    repo: Path,
    timeout: int,
    generate_fn: Callable,
    oracle_fn: Callable,
) -> dict:
    """Pure maximal-help generate-score inner loop — no git setup/teardown.

    generate_fn signature:
        (subject, name, parent_src, enriched_ctx, gherkin,
         worked_example, plan, failing_test_src) -> str

    oracle_fn signature:
        (repo, nodes, timeout) -> set[str]  (empty set = all passed)

    HONEST: oracle_fn is called ONLY to SCORE the candidate AFTER generation.
    The model never receives oracle feedback during generation.
    The worked_example is from a DIFFERENT task and is the only cross-task signal.

    Returns:
        maxhelp_pass: bool — did the maximal-help attempt go red->green?
        per_target:   list of {name, code} for each target function
    """
    from harness.commit_replay import _apply_func

    files = sorted({cf for cf, _, _ in targets})

    def _apply_and_score(codes: dict[tuple[str, str], str]) -> bool:
        """Apply all codes to their files, score with oracle, then restore."""
        for cf in files:
            content = orig[cf]
            for (cf2, name2), code in codes.items():
                if cf2 == cf and code:
                    content = _apply_func(content, name2, code)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # ORACLE: score-only — never used to guide generation
        fails = oracle_fn(repo, task["redgreen"], timeout)
        passed = len(fails) == 0

        # Restore files to parent state
        for cf in files:
            (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")

        return passed

    per_target: list[dict] = []
    codes: dict[tuple[str, str], str] = {}
    for cf, name, parent_src in targets:
        code = generate_fn(
            task["subject"],
            name,
            parent_src,
            enriched_ctxs.get((cf, name), ""),
            gherkins.get((cf, name), ""),
            worked_example,
            plans.get((cf, name), ""),
            failing_tests.get((cf, name), ""),
        )
        codes[(cf, name)] = code
        per_target.append({"name": name, "code": code})

    maxhelp_pass = _apply_and_score(codes)

    return {
        "maxhelp_pass": maxhelp_pass,
        "per_target": per_target,
    }

# #EXT-026-REQ-1 End


# ---------------------------------------------------------------------------
# #EXT-026-REQ-2 Start
# Task-level probe with git setup/teardown
# ---------------------------------------------------------------------------

def probe_task_maxhelp(
    repo: Path,
    task: dict,
    branch: str,
    corpus: list[dict],
    repos_dir: Path,
    timeout: int = 120,
    _generate_fn: Callable | None = None,
    _oracle_fn: Callable | None = None,
    _worked_example: dict | str | None = "auto",
) -> dict:
    """Probe one task with the maximal-help strategy.

    Sets up git state (checkout parent + commit tests), builds all three help layers
    (enriched context, worked example from a different task, decomp plan), generates
    via the maximal-help prompt, and scores with the hidden oracle.

    HONEST: the hidden oracle is score-only; it is never shown to the model.
    The worked_example is always from a different corpus task (different sha).

    Args:
        repo:            path to the repo checkout.
        task:            corpus task dict.
        branch:          current branch name (for _reset cleanup).
        corpus:          full task corpus list (for worked example selection).
        repos_dir:       path containing repo checkouts.
        timeout:         oracle Docker timeout (seconds).
        _generate_fn:    optional override for code generation (offline tests).
                         Signature: (subject, name, parent_src, enriched_ctx, gherkin,
                                     worked_example, plan, failing_test) -> str
        _oracle_fn:      optional override for the hidden oracle (offline tests).
                         Signature: (repo, nodes, timeout) -> set[str]
        _worked_example: "auto" = build from corpus (default);
                         None   = no worked example in prompt;
                         dict   = use this pre-built example (offline tests).

    Returns dict with keys:
        skipped:      bool
        reason:       str (when skipped)
        maxhelp_pass: bool
        per_target:   list of {name, code}
    """
    from harness.commit_replay import (
        _target_funcs, _file_context, g_gherkin,
        _run_nodes, _git, _spec, _reset, _test_source,
    )
    from harness.repo_context import enriched_file_context
    from harness.decomp_probe import _g_plan

    generate_fn = _generate_fn if _generate_fn is not None else _g_code_maxhelp
    oracle_fn = _oracle_fn if _oracle_fn is not None else _run_nodes

    targets = _target_funcs(repo, task)
    if not targets:
        return {"skipped": True, "reason": "no_target",
                "maxhelp_pass": False, "per_target": []}
    if len(targets) > 4:
        return {"skipped": True, "reason": "capped",
                "maxhelp_pass": False, "per_target": []}

    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", _spec(repo)["test"])

        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}

        # Layer 1: enriched per-function context (direct-dep signatures + bodies)
        enriched_ctxs: dict[tuple[str, str], str] = {
            (cf, name): enriched_file_context(orig[cf], name)
            for cf, name, _ in targets
        }

        # Layer 3 setup: gherkin spec + decomposition plan per target
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        gherkins: dict[tuple[str, str], str] = {}
        plans: dict[tuple[str, str], str] = {}
        for cf, name, parent_src in targets:
            gk = g_gherkin(task["subject"], name, parent_src, ctx[cf])
            gherkins[(cf, name)] = gk
            # Use enriched context for plan — richer context = more accurate plan
            plan = _g_plan(
                task["subject"], name, parent_src, enriched_ctxs[(cf, name)], gk
            )
            plans[(cf, name)] = plan

        # Failing test source (visible spec — always safe to include in prompt)
        failing_test_src = _test_source(repo, task)
        failing_tests: dict[tuple[str, str], str] = {
            (cf, name): failing_test_src for cf, name, _ in targets
        }

        # Layer 2: worked example from a DIFFERENT corpus task
        if isinstance(_worked_example, str) and _worked_example == "auto":
            worked_example: dict | None = _build_worked_example(
                corpus, task["sha"], repos_dir
            )
        elif isinstance(_worked_example, dict) or _worked_example is None:
            worked_example = _worked_example
        else:
            worked_example = None

        result = _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=worked_example,
            plans=plans,
            task=task,
            repo=repo,
            timeout=timeout,
            generate_fn=generate_fn,
            oracle_fn=oracle_fn,
        )
        result["skipped"] = False
        return result

    except Exception as e:  # noqa: BLE001
        return {"skipped": True, "reason": f"err:{type(e).__name__}",
                "maxhelp_pass": False, "per_target": []}
    finally:
        _reset(repo, branch)

# #EXT-026-REQ-2 End


# ---------------------------------------------------------------------------
# #EXT-026-REQ-3 Start
# Entry point: load fail tasks, run probe, summarize with verdict
# ---------------------------------------------------------------------------

def run_maximal_help(n: int = 6) -> None:
    """Run the maximal-help probe on the first n [fail] tasks from bigbar_jaros.txt.

    HYPOTHESIS: if retrieved context + worked example + decomp plan (three deepening
    layers) crack tasks that pass@20 sampling AND decomp both failed -> no new model
    needed; harness-deepening is the lever.
    If 0/N cracked -> confirms the hard class needs a DECORRELATED model (EXT-021).

    HONEST: the hidden oracle is score-only. The model never sees oracle output
    during generation. The worked example is always from a DIFFERENT task.
    """
    from harness.commit_replay import tasks_corpus, _git, wilson
    from harness.passk_probe import _parse_fail_shas, _resolve_tasks

    bigbar = _ROOT / ".jaros-data" / "artifacts" / "bigbar_jaros.txt"
    if not bigbar.exists():
        print(
            f"ERROR: {bigbar} not found. Run the big-bar eval first to produce bigbar_jaros.txt.",
            file=sys.stderr,
        )
        sys.exit(1)

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

    print(f">>> EXT-026 maximal-help probe  tasks={len(fail_tasks)}", flush=True)
    print(
        ">>> HONEST: oracle score-only — NEVER shown to model during generation",
        flush=True,
    )
    print(
        ">>> HYPOTHESIS: harness-deepening (ctx + example + plan) cracks gemma+qwen 0/8 class",
        flush=True,
    )
    print(
        ">>> Three layers: retrieved context + worked example (different task) + decomp plan",
        flush=True,
    )
    print(f">>> Probing tasks: {[t['sha'][:8] for t in fail_tasks]}", flush=True)

    results: list[dict] = []
    for i, task in enumerate(fail_tasks):
        repo_path = repos_dir / task["repo"]
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        print(
            f"\n  task {i + 1}/{len(fail_tasks)} [{task['repo']}] {task['sha'][:8]}"
            f" | {task['subject'][:52]}",
            flush=True,
        )
        result = probe_task_maxhelp(repo_path, task, branch, corpus, repos_dir)
        result["sha"] = task["sha"][:8]
        result["subject"] = task["subject"][:52]
        result["repo"] = task["repo"]
        results.append(result)

        if result["skipped"]:
            print(f"  => SKIP ({result.get('reason', '?')})", flush=True)
        else:
            crack_s = "CRACKED" if result["maxhelp_pass"] else "fail   "
            print(f"  => maxhelp={crack_s}", flush=True)
            if result["maxhelp_pass"]:
                for pt in result.get("per_target", []):
                    print(f"  [cracked fn] {pt['name']}", flush=True)

    # --- Summary table ---
    probed = [r for r in results if not r["skipped"]]
    n_tasks = len(probed)
    n_skipped = len(results) - n_tasks
    n_cracked = sum(1 for r in probed if r["maxhelp_pass"])

    print(f"\n{'=' * 72}", flush=True)
    print(
        f">>> EXT-026 maximal-help SUMMARY  ({n_tasks} tasks probed, {n_skipped} skipped)",
        flush=True,
    )
    print(flush=True)
    header = f"{'SHA':>8}  {'maxhelp':>7}  subject"
    print(header, flush=True)
    print("-" * 72, flush=True)
    for r in results:
        sha = r.get("sha", "?")
        subj = r.get("subject", "?")
        if r["skipped"]:
            print(
                f"{sha:>8}  {'SKIP':>7}  {subj} [{r.get('reason', '')}]", flush=True
            )
        else:
            crack_s = "CRACK" if r["maxhelp_pass"] else "no"
            print(f"{sha:>8}  {crack_s:>7}  {subj}", flush=True)

    print("-" * 72, flush=True)
    print(
        f">>> raw baseline (gemma+qwen, no harness help)    = 0/8 = 0.0%", flush=True
    )
    if n_tasks > 0:
        print(
            f">>> maximal-help (ctx + example + plan, temp=0)   = {n_cracked}/{n_tasks}"
            f" = {n_cracked / n_tasks * 100:.1f}%",
            flush=True,
        )
        lo, hi = wilson(n_cracked, n_tasks)
        print(f">>> Wilson95: [{lo * 100:.1f}%, {hi * 100:.1f}%]", flush=True)

    print(flush=True)
    if n_tasks > 0:
        if n_cracked > 0:
            print(
                f">>> VERDICT: HARNESS-DEEPENING HELPS — cracked {n_cracked}/{n_tasks} "
                f"tasks that pass@20 and decomp both failed.",
                flush=True,
            )
            print(
                ">>> The additional context + worked example + plan scaffolding unlocked capability.",
                flush=True,
            )
            print(
                ">>> Next: productionize the three-layer prompt as the default hard-task path.",
                flush=True,
            )
        else:
            print(
                f">>> VERDICT: HARNESS-DEEPENING DOES NOT HELP — 0/{n_tasks} cracked.",
                flush=True,
            )
            print(
                ">>> These tasks are beyond prompt-level harness deepening.",
                flush=True,
            )
            print(
                ">>> Next: route this hard class to a DECORRELATED model (EXT-021 router).",
                flush=True,
            )
    print(f"{'=' * 72}", flush=True)

# #EXT-026-REQ-3 End


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "EXT-026: maximal-help ceiling probe.\n"
            "For each hard greedy-fail task: give the model maximal help\n"
            "(retrieved context + worked example from a DIFFERENT task + decomp plan),\n"
            "generate at temp=0, score via the hidden oracle (_run_nodes red->green).\n"
            "HONEST: oracle is score-only; model never sees oracle output.\n"
            "Worked example is ALWAYS from a different corpus task.\n\n"
            "Run command:\n"
            "  python -m harness.maximal_help_probe --n 6"
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
    run_maximal_help(n=args.n)
