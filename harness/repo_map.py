"""Repo map (EXT-004, inspired by Aider's tree-sitter repo map + a PageRank-style ranking).

Gives the small local model a compact, ranked overview of a codebase's PUBLIC SURFACE — the
top-level functions/classes per file — so it can understand cross-file structure without
reading every file (Claude Code's "understand the codebase first", done cheaply). Pure
deterministic extraction (stdlib `ast`, no tree-sitter dep): a TOOL, the model just consumes
the text. Files are ranked by how often their symbols are referenced elsewhere (a connectivity
proxy for importance), then truncated to a token-ish budget — Aider's key insight that you
surface the MOST-referenced identifiers, not everything.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_SKIP = {".git", "__pycache__", ".venv", "node_modules", ".jaros-data", "datasets"}


def _symbols(src: str) -> list[str]:
    """Top-level def/class names (the file's public surface)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def build_repo_map(root: str, *, max_files: int = 40, max_syms: int = 10) -> str:
    """Compact ranked map: 'relpath: symA, symB, ...' lines, most-referenced files first."""
    root_p = Path(root)
    files: dict[Path, list[str]] = {}
    srcs: dict[Path, str] = {}
    for p in root_p.rglob("*.py"):
        if any(part in _SKIP for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        syms = _symbols(src)
        if syms:
            files[p] = syms
            srcs[p] = src

    # rank: how often each file's symbols are referenced from OTHER files (connectivity)
    rank: dict[Path, int] = {}
    for p, syms in files.items():
        score = 0
        for sym in syms:
            pat = re.compile(rf"\b{re.escape(sym)}\b")
            for q, qsrc in srcs.items():
                if q != p:
                    score += len(pat.findall(qsrc))
        rank[p] = score

    ordered = sorted(files, key=lambda p: (rank[p], -len(str(p))), reverse=True)[:max_files]
    lines = []
    for p in ordered:
        try:
            rel = p.relative_to(root_p).as_posix()
        except ValueError:
            rel = p.name
        syms = files[p][:max_syms]
        more = "" if len(files[p]) <= max_syms else f", +{len(files[p]) - max_syms}"
        lines.append(f"{rel}: {', '.join(syms)}{more}")
    return "\n".join(lines)
