"""EXT-027 -- Verified-solution memory (a memory form, kill-test-gated).

When a solve PASSES the test gate, ``record_verified`` appends the (problem,
code) pair to a persistent JSONL store keyed by the deterministic problem
signature.  ``recall_similar`` retrieves the most structurally similar PAST
verified solution for a new problem -- using DETERMINISTIC signature matching
(no embeddings, per the retrieval-negative caution).  ``inject_verified_example``
formats the recalled solution as a WORKED EXAMPLE block to prepend to a solve
prompt, so memory can change the solve.

DISCIPLINE (HYPOTHESIS to KILL-TEST, not assume):
The prior behavior-keyed RAG few-shot was a MEASURED NEGATIVE on the 2B.
This module builds the scaffold; the KILL-TEST -- comparing solve WITH vs
WITHOUT injected recalled verified examples on an honest bar (HumanEval/MBPP
or the 101-bar) -- is DOCUMENTED here and must be run before trusting this
memory form as a default lever.  A NON-RESULT is the honest expected outcome;
record it faithfully either way.

HONESTY INVARIANT: ``recall_similar`` NEVER returns a solution for the same
task as the current problem (exact ``task_sample`` match is excluded).  The
memory can only show solutions from DIFFERENT past problems.

Store path: ``.jaros-data/artifacts/solution_memory.jsonl``
"""
from __future__ import annotations

# #EXT-027-REQ-1 Start
import datetime
import json
from pathlib import Path
from typing import Any

from harness.new_class_log import _build_signature, _normalise  # noqa: PLC2701

_DEFAULT_PATH = Path(".jaros-data/artifacts/solution_memory.jsonl")

# Max chars of task source stored as task_sample (consistent with new_class_log)
_SAMPLE_LEN = 200


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_problem_class(p: dict, sig: dict) -> str:
    """Derive a problem class string from the problem dict or its signature.

    Checks the explicit ``problem_class`` field first; falls back to
    deterministic rules derived from signature features.  This is the same
    logic applied for both recording and recalling, so similar problems
    receive the same class label on both sides.
    """
    explicit = p.get("problem_class")
    if explicit and isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if sig.get("is_repo_task"):
        return "multi-step-repo"
    if sig.get("is_multi_file"):
        return "multi-file"
    return "standalone-fn-gen"


def _sig_overlap_score(sig_a: dict, sig_b: dict) -> int:
    """Deterministic integer score counting matching signature fields.

    Higher weight on more discriminating features so the best structural
    match floats to the top.  Returns a non-negative integer.
    """
    score = 0
    if sig_a.get("language") == sig_b.get("language"):
        score += 3
    if sig_a.get("fn_len_bucket") == sig_b.get("fn_len_bucket"):
        score += 2
    if sig_a.get("source_len_bucket") == sig_b.get("source_len_bucket"):
        score += 1
    if sig_a.get("has_examples") == sig_b.get("has_examples"):
        score += 1
    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_verified(
    problem: Any,
    code: str,
    *,
    path: "str | Path | None" = None,
) -> None:
    """Append one JSONL record for a verified (test-gate-passing) solution.

    Called by the solve pipeline when a generated candidate passes the
    deterministic test gate.  Stores enough information to later recall and
    inject this solution as a worked example for a similar future problem.

    Parameters
    ----------
    problem:
        The raw problem dict (or object with ``__dict__``).  Missing or
        wrong-typed fields are handled defensively.
    code:
        The generated code that PASSED the test gate.
    path:
        Override the output file path.  Defaults to
        ``.jaros-data/artifacts/solution_memory.jsonl``.

    Notes
    -----
    Never raises.  All exceptions are silently swallowed (best-effort, Tenet 1).
    """
    store_path = Path(path) if path is not None else _DEFAULT_PATH
    try:
        p = _normalise(problem)
        sig = _build_signature(p)
        problem_class = _infer_problem_class(p, sig)
        source: str = str(p.get("source", p.get("prompt", p.get("text", ""))))
        record: dict = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "signature": sig,
            "problem_class": problem_class,
            "code": code,
            "task_sample": source[:_SAMPLE_LEN],
        }
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with store_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # best-effort; never block the caller


def recall_similar(
    problem: Any,
    *,
    path: "str | Path | None" = None,
) -> "dict | None":
    """Find the most structurally similar past verified solution.

    Matching is DETERMINISTIC -- by signature overlap score (no embeddings,
    per the retrieval-negative caution from the prior RAG negative result).
    The current problem's own task is EXCLUDED by exact ``task_sample``
    match (honesty invariant: never recall the target's own answer).

    Parameters
    ----------
    problem:
        The raw problem dict.  Missing or wrong-typed fields handled
        defensively.
    path:
        Override the store path.

    Returns
    -------
    dict | None
        ``{"code": str, "signature": dict, "problem_class": str}`` for the
        best same-class match, or ``None`` when no suitable match exists
        (store absent, no same-class records, or all same-class records are
        the same task).
    """
    store_path = Path(path) if path is not None else _DEFAULT_PATH
    if not store_path.exists():
        return None

    try:
        p = _normalise(problem)
        sig = _build_signature(p)
        problem_class = _infer_problem_class(p, sig)
        source: str = str(p.get("source", p.get("prompt", p.get("text", ""))))
        self_sample = source[:_SAMPLE_LEN]

        records: list[dict] = []
        try:
            with store_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            return None

        best_score = -1
        best_record: "dict | None" = None

        for rec in records:
            # Must be same problem class
            if rec.get("problem_class") != problem_class:
                continue
            # HONESTY: exclude the same task by exact task_sample match
            # Only skip when self_sample is non-empty (avoid over-excluding on
            # empty-source problems)
            if self_sample and rec.get("task_sample") == self_sample:
                continue
            # Score by deterministic signature feature overlap
            rec_sig = rec.get("signature", {})
            if not isinstance(rec_sig, dict):
                continue
            score = _sig_overlap_score(sig, rec_sig)
            if score > best_score:
                best_score = score
                best_record = rec

        if best_record is None:
            return None

        return {
            "code": best_record.get("code", ""),
            "signature": best_record.get("signature", {}),
            "problem_class": best_record.get("problem_class", ""),
        }
    except Exception:
        return None


def inject_verified_example(
    spec_or_context: str,
    recalled: "dict | None",
) -> str:
    """Prepend a verified worked-example block to a solve prompt.

    If ``recalled`` is None, empty, or has no code, returns
    ``spec_or_context`` unchanged so callers can always call this
    unconditionally.

    The block is clearly labelled so the model sees it as a reference from a
    DIFFERENT past problem, not this task's answer -- matching the honesty
    framing in ``maximal_help_probe._build_maxhelp_prompt``.

    Parameters
    ----------
    spec_or_context:
        The solve prompt or context string to augment.
    recalled:
        The result of ``recall_similar`` -- a dict with ``code``,
        ``signature``, ``problem_class``, or None.

    Returns
    -------
    str
        The augmented context with the worked-example block prepended, or
        the original string when ``recalled`` is None or has no usable code.
    """
    if not recalled:
        return spec_or_context
    code = recalled.get("code", "")
    if not code or not code.strip():
        return spec_or_context
    problem_class = recalled.get("problem_class", "unknown")
    block = (
        "=== VERIFIED SOLUTION MEMORY"
        " (from a similar past problem -- NOT this task's answer) ===\n"
        f"Problem class: {problem_class}\n"
        "Here is a verified solution to a similar problem:\n"
        f"{code.rstrip()}\n"
        "=== END VERIFIED SOLUTION MEMORY ===\n\n"
    )
    return block + spec_or_context

# #EXT-027-REQ-1 End
