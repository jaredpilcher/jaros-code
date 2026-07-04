"""EXT-037 / REQ-5: FINALIZE step -- the toolbelt actually WIELDED by the product.

The sentence-to-system product (EXT-036) can plan/build/assemble/accept a system, but
until this module it only ever emitted SOURCE FILES -- it never versioned or set up
the result. ``finalize_system(root, ...)`` runs AFTER a successful ``/buildsystem``
ship and delivers a versioned, set-up project, the Claude-Code-like default:

  1. git-init + commit the shipped system as a versioned deliverable, through the
     secret-guarded ``git.init``/``git.commit`` tools (EXT-037 / REQ-4) -- the
     existing secret guard refuses ``.env``/keys/credentials, so nothing here needs
     to re-implement that check.
  2. venv-if-deps: creates a root ``.venv`` (offline stdlib ``venv``/``ensurepip``, no
     network) ONLY when the built system actually declares a dependency -- an
     existing ``requirements.txt`` in ``root``, or a detectable non-stdlib top-level
     import across the built modules. A stdlib-only system (the common case for a
     small built system) SKIPS the venv entirely -- no noise. When a venv is created
     and no ``requirements.txt`` exists yet, the detected package names are recorded
     into one via ``env.venv_pin``'s explicit-``packages`` mode (still fully offline).
  3. NO auto-run of the generated code, ever, by default -- this module never touches
     ``shell.exec`` or otherwise executes the built system (a smoke-run behind that
     gated tool is an explicit LATER opt-in, not this task).

Every effect above is dispatched through ``harness.coding_loop.Runtime`` -- the SAME
Jaros-native gate -> executor -> decision-log choke point every other Decision in
this codebase goes through -- rather than calling each tool's ``validate()``/
``execute()`` ad hoc. That is the deliberate choice for REQ-5's own bar ("logged +
replayable"): routing through ``Runtime`` means every finalize effect is validated by
the real gate, hash-chain logged via the real ``DecisionLog``, and its accepted
Decision is the same replayable record every other Runtime-mediated effect produces
-- calling tool classes directly (as the offline REQ-2/REQ-3/REQ-4 test suites do)
would skip that log entirely.

``finalize_system`` NEVER raises: a rejected git commit (e.g. a secret path), a venv
that fails to create, a missing git binary, or any unexpected exception is caught and
reported in the returned dict's ``steps``/``note`` -- never propagated. A finalize
failure must never take down a successful build; the shipped system is unaffected
either way.

Honest limitation: only the venv is CREATED and detected dependency names are PINNED
into ``requirements.txt``; no package is actually installed over the network by this
step (consistent with the toolbelt's "no external network egress by default" safety
envelope -- design.md). Installing declared dependencies for real is a later opt-in,
not this task's scope.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = str(_REPO_ROOT / ".jaros-data" / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# #EXT-037-REQ-5 Start
from jaros.core import create_decision  # noqa: E402

from harness.coding_loop import DATA_DIR, Runtime  # noqa: E402

_DEFAULT_VENV_PATH = ".venv"
_DEFAULT_REQUIREMENTS = "requirements.txt"
_DEFAULT_COMMIT_MESSAGE = "Initial commit: system built by /buildsystem"

# Conservative dependency-detection heuristic: anything NOT in the stdlib (and not
# one of the system's own module names) counts as a declared third-party dependency.
_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def _decision(dtype: str, payload: dict):
    return create_decision(id=f"finalize-{dtype}-{uuid.uuid4().hex[:8]}", source="system_finalize",
                            type=dtype, payload=payload)


def _detect_top_level_imports(source: str) -> set:
    """Best-effort, never-raise: top-level module names imported by ``source``."""
    names: set = set()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def _detect_dependencies(root: str, modules: dict) -> tuple:
    """Returns ``(has_deps, package_names, reason)`` -- never raises.

    An existing ``requirements.txt`` in ``root`` always wins (the system already
    declared its deps explicitly); otherwise scan every built module's top-level
    imports for a name that is neither stdlib nor one of the system's own modules.
    """
    req_path = os.path.join(root, _DEFAULT_REQUIREMENTS)
    if os.path.isfile(req_path):
        try:
            lines = [ln.strip() for ln in Path(req_path).read_text(encoding="utf-8").splitlines()]
            packages = [ln for ln in lines if ln and not ln.startswith("#")]
        except OSError:
            packages = []
        return True, packages, f"existing {_DEFAULT_REQUIREMENTS}"

    imported: set = set()
    for source in (modules or {}).values():
        if isinstance(source, str):
            imported |= _detect_top_level_imports(source)
    own_modules = {name[:-3] if name.endswith(".py") else name for name in (modules or {})}
    third_party = sorted(n for n in imported if n and n not in _STDLIB_MODULES and n not in own_modules)
    if third_party:
        return True, third_party, "detected non-stdlib import(s): " + ", ".join(third_party)
    return False, [], "stdlib-only, no dependencies detected"


def finalize_system(root, modules: "dict | None" = None, *, git: bool = True,
                     venv: str = "auto", commit_message: "str | None" = None,
                     data_dir: "str | Path | None" = None) -> dict:
    """Post-build FINALIZE: git-commit the shipped system, venv-if-deps, never run it.

    ``venv`` is one of ``"auto"`` (create only when a dependency is detected --
    the default), ``"always"``, or ``"off"``. ``git=False``/``venv="off"`` cleanly
    disable each half of finalize independently; NEVER raises -- always returns a
    dict with an honest ``ok``/``steps``/``note``, even on total failure.
    """
    steps: list = []
    root = str(root)
    try:
        if not os.path.isdir(root):
            return {"ok": False, "steps": steps, "note": f"finalize skipped: root does not exist: {root!r}"}

        rt = Runtime(data_dir=Path(data_dir) if data_dir else DATA_DIR, root=root)

        # --- 1. git-init + commit -------------------------------------------------
        if git:
            try:
                init_out = rt.apply(_decision("git.init", {"root": root}))
                steps.append({"step": "git.init", "ok": True, "output": init_out})
            except Exception as exc:
                steps.append({"step": "git.init", "ok": False, "error": str(exc)})

            try:
                message = commit_message or _DEFAULT_COMMIT_MESSAGE
                commit_out = rt.apply(_decision("git.commit", {"root": root, "message": message}))
                steps.append({"step": "git.commit", "ok": bool(commit_out.get("committed")),
                              "output": commit_out})
            except Exception as exc:
                # A rejected commit (e.g. a secret path in the tree) or any other git
                # failure is reported, never forced through and never raised.
                steps.append({"step": "git.commit", "ok": False, "error": str(exc)})
        else:
            steps.append({"step": "git", "ok": True, "skipped": "git=False"})

        # --- 2. venv-if-deps --------------------------------------------------------
        has_deps, packages, dep_reason = _detect_dependencies(root, modules or {})
        if venv == "off":
            steps.append({"step": "venv", "ok": True, "skipped": "venv=off"})
        else:
            do_venv = venv == "always" or (venv == "auto" and has_deps)
            if not do_venv:
                steps.append({"step": "venv", "ok": True, "skipped": dep_reason})
            else:
                try:
                    venv_out = rt.apply(_decision(
                        "env.venv_create", {"root": root, "venv_path": _DEFAULT_VENV_PATH}))
                    steps.append({"step": "env.venv_create", "ok": bool(venv_out.get("created")),
                                  "output": venv_out, "reason": dep_reason})
                except Exception as exc:
                    steps.append({"step": "env.venv_create", "ok": False, "error": str(exc)})

                req_path = os.path.join(root, _DEFAULT_REQUIREMENTS)
                if packages and not os.path.isfile(req_path):
                    try:
                        pin_out = rt.apply(_decision(
                            "env.venv_pin", {"root": root, "packages": packages}))
                        steps.append({"step": "env.venv_pin", "ok": bool(pin_out.get("written")),
                                      "output": pin_out})
                    except Exception as exc:
                        steps.append({"step": "env.venv_pin", "ok": False, "error": str(exc)})

        ok = all(s.get("ok", True) for s in steps)
        return {"ok": ok, "steps": steps, "note": "finalize complete",
                "dependenciesDetected": has_deps}
    except Exception as exc:  # pragma: no cover-defensive -- finalize must never raise
        return {"ok": False, "steps": steps, "note": f"finalize failed: {exc}"}
# #EXT-037-REQ-5 End
