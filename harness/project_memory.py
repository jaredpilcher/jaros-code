"""Long-term project memory (EXT-009 / REQ-3): a `.jcode/memory.md` the harness owns — conventions
and learnings that persist across runs, the small-model analogue of Claude Code's `CLAUDE.md`.

This module is the DETERMINISTIC read/write only. Anchoring the agent flow on this memory (feeding
it to the planner/fix model) is a separate, eval-gated step — kept apart because feeding extra
context to a 2B can distract it (the few-shot lesson), so it must be measured before it ships.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

_HEADER = "# jcode project memory\n\n"


def _mem_path(cwd: str) -> Path:
    return Path(cwd) / ".jcode" / "memory.md"


def read_memory(cwd: str) -> str:
    """The project memory text, or "" if none (graceful)."""
    p = _mem_path(cwd)
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    except OSError:
        return ""


def append_memory(cwd: str, note: str) -> str:
    """Append a dated note/convention to `.jcode/memory.md` (creating it with a header). Returns
    the file path. Deterministic file I/O — the only writer of project memory."""
    note = note.strip()
    if not note:
        return ""
    p = _mem_path(cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = read_memory(cwd) or _HEADER
    p.write_text(body.rstrip() + "\n" + f"- {date.today().isoformat()}: {note}\n", encoding="utf-8")
    return str(p)
