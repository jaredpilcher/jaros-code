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
    """An ordered transcript of conversation turns + a session id.

    # #EXT-044-REQ-1 Start
    EXT-044 adds an optional display `name` (so `-r`/`--fork` can address a session by NAME, not
    just its id) and `created`/`last_active` timestamps (so `-c`/`--continue` can find "the
    most-recently-active session" without scanning file mtimes). All three default sanely, so a
    pre-EXT-044 persisted session (no name/timestamps in its JSON) still loads cleanly.
    # #EXT-044-REQ-1 End
    """

    def __init__(self, id: str | None = None, turns: list[dict] | None = None,
                 # #EXT-044-REQ-1 Start
                 name: "str | None" = None, created: "float | None" = None,
                 last_active: "float | None" = None,
                 # #EXT-044-REQ-1 End
                 ) -> None:
        self.id = id or uuid.uuid4().hex[:12]
        self.turns: list[dict] = list(turns) if turns else []
        # #EXT-044-REQ-1 Start
        self.name: "str | None" = name
        _now = time.time()
        self.created: float = created if created is not None else _now
        self.last_active: float = last_active if last_active is not None else _now
        # #EXT-044-REQ-1 End

    def append(self, role: str, text: str) -> None:
        self.turns.append({"role": role, "text": text, "ts": time.time()})
        self.last_active = time.time()  # #EXT-044-REQ-1

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
        return {
            "id": self.id, "turns": self.turns,
            # #EXT-044-REQ-1 Start
            "name": self.name, "created": self.created, "last_active": self.last_active,
            # #EXT-044-REQ-1 End
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data.get("id"), turns=list(data.get("turns") or []),
            # #EXT-044-REQ-1 Start
            name=data.get("name"), created=data.get("created"), last_active=data.get("last_active"),
            # #EXT-044-REQ-1 End
        )


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def save_session(session: Session) -> None:
    """Best-effort persist — a write failure must NEVER crash the REPL."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _path(session.id).write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass
    # #EXT-044-REQ-1 Start
    try:
        idx = _load_index()
        idx[session.id] = {"name": session.name, "created": session.created,
                            "last_active": session.last_active}
        _save_index(idx)
    except Exception:
        pass
    # #EXT-044-REQ-1 End


def load_session(session_id: str) -> "Session | None":
    """Load a persisted session by id, or None if missing/corrupt."""
    try:
        data = json.loads(_path(session_id).read_text(encoding="utf-8"))
        return Session.from_dict(data)
    except Exception:
        return None


def list_sessions(limit: int = 10) -> list[dict]:
    """Recent persisted sessions (id, turn count), newest-modified first.

    # #EXT-044-REQ-1 Start
    Also surfaces `name`/`last_active` per row (EXT-044), and skips `index.json` itself (it
    lives alongside the per-session transcript files but is not a session).
    # #EXT-044-REQ-1 End
    """
    try:
        files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    out: list[dict] = []
    for p in files:
        if p.name == INDEX_FILENAME:  # #EXT-044-REQ-1 -- not a session file, skip it
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "id": data.get("id", p.stem), "turns": len(data.get("turns") or []),
                # #EXT-044-REQ-1 Start
                "name": data.get("name"), "last_active": data.get("last_active"),
                # #EXT-044-REQ-1 End
            })
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out
# #EXT-036-REQ-12 End


# #EXT-044-REQ-1 Start
# EXT-044: durable session identity (name + timestamps) and a small index
# (.jaros-data/sessions/index.json) so a session can be looked up by NAME as well as by id, and
# so "the most-recently-active session" (`-c`/`--continue`) is a cheap lookup rather than a
# directory scan. Pure deterministic state (Tenet 1) — never raises; a missing/corrupt index
# degrades to an honest empty result rather than crashing the CLI.

INDEX_FILENAME = "index.json"


def _index_path() -> Path:
    return SESSIONS_DIR / INDEX_FILENAME


def _load_index() -> dict:
    """The persisted {id: {name, created, last_active}} index. Never raises — a missing or
    corrupt index degrades to an empty dict (every id/name lookup then honestly misses, rather
    than crashing)."""
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_index(idx: dict) -> None:
    """Best-effort persist — an index write failure must never crash the caller."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _index_path().write_text(json.dumps(idx, indent=2), encoding="utf-8")
    except Exception:
        pass


def resolve_session_ref(ref: "str | None") -> "str | None":
    """Resolve a CLI-supplied session reference to a canonical session id: try `ref` as an exact
    id first (a session file exists under that name), then fall back to a NAME lookup in the
    index (the most-recently-active match wins when more than one session shares a name).
    Returns `None` — an honest "not found" — when neither resolves. Never raises."""
    if not ref:
        return None
    try:
        if _path(ref).is_file():
            return ref
    except Exception:
        pass
    try:
        idx = _load_index()
        matches = [sid for sid, meta in idx.items()
                   if isinstance(meta, dict) and meta.get("name") == ref]
        if matches:
            return max(matches, key=lambda sid: idx.get(sid, {}).get("last_active", 0) or 0)
    except Exception:
        pass
    return None


def most_recent_session_id() -> "str | None":
    """The id of the most-recently-active persisted session (for `-c`/`--continue`), or `None`
    when no session has ever been saved. Prefers the index's `last_active`; falls back to file
    mtime (via `list_sessions`, the pre-EXT-044 heuristic) so a sessions dir saved before this
    spec still resolves. Never raises."""
    try:
        idx = _load_index()
        if idx:
            return max(idx, key=lambda sid: idx.get(sid, {}).get("last_active", 0) or 0)
    except Exception:
        pass
    try:
        rows = list_sessions(limit=1)
        return rows[0]["id"] if rows else None
    except Exception:
        return None


def set_session_name(session: "Session", name: str) -> None:
    """Assign a display name to a session and persist it immediately (used by `/name` and the
    one-shot `--name` flag). Best-effort — never raises."""
    try:
        session.name = name
        save_session(session)
    except Exception:
        pass


def fork_session(ref: str) -> "Session | None":
    """Branch the session referenced by `ref` (an id or a name) into a brand-new session with
    its own id and a COPY of the source transcript — the source session file is only ever read
    (`load_session`), never opened for writing, so it is left completely unchanged. Returns the
    new (already-persisted) `Session`, or `None` when `ref` doesn't resolve to any known session.
    Never raises."""
    try:
        sid = resolve_session_ref(ref)
        if sid is None:
            return None
        src = load_session(sid)
        if src is None:
            return None
        forked_name = f"{src.name}-fork" if src.name else None
        forked = Session(turns=[dict(t) for t in src.turns], name=forked_name)
        save_session(forked)
        return forked
    except Exception:
        return None
# #EXT-044-REQ-1 End


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
