"""MBPP eval for qwen2.5-coder-3b — verify standalone-fn-gen edge vs gemma (EXT-021/REQ-5).

OPERATOR: Serve qwen FIRST (via the model-manager or curl POST /serve qwen2.5-coder-3b),
then run:

    python -m harness.eval_qwen_mbpp [N]

where N is the number of MBPP problems (default 20). Do NOT call this while gemma is
served — it reads whatever model is currently on :8000.

WHY MBPP (not just HumanEval)
==============================
Qwen2.5-coder-3b scores ~92% HumanEval vs gemma's ~82%. HumanEval is widely believed to
be more contaminated in code-coder pre-training data than MBPP. This eval runs the same
qwen_code direct-instruct gen on MBPP[:N], giving an honest second measurement that
distinguishes real capability from benchmark memorisation.

MBPP vs HumanEval: key differences handled here
================================================
HumanEval problems include a ``def {fn_name}(...)`` stub with the FULL signature and
docstring. We extract fn_name from that stub (``re.search(r"def\\s+(\\w+)", stub)``).

MBPP problems are DIFFERENT:
- The stub written by ``problem_to_task`` is ``def {entry}(*args, **kwargs): raise
  NotImplementedError`` — a generic placeholder, NOT a real signature.
- The REAL function name lives in the test_list asserts, e.g.
  ``assert add_two_numbers(1, 2) == 3`` → fn_name = ``add_two_numbers``.
- There is NO signature/docstring preamble to prepend (unlike HumanEval's import lines).
  Instead we scan the generated code and prepend any detected stdlib imports so that
  solution.py is self-contained and importable.

A naive HumanEval copy that reads fn_name from a def-stub, or defaults to "solution",
would produce a function with the WRONG name → ``from solution import {entry}`` in the
test file would raise ImportError → ALL tasks fail → a false-low score (the exact trap
this eval avoids).

Honesty
=======
- The MBPP test asserts (visible in the problem dict) are included in the spec shown to
  qwen — they are the visible contract. The hidden oracle (the hidden tests in mbpp.jsonl)
  never touches the generation prompt; they only score.
- The run prints per-task results and a final comparison to gemma's known MBPP scores.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]

# #EXT-021-REQ-5 Start


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gather_needed_imports(code: str) -> str:
    """Scan the generated function for common stdlib module attribute accesses and return
    the necessary import lines (e.g. ``import math\\n``).

    qwen_code's fence-stripping slices from ``def {name}`` onward, so any ``import``
    lines qwen emitted ABOVE the def are dropped. This function re-detects the need by
    looking for ``module.something`` attribute access patterns in the code body, then
    prepends the required top-level import.

    Only adds an import when the module is accessed via ``mod.`` notation (the most
    common case in MBPP solutions). Local ``import math`` inside the function body, if
    qwen wrote one, still works fine — the two forms are not mutually exclusive.
    """
    stdlib_modules = [
        "math", "re", "collections", "heapq", "itertools", "functools",
        "string", "sys", "os", "random", "statistics", "operator", "bisect",
        "copy", "json", "datetime", "struct", "io",
    ]
    needed: list[str] = []
    for mod in stdlib_modules:
        if re.search(rf'\b{re.escape(mod)}\s*\.', code):
            needed.append(f"import {mod}")
    return ("\n".join(needed) + "\n") if needed else ""


# ---------------------------------------------------------------------------
# Main eval
# ---------------------------------------------------------------------------

def run_qwen_mbpp(
    n: int = 20,
    *,
    _problems_override: Optional[list] = None,
    _qwen_code_fn: Optional[Callable] = None,
    _run_fn: Optional[Callable] = None,
) -> dict:
    """Run MBPP[:n] through qwen2.5-coder-3b and return {passed, total, score_pct}.

    Parameters
    ----------
    n : int
        Number of MBPP problems to evaluate (default 20).
    _problems_override : list, optional
        Inject a pre-loaded problem list (for offline tests; skips ``_read_problems()``).
    _qwen_code_fn : callable, optional
        ``(spec, fn_name, context) -> str``: code-generation function.
        Default: ``harness.qwen_adapt.qwen_code`` (requires Jetson serving qwen).
    _run_fn : callable, optional
        ``(cmd, cwd, timeout) -> bool``: test runner.
        Default: ``harness.pass1_eval._run_with_treekill``.

    Returns
    -------
    dict
        ``{"passed": int, "total": int, "score_pct": float}``
    """
    # Lazy imports so the module can be imported without loading the heavy harness
    if _qwen_code_fn is None:
        from harness.qwen_adapt import qwen_code as _qwen_code_fn  # type: ignore[assignment]
    if _run_fn is None:
        from harness.pass1_eval import _run_with_treekill as _run_fn  # type: ignore[assignment]

    from harness.mbpp import _entry_point, problem_to_task
    from harness.eval_runner import setup_task

    if _problems_override is not None:
        problems = _problems_override[:n]
    else:
        from harness.mbpp import _read_problems
        problems = _read_problems()[:n]

    passed = 0
    total = 0
    skipped = 0

    print(f"\nqwen MBPP eval  n={n}  (gemma baseline: direct ~25%, gated ~48%)")
    print("  " + "-" * 60)

    for p in problems:
        tid = f"mbpp_{p['task_id']}"

        # MBPP fn_name: extracted from test_list asserts, NOT from any def-stub.
        # This is the CRITICAL difference from the HumanEval path: MBPP stubs are
        # generic ``def {entry}(*args, **kwargs)`` placeholders; reading fn_name from
        # the def would still give the right name (because problem_to_task uses entry),
        # but relying on the def-stub would be fragile and confusing. We go direct to
        # the source: the test asserts that define the visible contract.
        fn_name = _entry_point(p.get("test_list", []))
        if not fn_name:
            print(f"  SKIP  {tid}: no callable entry_point found in test_list", flush=True)
            skipped += 1
            continue

        task = problem_to_task(p)
        if task is None:
            print(f"  SKIP  {tid}: problem_to_task returned None", flush=True)
            skipped += 1
            continue

        total += 1

        # Spec: the natural-language description + the visible test asserts.
        # These are the VISIBLE contract — honest (Tenet 3): the hidden oracle only scores.
        spec = (
            p["text"].strip()
            + "\n\nVisible tests (your function must pass these):\n"
            + "\n".join(p["test_list"])
        )

        # Context: entry point name (so qwen knows the expected function name) +
        # any test_setup_code the MBPP problem provides.
        setup_code = (p.get("test_setup_code") or "").strip()
        context_parts = [f"Function name: {fn_name}"]
        if setup_code:
            context_parts.append(f"Setup code (do not redefine these):\n{setup_code}")
        context = "\n".join(context_parts)

        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            # Write test_solution.py (and any other task files) into the workdir.
            # solution.py is intentionally NOT written yet — we overwrite it below.
            setup_task(task, workdir)

            # Generate the function implementation via qwen's direct-instruct path.
            code = _qwen_code_fn(spec, fn_name, context)

            # Assemble self-contained solution.py:
            # 1. Detect and prepend any stdlib imports referenced in the generated code
            #    (qwen_code slices from ``def {name}`` onward, dropping pre-def imports).
            # 2. Append the generated function def.
            imports_preamble = _gather_needed_imports(code)
            solution_src = imports_preamble + code

            (workdir / "solution.py").write_text(solution_src, encoding="utf-8", newline="\n")

            ok = _run_fn(task.test_cmd, str(workdir), 60)

        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {tid}  fn={fn_name}", flush=True)
        if ok:
            passed += 1

    score_pct = (passed / total * 100) if total else 0.0
    print("  " + "-" * 60)
    if total == 0:
        print("  No problems evaluated (all skipped or dataset missing).", flush=True)
    else:
        print(f"  qwen MBPP pass@1 : {passed}/{total}  ({score_pct:.0f}%)", flush=True)
        print(f"  gemma baseline   : direct ~25%,  gated ~48%", flush=True)
        print(
            f"  HumanEval edge   : qwen 92% vs gemma 82%"
            f" — MBPP result above distinguishes real edge from contamination",
            flush=True,
        )
    if skipped:
        print(f"  skipped (no entry_point): {skipped}", flush=True)

    return {"passed": passed, "total": total, "score_pct": round(score_pct, 1)}

# #EXT-021-REQ-5 End


def main() -> None:
    """CLI entry point: python -m harness.eval_qwen_mbpp [N]

    Requires qwen2.5-coder-3b to be served on the Jetson BEFORE running.
    Does NOT swap the model automatically.

    Example workflow:
        # 1. Serve qwen on the Jetson (model-manager API):
        #    curl -s -X POST http://192.168.1.183:8001/serve \\
        #         -H 'Content-Type: application/json' \\
        #         -d '{"model_id": "qwen2.5-coder-3b"}'
        # 2. Run the eval:
        #    python -m harness.eval_qwen_mbpp 20
        # 3. Restore gemma:
        #    curl -s -X POST http://192.168.1.183:8001/serve \\
        #         -H 'Content-Type: application/json' \\
        #         -d '{"model_id": "gemma-4-e2b"}'
    """
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    run_qwen_mbpp(n=n)


if __name__ == "__main__":
    main()
