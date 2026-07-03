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
