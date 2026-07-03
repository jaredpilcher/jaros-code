"""Test-gated refactoring (EXT-003): rename a symbol across a repo, behavior-preserving.

A NEW capability class — the harness could fix/implement but not REFACTOR. Refactoring is a
perfect two-plane fit: the edit is DETERMINISTIC (rename every occurrence of the symbol across
.py files — no model needed) and correctness is the GATE (the suite, green before, must stay
green after). If the rename turns the suite red, it touched something it shouldn't have, so we
REVERT — the rename can never silently break behavior.

The rename is SCOPED to Python identifier tokens (EXT-003 REQ-6): a `tokenize`-based pass finds
only `tokenize.NAME` tokens equal to `old` and rewrites them in place by POSITION, leaving every
STRING/FSTRING/COMMENT untouched and the rest of each file byte-identical — so a same-named
comment, docstring, or string-literal value is never rewritten (a diff Claude Code would never
produce). The test-gate still guarantees behavior preservation independently of scoping.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

from harness.multi_file import _run, _snapshot, _restore  # reuse run/snapshot/restore


# #EXT-003-REQ-6 Start
def _rename_identifier_tokens(src: str, old: str, new: str) -> tuple[str, int]:
    """Tokenize `src` and rename every NAME token equal to `old` to `new`, editing the source
    by TOKEN POSITION (never `tokenize.untokenize`, which reformats) so STRING/FSTRING/COMMENT
    tokens and all surrounding formatting stay byte-identical. Returns (new_src, count). Raises
    tokenize.TokenError/IndentationError/SyntaxError on unparseable source (caller skips it)."""
    lines = src.splitlines(keepends=True)
    spans_by_line: dict[int, list[tuple[int, int]]] = {}
    count = 0
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NAME and tok.string == old:
            (srow, scol), (erow, ecol) = tok.start, tok.end
            if srow != erow:
                continue  # NAME tokens are single-line; defensive skip of the impossible
            spans_by_line.setdefault(srow, []).append((scol, ecol))
            count += 1
    if count == 0:
        return src, 0
    for lineno, spans in spans_by_line.items():
        line = lines[lineno - 1]
        for scol, ecol in sorted(spans, reverse=True):   # reverse order: earlier spans stay valid
            line = line[:scol] + new + line[ecol:]
        lines[lineno - 1] = line
    return "".join(lines), count
# #EXT-003-REQ-6 End


def rename_symbol(cwd: str, old: str, new: str,
                  test_cmd: str = "python -m pytest -q") -> dict:
    """Rename identifier `old` -> `new` across the repo's .py files (NAME tokens only — not
    inside strings/comments/docstrings), gated by the suite staying green. Pre-req: a refactor
    preserves PASSING tests, so the suite must be green first."""
    if not (old.isidentifier() and new.isidentifier()):
        return {"renamed": False, "occurrences": 0, "note": "old/new must be identifiers"}
    ok0, _ = _run(cwd, test_cmd)
    if not ok0:
        return {"renamed": False, "occurrences": 0, "note": "suite not green before rename"}

    snap = _snapshot(cwd)
    # #EXT-003-REQ-6 Start
    occ, files = 0, 0
    for p in Path(cwd).rglob("*.py"):
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            new_src, n = _rename_identifier_tokens(src, old, new)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            continue   # unparseable file — skip safely, leave unchanged, never crash the rename
        if n:
            p.write_text(new_src, encoding="utf-8", newline="\n")
            occ += n
            files += 1
    # #EXT-003-REQ-6 End

    ok1, _ = _run(cwd, test_cmd)
    if ok1:
        return {"renamed": True, "occurrences": occ, "files": files,
                "note": f"renamed {old}->{new} ({occ} occurrences in {files} files), suite green"}
    _restore(snap)   # the rename broke something it shouldn't have — never ship a red suite
    return {"renamed": False, "occurrences": occ, "files": files,
            "note": f"rename {old}->{new} turned the suite red; reverted"}


def move_symbol(cwd: str, symbol: str, from_file: str, to_file: str,
                test_cmd: str = "python -m pytest -q") -> dict:
    """Move a top-level function/class from one module to another, test-gated. The source
    module RE-EXPORTS it (`from <to> import <symbol>`) so existing importers keep working;
    if the move turns the suite red (e.g. the symbol needed imports left behind), REVERT.
    Deterministic: ast finds the symbol's exact line span (decorators included)."""
    root = Path(cwd)
    src_p, dst_p = root / from_file, root / to_file
    if not src_p.is_file():
        return {"moved": False, "note": f"{from_file} not found"}
    ok0, _ = _run(cwd, test_cmd)
    if not ok0:
        return {"moved": False, "note": "suite not green before move"}
    src = src_p.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"moved": False, "note": f"{from_file} not parseable"}
    node = next((n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and n.name == symbol), None)
    if node is None:
        return {"moved": False, "note": f"{symbol} is not a top-level def/class in {from_file}"}

    start = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1   # 0-based, incl decorators
    end = node.end_lineno                                                      # 1-based inclusive
    lines = src.splitlines(keepends=True)
    block = "".join(lines[start:end]).rstrip() + "\n"

    snap = _snapshot(cwd)
    to_mod = Path(to_file).stem
    remaining = f"from {to_mod} import {symbol}\n" + "".join(lines[:start] + lines[end:])
    src_p.write_text(remaining, encoding="utf-8", newline="\n")
    dst_src = dst_p.read_text(encoding="utf-8") if dst_p.is_file() else ""
    sep = "\n\n\n" if dst_src.strip() else ""
    dst_p.write_text(dst_src.rstrip() + sep + block, encoding="utf-8", newline="\n")

    ok1, _ = _run(cwd, test_cmd)
    if ok1:
        return {"moved": True, "note": f"moved {symbol} {from_file}->{to_file} (re-exported), suite green"}
    _restore(snap)
    return {"moved": False, "note": f"moving {symbol} turned the suite red; reverted"}
