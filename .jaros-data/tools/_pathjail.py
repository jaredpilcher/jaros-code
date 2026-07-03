"""Shared root-jail helper for filesystem writers (EXT-037 / REQ-1).

Every CREATE/WRITE/UPDATE effect (``write_file``, ``apply_patch``, ``search_replace``,
and any future writer) must be confined to the project root folder. This is the ONE
deterministic choke point every writer tool imports -- no divergent copy of the
containment logic (PRIME-001 Tenet 3). Reads are not jailed; only this module's
write/update callers apply it.

Resolution uses ``os.path.realpath``, which collapses BOTH ``..`` traversal AND
symlinks to their real on-disk target, so a symlink planted inside root that points
outside root is caught by the same containment check as a literal ``..`` escape --
no special-casing needed.

Underscore-prefixed so the Jaros custom-tool loader (``load_custom_tools``) skips it
as a tool module, mirroring ``_codesafety.py``.
"""

from __future__ import annotations

import os

# #EXT-037-REQ-1 Start


class PathEscapeError(Exception):
    """Raised when a target path resolves outside its jailed root."""


def _real(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def path_jail(root: str, target: str) -> str:
    """Resolve ``target`` against ``root`` and enforce containment.

    ``target`` may be an absolute path (as the writer tools already receive, e.g.
    ``str(Path(cwd) / fname)``) or a path relative to ``root``. Returns the resolved
    absolute real path when it is contained within ``root``; raises
    ``PathEscapeError`` otherwise (``..`` traversal, an outside absolute path, or a
    symlink that resolves outside root).
    """
    if not isinstance(root, str) or not root:
        raise PathEscapeError("path_jail requires a non-empty 'root' string")
    if not isinstance(target, str) or not target:
        raise PathEscapeError("path_jail requires a non-empty 'target' string")

    root_real = os.path.realpath(root)
    candidate = target if os.path.isabs(target) else os.path.join(root, target)
    resolved = os.path.realpath(candidate)

    root_norm = os.path.normcase(root_real)
    resolved_norm = os.path.normcase(resolved)
    try:
        contained = os.path.commonpath([root_norm, resolved_norm]) == root_norm
    except ValueError:
        # e.g. different drives on Windows -- definitely not contained.
        contained = False

    if not contained:
        raise PathEscapeError(
            f"target escapes root: {target!r} resolved to {resolved!r}, "
            f"which is outside root {root_real!r}"
        )
    return resolved


def path_escape_reason(root: str, target: str) -> str | None:
    """Return ``None`` if ``target`` is safely contained within ``root``, else a
    human-readable rejection reason. One-line convenience for a tool's ``validate()``,
    mirroring the ``unsafe_reason`` helper in ``_codesafety.py``."""
    try:
        path_jail(root, target)
        return None
    except PathEscapeError as exc:
        return str(exc)
# #EXT-037-REQ-1 End
