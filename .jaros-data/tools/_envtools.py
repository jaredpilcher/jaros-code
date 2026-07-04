"""Shared environment-tooling helpers (EXT-037 / REQ-3).

Underscore-prefixed so the Jaros custom-tool loader (``load_custom_tools``) skips it
as a tool module, mirroring ``_pathjail.py`` / ``_codesafety.py``.
"""

from __future__ import annotations

import os
import sys

# #EXT-037-REQ-3 Start


def venv_python_path(venv_dir: str) -> str:
    """Return the expected path to ``venv_dir``'s own python executable.

    Cross-platform layout of a stdlib ``venv``: ``Scripts/python.exe`` on Windows,
    ``bin/python`` on POSIX. Does not require the path to already exist -- callers
    check that separately (e.g. to detect a not-yet-created venv).
    """
    if sys.platform == "win32":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


# Pip flags that broaden an install beyond the target venv -- a system-wide or
# user-site install is exactly what REQ-3's safety gate must refuse by default.
_GLOBAL_INSTALL_FLAGS = {
    "--user", "--target", "--prefix", "--system", "--global",
    "--root", "--break-system-packages",
}


def global_install_flag(args) -> str | None:
    """Return the first disallowed global/system-scope pip flag found in ``args``,
    or ``None`` if none are present. Matches the bare flag or its ``--flag=value``
    form, case-insensitively -- the deterministic gate that keeps every install
    confined to the caller's own project venv (EXT-037 / REQ-3)."""
    if not args:
        return None
    for arg in args:
        if not isinstance(arg, str):
            continue
        key = arg.split("=", 1)[0].strip().lower()
        if key in _GLOBAL_INSTALL_FLAGS:
            return arg
    return None
# #EXT-037-REQ-3 End
