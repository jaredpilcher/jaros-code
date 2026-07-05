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


# #EXT-042-REQ-5 Start
def append_memory(cwd: str, note: str, runtime: "object | None" = None) -> str:
    """Append a dated note/convention to `.jcode/memory.md` (creating it with a header). Returns
    the file path on success, or "" for an empty note / a failed write.

    EXT-042 REQ-5 (Tenet 1): when `runtime` is given -- any object exposing `.apply(decision)`,
    e.g. a `harness.coding_loop.Runtime` -- the write is performed as a real `code.write_file`
    Decision applied through it (gate + EXT-037 root-jail + hash-chain log), instead of a raw
    `Path.write_text`. `runtime=None` (the default) preserves the prior direct-write behavior
    byte-for-byte, so every pre-existing caller/test of this function is unaffected."""
    note = note.strip()
    if not note:
        return ""
    p = _mem_path(cwd)
    body = read_memory(cwd) or _HEADER
    new_content = body.rstrip() + "\n" + f"- {date.today().isoformat()}: {note}\n"

    if runtime is not None:
        try:
            import uuid

            from jaros.core import create_decision
            decision = create_decision(
                id=f"remember-{uuid.uuid4().hex}", source="project_memory.append",
                type="code.write_file",
                payload={"path": str(p), "content": new_content, "root": str(Path(cwd).resolve())},
            )
            runtime.apply(decision)
        except Exception:
            return ""
        return str(p)

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new_content, encoding="utf-8")
    return str(p)
# #EXT-042-REQ-5 End
