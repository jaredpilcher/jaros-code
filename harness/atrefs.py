"""Deterministic ``@path`` / ``@dir/`` reference expansion (EXT-051 REQ-1).

Pure string-composition module: finds ``@<path>`` tokens in a plain-language request and, via
CALLER-SUPPLIED ``read_file``/``list_dir`` callables (so a caller can wire the EXISTING gated
read path -- ``fs.read``/``fs.list`` -- without this module doing any host I/O or gating itself),
inlines each referenced file's content (bounded, truncation noted) or a bounded directory listing
after the original text. Never a model decision anywhere in this module, never crashes on a
missing/unreadable path or a misbehaving callable -- degrades to an honest annotated block instead.

Two-plane discipline (Tenet 1): this module is pure execution-plane string composition. The
actual host read happens through whatever gated tool the caller's ``read_file``/``list_dir``
callables wrap (``harness.cli.JcodeCli._at_ref_read``/``_at_ref_list``, which route through the
SAME ``self._tool("fs.read"/"fs.list", ...)`` seam ``/read``/``/ls`` already use) -- never a raw
``open()``/``os.listdir()`` here.
"""

# #EXT-051-REQ-1 Start
from __future__ import annotations

import re

# Whitespace/start-of-string anchored so an "@" embedded mid-word (e.g. an email address) is
# never mistaken for a reference. Captures path-safe characters; a directory reference keeps its
# trailing "/" as the directory sentinel.
_AT_REF_RE = re.compile(r"(?<!\S)@([A-Za-z0-9_./\\-]+)")
_TRAILING_PUNCTUATION = ").,:;!?"

_MAX_CHARS = 4000          # bounds a single referenced file's inlined content
_MAX_DIR_ENTRIES = 40      # bounds a single referenced directory's inlined listing


def find_at_refs(text: "str | None") -> "list[str]":
    """Distinct ``@``-prefixed path tokens in ``text``, in first-seen order. Never raises --
    ``None``/empty input (or any internal failure) degrades to ``[]``."""
    if not text:
        return []
    try:
        seen: "list[str]" = []
        for m in _AT_REF_RE.finditer(text):
            token = m.group(1)
            # Strip trailing sentence punctuation ("check @foo.py." -> "foo.py") but never strip
            # a ref's own trailing "/" -- that is the directory sentinel, not punctuation.
            if not token.endswith("/") and not token.endswith("\\"):
                token = token.rstrip(_TRAILING_PUNCTUATION)
            if token and token not in seen:
                seen.append(token)
        return seen
    except Exception:
        return []


def _file_block(ref: str, content: "str | None", truncated: bool, max_chars: int,
                 error: "str | None" = None) -> str:
    if error is not None or content is None:
        return f"--- @{ref} (not found) ---"
    bounded = content[:max_chars]
    overflowed = truncated or len(content) > max_chars
    note = " [truncated]" if overflowed else ""
    return f"--- @{ref}{note} ---\n{bounded}"


def _dir_block(ref: str, entries: "list[str] | None", truncated: bool, max_dir_entries: int,
                error: "str | None" = None) -> str:
    if error is not None or entries is None:
        return f"--- @{ref} (not found) ---"
    bounded = list(entries)[:max_dir_entries]
    overflowed = truncated or len(entries) > max_dir_entries
    note = " [truncated]" if overflowed else ""
    listing = "\n".join(bounded) if bounded else "(empty directory)"
    return f"--- @{ref}{note} ---\n{listing}"


def expand_at_refs(text: "str | None", read_file, list_dir,
                    max_chars: int = _MAX_CHARS, max_dir_entries: int = _MAX_DIR_ENTRIES) -> str:
    """Deterministically inline every ``@path``/``@dir/`` reference in ``text`` as a labeled block
    appended AFTER the original text -- the ``@token`` itself is left in place, unrewritten, so
    the request still reads naturally. ``text`` with no references at all (or on any internal
    failure) is returned byte-identical -- a complete no-op. Never raises, regardless of what
    ``read_file``/``list_dir`` do (a raised exception or a ``None`` result both degrade to an
    honest ``(not found)``-style annotation)."""
    try:
        refs = find_at_refs(text)
    except Exception:
        return text if isinstance(text, str) else ""
    if not text or not refs:
        return text if isinstance(text, str) else ""

    blocks: "list[str]" = []
    for ref in refs:
        try:
            if ref.endswith("/") or ref.endswith("\\"):
                try:
                    entries, truncated = list_dir(ref)
                    error = None
                except Exception as exc:
                    entries, truncated, error = None, False, str(exc)
                blocks.append(_dir_block(ref, entries, truncated, max_dir_entries, error=error))
            else:
                try:
                    content, truncated = read_file(ref)
                    error = None
                except Exception as exc:
                    content, truncated, error = None, False, str(exc)
                blocks.append(_file_block(ref, content, truncated, max_chars, error=error))
        except Exception:
            blocks.append(f"--- @{ref} (not found) ---")

    if not blocks:
        return text
    return text + "\n\n" + "\n\n".join(blocks)
# #EXT-051-REQ-1 End
