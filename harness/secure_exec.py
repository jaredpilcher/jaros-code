"""Secure sandboxed execution of generated code + gated egress (EXT-037 / REQ-7).

**The live gap this closes (foundation only — see the honest scope note below):**
`harness.system_builder.build_system`'s acceptance step runs model-generated code on the host as
a plain ``subprocess`` call (``python main.py``, ``uvicorn main:app``) with a ``cwd=<build dir>``
but **no environment restriction** — the child inherits the FULL host environment, including
secrets (API keys, ``LLAMACPP_*``, tokens), runs with full host permissions, has unrestricted
network egress, and is never statically scanned before it runs. This module is the FOUNDATION
for closing that gap: a deterministic AST scanner that classifies dangerous operations, a
first-class ``EgressPolicy`` that GATES (never blankets) network egress, and a sandboxed runner
with a scrubbed environment and POSIX resource caps.

**Owner constraint — egress is GATED, not BLOCKED.** Web research and dependency installation
both need controlled network access, so the design is DEFAULT-DENY with an explicit ALLOW-LIST a
caller supplies for the hosts it actually needs (e.g. ``EgressPolicy.allow("pypi.org",
"docs.python.org")``) — never a blanket network kill. :func:`scan_code` checks EVERY network
CALL's literal host individually against the supplied policy's ``is_host_allowed(host)`` — an
``allow_list`` policy is NOT a blanket pass for all egress in the scanned code, it permits ONLY
the specific host(s) it names. Fail-closed: an unlisted host, or a call whose target host cannot
be statically proven (a non-literal/undeterminable argument), is STILL a violation even when an
``allow_list`` policy is supplied.

**Honest scope note (Tenet 3):** this module is standalone and self-contained. It is
*deliberately NOT yet wired into* ``harness/system_builder.py``'s acceptance-run step — that
remains an explicit, separate follow-up task, not silently deferred. Likewise, true RUNTIME
network-egress blocking needs an OS-level mechanism (a Linux network namespace or firewall rule)
that this module does NOT implement; today's egress gate operates at the STATIC layer only (the
AST scan + ``EgressPolicy`` refuse un-permitted egress code before it is ever run). Runtime
egress enforcement on the Jetson/Linux deployment target is a named follow-up, not claimed here.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

# #EXT-037-REQ-7 Start

# --------------------------------------------------------------------------------------------
# EgressPolicy — the ONE mechanism that GATES network egress (default-deny + explicit allow-list)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EgressPolicy:
    """Controls whether network-egress operations are permitted.

    ``mode="deny"`` (the default) permits nothing. ``mode="allow_list"`` permits exactly the
    hosts named in ``allowed_hosts`` — an explicit opt-in per host, never a blanket network
    kill AND never a blanket allow. This is how research/dependency-install code paths get
    CONTROLLED egress: the caller passes a policy allow-listing only the hosts it needs.
    """

    mode: str = "deny"
    allowed_hosts: frozenset = field(default_factory=frozenset)

    def is_host_allowed(self, host: Any) -> bool:
        """Return True only if this policy explicitly permits ``host``."""
        if self.mode != "allow_list":
            return False
        if not isinstance(host, str) or not host:
            return False
        host_norm = host.strip().lower()
        return any(host_norm == h.strip().lower() for h in self.allowed_hosts)

    @classmethod
    def allow(cls, *hosts: str) -> "EgressPolicy":
        """Build an allow-list policy permitting exactly the given hosts."""
        return cls(mode="allow_list", allowed_hosts=frozenset(h for h in hosts if h))


EgressPolicy.DENY_ALL = EgressPolicy(mode="deny")  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------------
# scan_code — deterministic AST scanner classifying dangerous operations
# --------------------------------------------------------------------------------------------

CATEGORY_NETWORK = "NETWORK/EGRESS"
CATEGORY_SUBPROCESS = "SUBPROCESS/SHELL"
CATEGORY_DYNAMIC_EXEC = "DYNAMIC-EXEC"
CATEGORY_DESTRUCTIVE_FS = "DESTRUCTIVE/FS-OUTSIDE-ROOT"

# #EXT-037-REQ-15 Start
# Module-import egress classification is SUBMODULE-PRECISE, not root-name matching -- root
# matching over-flagged INBOUND LISTENERS (`http.server`, `socketserver`, which bind/accept
# local sockets and cannot themselves initiate an outbound connection) and PURE PARSERS
# (`urllib.parse`, `html.parser`, `email.parser`, which do no I/O at all) just because they
# share a root package name with a genuine egress-capable module. See ``_is_network_module``
# for the exact precedence (explicit allowlist first, then explicit always-flag, then
# per-root default-deny) -- the posture stays default-deny: anything NOT explicitly
# allowlisted below keeps today's flagged behavior.

# Dotted (or bare) module names that are ALWAYS egress/network regardless of how they are
# imported -- each can itself initiate an outbound connection.
_NETWORK_MODULES = {
    "socket", "urllib", "urllib.request", "urllib2",
    "http.client", "httplib", "requests", "httpx", "aiohttp", "ftplib",
    "smtplib", "telnetlib", "xmlrpc.client", "paramiko",
}
# Root package names whose submodules need PRECISE (not blanket) matching: some submodules
# under these roots are listeners/parsers (allow-listed below) while others (or a bare
# `import <root>` with no submodule at all) remain egress-capable and stay flagged.
_NETWORK_PRECISE_ROOTS = {"urllib", "http", "xmlrpc"}
# Exact submodule dotted names explicitly carved OUT of egress classification: inbound
# listeners (bind/accept local sockets -- cannot exfiltrate) and pure string parsers (no I/O
# at all). `socket`/raw sockets are deliberately NOT here -- a raw `socket.socket()` can
# `connect()` out even though servers also use it, so it stays flagged (see module docstring
# / STANDING SECURITY ORDER: this is precision, not relaxation).
_NETWORK_ALLOWED_SUBMODULES = {
    "http.server", "socketserver", "urllib.parse", "html.parser", "email.parser",
}


def _is_network_module(mod: str) -> bool:
    """Return True if importing ``mod`` (a fully dotted module path exactly as written in the
    import statement, e.g. ``"http.server"``, ``"urllib"``, ``"urllib.parse"``) is
    NETWORK/EGRESS. Precedence: (1) an exact match in the explicit listener/parser allowlist is
    NEVER egress; (2) an exact match in ``_NETWORK_MODULES`` is ALWAYS egress; (3) any other
    submodule (or a bare ``import <root>`` with no submodule) under a
    ``_NETWORK_PRECISE_ROOTS`` root default-denies (stays flagged, unchanged from prior
    behavior) since it is not explicitly proven safe; (4) anything else is not a recognized
    network module at all."""
    if mod in _NETWORK_ALLOWED_SUBMODULES:
        return False
    if mod in _NETWORK_MODULES:
        return True
    root = mod.split(".")[0]
    if root in _NETWORK_PRECISE_ROOTS:
        return True
    return root in _NETWORK_ROOT_MODULES


_NETWORK_ROOT_MODULES = {m.split(".")[0] for m in _NETWORK_MODULES} - _NETWORK_PRECISE_ROOTS
# #EXT-037-REQ-15 End

_SUBPROCESS_MODULES = {"subprocess", "pty", "commands"}
_SUBPROCESS_OS_ATTRS = {"system", "popen", "execl", "execle", "execlp", "execlpe",
                         "execv", "execve", "execvp", "execvpe", "spawnl", "spawnle",
                         "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"}

_DYNAMIC_EXEC_NAMES = {"eval", "exec", "compile", "__import__"}
_DYNAMIC_EXEC_ATTR_MODULES = {"importlib": {"import_module", "__import__"}}

_DESTRUCTIVE_OS_ATTRS = {"remove", "unlink", "rmdir", "removedirs", "chmod"}
_DESTRUCTIVE_SHUTIL_ATTRS = {"rmtree"}
_WRITE_MODE_MARKERS = ("w", "a", "x", "+")


def _hostname_from_url(url: Any) -> str | None:
    """Best-effort parse a literal URL string into a lowercased hostname. Returns ``None`` if
    ``url`` isn't a non-empty string or no hostname can be parsed out of it -- callers treat a
    ``None`` host as UNDETERMINABLE (fail-closed: never treated as implicitly allowed)."""
    if not isinstance(url, str) or not url:
        return None
    try:
        from urllib.parse import urlparse

        candidate = url if "//" in url else f"//{url}"
        host = urlparse(candidate).hostname
        return host.lower() if host else None
    except Exception:
        return None


def _literal_str_arg(node: ast.Call, keyword_names: tuple = ()) -> str | None:
    """Return the first literal string POSITIONAL argument of a call, or (failing that) the
    first literal string value of a keyword argument named in ``keyword_names``. Returns
    ``None`` when no literal string is found (e.g. a variable/expression was passed) -- this is
    the exact signal callers use to treat a target host as statically UNDETERMINABLE."""
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in node.keywords:
        if kw.arg in keyword_names and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, str):
            return kw.value.value
    return None


# Dotted call targets whose first literal argument is a URL (host extracted via urlparse).
_NETWORK_URL_CALL_DOTTED = {
    "requests.get", "requests.post", "requests.put", "requests.delete", "requests.patch",
    "requests.head", "requests.options", "requests.request",
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete", "httpx.patch",
    "httpx.head", "httpx.options", "httpx.request",
    "urllib.request.urlopen", "urllib.request.Request", "urllib2.urlopen",
}
# Dotted call targets whose first literal argument IS the host directly (not a URL).
_NETWORK_HOST_CALL_DOTTED = {
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "httplib.HTTPConnection", "httplib.HTTPSConnection",
}


def _dotted_name(node: ast.AST) -> str | None:
    """Best-effort reconstruct a dotted attribute/name chain, e.g. ``os.path.remove``."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return None
    return ".".join(reversed(parts))


def _is_absolute_or_escaping(path_str: str) -> bool:
    if not isinstance(path_str, str) or not path_str:
        return False
    if os.path.isabs(path_str):
        return True
    if path_str.startswith("\\\\"):
        return True
    # Windows drive-letter absolute path even when scanned on POSIX.
    if len(path_str) >= 2 and path_str[1] == ":" and path_str[0].isalpha():
        return True
    parts = path_str.replace("\\", "/").split("/")
    return ".." in parts


@dataclass
class ScanPolicy:
    """Per-category default-deny flags a caller can deliberately loosen."""

    deny_subprocess: bool = True
    deny_dynamic_exec: bool = True
    deny_destructive_fs: bool = True


@dataclass
class SecurityReport:
    ok: bool
    violations: list = field(default_factory=list)
    egress_ops: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _classify_import(node, filename: str, violations: list, egress_ops: list) -> None:
    # #EXT-037-REQ-15 Start
    if isinstance(node, ast.Import):
        for alias in node.names:
            mod = alias.name
            root = mod.split(".")[0]
            if _is_network_module(mod):
                egress_ops.append({
                    "category": CATEGORY_NETWORK, "detail": f"import {mod}",
                    "lineno": getattr(node, "lineno", None), "file": filename,
                    "kind": "import", "host": None,
                })
            elif root in _SUBPROCESS_MODULES:
                violations.append({
                    "category": CATEGORY_SUBPROCESS, "detail": f"import {mod}",
                    "lineno": getattr(node, "lineno", None), "file": filename,
                })
    elif isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        root = mod.split(".")[0]
        if mod in _NETWORK_PRECISE_ROOTS:
            # `from <root> import a, b, c` where <root> is itself a precise root (e.g.
            # `from urllib import parse, request`) -- each imported NAME is a submodule of
            # <root>, so classify PER NAME. A mixed import (some names safe, one not) still
            # flags on the unsafe name -- never silently allowed because a sibling name was
            # allowlisted.
            for alias in node.names:
                submod = f"{mod}.{alias.name}"
                if _is_network_module(submod):
                    egress_ops.append({
                        "category": CATEGORY_NETWORK,
                        "detail": f"from {mod} import {alias.name}",
                        "lineno": getattr(node, "lineno", None), "file": filename,
                        "kind": "import", "host": None,
                    })
        elif _is_network_module(mod):
            egress_ops.append({
                "category": CATEGORY_NETWORK, "detail": f"from {mod} import ...",
                "lineno": getattr(node, "lineno", None), "file": filename,
                "kind": "import", "host": None,
            })
        elif root in _SUBPROCESS_MODULES:
            violations.append({
                "category": CATEGORY_SUBPROCESS, "detail": f"from {mod} import ...",
                "lineno": getattr(node, "lineno", None), "file": filename,
            })
        # #EXT-037-REQ-15 End
        if root == "importlib":
            for alias in node.names:
                if alias.name in _DYNAMIC_EXEC_ATTR_MODULES.get("importlib", set()):
                    violations.append({
                        "category": CATEGORY_DYNAMIC_EXEC,
                        "detail": f"from importlib import {alias.name}",
                        "lineno": getattr(node, "lineno", None), "file": filename,
                    })


def _classify_call(node: ast.Call, filename: str, violations: list, egress_ops: list) -> None:
    func = node.func
    lineno = getattr(node, "lineno", None)

    # Bare-name calls: eval(...), exec(...), compile(...), __import__(...)
    if isinstance(func, ast.Name) and func.id in _DYNAMIC_EXEC_NAMES:
        violations.append({
            "category": CATEGORY_DYNAMIC_EXEC, "detail": f"{func.id}(...)",
            "lineno": lineno, "file": filename,
        })
        return

    dotted = _dotted_name(func) if isinstance(func, ast.Attribute) else None

    if isinstance(func, ast.Attribute):
        base = func.value
        base_name = base.id if isinstance(base, ast.Name) else None

        # --- network/egress calls: extract a literal host so it can be gated PER HOST below,
        # not just per-category. `host` stays None when it cannot be statically proven (a
        # variable/expression rather than a string literal) -- callers treat None as
        # UNDETERMINABLE and fail-closed (never implicitly permitted by an allow_list policy).
        network_hit = False
        host: str | None = None
        if dotted in _NETWORK_URL_CALL_DOTTED:
            network_hit = True
            url = _literal_str_arg(node, keyword_names=("url", "fullurl"))
            host = _hostname_from_url(url) if url else None
        elif dotted in _NETWORK_HOST_CALL_DOTTED:
            network_hit = True
            literal_host = _literal_str_arg(node, keyword_names=("host",))
            host = literal_host.strip().lower() if literal_host else None
        elif dotted == "socket.create_connection":
            network_hit = True
            if node.args and isinstance(node.args[0], (ast.Tuple, ast.List)) and node.args[0].elts:
                first_elt = node.args[0].elts[0]
                if isinstance(first_elt, ast.Constant) and isinstance(first_elt.value, str):
                    host = first_elt.value.strip().lower()
        elif base_name in {"requests", "httpx", "aiohttp"}:
            # A method/attribute on these modules not covered by the specific dotted patterns
            # above (e.g. `requests.Session()`, `aiohttp.ClientSession()`) -- still network
            # activity, but no literal host to extract; host stays None (undeterminable).
            network_hit = True
            url = _literal_str_arg(node, keyword_names=("url", "fullurl"))
            host = _hostname_from_url(url) if url else None

        if network_hit:
            egress_ops.append({
                "category": CATEGORY_NETWORK, "detail": f"{dotted}(...)",
                "lineno": lineno, "file": filename, "kind": "call", "host": host,
            })
            return

        # os.system / os.popen / os.exec*/spawn*
        if base_name == "os" and func.attr in _SUBPROCESS_OS_ATTRS:
            violations.append({
                "category": CATEGORY_SUBPROCESS, "detail": f"os.{func.attr}(...)",
                "lineno": lineno, "file": filename,
            })
        # os.remove/unlink/rmdir/removedirs/chmod
        elif base_name == "os" and func.attr in _DESTRUCTIVE_OS_ATTRS:
            violations.append({
                "category": CATEGORY_DESTRUCTIVE_FS, "detail": f"os.{func.attr}(...)",
                "lineno": lineno, "file": filename,
            })
        # shutil.rmtree
        elif base_name == "shutil" and func.attr in _DESTRUCTIVE_SHUTIL_ATTRS:
            violations.append({
                "category": CATEGORY_DESTRUCTIVE_FS, "detail": f"shutil.{func.attr}(...)",
                "lineno": lineno, "file": filename,
            })
        # subprocess.* (run, Popen, call, check_call, check_output, ...)
        elif base_name == "subprocess":
            violations.append({
                "category": CATEGORY_SUBPROCESS, "detail": f"subprocess.{func.attr}(...)",
                "lineno": lineno, "file": filename,
            })
        # importlib.import_module(...)
        elif base_name == "importlib" and func.attr == "import_module":
            violations.append({
                "category": CATEGORY_DYNAMIC_EXEC, "detail": "importlib.import_module(...)",
                "lineno": lineno, "file": filename,
            })
        # .write_text/.write_bytes on a Path-like literal path is handled by the dedicated
        # Path(...).write_*() check below (kept as its own pass for determinism/clarity).

    # open(path, mode) with an absolute/escaping literal path in write-ish mode
    if isinstance(func, ast.Name) and func.id == "open" and node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            mode = None
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            mode_str = mode if isinstance(mode, str) else "r"
            is_write_mode = any(m in mode_str for m in _WRITE_MODE_MARKERS)
            if is_write_mode and _is_absolute_or_escaping(first.value):
                violations.append({
                    "category": CATEGORY_DESTRUCTIVE_FS,
                    "detail": f"open({first.value!r}, {mode_str!r}) escapes/absolute",
                    "lineno": lineno, "file": filename,
                })

    # Path(...).write_text(...) / Path(...).write_bytes(...) with a literal escaping path
    if isinstance(func, ast.Attribute) and func.attr in {"write_text", "write_bytes"}:
        base = func.value
        if isinstance(base, ast.Call) and isinstance(base.func, ast.Name) and base.func.id == "Path" \
                and base.args and isinstance(base.args[0], ast.Constant) \
                and isinstance(base.args[0].value, str):
            path_literal = base.args[0].value
            if _is_absolute_or_escaping(path_literal):
                violations.append({
                    "category": CATEGORY_DESTRUCTIVE_FS,
                    "detail": f"Path({path_literal!r}).{func.attr}(...) escapes/absolute",
                    "lineno": lineno, "file": filename,
                })


def _scan_one_file(filename: str, code: str, violations: list, egress_ops: list, notes: list) -> None:
    if not isinstance(code, str):
        violations.append({
            "category": "PARSE-ERROR", "detail": f"non-string source for {filename!r}",
            "lineno": None, "file": filename,
        })
        return
    try:
        tree = ast.parse(code, filename=filename)
    except SyntaxError as exc:
        violations.append({
            "category": "PARSE-ERROR", "detail": f"unparseable source: {exc}",
            "lineno": getattr(exc, "lineno", None), "file": filename,
        })
        return
    except Exception as exc:  # pragma: no cover - never raise on garbage input
        violations.append({
            "category": "PARSE-ERROR", "detail": f"scan failed: {exc}",
            "lineno": None, "file": filename,
        })
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _classify_import(node, filename, violations, egress_ops)
        elif isinstance(node, ast.Call):
            _classify_call(node, filename, violations, egress_ops)


def scan_code(sources, *, egress_policy: "EgressPolicy | None" = None,
              scan_policy: "ScanPolicy | None" = None) -> SecurityReport:
    """AST-scan ``sources`` (a single code string, or ``{filename: code}``) and classify
    dangerous operations. Never raises -- unparseable source is recorded as a violation.

    ``ok`` is decided by policy: SUBPROCESS/SHELL, DYNAMIC-EXEC, and DESTRUCTIVE/FS-OUTSIDE-ROOT
    matches are always violations (when their ``ScanPolicy`` flag is True, the default).

    NETWORK/EGRESS matches are recorded in ``egress_ops`` always. Each CALL-site egress op
    (``kind="call"``, e.g. ``requests.get("https://pypi.org/...")``) carries a ``host`` extracted
    from its literal argument where statically possible. Such a call is permitted (kept OUT of
    ``violations``) ONLY IF ``egress_policy`` is in ``allow_list`` mode AND
    ``egress_policy.is_host_allowed(host)`` is True for THAT specific host -- an allow_list policy
    is never a blanket pass for every egress op in the code. Fail-closed: an unlisted host, or a
    call whose host could not be statically determined (``host is None`` -- a variable/expression
    rather than a string literal), is STILL a violation even under an allow_list policy. A bare
    ``import`` of a network module (``kind="import"``, no host to check -- importing performs no
    network action by itself) is a violation only when no ``allow_list`` policy is supplied at
    all. This is a STATIC gate only: it decides before the code ever runs; it does not itself
    enforce anything at runtime (see :func:`run_sandboxed`'s own honest scope note).
    """
    scan_policy = scan_policy or ScanPolicy()
    violations: list = []
    egress_ops: list = []
    notes: list = []

    try:
        if isinstance(sources, str):
            file_map = {"<string>": sources}
        elif isinstance(sources, dict):
            file_map = sources
        else:
            return SecurityReport(
                ok=False,
                violations=[{"category": "PARSE-ERROR",
                             "detail": f"scan_code requires a str or dict, got {type(sources)!r}",
                             "lineno": None, "file": None}],
                egress_ops=[], notes=["invalid sources argument"],
            )

        for filename, code in file_map.items():
            _scan_one_file(filename, code, violations, egress_ops, notes)

        # Apply the ScanPolicy loosening (deliberate, per-category opt-out).
        kept_violations = []
        for v in violations:
            cat = v.get("category")
            if cat == CATEGORY_SUBPROCESS and not scan_policy.deny_subprocess:
                notes.append(f"SUBPROCESS/SHELL violation loosened by ScanPolicy: {v.get('detail')}")
                continue
            if cat == CATEGORY_DYNAMIC_EXEC and not scan_policy.deny_dynamic_exec:
                notes.append(f"DYNAMIC-EXEC violation loosened by ScanPolicy: {v.get('detail')}")
                continue
            if cat == CATEGORY_DESTRUCTIVE_FS and not scan_policy.deny_destructive_fs:
                notes.append(f"DESTRUCTIVE/FS violation loosened by ScanPolicy: {v.get('detail')}")
                continue
            kept_violations.append(v)
        violations = kept_violations

        # Egress is GATED PER HOST, not by a blanket category pass. An allow_list policy permits
        # ONLY the specific host(s) it names -- it is never a blanket pass for every egress op in
        # the scanned code. Fail-closed: an unlisted host, or a call whose host could not be
        # statically proven (`host is None`), is STILL a violation even under an allow_list
        # policy; we never treat an unverifiable target as implicitly allowed.
        if egress_ops:
            policy = egress_policy
            allow_list_active = bool(policy) and policy.mode == "allow_list"
            unpermitted = []
            for op in egress_ops:
                if not allow_list_active:
                    # No permitting policy at all: default-deny means every egress op (import
                    # mention or call alike) is refused.
                    unpermitted.append(op)
                    continue
                if op.get("kind") != "call":
                    # A bare import of a network module carries no host to check and performs no
                    # network action by itself -- not gated per-host once an allow_list policy is
                    # in effect for this scan.
                    continue
                host = op.get("host")
                if host is None or not policy.is_host_allowed(host):
                    unpermitted.append(op)

            for op in unpermitted:
                violations.append({**op, "detail": f"unpermitted egress: {op.get('detail')}"})

            if unpermitted:
                notes.append(
                    "egress operations found that are NOT permitted by the supplied EgressPolicy "
                    "-- an unlisted host, a statically-undeterminable target (fail-closed: an "
                    "unproven host is denied, never implicitly allowed), or no policy at all"
                )
            if len(unpermitted) < len(egress_ops):
                notes.append(
                    "some egress call(s) were permitted at SCAN TIME because their literal host "
                    "individually matched an allow_list EgressPolicy; this is a STATIC check "
                    "only -- real runtime network-egress enforcement (a Linux network namespace "
                    "or firewall rule on the Jetson/Linux deployment target) is a separate, "
                    "explicit follow-up NOT implemented by this module"
                )

        ok = len(violations) == 0
        return SecurityReport(ok=ok, violations=violations, egress_ops=egress_ops, notes=notes)
    except Exception as exc:  # never raise
        return SecurityReport(
            ok=False,
            violations=[{"category": "SCAN-ERROR", "detail": str(exc), "lineno": None, "file": None}],
            egress_ops=[], notes=[f"scan_code failed unexpectedly: {exc}"],
        )


# --------------------------------------------------------------------------------------------
# run_sandboxed — scrubbed env + resource caps + timeout/tree-kill
# --------------------------------------------------------------------------------------------

_SAFE_ENV_KEYS = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "LANG", "LC_ALL", "TMP", "TEMP",
    "TMPDIR", "PYTHONPATH", "PYTHONIOENCODING", "HOME", "USERPROFILE", "PATHEXT",
)


def _scrubbed_env(extra_env: dict | None) -> dict:
    """Build a minimal safe environment: only a small allow-list of host vars survives, plus
    whatever ``extra_env`` supplies. Everything else (secrets, tokens, API keys, LLAMACPP_*,
    etc.) is dropped -- this is the key protection this module provides."""
    env: dict = {}
    for key in _SAFE_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    if isinstance(extra_env, dict):
        for k, v in extra_env.items():
            if isinstance(k, str):
                env[k] = str(v)
    return env


def _kill_tree(proc) -> None:
    """Kill *proc* AND its descendants (mirrors ``shell_exec_tool.py::_kill_tree`` /
    ``harness.research_scripts._kill_tree`` exactly -- the same choke point, not a divergent
    copy) so a hung sandboxed child never orphans a process."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _make_preexec_fn(mem_mb: int, timeout: float):
    """Build a POSIX-only ``preexec_fn`` applying RLIMIT_AS/RLIMIT_CPU caps. Returns ``None``
    on Windows or if the stdlib ``resource`` module is unavailable -- guarded/optional, never
    raises the caller."""
    if sys.platform == "win32":
        return None
    try:
        import resource  # POSIX-only stdlib module
    except Exception:
        return None

    def _preexec():
        try:
            mem_bytes = int(mem_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            pass
        try:
            cpu_s = max(int(timeout) + 1, 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        except Exception:
            pass

    return _preexec


# TASK-11 (REQ-7 follow-up): sentinel distinguishing "caller omitted stdin entirely" (preserve
# the original no-stdin-pipe behavior byte-for-byte -- the child inherits the parent's stdin,
# exactly as before this task) from "caller explicitly passed stdin=<str-or-None>" (a real value
# -- even ``None`` -- means the caller wants stdin PIPED, so an omitted/``None`` value still
# sends an immediate EOF instead of inheriting the parent's stdin). A plain ``None`` default
# could not make this distinction. Already inside this module's existing REQ-7 Start/End wrap.
_STDIN_UNSET = object()


def run_sandboxed(cmd, *, cwd, egress_policy: "EgressPolicy | None" = None,
                   timeout: float = 30, mem_mb: int = 512, extra_env: dict | None = None,
                   stdin: "str | None" = _STDIN_UNSET) -> dict:
    """Execute ``cmd`` with a scrubbed environment, a resource-capped (POSIX) subprocess, the
    caller's ``cwd``, and a timeout + process-tree kill. Never raises.

    ``stdin`` (TASK-11, REQ-7 follow-up): when the caller EXPLICITLY passes ``stdin`` (a string,
    or ``None``), the child's stdin is piped and fed that string (``None`` sends immediate EOF --
    no data written, matching the exact behavior ``harness.system_suite._run_cli`` relied on
    before it was routed through this function). When the caller omits ``stdin`` entirely (the
    default), behavior is UNCHANGED from before this parameter existed: no stdin pipe is set up,
    so the child inherits the parent's stdin -- this keeps every existing caller (e.g.
    ``harness.system_builder``'s acceptance-check runner) byte-for-byte backward compatible.

    **Honest platform/egress note:** this function does NOT implement runtime network-egress
    blocking (that needs an OS network namespace or firewall rule -- a Linux/Jetson follow-up).
    ``egress_policy`` is accepted for API symmetry with :func:`secure_run_generated` and is
    recorded in the returned ``note``, but the only egress GATE actually enforced today is the
    static one in :func:`scan_code` (called by :func:`secure_run_generated` before this ever
    runs). POSIX resource caps (RLIMIT_AS/RLIMIT_CPU) are applied via a ``preexec_fn`` when the
    ``resource`` module is available; on Windows there is no equivalent, and this is documented
    honestly rather than silently skipped.
    """
    egress_policy = egress_policy or EgressPolicy.DENY_ALL
    stdin_requested = stdin is not _STDIN_UNSET
    stdin_value = stdin if isinstance(stdin, str) else None
    try:
        if not cmd:
            return {
                "ok": False, "returncode": None, "stdout": "", "stderr": "empty command",
                "timed_out": False, "killed": False,
                "note": "run_sandboxed requires a non-empty cmd",
            }
        if not isinstance(cwd, str) or not cwd or not os.path.isdir(cwd):
            return {
                "ok": False, "returncode": None, "stdout": "", "stderr": "",
                "timed_out": False, "killed": False,
                "note": f"run_sandboxed requires an existing 'cwd' directory, got {cwd!r}",
            }

        env = _scrubbed_env(extra_env)
        use_shell = isinstance(cmd, str)
        popen_kwargs: dict = dict(
            cwd=cwd, env=env, shell=use_shell,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if stdin_requested:
            popen_kwargs["stdin"] = subprocess.PIPE
        preexec_fn = _make_preexec_fn(mem_mb, timeout)
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True
            if preexec_fn is not None:
                popen_kwargs["preexec_fn"] = preexec_fn

        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
        except Exception as exc:
            return {
                "ok": False, "returncode": None, "stdout": "", "stderr": f"failed to start: {exc}",
                "timed_out": False, "killed": False,
                "note": (
                    f"run_sandboxed failed to start the process (egress_policy.mode="
                    f"{egress_policy.mode!r}): {exc}"
                ),
            }

        try:
            if stdin_requested:
                out, err = proc.communicate(input=stdin_value, timeout=timeout)
            else:
                out, err = proc.communicate(timeout=timeout)
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": out or "",
                "stderr": err or "",
                "timed_out": False,
                "killed": False,
                "note": (
                    f"completed; env scrubbed to {sorted(env.keys())}; egress_policy.mode="
                    f"{egress_policy.mode!r} (runtime egress enforcement is a Linux "
                    f"namespace/firewall follow-up, not implemented here)"
                ),
            }
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                out, err = proc.communicate(timeout=5)
            except Exception:
                out, err = "", ""
            return {
                "ok": False,
                "returncode": None,
                "stdout": out or "",
                "stderr": err or "",
                "timed_out": True,
                "killed": True,
                "note": f"timed out after {timeout}s; process tree killed",
            }
    except Exception as exc:  # never raise -- an honest diagnostic observation instead
        return {
            "ok": False, "returncode": None, "stdout": "", "stderr": "",
            "timed_out": False, "killed": False,
            "note": f"run_sandboxed failed unexpectedly: {exc}",
        }


# --------------------------------------------------------------------------------------------
# secure_run_generated — the gate a caller (build_system acceptance, future follow-up) uses
# --------------------------------------------------------------------------------------------


def secure_run_generated(sources, cmd, *, cwd, egress_policy: "EgressPolicy | None" = None) -> dict:
    """Scan ``sources`` first; refuse to run on any violation (``blocked=True``, nothing
    executed); otherwise delegate to :func:`run_sandboxed`. Never raises.

    This is the gate a caller such as ``harness.system_builder.build_system``'s acceptance
    step would use to run model-generated code safely -- **not yet wired in** (an explicit,
    separate follow-up; see the module docstring's honest scope note).
    """
    egress_policy = egress_policy or EgressPolicy.DENY_ALL
    try:
        report = scan_code(sources, egress_policy=egress_policy)
        if not report.ok:
            return {"ran": False, "blocked": True, "report": report}
        run_result = run_sandboxed(cmd, cwd=cwd, egress_policy=egress_policy)
        return {"ran": True, "blocked": False, "report": report, **run_result}
    except Exception as exc:  # never raise
        return {
            "ran": False, "blocked": True,
            "report": SecurityReport(ok=False, violations=[{
                "category": "SCAN-ERROR", "detail": str(exc), "lineno": None, "file": None,
            }], egress_ops=[], notes=[f"secure_run_generated failed unexpectedly: {exc}"]),
        }
# #EXT-037-REQ-7 End
