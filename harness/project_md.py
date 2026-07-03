"""EXT-036 REQ-17: per-repo JAROS.md project instructions, auto-injected every prompt.

Analog of Claude Code's CLAUDE.md: a per-repo ``JAROS.md`` (project instructions/conventions)
discovered at the repo root (falling back to ``.jaros/JAROS.md``), BOUNDED to fit the small
model's context, and folded as a ``PROJECT INSTRUCTIONS:`` preamble into every plain-language
turn (see ``harness/cli.py``). Pure deterministic file I/O — never raises; an absent/unreadable
file is a graceful no-op ("").
"""

# #EXT-036-REQ-17 Start
from __future__ import annotations

from pathlib import Path

MAX_CHARS = 2000


def load_project_md(root: "str | Path" = ".") -> str:
    """Discover + load ``JAROS.md`` for `root` (repo root, falling back to
    ``.jaros/JAROS.md``), bounded to `MAX_CHARS` characters (small-model context). Returns
    "" when neither file exists or is unreadable — never raises (two-plane discipline: this
    is deterministic state, the model only ever receives the text)."""
    root = Path(root)
    for candidate in (root / "JAROS.md", root / ".jaros" / "JAROS.md"):
        try:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8")
                return text[:MAX_CHARS] + ("..." if len(text) > MAX_CHARS else "")
        except OSError:
            continue
    return ""
# #EXT-036-REQ-17 End
