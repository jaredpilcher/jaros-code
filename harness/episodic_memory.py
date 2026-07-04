"""Episodic (action+rationale) memory — groundwork + experience-recall for planning.

EXT-036 REQ-24 / PRIME-001 intent capability (f): a durable, referenceable record of
what the system DID and WHY, so a planner can recognize "do that again" / "like
before" requests and retrieve+reconcile against relevant prior work before forming a
new plan.

GUARD (Tenet 3, from a measured negative — see memory
`jaros-code-retrieval-fewshot-negative`): this is PLAN + PROVENANCE recall, NOT
behavior-keyed few-shot CODE examples — that mechanism measured NEGATIVE for solving
quality on the 2B (behavior-keyed RAG few-shot lowered the pass rate). Recall here
informs a plan's CONTEXT (what was done before and why) — it must never be used to
paste stale code into a solving prompt as an example to imitate.

v1 is DETERMINISTIC: no model call, no embeddings. Similarity is plain token-set
Jaccard overlap over `action + rationale` text plus a shared-tag bonus. Embeddings-
based semantic recall is an explicit, separate, later follow-up.

This module is self-contained and never wired into the build/orchestrator paths yet
(an explicit follow-up noted in REQ-24) — it only builds and proves the store +
recall mechanism.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".jaros-data" / "artifacts" / "episodic"
DEFAULT_STORE = ARTIFACTS / "actions.jsonl"

# Deterministic scoring constants (no model call, no randomness).
_TAG_BONUS = 0.25

# #EXT-036-REQ-24 Start


def _safe_str(value: Any) -> str:
    """Best-effort, never-raising coercion to a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _safe_tags(tags: Any) -> list[str]:
    """Best-effort, never-raising coercion of `tags` to a list[str]."""
    if tags is None:
        return []
    if isinstance(tags, (str, bytes)):
        # A single tag passed as a bare string — treat as one tag, not chars.
        s = _safe_str(tags).strip()
        return [s] if s else []
    try:
        out: list[str] = []
        for t in tags:
            s = _safe_str(t).strip()
            if s:
                out.append(s)
        return out
    except Exception:
        return []


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable version of `value`, never raising."""
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except Exception:
        try:
            return str(value)
        except Exception:
            return None


def record_action(
    action: Any,
    rationale: Any,
    *,
    tags: Any = None,
    outcome: Any = None,
    meta: Any = None,
    store: Path | str = DEFAULT_STORE,
) -> dict[str, Any]:
    """Append one `{action, rationale, tags, outcome, meta, seq}` record to `store`.

    Never raises: garbage/`None`/non-string inputs are coerced to safe defaults, and
    any I/O failure (unwritable path, missing parent, etc.) is swallowed — the
    attempted record is still returned so a caller never loses the shape of what it
    tried to record. `seq` is a monotonic, deterministic ordinal derived from the
    store's current line count (no wall-clock dependency).
    """
    store_path = Path(store)

    existing = load_actions(store=store_path)
    seq = len(existing)

    record: dict[str, Any] = {
        "seq": seq,
        "action": _safe_str(action),
        "rationale": _safe_str(rationale),
        "tags": _safe_tags(tags),
        "outcome": _json_safe(outcome),
        "meta": _json_safe(meta),
    }

    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(store_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass  # a store-write failure must never crash the caller (Tenet: never-raise)

    return record


def load_actions(store: Path | str = DEFAULT_STORE) -> list[dict[str, Any]]:
    """Parse `store`'s JSONL, skipping malformed lines. Never raises."""
    store_path = Path(store)
    if not store_path.exists():
        return []

    out: list[dict[str, Any]] = []
    try:
        with open(store_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue  # malformed line — skip, don't fail the whole read
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        return out  # best-effort: return whatever parsed before any I/O error

    return out


def _tokenize(text: Any) -> set[str]:
    s = _safe_str(text).lower()
    return {tok for tok in s.split() if tok}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    union = len(a | b)
    return inter / union if union else 0.0


def _score(query_tokens: set[str], query_tags: set[str], rec: dict[str, Any]) -> float:
    try:
        rec_text = _safe_str(rec.get("action")) + " " + _safe_str(rec.get("rationale"))
    except Exception:
        rec_text = ""
    rec_tokens = _tokenize(rec_text)
    lexical = _jaccard(query_tokens, rec_tokens)

    try:
        rec_tags = {_safe_str(t) for t in (rec.get("tags") or [])}
    except Exception:
        rec_tags = set()
    shared_tags = len(query_tags & rec_tags) if query_tags else 0

    return lexical + (_TAG_BONUS * shared_tags)


def recall_similar(
    query: Any,
    *,
    k: int = 5,
    tags: Any = None,
    store: Path | str = DEFAULT_STORE,
) -> list[dict[str, Any]]:
    """Return up to `k` past actions most similar to `query` (deterministic recall).

    Similarity = token-set Jaccard overlap between `query` and each action's
    `action + rationale` text, plus a fixed bonus per shared tag. NOT a model call,
    NOT embeddings (an explicit later follow-up). Ties are broken by recency
    (higher `seq` first, i.e. the most recent matching action wins a tie) so the
    ranking is stable and reproducible. Empty store / no match / bad input all
    return `[]`; never raises.
    """
    try:
        k_int = int(k)
    except Exception:
        k_int = 5
    if k_int <= 0:
        return []

    query_tokens = _tokenize(query)
    filter_tags = {t for t in _safe_tags(tags)}

    try:
        records = load_actions(store=store)
    except Exception:
        return []

    if filter_tags:
        try:
            records = [
                r
                for r in records
                if isinstance(r, dict) and filter_tags & {_safe_str(t) for t in (r.get("tags") or [])}
            ]
        except Exception:
            return []

    if not records:
        return []

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for rec in records:
        try:
            seq = int(rec.get("seq", 0))
        except Exception:
            seq = 0
        try:
            score = _score(query_tokens, filter_tags, rec)
        except Exception:
            score = 0.0
        scored.append((score, seq, rec))

    # Rank by score desc, then by seq desc (recency) for a stable, deterministic tie-break.
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    results = [rec for score, _seq, rec in scored if score > 0.0]
    return results[:k_int]


def reset(store: Path | str = DEFAULT_STORE) -> None:
    """Delete/truncate `store` so a fresh, isolated state can start. Best-effort."""
    store_path = Path(store)
    try:
        if store_path.exists():
            store_path.unlink()
    except Exception:
        pass


# #EXT-036-REQ-24 End
