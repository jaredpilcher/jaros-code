"""Deterministic secret/ignored-path guard for git staging (EXT-037 / REQ-4).

Mirrors jaros-code's own commit discipline (CLAUDE.md: "Never commit `.env`,
secrets, logs, or runtime state") as a hard, pattern-based refusal that
``git.commit`` applies to every path it would actually stage, whether the caller
named files explicitly or asked to stage "everything". A pattern match is a
REJECT, never a silent skip -- the whole commit is refused so a caller finds out
immediately rather than discovering later that a secret slipped through.

Underscore-prefixed so the Jaros custom-tool loader (``load_custom_tools``) skips
it as a tool module, mirroring ``_pathjail.py`` / ``_envtools.py`` / ``_codesafety.py``.
"""

from __future__ import annotations

import re

# #EXT-037-REQ-4 Start
_SECRET_OR_IGNORED_PATTERNS = [
    # dotenv files (`.env`, `.env.local`, `.env.production`, ...)
    r"(^|[\\/])\.env(\.[^\\/]*)?$",
    # private key / certificate / keystore material
    r"\.pem$", r"\.key$", r"\.pfx$", r"\.p12$", r"\.jks$",
    r"(^|[\\/])id_rsa(\.pub)?$", r"(^|[\\/])id_dsa(\.pub)?$",
    r"(^|[\\/])id_ecdsa(\.pub)?$", r"(^|[\\/])id_ed25519(\.pub)?$",
    # common credential / secrets files
    r"credentials(\.json)?$", r"secrets?\.ya?ml$", r"secrets?\.json$",
    r"\.pypirc$", r"\.npmrc$", r"\.netrc$",
    r"(^|[\\/])\.aws[\\/]credentials$",
    # ignored/runtime paths (mirrors this repo's own .gitignore discipline)
    r"\.log$", r"(^|[\\/])__pycache__([\\/]|$)", r"\.pyc$",
    r"(^|[\\/])node_modules([\\/]|$)",
    r"(^|[\\/])\.jaros-data[\\/](state|artifacts|inbox|outbox|processed|failed|claimed)([\\/]|$)",
]
_SECRET_RE = re.compile("|".join(_SECRET_OR_IGNORED_PATTERNS), re.IGNORECASE)


def secret_or_ignored_reason(path: str) -> str | None:
    """Return ``None`` if ``path`` looks safe to stage/commit, else a human
    rejection reason naming the matched pattern. Path-shape only (no filesystem
    access) so it is cheap and deterministic to run over every candidate file a
    commit would touch."""
    if not isinstance(path, str) or not path:
        return None
    normalized = path.replace("\\", "/")
    match = _SECRET_RE.search(normalized)
    if match is None:
        return None
    return f"matches secret/ignored pattern {match.group(0)!r}"
# #EXT-037-REQ-4 End
