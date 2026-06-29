"""New-class recorder for the multi-model routing harness (EXT-021, REQ-7 DISCOVER).

When ``model_router.route`` falls back to the deterministic default because no
measured coverage exists for the classified problem class (HARNESS-GAP), it calls
``record_unhandled`` here.  Each call appends a single JSONL record to
``.jaros-data/artifacts/new_classes.jsonl``.

The governance loop calls ``review_new_classes`` to inspect clusters of recurring
unhandled signatures.  When a cluster exceeds a threshold, that is the signal to
name a new class and re-profile the roster (REQ-5).

Writing is strictly best-effort: this module never raises into the caller; a
logging failure is silently swallowed so the routing decision path stays clean.
"""
from __future__ import annotations

# #EXT-021-REQ-7 Start
import datetime
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_DEFAULT_LOG_PATH = Path(".jaros-data/artifacts/new_classes.jsonl")

# Maximum chars of task text stored as a sample in each record
_SAMPLE_LEN = 200


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise(problem: Any) -> dict:
    """Return *problem* as a plain dict; never raises."""
    if isinstance(problem, dict):
        return problem
    try:
        return vars(problem)
    except TypeError:
        return {}


def _detect_language(p: dict) -> str:
    """Cheap language detection from explicit field, file extensions, or source patterns."""
    explicit = p.get("language")
    if explicit and isinstance(explicit, str):
        lang = explicit.strip().lower()
        if lang:
            return lang

    # Check file extensions
    files = p.get("files", [])
    if isinstance(files, dict):
        files = list(files.keys())
    for f in (files or []):
        ext = Path(str(f)).suffix.lower()
        if ext == ".py":
            return "python"
        if ext in (".js", ".ts", ".jsx", ".tsx"):
            return "javascript"
        if ext == ".java":
            return "java"
        if ext == ".go":
            return "go"
        if ext == ".rs":
            return "rust"
        if ext in (".cpp", ".cc", ".cxx", ".c", ".h"):
            return "cpp"

    # Heuristic on source
    source: str = str(p.get("source", p.get("prompt", p.get("text", ""))))
    if "def " in source or "import " in source or "class " in source:
        return "python"
    if "function " in source or "const " in source or "let " in source:
        return "javascript"

    return "unknown"


def _extract_error_signal(p: dict) -> str:
    """Extract a compact error/failure signal from the problem dict if present.

    Looks for common keys that carry traceback or test-failure information and
    returns a short canonical string: ``"ErrorType:touched-symbol"`` or the
    last non-empty line of the error text.  Empty string when no signal found.
    """
    for key in ("error", "traceback", "test_output", "exception", "failure", "stderr"):
        val = p.get(key)
        if val and isinstance(val, str):
            # Try to extract a named exception type + brief context
            match = re.search(
                r"(AttributeError|TypeError|ValueError|ImportError|NameError|"
                r"AssertionError|KeyError|IndexError|RuntimeError|SyntaxError)"
                r"[:\s]*([^\n]{0,60})",
                val,
            )
            if match:
                return f"{match.group(1)}:{match.group(2).strip()[:60]}"
            # Fall back to last non-empty line (e.g. a test assertion message)
            lines = [ln.strip() for ln in val.splitlines() if ln.strip()]
            if lines:
                return lines[-1][:80]
    return ""


def _fn_len_bucket(n: int) -> str:
    if n <= 0:
        return "empty"
    if n < 15:
        return "small"
    if n < 50:
        return "medium"
    return "large"


def _source_len_bucket(n: int) -> str:
    if n <= 0:
        return "empty"
    if n < 300:
        return "short"
    if n < 1500:
        return "medium"
    return "long"


def _build_signature(p: dict) -> dict:
    """Build a deterministic, cheap feature signature from a normalised problem dict.

    All field lookups are defensive; missing or wrong-typed fields fall back to
    safe defaults so this never raises.
    """
    source: str = str(p.get("source", p.get("prompt", p.get("text", ""))))
    fn_len = len(source.splitlines()) if source else 0
    source_len = len(source)

    has_examples_flag = p.get("has_examples")
    if has_examples_flag is None:
        has_examples: bool = ">>>" in source
    else:
        has_examples = bool(has_examples_flag)

    is_repo_flag = p.get("is_repo_task")
    if is_repo_flag is None:
        is_repo_task: bool = bool(
            p.get("repo_root") or p.get("repo_path") or p.get("task_type") == "repo"
        )
    else:
        is_repo_task = bool(is_repo_flag)

    is_multi_flag = p.get("is_multi_file")
    if is_multi_flag is None:
        files = p.get("files", [])
        is_multi_file: bool = bool(
            (isinstance(files, (list, tuple)) and len(files) > 1)
            or (isinstance(files, dict) and len(files) > 1)
        )
    else:
        is_multi_file = bool(is_multi_flag)

    return {
        "language": _detect_language(p),
        "is_repo_task": is_repo_task,
        "is_multi_file": is_multi_file,
        "has_examples": has_examples,
        "fn_len_bucket": _fn_len_bucket(fn_len),
        "source_len_bucket": _source_len_bucket(source_len),
        "error_signal": _extract_error_signal(p),
    }


def _signature_key(sig: dict) -> tuple:
    """Return a hashable, deterministic key from a signature dict for grouping."""
    return (
        sig.get("language", "unknown"),
        bool(sig.get("is_repo_task", False)),
        bool(sig.get("is_multi_file", False)),
        bool(sig.get("has_examples", False)),
        sig.get("fn_len_bucket", "empty"),
        sig.get("source_len_bucket", "empty"),
        sig.get("error_signal", ""),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_unhandled(
    problem: Any,
    decision: dict,
    *,
    path: "str | Path | None" = None,
) -> None:
    """Append one JSONL record for an unhandled (HARNESS-GAP) problem.

    Parameters
    ----------
    problem:
        The raw problem passed to ``route()``.  Accepts dict or any object with
        ``__dict__``; missing fields are handled defensively.
    decision:
        The inert decision dict returned by ``route()``.  Expected keys:
        ``model_id``, ``confidence``, ``rationale``, ``problem_class``.
    path:
        Override the output file path.  Defaults to
        ``.jaros-data/artifacts/new_classes.jsonl``.  Pass a tmp path in tests.

    Notes
    -----
    Never raises.  All exceptions are silently swallowed so the routing decision
    path is never blocked by a logging failure (best-effort, Tenet 1).
    """
    log_path = Path(path) if path is not None else _DEFAULT_LOG_PATH
    try:
        p = _normalise(problem)
        sig = _build_signature(p)
        source: str = str(p.get("source", p.get("prompt", p.get("text", ""))))
        record: dict = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "signature": sig,
            "chosen_default": str(decision.get("model_id", "")),
            "confidence": float(decision.get("confidence", 0.0)),
            "rationale": str(decision.get("rationale", "")),
            "problem_class": str(decision.get("problem_class", "")),
            "task_sample": source[:_SAMPLE_LEN],
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # best-effort; never block the caller


def review_new_classes(*, path: "str | Path | None" = None) -> dict:
    """Read the unhandled-class log and return a summary for the governance loop.

    Parameters
    ----------
    path:
        Override the log file path.  Defaults to
        ``.jaros-data/artifacts/new_classes.jsonl``.

    Returns
    -------
    dict
        ``total``          int   — total records in the log.
        ``groups``         dict  — str(signature_key) -> list[record].
        ``top_signatures`` list  — [(str(signature_key), count), ...] sorted
                                   descending by count, so the most-recurring
                                   unhandled signature is first.

    When a top signature's count exceeds a governance threshold the loop should
    name a new class and trigger re-profiling (REQ-5).
    """
    log_path = Path(path) if path is not None else _DEFAULT_LOG_PATH

    records: list[dict] = []
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass  # corrupt file -> return what was successfully parsed

    groups: dict[tuple, list[dict]] = {}
    for rec in records:
        raw_sig = rec.get("signature", {})
        key = _signature_key(raw_sig) if isinstance(raw_sig, dict) else (str(raw_sig),)
        groups.setdefault(key, []).append(rec)

    counts: Counter = Counter({k: len(v) for k, v in groups.items()})
    top = counts.most_common()

    return {
        "total": len(records),
        "groups": {str(k): v for k, v in groups.items()},
        "top_signatures": [(str(k), cnt) for k, cnt in top],
    }

# #EXT-021-REQ-7 End
