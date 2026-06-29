"""Qwen2.5-Coder-3B profiler — earns and records class coverage honestly (EXT-021, REQ-4/REQ-5).

Usage (operator, AFTER serving qwen on the Jetson via the model-manager):

    python -m harness.profile_qwen --humaneval 20 --hard 8

The profiler:
1. Records the currently-served model (GET model-manager /current).
2. Ensures qwen2.5-coder-3b is served (POST model-manager /serve qwen2.5-coder-3b).
3. CLASS standalone-fn-gen: HumanEval[:N] pass@1 with qwen_code direct gen; score >=50%.
4. CLASS multi-step-repo: first M bigbar [fail] greedy-fail tasks solved with qwen_code,
   scored via the _run_nodes Docker oracle (red->green); bar >=1/M cracked.
   (Gemma's pass@k probe got 0/7 on this class — the hard class gemma fails.)
5. Records earned classes into qwen's profile JSON ONLY if the bar is cleared (honest,
   Tenet 3): a class appears in classes[] only with recorded evidence {name, bar, score, date}.
6. ALWAYS restores the original served model in a finally block, even on eval error.
7. Prints a clear REPORT: standalone-fn-gen score, multi-step-repo cracks/M, and the
   VERDICT: does qwen cover a class gemma fails?

All serve/restore/eval functions are INJECTABLE for offline testing (no live Jetson,
no Docker, no real LLM calls needed in tests).

Estimated live runtime
----------------------
  --humaneval 20  :  ~10-15 min (20 HumanEval problems, 60s each max)
  --hard 8        :  ~20-40 min (8 Docker oracle runs, up to 3 min each)
  Restore         :  ~15-20 s (model swap)
  Total           :  ~35-60 min

Restoring original model: gemma is ALWAYS restored in the finally block even if
the eval raises. The model-manager API (port 8001) handles the swap; the Jetson
remains unchanged if the API is unreachable (error is printed, not silenced).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

# #EXT-021-REQ-4 Start
# #EXT-021-REQ-5 Start

_ROOT = Path(__file__).resolve().parents[1]
_MODELS_DIR = _ROOT / ".jaros-data" / "config" / "models"
_QWEN_ID = "qwen2.5-coder-3b"

# Honesty bars (Tenet 3 — a class is ONLY earned with evidence)
_HE_BAR_PCT: float = 0.50    # standalone-fn-gen: >=50% HumanEval pass@1
_REPO_BAR_N: int = 1          # multi-step-repo: >=1 cracked (gemma gets 0 on the hard set)


# ---------------------------------------------------------------------------
# Helper: parse bigbar result file for [fail] SHAs
# ---------------------------------------------------------------------------

def _parse_fail_shas(bigbar_txt: Path) -> list[str]:
    """Extract 8-char SHA prefixes for [fail] lines in a bigbar results file.

    Parses lines like:
        2/101 [more-itertools] cca32949 [fail] | fix last() when ...
    Returns e.g. ["cca32949", "f8ccab22", ...] in order of appearance.
    Returns [] when the file does not exist or has no [fail] lines.
    """
    if not bigbar_txt.is_file():
        return []
    shas: list[str] = []
    for line in bigbar_txt.read_text(encoding="utf-8").splitlines():
        m = re.search(r"\] (\w{8}) \[fail\]", line)
        if m:
            shas.append(m.group(1))
    return shas


def _load_fail_tasks(m_count: int, repos_dir: Optional[Path] = None) -> list[dict]:
    """Load the first *m_count* [fail] tasks from the bigbar corpus.

    Reads bigbar_jaros.txt to find gemma's fail SHAs, then loads the corpus
    JSON files (more-itertools_valid_tasks.json etc.) and returns the matching
    task dicts in the same order.  Returns [] when either the bigbar file or the
    corpus JSONs are missing (caller reports this gracefully).
    """
    try:
        from harness.commit_replay import tasks_corpus
    except ImportError:
        return []
    bigbar_txt = _ROOT / ".jaros-data" / "artifacts" / "bigbar_jaros.txt"
    fail_shas = _parse_fail_shas(bigbar_txt)
    if not fail_shas:
        return []
    corpus = tasks_corpus(repos_dir=repos_dir)
    by_sha8: dict[str, dict] = {t["sha"][:8]: t for t in corpus}
    fail_tasks = [by_sha8[s] for s in fail_shas if s in by_sha8]
    return fail_tasks[:m_count]


# ---------------------------------------------------------------------------
# Real eval implementations (used in production; inject stubs in tests)
# ---------------------------------------------------------------------------

def _real_humaneval_eval(n: int) -> dict:
    """HumanEval[:n] pass@1 using qwen_code direct gen. Returns result dict."""
    import importlib.util as _ilu
    from harness.qwen_adapt import qwen_code
    from harness.humaneval import _read_problems, problem_to_task
    from harness.eval_runner import setup_task
    from harness.pass1_eval import _run_with_treekill

    problems = _read_problems()[:n]
    tasks = [problem_to_task(p) for p in problems]

    # Load body_completer for signature_and_docstring (reuse proven sig extraction)
    _bc_spec = _ilu.spec_from_file_location(
        "_qwen_bc_he",
        _ROOT / ".jaros-data" / "agents" / "body_completer_agent.py",
    )
    _bc = _ilu.module_from_spec(_bc_spec)
    _bc_spec.loader.exec_module(_bc)

    passed = 0
    for task in tasks:
        with tempfile.TemporaryDirectory() as d:
            target = setup_task(task, Path(d))
            stub = Path(target).read_text(encoding="utf-8")
            m_fn = re.search(r"def\s+(\w+)", stub)
            fn_name = m_fn.group(1) if m_fn else "solution"
            sig_doc = _bc.signature_and_docstring(stub)
            # Direct qwen_code: no Gherkin, no body-only splice — full function gen
            solution = qwen_code(task.instruction, fn_name, sig_doc)
            Path(d, "solution.py").write_text(solution, encoding="utf-8", newline="\n")
            ok = _run_with_treekill(task.test_cmd, d, timeout=60)
        if ok:
            passed += 1

    total = len(tasks)
    pct = passed / total if total else 0.0
    return {
        "passed": passed,
        "total": total,
        "score": f"~{passed}/{total} ({pct * 100:.0f}%)",
        "passed_bool": pct >= _HE_BAR_PCT,
    }


def _real_repo_eval(m_count: int, repos_dir: Optional[Path] = None) -> dict:
    """Solve first m_count bigbar [fail] tasks with qwen_code, scored via Docker oracle.

    Mirrors attempt_gherkin_jaros's structure but uses qwen_code (direct instruct,
    no Gherkin) instead of the multi-step Gherkin+self-test loop.
    Honest: the oracle (_run_nodes) scores; nothing leaks the hidden tests into the
    generation prompt.
    """
    from harness.qwen_adapt import qwen_code
    from harness.commit_replay import (
        _target_funcs, _file_context, _apply_func, _test_source,
        _run_nodes, _reset, _git, _spec,
    )

    if repos_dir is None:
        repos_dir = _ROOT / ".jaros-data" / "repos"

    fail_tasks = _load_fail_tasks(m_count, repos_dir=repos_dir)
    if not fail_tasks:
        return {
            "cracked": 0,
            "total": 0,
            "passed_bool": False,
            "score": "0/0",
            "error": "no [fail] tasks found (bigbar_jaros.txt or corpus JSONs missing)",
        }

    def _attempt(task: dict) -> str:
        """Attempt one repo task with qwen_code. Returns 'pass'/'fail'/'no_target'/etc."""
        repo = repos_dir / task["repo"]
        branch = (_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() or "main")
        targets = _target_funcs(repo, task)
        if not targets:
            return "no_target"
        if len(targets) > 4:
            return "capped"
        files = sorted({cf for cf, _, _ in targets})
        try:
            _git(repo, "checkout", "-f", task["parent"])
            _git(repo, "checkout", task["sha"], "--", _spec(repo)["test"])
            orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
            ctx = {cf: _file_context(orig[cf]) for cf in files}
            final: dict[str, dict] = {}
            for cf, fn_name, parent_src in targets:
                test_src = _test_source(repo, task)
                # Build context: current source + failing test + module preamble.
                # HONESTY: test_src is the FAILING (red) test from the task — the visible
                # spec.  The HIDDEN oracle (task["redgreen"]) is NEVER passed here; it only
                # scores at the end via _run_nodes.
                parts: list[str] = []
                if parent_src:
                    parts.append(f"Current implementation:\n{parent_src}")
                parts.append(f"Failing test (must pass after your change):\n{test_src[:1600]}")
                if ctx[cf]:
                    parts.append(f"Module context:\n{ctx[cf]}")
                context = "\n\n".join(parts)
                code = qwen_code(f"COMMIT INTENT: {task['subject']}", fn_name, context)
                final.setdefault(cf, {})[fn_name] = code or ""
            for cf in files:
                content = orig[cf]
                for n2, c2 in final.get(cf, {}).items():
                    if c2:
                        content = _apply_func(content, n2, c2)
                (repo / cf).write_text(content, encoding="utf-8", newline="\n")
            return "pass" if not _run_nodes(repo, task["redgreen"]) else "fail"
        except Exception as exc:  # noqa: BLE001
            return f"err:{type(exc).__name__}"
        finally:
            _reset(repo, branch)

    cracked = 0
    total = len(fail_tasks)
    for i, task in enumerate(fail_tasks):
        r = _attempt(task)
        print(
            f"  repo {i + 1}/{total} {task['sha'][:8]} [{r}] | {task['subject'][:50]}",
            flush=True,
        )
        if r == "pass":
            cracked += 1

    return {
        "cracked": cracked,
        "total": total,
        "passed_bool": cracked >= _REPO_BAR_N,
        "score": f"{cracked}/{total}",
    }


# ---------------------------------------------------------------------------
# Production serve / restore via model-manager HTTP API (injectable in tests)
# ---------------------------------------------------------------------------

def _default_serve_fn() -> None:
    """Serve qwen2.5-coder-3b via the model-manager API (Jetson HTTP, port 8001)."""
    from harness.model_rewire import _manager_swap
    result = _manager_swap(_QWEN_ID)
    if not result.get("ok"):
        raise RuntimeError(
            f"model-manager failed to serve {_QWEN_ID}: {result}"
        )


def _default_get_current_fn() -> Optional[str]:
    """Return the currently-served model id from the model-manager (None if unknown)."""
    try:
        from harness.model_rewire import _manager_current
        return _manager_current()
    except Exception:
        return None


def _default_restore_fn(model_id: str) -> None:
    """Restore *model_id* via the model-manager API. Errors are logged, not raised."""
    if not model_id:
        return
    try:
        from harness.model_rewire import _manager_swap
        _manager_swap(model_id)
    except Exception as exc:
        print(f"  [WARN] restore to {model_id!r} failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core profiling function — all side-effects are injectable (offline-testable)
# ---------------------------------------------------------------------------

def run_profile_qwen(
    *,
    n: int = 20,
    m: int = 8,
    models_dir: Optional[Path] = None,
    serve_fn: Optional[Callable[[], None]] = None,
    get_current_fn: Optional[Callable[[], Optional[str]]] = None,
    restore_fn: Optional[Callable[[str], None]] = None,
    humaneval_eval_fn: Optional[Callable[[int], dict]] = None,
    repo_eval_fn: Optional[Callable[[int], dict]] = None,
    repos_dir: Optional[Path] = None,
    now: Optional[Callable[[], str]] = None,
) -> dict:
    """Profile qwen2.5-coder-3b and record earned classes into its profile JSON.

    All side-effecting operations are injectable so the function runs fully
    offline in tests (no live Jetson, no Docker, no real LLM calls).

    Parameters
    ----------
    n : int
        Number of HumanEval problems for standalone-fn-gen eval (default 20).
    m : int
        Number of bigbar [fail] tasks for multi-step-repo eval (default 8).
    models_dir : Path, optional
        Directory containing qwen's profile JSON. Defaults to
        ``.jaros-data/config/models/``.
    serve_fn : callable, optional
        ``() -> None``: ensure qwen2.5-coder-3b is served on the Jetson.
        Default: POST model-manager /serve qwen2.5-coder-3b.
    get_current_fn : callable, optional
        ``() -> str | None``: return the currently-served model id (for restore).
        Default: GET model-manager /current.
    restore_fn : callable, optional
        ``(model_id: str) -> None``: restore the original served model in finally.
        Default: POST model-manager /serve <original>.
    humaneval_eval_fn : callable, optional
        ``(n: int) -> dict``: run the HumanEval eval. Returns a dict with
        at minimum ``{"passed_bool": bool, "score": str}``.
        Default: real qwen_code HumanEval pass@1 (requires Jetson serving qwen).
    repo_eval_fn : callable, optional
        ``(m: int) -> dict``: run the multi-step-repo eval. Returns a dict with
        at minimum ``{"passed_bool": bool, "cracked": int, "total": int, "score": str}``.
        Default: real qwen_code + Docker oracle on bigbar [fail] tasks.
    repos_dir : Path, optional
        Path to local repo checkouts (used by the default repo_eval_fn).
    now : callable, optional
        ``() -> str``: ISO date string for evidence records. Default: today.

    Returns
    -------
    dict
        ``{"added": [...], "rejected": [...], "he_result": {...}, "repo_result": {...}}``

        added    — class names written to the profile (bar cleared).
        rejected — class names NOT added (below bar — honest).
    """
    import datetime

    if models_dir is None:
        models_dir = _MODELS_DIR
    models_dir = Path(models_dir)

    _now: Callable[[], str] = (
        now if now is not None else (lambda: datetime.date.today().isoformat())
    )

    # Wire real implementations as defaults (injectable = None means use real)
    _serve = serve_fn if serve_fn is not None else _default_serve_fn
    _get_current = get_current_fn if get_current_fn is not None else _default_get_current_fn
    _restore = restore_fn if restore_fn is not None else _default_restore_fn
    _he_eval: Callable[[int], dict] = (
        humaneval_eval_fn if humaneval_eval_fn is not None
        else (lambda n_: _real_humaneval_eval(n_))
    )
    _repo_eval: Callable[[int], dict] = (
        repo_eval_fn if repo_eval_fn is not None
        else (lambda m_: _real_repo_eval(m_, repos_dir=repos_dir))
    )

    # Record original model BEFORE touching anything (for the finally restore)
    original_model: Optional[str] = _get_current()
    print(f"[profile_qwen] currently served model: {original_model!r}", flush=True)

    # Load qwen's profile JSON (must exist before profiling)
    profile_path = models_dir / f"{_QWEN_ID}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Qwen profile JSON not found: {profile_path}\n"
            "Run: python -m harness.profile_qwen --humaneval 20 --hard 8"
        )
    profile_data: dict = json.loads(profile_path.read_text(encoding="utf-8"))
    existing_names: set[str] = {
        c["name"]
        for c in profile_data.get("classes", [])
        if isinstance(c, dict) and "name" in c
    }

    added: list[str] = []
    rejected: list[str] = []
    he_result: dict = {}
    repo_result: dict = {}

    try:
        # Ensure qwen is served BEFORE any eval calls
        print(f"[profile_qwen] serving {_QWEN_ID} ...", flush=True)
        _serve()
        print(f"[profile_qwen] {_QWEN_ID} is now served.", flush=True)

        # -------------------------------------------------------------------
        # CLASS 1: standalone-fn-gen (HumanEval pass@1)
        # -------------------------------------------------------------------
        if "standalone-fn-gen" not in existing_names:
            print(
                f"\n[profile_qwen] CLASS standalone-fn-gen: HumanEval[:{n}] ...",
                flush=True,
            )
            he_result = _he_eval(n)
            he_passed = bool(he_result.get("passed_bool", False))
            he_score = he_result.get("score", "?")
            verdict = "PASSED BAR" if he_passed else "BELOW BAR"
            print(
                f"[profile_qwen] standalone-fn-gen: {he_score}  "
                f"(bar >=50%)  -> {verdict}",
                flush=True,
            )
            if he_passed:
                entry: dict = {
                    "name": "standalone-fn-gen",
                    "bar": f"HumanEval pass@1 >=50% (held-out HumanEval[:{n}])",
                    "score": he_score,
                    "date": _now(),
                    "note": "Qwen2.5-Coder-3B direct instruct gen (qwen-instruct-direct, no Gherkin).",
                }
                profile_data.setdefault("classes", []).append(entry)
                existing_names.add("standalone-fn-gen")
                added.append("standalone-fn-gen")
            else:
                rejected.append("standalone-fn-gen")
        else:
            print(
                "[profile_qwen] standalone-fn-gen: already recorded in profile, skipping.",
                flush=True,
            )
            he_result = {"skipped": True}

        # -------------------------------------------------------------------
        # CLASS 2: multi-step-repo (bigbar [fail] tasks)
        # -------------------------------------------------------------------
        if "multi-step-repo" not in existing_names:
            print(
                f"\n[profile_qwen] CLASS multi-step-repo: first {m} bigbar [fail] tasks ...",
                flush=True,
            )
            repo_result = _repo_eval(m)
            repo_passed = bool(repo_result.get("passed_bool", False))
            cracked = int(repo_result.get("cracked", 0))
            total_r = int(repo_result.get("total", m))
            verdict = "PASSED BAR" if repo_passed else "BELOW BAR"
            print(
                f"[profile_qwen] multi-step-repo: {cracked}/{total_r} cracked  "
                f"(bar >=1)  -> {verdict}",
                flush=True,
            )
            if repo_passed:
                entry = {
                    "name": "multi-step-repo",
                    "bar": (
                        f"bigbar [fail] tasks: >=1/{m} cracked "
                        f"(gemma gets 0 on this hard class)"
                    ),
                    "score": repo_result.get("score", f"{cracked}/{total_r}"),
                    "date": _now(),
                    "note": (
                        "Qwen2.5-Coder-3B direct instruct code-gen on gemma's hard "
                        "multi-step-repo class. Oracle: _run_nodes Docker red->green."
                    ),
                }
                profile_data.setdefault("classes", []).append(entry)
                existing_names.add("multi-step-repo")
                added.append("multi-step-repo")
            else:
                rejected.append("multi-step-repo")
        else:
            print(
                "[profile_qwen] multi-step-repo: already recorded in profile, skipping.",
                flush=True,
            )
            repo_result = {"skipped": True}

        # Persist updated profile JSON
        profile_path.write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
        print(f"\n[profile_qwen] Profile saved: {profile_path}", flush=True)

    finally:
        # ALWAYS restore the original served model — even on eval error (Tenet 3)
        restore_target = original_model or "gemma-4-e2b"
        print(
            f"\n[profile_qwen] Restoring original model: {restore_target!r}",
            flush=True,
        )
        _restore(restore_target)

    # -------------------------------------------------------------------
    # REPORT
    # -------------------------------------------------------------------
    print("\n" + "=" * 70, flush=True)
    print("QWEN2.5-CODER-3B PROFILING REPORT", flush=True)
    print("=" * 70, flush=True)

    print(f"\n  standalone-fn-gen  (HumanEval[:{n}] pass@1):", flush=True)
    if he_result.get("skipped"):
        print("    [already recorded — skipped]", flush=True)
    else:
        he_verdict = "EARNED" if "standalone-fn-gen" in added else "REJECTED (below bar)"
        print(f"    score : {he_result.get('score', '?')}", flush=True)
        print(f"    bar   : >=50% HumanEval pass@1", flush=True)
        print(f"    result: {he_verdict}", flush=True)

    print(f"\n  multi-step-repo  (first {m} bigbar [fail] tasks):", flush=True)
    if repo_result.get("skipped"):
        print("    [already recorded — skipped]", flush=True)
    else:
        repo_verdict = "EARNED" if "multi-step-repo" in added else "REJECTED (below bar)"
        cracked_r = repo_result.get("cracked", 0)
        total_r2 = repo_result.get("total", m)
        print(f"    cracked: {cracked_r}/{total_r2}", flush=True)
        print(f"    bar    : >=1 cracked (gemma gets 0 on this class)", flush=True)
        print(f"    result : {repo_verdict}", flush=True)

    covers = "multi-step-repo" in added
    print(f"\n  Classes earned  : {added if added else 'none'}", flush=True)
    print(f"  Classes rejected: {rejected if rejected else 'none'}", flush=True)
    print(
        f"\n  VERDICT: Does qwen cover a class gemma fails (multi-step-repo)? "
        f"{'YES' if covers else 'NO'}",
        flush=True,
    )
    print("=" * 70, flush=True)

    return {
        "added": added,
        "rejected": rejected,
        "he_result": he_result,
        "repo_result": repo_result,
    }

# #EXT-021-REQ-4 End
# #EXT-021-REQ-5 End


def main() -> None:
    """CLI entry point: python -m harness.profile_qwen [--humaneval N] [--hard M]"""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Profile qwen2.5-coder-3b on standalone-fn-gen and multi-step-repo classes.\n\n"
            "IMPORTANT: Requires the Jetson to be reachable and qwen to be loadable.\n"
            "The model-manager (port 8001) must be running on the Jetson.\n"
            "Gemma is restored automatically in a finally block after the run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--humaneval", type=int, default=20, metavar="N",
        help="HumanEval problems for standalone-fn-gen eval (default: 20).",
    )
    parser.add_argument(
        "--hard", type=int, default=8, metavar="M",
        help="Bigbar [fail] tasks for multi-step-repo eval (default: 8).",
    )
    parser.add_argument(
        "--repos-dir", type=Path, default=None,
        help="Path to local repo checkouts (.jaros-data/repos by default).",
    )
    parser.add_argument(
        "--models-dir", type=Path, default=None,
        help="Path to model profile JSON directory (default: .jaros-data/config/models/).",
    )
    args = parser.parse_args()

    run_profile_qwen(
        n=args.humaneval,
        m=args.hard,
        models_dir=args.models_dir,
        repos_dir=args.repos_dir,
    )


if __name__ == "__main__":
    main()
