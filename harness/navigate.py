"""Code navigation (EXT-004): AST-based find-usages. Unlike grep, this resolves the symbol in
the SYNTAX — a reference (Name load / Attribute access) or a definition — so it ignores matches
inside strings and comments. Deterministic (a tool), Python via stdlib `ast`. Useful on its own
(Claude Code's "find references") and as the precise basis for a future AST-scoped rename.
"""
from __future__ import annotations

import ast
from pathlib import Path

_SKIP = {".git", "__pycache__", ".venv", "node_modules", ".jaros-data", "datasets"}


def find_usages(cwd: str, symbol: str) -> list[dict]:
    """Every place `symbol` is referenced or defined across the repo's .py files, as
    {file, line, kind, text}. kind ∈ {def, class, ref, attr}."""
    root = Path(cwd)
    out: list[dict] = []
    for p in root.rglob("*.py"):
        if any(part in _SKIP for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        lines = src.splitlines()
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.name
        for node in ast.walk(tree):
            kind = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                kind = "def"
            elif isinstance(node, ast.ClassDef) and node.name == symbol:
                kind = "class"
            elif isinstance(node, ast.Name) and node.id == symbol:
                kind = "ref"
            elif isinstance(node, ast.Attribute) and node.attr == symbol:
                kind = "attr"
            if kind and hasattr(node, "lineno"):
                ln = node.lineno
                out.append({"file": rel, "line": ln, "kind": kind,
                            "text": lines[ln - 1].strip() if 0 < ln <= len(lines) else ""})
    out.sort(key=lambda u: (u["file"], u["line"]))
    return out
