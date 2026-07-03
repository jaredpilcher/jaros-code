"""EXT-036 REQ-12: a lightweight, deterministic conversational session.

An ordered transcript of ``{role, text, ts}`` turns plus a session id, persisted to
``.jaros-data/sessions/<id>.json`` so a jcode REPL conversation can be resumed later
(``/resume <id>``). Pure deterministic state (two-plane discipline) — the model never
judges anything here; the CLI just hands it a BOUNDED slice of the transcript when it
routes a plain-language request, so follow-ups can resolve against prior turns.
"""

# #EXT-036-REQ-12 Start
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = ROOT / ".jaros-data" / "sessions"


class Session:
    """An ordered transcript of conversation turns + a session id."""

    def __init__(self, id: str | None = None, turns: list[dict] | None = None) -> None:
        self.id = id or uuid.uuid4().hex[:12]
        self.turns: list[dict] = list(turns) if turns else []

    def append(self, role: str, text: str) -> None:
        self.turns.append({"role": role, "text": text, "ts": time.time()})

    def recent(self, cap: int = 6, max_chars: int = 300) -> list[dict]:
        """Bounded recent transcript for conversation-aware routing: the last `cap`
        turns, each truncated to `max_chars` — small model, small context (REQ-12)."""
        out = []
        for t in self.turns[-cap:]:
            text = t.get("text", "")
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            out.append({"role": t.get("role", "user"), "text": text})
        return out

    def to_dict(self) -> dict:
        return {"id": self.id, "turns": self.turns}

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(id=data.get("id"), turns=list(data.get("turns") or []))


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def save_session(session: Session) -> None:
    """Best-effort persist — a write failure must NEVER crash the REPL."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _path(session.id).write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass


def load_session(session_id: str) -> "Session | None":
    """Load a persisted session by id, or None if missing/corrupt."""
    try:
        data = json.loads(_path(session_id).read_text(encoding="utf-8"))
        return Session.from_dict(data)
    except Exception:
        return None


def list_sessions(limit: int = 10) -> list[dict]:
    """Recent persisted sessions (id, turn count), newest-modified first."""
    try:
        files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    out: list[dict] = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": data.get("id", p.stem), "turns": len(data.get("turns") or [])})
        except Exception:
            continue
    return out
# #EXT-036-REQ-12 End


# #EXT-036-REQ-15 Start
# Short-term memory condensation (REQ-15): the small model has a finite context window, so a
# transcript that keeps growing must eventually be CONDENSED — the oldest turns folded into a
# single running summary — instead of either dropping them silently or blowing the budget.
# Deterministic budget check; the ONLY model step is producing the summary text itself.

MAX_TURNS = 40            # total transcript length that triggers condensation
CONDENSE_KEEP = 6         # most-recent turns kept verbatim after condensing (matches recent()'s default cap)
MAX_SUMMARY_CHARS = 800   # bound the (model or fallback) summary text — small-model context


def _fallback_truncate(turns: list[dict], max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Deterministic fallback when the model summary call fails or is unusable: a bounded,
    truncated concatenation of the oldest turns so SOME signal from them survives (lossy, but
    never raises and never silently drops the older context entirely)."""
    joined = " | ".join(f"{t.get('role', 'user')}: {t.get('text', '')}" for t in turns)
    return joined[:max_chars]


def _summarize_turns(turns: list[dict], llm=None) -> str:
    """ONE narrow model call: summarize the given (oldest) turns into a short, factual
    paragraph that preserves task-relevant facts a later turn might need. Guarded — any
    failure (no reachable model, empty/unparseable output) falls back to a deterministic
    truncation; this function NEVER raises."""
    if not turns:
        return ""
    try:
        if llm is None:
            from harness.coding_loop import build_llm
            llm = build_llm()
        from jaros.llm import LlmRequest
        transcript = "\n".join(f"{t.get('role', 'user')}: {t.get('text', '')}" for t in turns)
        prompt = (
            "Summarize the following OLDER conversation turns into a short, factual paragraph "
            "that preserves task-relevant facts (names, decisions, files, values) a later turn "
            "might still need. Do not invent anything not stated. Be concise.\n\n"
            f"{transcript}\n\nSummary:"
        )
        text = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 200})).text
        text = (text or "").strip()
        if not text:
            raise ValueError("empty summary")
        return text[:MAX_SUMMARY_CHARS]
    except Exception:
        return _fallback_truncate(turns)


def condense(session: "Session", llm=None, keep: int = CONDENSE_KEEP, max_chars: int = 300) -> list[dict]:
    """The bounded slice to inject into plain-language routing (REQ-15).

    Deterministic budget check: when ``session.turns`` is within ``MAX_TURNS``, this is
    BYTE-IDENTICAL to ``session.recent(cap=keep, max_chars=max_chars)`` — no behavior change
    for short/under-budget sessions. Once the transcript exceeds the budget, the OLDEST turns
    (everything before the most-recent `keep`) are folded via ONE narrow model call into a
    single ``{"role": "summary", "text": ...}`` entry, and the returned slice becomes
    ``[summary] + recent turns`` — staying within budget while keeping the thread. The summary
    is an honestly-lossy best-effort recall (never a claim of full transcript recall); on any
    model failure it falls back to a deterministic truncation of the oldest turns rather than
    raising."""
    if len(session.turns) <= MAX_TURNS:
        return session.recent(cap=keep, max_chars=max_chars)

    recent_turns = session.recent(cap=keep, max_chars=max_chars)
    oldest = session.turns[: len(session.turns) - keep]
    summary_text = _summarize_turns(oldest, llm)
    return [{"role": "summary", "text": summary_text}] + recent_turns
# #EXT-036-REQ-15 End
