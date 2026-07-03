"""EXT-036 TASK-10: multi-level tests -- integration + performance (REQ-6).

Beyond unit tests (``harness.daily_driver`` write-tests) and the system-level acceptance
checklist (``harness.system_builder._derive_acceptance_checklist`` / ``_run_check``, which
exercises the assembled system's API), this module adds two more explicit test LEVELS:

  - ``integration_check`` -- an executable CROSS-MODULE scenario: a standalone script that
    imports >=2 of the system's modules and asserts a real interaction between them (not
    just one module in isolation). If no ``flow_code`` is supplied, a narrow model call
    derives one (best-effort); the RUN itself is always deterministic.
  - ``perf_check`` -- runs a real entry command and MEASURES actual wall-clock time,
    asserting it against a caller-supplied threshold. A genuinely slow system genuinely
    fails; nothing is estimated or faked.

Two-plane split: the only model step is deriving a flow script when the caller doesn't
supply one; assembling modules, running the scenario/command, measuring elapsed time, and
judging pass/fail are entirely deterministic. Both functions reuse
``harness.multi_file._run`` (the guarded, timeout/tree-kill-safe subprocess runner already
used by ``harness.system_builder._run_check``) and NEVER raise -- any failure (bad/missing
modules, unreadable root, a model call that errors) is reported as a non-passing result with
a diagnostic ``output``, never an exception.

HONESTY (Tenet 3): a broken cross-module flow is reported ``passed: False`` with the real
run output, never coerced to a pass; an over-threshold perf run is reported ``passed:
False`` with the REAL measured ``elapsed``, never adjusted or hidden.
"""

from __future__ import annotations

import time
from pathlib import Path

# #EXT-036-REQ-6 Start
from harness.system_builder import _call, _strip_fences

INTEGRATION_FLOW_PROMPT = (
    "SYSTEM MODULES:\n{sources}\n\n"
    "Write ONE standalone Python INTEGRATION test script that imports AT LEAST TWO of the "
    "modules above and asserts a REAL cross-module interaction (feed one module's output "
    "into another and assert on the combined result). Output ONLY the Python code (no "
    "markdown fences, no prose)."
)

_CHECK_MAX_TOKENS = 900


def _assemble(modules: "dict | None", root: Path) -> bool:
    """Deterministically write ``{name: code}`` modules onto ``root``. Guarded -- an
    unwritable root or a bad ``modules`` value returns False rather than raising."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        for name, code in (modules or {}).items():
            if not name:
                continue
            (root / name).write_text(code or "", encoding="utf-8", newline="\n")
        return True
    except (OSError, AttributeError, TypeError):
        return False


def _derive_flow_code(modules: "dict | None", llm) -> str:
    """Best-effort model derivation of a cross-module integration flow when the caller did
    not supply one. Guarded -- any model failure yields "" (no flow to run), never raises."""
    sources = "\n\n".join(f"# {name}:\n{code}" for name, code in (modules or {}).items())
    try:
        raw = _call(llm, INTEGRATION_FLOW_PROMPT.format(sources=sources), max_tokens=_CHECK_MAX_TOKENS)
    except Exception:
        return ""
    return _strip_fences(raw)


def integration_check(modules: "dict | None", root: "str | Path", flow_code: "str | None" = None,
                       llm=None) -> dict:
    """Assemble ``modules`` onto ``root`` and run a REAL cross-module INTEGRATION scenario.

    ``flow_code`` is standalone Python that imports >=2 modules and asserts a genuine
    cross-module interaction. When omitted, a narrow model call (``llm``) derives one
    best-effort; if no ``llm`` is available either, the check honestly fails rather than
    fabricating a result. Returns ``{"passed": bool, "output": str}`` -- the run is real
    (reuses ``harness.multi_file._run``, the same guarded/timeout-safe runner the system-
    level acceptance checks use), so a genuinely broken cross-module interaction FAILS for
    real. NEVER raises.
    """
    from harness.multi_file import _run as _run_cmd

    try:
        root = Path(root)
    except TypeError:
        return {"passed": False, "output": "invalid root"}

    if not _assemble(modules, root):
        return {"passed": False, "output": "could not assemble modules onto root"}

    code = flow_code
    if not code or not str(code).strip():
        if llm is None:
            return {"passed": False, "output": "no flow_code given and no llm to derive one"}
        code = _derive_flow_code(modules, llm)
    if not code or not str(code).strip():
        return {"passed": False, "output": "no integration flow to run"}

    flow_path = root / "_s2s_integration_check.py"
    try:
        flow_path.write_text(code, encoding="utf-8", newline="\n")
        ok, out = _run_cmd(str(root), "python _s2s_integration_check.py")
        return {"passed": bool(ok), "output": out}
    except Exception as exc:
        return {"passed": False, "output": str(exc)}
    finally:
        try:
            flow_path.unlink()
        except OSError:
            pass


def perf_check(modules: "dict | None", root: "str | Path", entry_cmd: "str | None",
                threshold_s: float) -> dict:
    """Assemble ``modules`` onto ``root`` (if any) and run ``entry_cmd``, MEASURING real
    wall-clock elapsed time. ``passed`` requires BOTH the command to actually succeed
    (non-zero exit is a real failure, not a timing question) AND the measured ``elapsed``
    to be at or under ``threshold_s`` -- a genuinely slow system genuinely fails, never
    estimated or coerced. Returns ``{"passed": bool, "elapsed": float | None, "output":
    str}``. NEVER raises (bad/missing modules, a missing ``entry_cmd``, or a run error all
    return a non-passing result with a diagnostic ``output``).
    """
    from harness.multi_file import _run as _run_cmd

    try:
        root = Path(root)
    except TypeError:
        return {"passed": False, "elapsed": None, "output": "invalid root"}

    if modules and not _assemble(modules, root):
        return {"passed": False, "elapsed": None, "output": "could not assemble modules onto root"}
    if not root.exists():
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"passed": False, "elapsed": None, "output": f"could not create root: {exc}"}

    if not entry_cmd or not str(entry_cmd).strip():
        return {"passed": False, "elapsed": None, "output": "no entry_cmd given"}

    try:
        start = time.perf_counter()
        ok, out = _run_cmd(str(root), entry_cmd)
        elapsed = time.perf_counter() - start
    except Exception as exc:
        return {"passed": False, "elapsed": None, "output": str(exc)}

    passed = bool(ok) and elapsed <= threshold_s
    return {"passed": passed, "elapsed": elapsed, "output": out}
# #EXT-036-REQ-6 End
