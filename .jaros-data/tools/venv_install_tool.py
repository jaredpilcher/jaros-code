"""Effectful execution-plane tool ``env.venv_install`` (EXT-037 / REQ-3).

Installs a dependency into an existing project-root venv's OWN pip -- never a
global/system pip. Safety gates (all in ``validate()``, never a default-on
override):
  - the venv path is root-jailed (EXT-037 / REQ-1's ``path_jail`` choke point);
  - a package spec that looks like a flag (starts with ``-``) is refused, so a
    package string can't smuggle an option into the pip invocation;
  - any ``extra_args`` entry naming a global/system-scope pip flag (``--user``,
    ``--target``, ``--prefix``, ``--system``, ``--global``, ``--root``,
    ``--break-system-packages``) is refused;
  - the decision is refused outright if the venv's python does not already exist
    (no silent fallback to an ambient/system interpreter), unless ``dry_run: true``.

Supports a ``dry_run: true`` payload flag: ``execute()`` then returns the
constructed pip invocation WITHOUT running it. This lets the harness (and the
offline test suite, which must never touch PyPI/network) confirm the exact
venv-scoped command that would run; the real (non-dry-run) path is unchanged and
actually installs.
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
    from _envtools import global_install_flag, venv_python_path
except Exception:  # pragma: no cover - fail safe if helper missing
    def venv_python_path(venv_dir):  # type: ignore
        if sys.platform == "win32":
            return os.path.join(venv_dir, "Scripts", "python.exe")
        return os.path.join(venv_dir, "bin", "python")

    def global_install_flag(args):  # type: ignore
        return None

# #EXT-037-REQ-3 Start
_DEFAULT_VENV_PATH = ".venv"
_DEFAULT_TIMEOUT_S = 120


def _packages_from(payload) -> list[str] | None:
    packages = payload.get("packages")
    if packages is None:
        pkg = payload.get("package")
        packages = [pkg] if pkg else None
    if not isinstance(packages, list) or not packages:
        return None
    if not all(isinstance(p, str) and p for p in packages):
        return None
    return packages


class VenvInstallTool:
    NAME = "env.venv_install"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            return ValidationResult.reject("env.venv_install requires a non-empty 'root' string")
        venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
        if not isinstance(venv_rel, str) or not venv_rel:
            return ValidationResult.reject("env.venv_install 'venv_path' must be a non-empty string")
        escape = path_escape_reason(root, venv_rel)
        if escape is not None:
            return ValidationResult.reject(f"env.venv_install refused venv path outside root: {escape}")

        packages = _packages_from(payload)
        if packages is None:
            return ValidationResult.reject("env.venv_install requires a non-empty 'package'/'packages'")
        for pkg in packages:
            if pkg.strip().startswith("-"):
                return ValidationResult.reject(
                    f"env.venv_install refused a package spec that looks like a flag: {pkg!r}")

        extra_args = payload.get("extra_args") or []
        if not isinstance(extra_args, list) or not all(isinstance(a, str) for a in extra_args):
            return ValidationResult.reject("env.venv_install 'extra_args' must be a list of strings")
        bad_flag = global_install_flag(extra_args)
        if bad_flag is not None:
            return ValidationResult.reject(
                f"env.venv_install refused a global-scope pip flag ({bad_flag!r}): "
                "installs are confined to the project venv, never system-wide")

        try:
            target = path_jail(root, venv_rel)
        except PathEscapeError as exc:
            return ValidationResult.reject(str(exc))
        python_path = venv_python_path(target)
        if not os.path.isfile(python_path) and not payload.get("dry_run"):
            return ValidationResult.reject(
                f"env.venv_install refused: venv python not found at {python_path!r} "
                "(create the venv first with env.venv_create, or pass dry_run=true)")
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        root = payload["root"]
        venv_rel = payload.get("venv_path", _DEFAULT_VENV_PATH)
        packages = _packages_from(payload) or []
        extra_args = payload.get("extra_args") or []
        dry_run = bool(payload.get("dry_run"))

        try:
            target = path_jail(root, venv_rel)
        except PathEscapeError as exc:
            return {"tool": self.NAME, "installed": False, "error": str(exc)}

        python_path = venv_python_path(target)
        command = [python_path, "-m", "pip", "install", *extra_args, *packages]

        if dry_run or not os.path.isfile(python_path):
            return {
                "tool": self.NAME,
                "command": command,
                "pythonPath": python_path,
                "installed": False,
                "dryRun": True,
            }

        try:
            proc = subprocess.run(
                command, capture_output=True, text=True,
                timeout=int(payload.get("timeout_s", _DEFAULT_TIMEOUT_S)))
        except Exception as exc:
            return {
                "tool": self.NAME,
                "command": command,
                "pythonPath": python_path,
                "installed": False,
                "error": str(exc),
            }

        return {
            "tool": self.NAME,
            "command": command,
            "pythonPath": python_path,
            "installed": proc.returncode == 0,
            "exitCode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
# #EXT-037-REQ-3 End
