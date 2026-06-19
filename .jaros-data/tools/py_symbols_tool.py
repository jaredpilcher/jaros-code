"""Read-only execution-plane tool ``py.symbols`` (EXT-001 / REQ-9).

Lists the top-level functions and classes defined in a Python file (via ``ast``), so
a navigation agent can locate the right symbol before editing. Read-only -> replay-safe.
"""

from __future__ import annotations

import ast
import os

from jaros.core.decision_gate import ValidationResult

# #EXT-001-REQ-9 Start


class PySymbolsTool:
    NAME = "py.symbols"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        if not payload.get("path") and "code" not in payload:
            return ValidationResult.reject("py.symbols requires a 'path' or 'code'")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        path = payload.get("path")
        if path:
            if not os.path.isfile(path):
                return {"tool": self.NAME, "path": path, "error": "not a file"}
            src = open(path, "r", encoding="utf-8", errors="replace").read()
        else:
            src = payload.get("code", "")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            return {"tool": self.NAME, "path": path, "error": f"syntax error: {exc.msg}", "line": exc.lineno}
        symbols = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({"name": node.name, "kind": "function", "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                symbols.append({"name": node.name, "kind": "class", "line": node.lineno})
        return {"tool": self.NAME, "path": path, "symbols": symbols, "count": len(symbols)}
# #EXT-001-REQ-9 End
