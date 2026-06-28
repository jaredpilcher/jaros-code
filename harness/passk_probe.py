"""EXT-019 — pass@k latent-capability probe.

DECISIVE TEST: does the 2B's latent capability exceed its pass@1?
The founding no-ceiling thesis predicts pass@k >> pass@1 — the 2B CAN produce
a correct solution within k tries for many tasks it fails on at pass@1; the
harness just fails to SELECT it (weak verifier). This probe measures that gap.

HONEST: the hidden oracle (_run_nodes red->green) is used ONLY to SCORE samples
after generation. It is NEVER shown to the model or used to guide/select during
generation. The k samples are blind. See EXT-019 REQ-1 / REQ-2.

Usage (Jetson must be running):
    python -m harness.passk_probe --tasks 15 --k 20 --temp 0.8

Estimated runtime: ~15 tasks * 20 samples * ~30s/sample = ~2–3 hours.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# #EXT-019-REQ-1 Start
# Pure helpers — no I/O, fully testable offline
# ---------------------------------------------------------------------------

def _parse_fail_shas(bigbar_text: str, n: int) -> list[str]:
    """Return the first n 8-char sha prefixes marked [fail] in bigbar_jaros.txt text."""
    shas: list[str] = []
    for line in bigbar_text.splitlines():
        m = re.match(r"\s+\d+/\d+ \[\S+\] ([0-9a-f]+) \[fail\]", line)
        if m:
            shas.append(m.group(1))
            if len(shas) >= n:
                break
    return shas


def _resolve_tasks(fail_shas: list[str], corpus: list[dict]) -> list[dict]:
    """Map each 8-char sha prefix from bigbar to its full task dict in the corpus.

    Deduplicates — each corpus task is included at most once regardless of
    how many bigbar entries reference it (should not happen, but defensive).
    """
    sha8_map: dict[str, dict] = {t["sha"][:8]: t for t in corpus}
    seen: set[str] = set()
    out: list[dict] = []
    for sha8 in fail_shas:
        task = sha8_map.get(sha8[:8])
        if task is not None and task["sha"] not in seen:
            seen.add(task["sha"])
            out.append(task)
    return out

# ---------------------------------------------------------------------------
# Sampling code generator (injectable for offline tests)
# ---------------------------------------------------------------------------

def _g_code_sampled(subject: str, name: str, parent_src: str | None,
                    context: str, gherkin: str, temp: float) -> str:
    """Generate code for `name` satisfying `gherkin` at configurable temperature.

    Mirrors ``g_code`` from commit_replay exactly but exposes ``temp`` so the
    probe can draw k samples at T>0. Inherits the proven indentation-repair layer.
    """
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm, _bc  # deferred — avoids import at module level

    cur = f"Current version:\n{parent_src}\n" if parent_src else ""
    ctx = f"Module context:\n{context}\n" if context else ""
    prompt = (
        f"Implement the Python function `{name}` to satisfy these behavior scenarios:\n{gherkin}\n\n"
        f"{ctx}{cur}COMMIT INTENT: {subject}\nOutput ONLY the complete `def {name}(...):` "
        f"definition — valid Python, correct indentation, no markdown, no prose, no test code."
    )
    reply = _llm().complete(LlmRequest(prompt=prompt, params={
        "temperature": temp, "max_tokens": 800})).text
    s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    i = s.find(f"def {name}")
    code = s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")
    if code:
        try:
            code = _bc.repair_indentation(_llm(), code)
        except Exception:  # noqa: BLE001 — repair is best-effort, never block
            pass
    return code


# ---------------------------------------------------------------------------
# Core sampling loop — no git operations, fully injectable for offline tests
# ---------------------------------------------------------------------------

def _core_probe(
    *,
    targets: list[tuple[str, str, str | None]],  # (code_file, func_name, parent_src_or_None)
    orig: dict[str, str],                         # {code_file: parent file content}
    gherkins: dict[tuple[str, str], str],         # {(cf, name): gherkin spec}
    task: dict,
    repo: Path,
    k: int,
    temp: float,
    timeout: int,
    generate_fn: Callable,
    oracle_fn: Callable,
) -> dict:
    """Pure sampling + scoring inner loop — no git setup/teardown.

    HONEST: oracle_fn is called ONLY to SCORE each candidate AFTER it has been
    generated. The model never receives oracle feedback during generation — each
    of the k samples is drawn blind.

    Returns:
        greedy_pass: bool — did the temp=0 greedy sample go red->green?
        n_passed:    int  — how many of the k blind samples passed?
        passk:       bool — did any of the k samples pass?
        k:           int
    """
    from harness.commit_replay import _apply_func  # deferred

    files = sorted({cf for cf, _, _ in targets})

    def _apply_sample_and_score(
        codes: dict[tuple[str, str], str],
    ) -> bool:
        """Apply all target-function codes to their files, score, then restore."""
        for cf in files:
            content = orig[cf]
            for (cf2, name2), code in codes.items():
                if cf2 == cf and code:
                    content = _apply_func(content, name2, code)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # ORACLE: score-only — never used to guide generation
        fails = oracle_fn(repo, task["redgreen"], timeout)
        passed = len(fails) == 0

        # Restore files to parent state for the next sample
        for cf in files:
            (repo / cf).write_text(orig[cf], encoding="utf-8", newline="\n")

        return passed

    # --- Greedy (temp=0) sample — informational ---
    greedy_codes = {
        (cf, name): generate_fn(task["subject"], name, parent_src, orig.get(cf, ""),
                                gherkins[(cf, name)], 0.0)
        for cf, name, parent_src in targets
    }
    greedy_pass = _apply_sample_and_score(greedy_codes)

    # --- k blind samples at temp T ---
    n_passed = 0
    for sample_idx in range(k):
        sample_codes = {
            (cf, name): generate_fn(task["subject"], name, parent_src, orig.get(cf, ""),
                                    gherkins[(cf, name)], temp)
            for cf, name, parent_src in targets
        }
        passed = _apply_sample_and_score(sample_codes)
        if passed:
            n_passed += 1
        print(f"    sample {sample_idx + 1}/{k}: {'PASS' if passed else 'fail'}", flush=True)

    return {
        "greedy_pass": greedy_pass,
        "n_passed": n_passed,
        "passk": n_passed > 0,
        "k": k,
    }


def probe_task(
    repo: Path,
    task: dict,
    branch: str,
    k: int,
    temp: float,
    timeout: int = 120,
    _generate_fn: Callable | None = None,
    _oracle_fn: Callable | None = None,
) -> dict:
    """Probe one task: k blind samples at temp T, scored by the hidden oracle.

    Mirrors ``attempt_gherkin_jaros`` up to g_code (gherkin spec built at temp=0
    for stability), then samples code generation k times at temperature ``temp``.
    Each sample is scored by the hidden oracle (red->green) — score-only, never
    shown to the model during generation.

    Args:
        repo: path to the repo checkout.
        task: corpus task dict (sha, parent, subject, redgreen, code_files, ...).
        branch: current branch name (for _reset cleanup).
        k: number of blind samples to draw at temp T.
        temp: sampling temperature for code generation (g_code calls).
        timeout: oracle Docker timeout per sample (seconds).
        _generate_fn: optional override for code generation (offline tests).
            Signature: (subject, name, parent_src, context, gherkin, temp) -> str
        _oracle_fn: optional override for the hidden oracle (offline tests).
            Signature: (repo, nodes, timeout) -> set[str]  (empty set = pass)

    Returns dict with keys:
        skipped:     bool
        reason:      str (present when skipped)
        greedy_pass: bool (temp=0, 1-shot, informational)
        passk:       bool (any of k samples go red->green)
        n_passed:    int
        k:           int
    """
    from harness.commit_replay import (
        _target_funcs, _file_context, g_gherkin,
        _run_nodes, _git, _spec, _reset,
    )

    generate_fn = _generate_fn if _generate_fn is not None else _g_code_sampled
    oracle_fn = _oracle_fn if _oracle_fn is not None else _run_nodes

    targets = _target_funcs(repo, task)
    if not targets:
        return {"skipped": True, "reason": "no_target",
                "passk": False, "n_passed": 0, "k": k, "greedy_pass": False}
    if len(targets) > 4:
        return {"skipped": True, "reason": "capped",
                "passk": False, "n_passed": 0, "k": k, "greedy_pass": False}

    files = sorted({cf for cf, _, _ in targets})
    try:
        # --- Setup: mirror attempt_gherkin_jaros up to g_code ---
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", _spec(repo)["test"])

        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}

        # Build gherkin spec ONCE per target at temp=0 (stable, not sampled)
        gherkins: dict[tuple[str, str], str] = {}
        for cf, name, parent_src in targets:
            gherkins[(cf, name)] = g_gherkin(task["subject"], name, parent_src, ctx[cf])

        result = _core_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            k=k,
            temp=temp,
            timeout=timeout,
            generate_fn=generate_fn,
            oracle_fn=oracle_fn,
        )
        result["skipped"] = False
        return result

    except Exception as e:  # noqa: BLE001
        return {"skipped": True, "reason": f"err:{type(e).__name__}",
                "passk": False, "n_passed": 0, "k": k, "greedy_pass": False}
    finally:
        _reset(repo, branch)

# #EXT-019-REQ-1 End


# ---------------------------------------------------------------------------
# #EXT-019-REQ-2 Start
# Entry point: load fails, resolve tasks, probe each, print summary
# ---------------------------------------------------------------------------

def run_probe(n: int = 15, k: int = 20, temp: float = 0.8) -> None:
    """Run the pass@k probe on the first n [fail] tasks from bigbar_jaros.txt.

    THE DECISIVE NUMBER: if pass@k >> pass@1 (which is 0 for all probed tasks),
    the 2B has latent capability the current harness cannot extract on first try.
    The bottleneck is SELECTION (the verifier), not model capability — confirming
    the no-ceiling thesis and pointing squarely at building a selector.

    HONEST: the hidden oracle is score-only. The model never sees oracle output
    during the k sampling rounds. Each sample is drawn blind.
    """
    from harness.commit_replay import tasks_corpus, _git, wilson

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

    print(f">>> EXT-019 pass@k probe  tasks={len(fail_tasks)}  k={k}  temp={temp}", flush=True)
    print(f">>> HONEST: oracle score-only — NEVER shown to model during generation", flush=True)
    print(f">>> Probing tasks: {[t['sha'][:8] for t in fail_tasks]}", flush=True)

    results: list[dict] = []
    for i, task in enumerate(fail_tasks):
        repo_path = repos_dir / task["repo"]
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
        print(f"\n  task {i + 1}/{len(fail_tasks)} [{task['repo']}] {task['sha'][:8]}"
              f" | {task['subject'][:52]}", flush=True)
        result = probe_task(repo_path, task, branch, k=k, temp=temp)
        result["sha"] = task["sha"][:8]
        result["subject"] = task["subject"][:52]
        result["repo"] = task["repo"]
        results.append(result)

        if result["skipped"]:
            print(f"  => SKIP ({result.get('reason', '?')})", flush=True)
        else:
            print(
                f"  => passk={'YES' if result['passk'] else 'NO '} "
                f"n_passed={result['n_passed']:>2}/{k}  "
                f"greedy={'PASS' if result.get('greedy_pass') else 'fail'}",
                flush=True,
            )

    # --- Summary table ---
    probed = [r for r in results if not r["skipped"]]
    n_tasks = len(probed)
    n_skipped = len(results) - n_tasks
    n_passk = sum(1 for r in probed if r["passk"])
    n_greedy = sum(1 for r in probed if r.get("greedy_pass"))

    print(f"\n{'=' * 72}", flush=True)
    print(f">>> EXT-019 pass@k SUMMARY  ({n_tasks} tasks probed, {n_skipped} skipped)",
          flush=True)
    print(f">>> k={k}  temp={temp}", flush=True)
    print(f"", flush=True)
    header = f"{'SHA':>8}  {'passk':>5}  {'n/k':>5}  {'greedy':>6}  subject"
    print(header, flush=True)
    print("-" * 72, flush=True)
    for r in results:
        sha = r.get("sha", "?")
        subj = r.get("subject", "?")
        if r["skipped"]:
            print(f"{sha:>8}  {'SKIP':>5}  {'':>5}  {'':>6}  {subj} [{r.get('reason','')}]",
                  flush=True)
        else:
            passk_s = "YES" if r["passk"] else "no"
            nk_s = f"{r['n_passed']}/{k}"
            greedy_s = "PASS" if r.get("greedy_pass") else "fail"
            print(f"{sha:>8}  {passk_s:>5}  {nk_s:>5}  {greedy_s:>6}  {subj}", flush=True)

    print("-" * 72, flush=True)
    print(f">>> pass@1  (known fail from bigbar)          = 0/{n_tasks} = 0.0%", flush=True)
    print(f">>> greedy  (temp=0, 1-shot, no fix-loop)     = {n_greedy}/{n_tasks}"
          f" = {n_greedy / n_tasks * 100:.1f}%  (informational, may differ from full pipeline)",
          flush=True)
    print(f">>> pass@{k:<3} (any of k blind samples pass)    = {n_passk}/{n_tasks}"
          f" = {n_passk / n_tasks * 100:.1f}%", flush=True)

    if n_tasks > 0:
        lo, hi = wilson(n_passk, n_tasks)
        print(f">>> Wilson95: [{lo * 100:.1f}%, {hi * 100:.1f}%]", flush=True)
        gap_pct = n_passk / n_tasks * 100
        print(f"", flush=True)
        if gap_pct >= 20:
            print(f">>> VERDICT: STRONG LATENT CAPABILITY — pass@k={gap_pct:.1f}% >> pass@1=0%",
                  flush=True)
            print(f">>> The bottleneck is SELECTION (verifier), not model capability.",
                  flush=True)
            print(f">>> Next: build a selector that picks the passing sample from k candidates.",
                  flush=True)
        elif gap_pct > 0:
            print(f">>> VERDICT: WEAK SIGNAL — pass@k={gap_pct:.1f}% > pass@1=0%", flush=True)
            print(f">>> Some latent capability. Try larger k or adjusted temp.", flush=True)
        else:
            print(f">>> VERDICT: NO LATENT SIGNAL — pass@k=0% across {k} samples.", flush=True)
            print(f">>> These tasks may need deeper decomposition or retrieval scaffolding.",
                  flush=True)
    print(f"{'=' * 72}", flush=True)

# #EXT-019-REQ-2 End


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "EXT-019: pass@k latent-capability probe.\n"
            "Measures whether the 2B can produce correct solutions within k tries\n"
            "for tasks the current harness fails at pass@1.\n"
            "HONEST: oracle is score-only; model never sees oracle output during sampling."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tasks", type=int, default=15,
        help="Number of [fail] tasks to probe from bigbar_jaros.txt (default: 15)",
    )
    parser.add_argument(
        "--k", type=int, default=20,
        help="Number of blind samples per task (default: 20)",
    )
    parser.add_argument(
        "--temp", type=float, default=0.8,
        help="Sampling temperature for code generation (default: 0.8)",
    )
    args = parser.parse_args()
    run_probe(n=args.tasks, k=args.k, temp=args.temp)
