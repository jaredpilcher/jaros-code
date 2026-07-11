"""Deterministic, OFFLINE dependency-security signal over the standard library itself
(EXT-037 / REQ-16, Phase 1).

**Owner directive (2026-07-10):** a "dependency security" gate for jaros-code cannot be the
usual CVE-database lookup a normal SCA tool runs, because generated systems here are
STDLIB-ONLY by design (Tenet 2 / the no-network-egress posture) and the stdlib has no
independent version to look up against a CVE feed. The honest risk model for stdlib is three
axes instead: (1) a module that is DEPRECATED/REMOVED across supported CPython versions (PEP
594 "dead batteries" + a handful of older removals) -- code that imports one will break on a
newer interpreter; (2) a stdlib API that is DANGEROUS when used carelessly (weak hashing,
``shell=True``, bare ``eval``/``exec``, a predictable ``tempfile.mktemp`` race, unpickling
untrusted bytes) -- these are real, well-known CVE-adjacent footguns even though the module
itself has no CVE; (3) an EOL interpreter -- the security floor a stdlib scan runs on top of.
This module is fully OFFLINE (no network, no CVE-DB call), deterministic, and never raises --
mirroring the house pattern already established by :mod:`harness.secure_exec` (``scan_code``)
and :mod:`harness.code_quality` (``assess_quality``).

**This ADDS a check; it never weakens any existing gate.** ``harness/secure_exec.py`` (the
egress/subprocess/dynamic-exec/destructive-fs scan gate, REQ-7) is untouched by this module.
``stdlib_safety_findings`` below is wired into ``build_system`` as a NON-GATING, ADVISORY
field only (mirroring ``harness/code_quality.py``'s ``quality`` field precedent) -- it can
never flip a build from ``done=True`` to ``done=False``. Deciding whether/when any of this
becomes a hard gate is deferred to a later phase, once real data exists.

It also hardens the REQ-66 stdlib-affordance-recommendation hint
(``harness.system_builder.spec_declared_stdlib_affordances``/``_spec_affordance_hint``): a
spec that names a dangerous/deprecated stdlib module (e.g. "the `pickle` module is allowed")
must never have that module surfaced as a RECOMMENDED affordance -- see
:func:`is_safe_affordance`.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass

# #EXT-037-REQ-16 Start

# PEP 594 "dead batteries" (removed 3.12/3.13) plus a handful of older stdlib removals/
# deprecations. Each note is a short, honest pointer to WHEN/WHY -- not exhaustive CPython
# changelog prose, just enough for a reader to know this module is on borrowed time.
DEPRECATED_REMOVED: dict[str, str] = {
    "telnetlib": "removed in 3.13 (PEP 594) -- also plaintext-credential risk",
    "cgi": "removed in 3.13 (PEP 594)",
    "cgitb": "removed in 3.13 (PEP 594)",
    "crypt": "removed in 3.13 (PEP 594) -- also a weak/legacy hashing API",
    "imghdr": "removed in 3.13 (PEP 594)",
    "nntplib": "removed in 3.13 (PEP 594)",
    "asyncore": "removed in 3.12 (PEP 594)",
    "asynchat": "removed in 3.12 (PEP 594)",
    "imp": "removed in 3.12 -- use importlib",
    "smtpd": "removed in 3.12 (PEP 594)",
    "sndhdr": "removed in 3.13 (PEP 594)",
    "spwd": "removed in 3.13 (PEP 594)",
    "nis": "removed in 3.13 (PEP 594)",
    "ossaudiodev": "removed in 3.13 (PEP 594)",
    "audioop": "removed in 3.13 (PEP 594)",
    "chunk": "removed in 3.13 (PEP 594)",
    "mailcap": "removed in 3.13 (PEP 594)",
    "msilib": "removed in 3.13 (PEP 594)",
    "pipes": "removed in 3.13 (PEP 594)",
    "uu": "removed in 3.13 (PEP 594)",
    "xdrlib": "removed in 3.13 (PEP 594)",
    "formatter": "removed in 3.10",
    "distutils": "deprecated since 3.10, removed in 3.12 -- use setuptools/sysconfig",
}

# Stdlib modules that must NEVER be surfaced as a RECOMMENDED affordance (REQ-66 coupling),
# even when a spec explicitly names them, because using them carries a genuine, well-known
# risk (arbitrary-code-execution-on-load for pickle/marshal/shelve, plaintext creds for
# telnetlib/crypt/cgi) that a "prefer this over hand-rolling it" nudge must never encourage.
# Unioned with DEPRECATED_REMOVED below so a dead-battery module is never recommended either.
_DANGEROUS_ONLY: set[str] = {"pickle", "marshal", "shelve", "telnetlib", "crypt", "cgi"}
DANGEROUS_AFFORDANCES: set[str] = _DANGEROUS_ONLY | set(DEPRECATED_REMOVED)

MIN_SUPPORTED = (3, 9)


def is_safe_affordance(module: str) -> bool:
    """False when `module` must never be recommended as a build-prompt affordance (REQ-66
    coupling) -- a member of :data:`DANGEROUS_AFFORDANCES` or :data:`DEPRECATED_REMOVED`.
    True otherwise (the common case, e.g. ``base64``, ``difflib``, ``textwrap``). Pure,
    never raises."""
    try:
        return module not in DANGEROUS_AFFORDANCES and module not in DEPRECATED_REMOVED
    except Exception:
        return True


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def _deprecated_import_findings(tree: ast.AST) -> list[dict]:
    findings: list[dict] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [_root_module(a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [_root_module(node.module)]
        for name in names:
            if name in DEPRECATED_REMOVED and name not in seen:
                seen.add(name)
                findings.append({
                    "kind": "deprecated_module",
                    "module": name,
                    "message": f"import of deprecated/removed stdlib module '{name}': "
                               f"{DEPRECATED_REMOVED[name]}",
                    "severity": "warn",
                })
    return findings


def _is_name(node: "ast.expr | None", name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_attr(node: "ast.expr | None", owner: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and _is_name(node.value, owner)
    )


def _dangerous_use_findings(tree: ast.AST) -> list[dict]:
    """Small, precise, conservative set of dangerous-USE patterns -- low false-positive by
    construction (each requires an exact call shape, no heuristics). Deliberately does NOT
    try to flag ``random.`` used for a token/secret (too ambiguous to detect reliably from a
    single call site without false-positiving on legitimate simulation/sampling use)."""
    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # hashlib.md5(...) / hashlib.sha1(...) -- weak hash
        if _is_attr(func, "hashlib", "md5") or _is_attr(func, "hashlib", "sha1"):
            findings.append({
                "kind": "dangerous_use",
                "api": f"hashlib.{func.attr}",
                "message": f"hashlib.{func.attr}() is a cryptographically weak hash -- "
                            "avoid for anything security-sensitive (passwords, integrity).",
                "severity": "advisory",
                "lineno": getattr(node, "lineno", None),
            })
        # subprocess-family call with shell=True
        elif isinstance(func, ast.Attribute) and func.attr in (
            "run", "call", "check_call", "check_output", "Popen",
        ) and _is_name(func.value, "subprocess"):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    findings.append({
                        "kind": "dangerous_use",
                        "api": f"subprocess.{func.attr}(shell=True)",
                        "message": "subprocess call with shell=True -- shell-injection risk "
                                    "if any argument includes untrusted input.",
                        "severity": "advisory",
                        "lineno": getattr(node, "lineno", None),
                    })
                    break
        # bare eval(...) / exec(...)
        elif _is_name(func, "eval") or _is_name(func, "exec"):
            findings.append({
                "kind": "dangerous_use",
                "api": func.id,
                "message": f"bare {func.id}() on dynamic input is an arbitrary-code-execution "
                            "risk.",
                "severity": "advisory",
                "lineno": getattr(node, "lineno", None),
            })
        # tempfile.mktemp(...) -- predictable-name TOCTOU race
        elif _is_attr(func, "tempfile", "mktemp"):
            findings.append({
                "kind": "dangerous_use",
                "api": "tempfile.mktemp",
                "message": "tempfile.mktemp() returns a name without creating the file -- "
                            "a TOCTOU race; use tempfile.mkstemp()/NamedTemporaryFile instead.",
                "severity": "advisory",
                "lineno": getattr(node, "lineno", None),
            })
        # pickle.load(...) / pickle.loads(...) -- untrusted-data deserialization risk
        elif _is_attr(func, "pickle", "load") or _is_attr(func, "pickle", "loads"):
            findings.append({
                "kind": "dangerous_use",
                "api": f"pickle.{func.attr}",
                "message": f"pickle.{func.attr}() on untrusted/unauthenticated data is an "
                            "arbitrary-code-execution risk.",
                "severity": "advisory",
                "lineno": getattr(node, "lineno", None),
            })
    return findings


def stdlib_safety_findings(code: str) -> list[dict]:
    """AST-scan `code` for (a) imports of a :data:`DEPRECATED_REMOVED` stdlib module and (b)
    a small, precise set of DANGEROUS-USE patterns (weak hashing, ``shell=True``, bare
    ``eval``/``exec``, ``tempfile.mktemp``, ``pickle.load``/``loads``). Each finding is
    ``{"kind", "module"/"api", "message", "severity"}`` (severity always ADVISORY-shaped --
    "warn" or "advisory", never a hard gate). Never raises: unparseable/non-string `code`
    returns ``[]``, exactly like a clean file would."""
    try:
        tree = ast.parse(code)
    except Exception:
        return []
    try:
        return _deprecated_import_findings(tree) + _dangerous_use_findings(tree)
    except Exception:
        return []


def interpreter_eol_warning(version_info=None) -> "str | None":
    """Compare `version_info` (default: the running interpreter's ``sys.version_info``)
    against :data:`MIN_SUPPORTED`. Returns a short warning string when the interpreter is
    below the minimum supported version, else ``None``. Pure -- a caller can pass a fake
    ``(major, minor)``-style tuple/sequence to test without touching the real interpreter.
    Never raises (a malformed `version_info` degrades to ``None``, i.e. "no warning")."""
    try:
        vi = version_info if version_info is not None else sys.version_info
        major, minor = vi[0], vi[1]
        if (major, minor) < MIN_SUPPORTED:
            return (
                f"interpreter {major}.{minor} is below the minimum supported "
                f"{MIN_SUPPORTED[0]}.{MIN_SUPPORTED[1]} -- EOL/security-patch risk"
            )
        return None
    except Exception:
        return None

# #EXT-037-REQ-16 End
