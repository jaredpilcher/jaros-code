"""Effectful execution-plane tool ``env.venv_pin`` (EXT-037 / REQ-3).

Records/pins dependencies into a root-jailed requirements file. Default mode runs
the venv's own ``pip freeze`` -- fully offline: it only lists ALREADY-installed
packages from the local venv, no network/PyPI access -- and writes the result;
callers may instead supply an explicit ``packages`` list to skip the freeze
entirely (e.g. when pinning versions decided elsewhere). The output path is
resolved through the shared root-jail (EXT-037 / REQ-1) and rejected if it would
escape the project root, matching ``write_file``/``apply_patch``/``search_replace``.
"""

from __future__ import annotations

import os
import subprocess
import sys

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
_DEFAULT_REQUIREMENTS_PATH = "requirements.txt"
_FREEZE_TIMEOUT_S = 60


class VenvPinTool:
    NAME = "env.venv_pin"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("env.venv_pin requires a non-empty 'root' string")
        requirements_rel = payload.get("requirements_path", _DEFAULT_REQUIREMENTS_PATH)
        if not isinstance(requirements_rel, str) or not requirements_rel:
            return ValidationResult.reject("env.venv_pin 'requirements_path' must be a non-empty string")
        escape = path_escape_reason(root, requirements_rel)
        if escape is not None:
            return ValidationResult.reject(f"env.venv_pin refused requirements path outside root: {escape}")

        packages = payload.get("packages")
        if packages is not None:
            if not isinstance(packages, list) or not all(isinstance(p, str) and p for p in packages):
                return ValidationResult.reject("env.venv_pin 'packages' must be a list of non-empty strings")
            return ValidationResult.accept(decision)

        # Freeze mode (default): the venv must already exist -- no fallback to an
        # ambient/system pip.
        venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
        if not isinstance(venv_rel, str) or not venv_rel:
            return ValidationResult.reject("env.venv_pin 'venv_path' must be a non-empty string")
        venv_escape = path_escape_reason(root, venv_rel)
        if venv_escape is not None:
            return ValidationResult.reject(f"env.venv_pin refused venv path outside root: {venv_escape}")
        try:
            target = path_jail(root, venv_rel)
        except PathEscapeError as exc:
            return ValidationResult.reject(str(exc))
        python_path = venv_python_path(target)
        if not os.path.isfile(python_path):
            return ValidationResult.reject(
                f"env.venv_pin refused: venv python not found at {python_path!r} "
                "(create the venv first with env.venv_create, or supply an explicit 'packages' list)")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        root = payload["root"]
        requirements_rel = payload.get("requirements_path", _DEFAULT_REQUIREMENTS_PATH)
        packages = payload.get("packages")

        try:
            req_target = path_jail(root, requirements_rel)
        except PathEscapeError as exc:
            return {"tool": self.NAME, "written": False, "error": str(exc)}

        if packages is not None:
            content = ("\n".join(packages) + "\n") if packages else ""
            source = "explicit"
        else:
            venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
            try:
                venv_target = path_jail(root, venv_rel)
            except PathEscapeError as exc:
                return {"tool": self.NAME, "written": False, "error": str(exc)}
            python_path = venv_python_path(venv_target)
            try:
                proc = subprocess.run([python_path, "-m", "pip", "freeze"],
                                       capture_output=True, text=True, timeout=_FREEZE_TIMEOUT_S)
                content = proc.stdout or ""
            except Exception as exc:
                return {"tool": self.NAME, "written": False, "error": str(exc)}
            source = "freeze"

        try:
            parent = os.path.dirname(req_target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(req_target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
        except Exception as exc:
            return {"tool": self.NAME, "written": False, "error": str(exc)}

        return {
            "tool": self.NAME,
            "requirementsPath": req_target,
            "source": source,
            "written": True,
            "bytesWritten": len(content.encode("utf-8")),
        }
# #EXT-037-REQ-3 End
