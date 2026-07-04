"""EXT-042: ``JCODE.md`` — the project-instruction memory hierarchy (Claude Code's ``CLAUDE.md``
equivalent for jaros-code). Closes `docs/GAP-MAP.md` Product-surface parity row #14.

Two auto-loaded tiers, mirroring Claude Code's project + user memory levels:
  * PROJECT  -- ``<repo>/JCODE.md``
  * USER     -- ``~/.jcode/JCODE.md``

Both are pure deterministic file I/O (Tenet 1 -- the *loading* is execution-plane, not a model
judgement): bounded to a small character budget for the small model's context, and NEVER raise --
an absent or unreadable file degrades to ``""``, exactly like ``harness/project_md.py``'s
``load_project_md`` precedent (EXT-036 REQ-17). This module is strictly ADDITIVE alongside that
existing JAROS.md wiring and ``harness/project_memory.py``'s ``.jcode/memory.md`` -- neither is
modified or replaced here.

``init_jcode_md`` is the ``/init`` generator: it writes a starter ``JCODE.md`` from deterministic
repo comprehension (``harness/repo_map.py``), through a root-jailed path (the EXT-037
``_pathjail.path_jail`` pattern), and never overwrites an existing file.
"""

# #EXT-042-REQ-1 Start
from __future__ import annotations

import os
import sys
from pathlib import Path

MAX_CHARS = 2000

_PROJECT_LABEL = "PROJECT INSTRUCTIONS (JCODE.md)"
_USER_LABEL = "USER INSTRUCTIONS (JCODE.md)"


def _bounded_read(path: Path) -> str:
    """Read `path` as UTF-8 text bounded to `MAX_CHARS`, or "" on any failure/absence."""
    try:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[:MAX_CHARS] + ("..." if len(text) > MAX_CHARS else "")


def load_project_jcode_md(root: "str | Path" = ".") -> str:
    """Discover + load the PROJECT-level ``JCODE.md`` at `root`'s repo root, bounded to
    `MAX_CHARS`. Returns "" when absent or unreadable -- never raises."""
    try:
        return _bounded_read(Path(root) / "JCODE.md")
    except Exception:
        return ""


def load_user_jcode_md() -> str:
    """Discover + load the USER-level ``~/.jcode/JCODE.md``, bounded to `MAX_CHARS`. Returns ""
    when absent or unreadable -- never raises (e.g. no resolvable home directory)."""
    try:
        home = Path.home()
    except Exception:
        return ""
    try:
        return _bounded_read(home / ".jcode" / "JCODE.md")
    except Exception:
        return ""


def load_jcode_md(root: "str | Path" = ".") -> str:
    """Combine the PROJECT + USER tiers into ONE clearly-labeled block for injection into the
    orchestrator/planner context (REQ-2). Returns "" when neither tier has content -- a graceful
    no-op that leaves downstream callers byte-identical to today. Never raises."""
    project = load_project_jcode_md(root)
    user = load_user_jcode_md()
    parts = []
    if project:
        parts.append(f"{_PROJECT_LABEL}:\n{project}")
    if user:
        parts.append(f"{_USER_LABEL}:\n{user}")
    return "\n\n".join(parts)
# #EXT-042-REQ-1 End


# #EXT-042-REQ-3 Start
_TOOLS_DIR = str(Path(__file__).resolve().parents[1] / ".jaros-data" / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
try:
    from _pathjail import PathEscapeError, path_jail  # root-jail helper (EXT-037 / REQ-1)
except Exception:  # pragma: no cover - fail safe if the helper is missing
    class PathEscapeError(Exception):  # type: ignore
        pass

    def path_jail(root, target):  # type: ignore
        return os.path.join(root, target) if not os.path.isabs(target) else target


_STARTER_TEMPLATE = """# JCODE.md

Project instructions for jaros-code / jcode -- auto-loaded into the orchestrator's context on
every session (see `docs/GAP-MAP.md` Product-surface parity row #14, the Claude Code CLAUDE.md
equivalent). Edit this file with conventions, architecture notes, and how-to-run steps you want
followed every time.

## Overview

(describe the project's purpose here)

## Structure

{structure}

## How to run

(describe the primary entrypoint / test command here)
"""

_NO_STRUCTURE = "(no Python modules detected -- run `/init` again after adding source files)"


def _starter_content(root: "str | Path") -> str:
    """Build the starter Markdown body, never raising -- a repo-map failure degrades to the
    generic placeholder rather than blocking the write."""
    try:
        from harness.repo_map import build_repo_map
        structure = build_repo_map(str(root)) or _NO_STRUCTURE
    except Exception:
        structure = _NO_STRUCTURE
    return _STARTER_TEMPLATE.format(structure=structure)


def init_jcode_md(root: "str | Path" = ".") -> str:
    """`/init` generator (REQ-3): write a starter ``JCODE.md`` at `root` from deterministic repo
    comprehension. Never overwrites an existing file (write-only-if-absent) and never raises --
    any failure degrades to a human-readable message, never an exception."""
    root_str = str(root)
    try:
        target = Path(root_str) / "JCODE.md"
        if target.is_file():
            return f"{target} already exists -- not overwritten (run `/memory` to view it)"
    except OSError as exc:
        return f"could not inspect {root_str}/JCODE.md: {exc}"

    content = _starter_content(root_str)

    try:
        resolved = path_jail(root_str, "JCODE.md")
    except PathEscapeError as exc:
        return str(exc)
    try:
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        Path(resolved).write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        return f"failed to write {resolved}: {exc}"
    return f"wrote {resolved}"
# #EXT-042-REQ-3 End
