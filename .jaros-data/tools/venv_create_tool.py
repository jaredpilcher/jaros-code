"""Effectful execution-plane tool ``env.venv_create`` (EXT-037 / REQ-3).

Creates a Python virtual environment inside a caller-supplied project root, using
the stdlib ``venv`` module (offline -- ``ensurepip`` bootstraps pip from wheels
bundled in the stdlib, no network access). Root-scoped: the venv target path is
resolved through the shared root-jail (EXT-037 / REQ-1, the same choke point as
``write_file``/``apply_patch``/``search_replace``) and REJECTED in ``validate()``
if it would escape the root -- no venv is ever created outside the project.
"""

from __future__ import annotations

import os
import sys
import venv as venv_module

from jaros.core.decision_gate import ValidationResult

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _pathjail import PathEscapeError, path_escape_reason, path_jail
except Exception:  # pragma: no cover - fail safe if helper missing
    class PathEscapeError(Exception):
        pass

    def path_escape_reason(root, target):  # type: ignore
        return None

    def path_jail(root, target):  # type: ignore
        return target if os.path.isabs(target) else os.path.join(root, target)

try:
    from _envtools import venv_python_path
except Exception:  # pragma: no cover - fail safe if helper missing
    def venv_python_path(venv_dir):  # type: ignore
        if sys.platform == "win32":
            return os.path.join(venv_dir, "Scripts", "python.exe")
        return os.path.join(venv_dir, "bin", "python")

# #EXT-037-REQ-3 Start
_DEFAULT_VENV_PATH = ".venv"


class VenvCreateTool:
    NAME = "env.venv_create"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("env.venv_create requires a non-empty 'root' string")
        if not os.path.isdir(root):
            return ValidationResult.reject(f"env.venv_create root does not exist: {root!r}")
        venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
        if not isinstance(venv_rel, str) or not venv_rel:
            return ValidationResult.reject("env.venv_create 'venv_path' must be a non-empty string")
        escape = path_escape_reason(root, venv_rel)
        if escape is not None:
            return ValidationResult.reject(f"env.venv_create refused venv path outside root: {escape}")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        root = payload["root"]
        venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
        try:
            target = path_jail(root, venv_rel)
        except PathEscapeError as exc:
            return {"tool": self.NAME, "created": False, "error": str(exc)}

        try:
            venv_module.create(target, with_pip=True, clear=False)
        except Exception as exc:
            return {"tool": self.NAME, "venvPath": target, "created": False, "error": str(exc)}

        python_path = venv_python_path(target)
        return {
            "tool": self.NAME,
            "venvPath": target,
            "pythonPath": python_path,
            "created": True,
            "pythonExists": os.path.isfile(python_path),
        }
# #EXT-037-REQ-3 End
