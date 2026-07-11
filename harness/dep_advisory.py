"""Deterministic, OFFLINE dependency-security signal over THIRD-PARTY package requirements
(EXT-037 / REQ-17, Phase 2 -- follows the stdlib-only Phase 1 in ``harness.stdlib_safety``).

**Owner directive (2026-07-10):** "gate builds on dependency security" -- Phase 1
(``harness/stdlib_safety.py`` / REQ-16) covered the stdlib-only risk model. Phase 2 covers the
other half: builds that DO declare a third-party dependency (an existing ``requirements.txt``,
or a detected non-stdlib top-level import -- see ``harness.system_finalize._detect_dependencies``)
are exactly where "old/vulnerable VERSION" is literally true, and the stdlib argument for "no
CVE database applies" no longer holds.

**ILLUSTRATIVE, EXPLICITLY-NON-EXHAUSTIVE, as of 2026-07 -- NOT a complete CVE database.** This
module does NOT vendor the OSV/NVD database (that is many hundreds of MB -- a storage-tight,
offline device cannot carry it), and it does NOT call PyPI/OSV/pip-audit over the network by
default (Tenet 2 -- $0/offline). Instead it curates a SMALL, HIGH-CONFIDENCE table of a
handful of genuinely well-known package/version advisories (:data:`KNOWN_VULNERABLE`) and flags
two honest, deterministic signals: (a) a dependency pinned below a known-vulnerable threshold,
and (b) a dependency that is NOT pinned to an exact version at all (its actual installed version
is unknowable at build time, so no security claim -- good or bad -- can honestly be made about
it; the fix is a config hygiene one: pin it). A full audit of a project's real dependency tree
needs an opt-in ``pip-audit``/OSV pass against the LIVE-installed versions -- deliberately NOT
run here (network + potentially large tool install, both against this repo's $0/offline/storage-
light constraints) -- see :func:`pip_audit_available`.

Mirrors the house pattern already established by :mod:`harness.secure_exec` (``scan_code``),
:mod:`harness.code_quality` (``assess_quality``), and :mod:`harness.stdlib_safety`
(``stdlib_safety_findings``): pure functions, never raise, ADVISORY findings only -- this module
adds a check, it never gates a build and never touches ``harness/secure_exec.py``'s existing
egress/subprocess/dynamic-exec/destructive-fs scan.
"""

from __future__ import annotations

import re

# #EXT-037-REQ-17 Start

_REQ_RE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)"          # package name
    r"(?:\[[^\]]*\])?"                  # optional extras, e.g. pkg[extra]
    r"\s*"
    r"(==|>=|<=|~=|!=|>|<)?"            # optional operator (first one only)
    r"\s*"
    r"([A-Za-z0-9_.\-\*]+)?"            # optional version
)


def parse_requirement(line: str) -> "tuple[str, str | None, str | None]":
    """Parse a single requirement-file/import-derived line into ``(name, operator, version)``.

    Handles pinned specs (``flask==2.0.1``), range specs (``requests>=2.0``), a bare name
    (``pyyaml``), extras (``pkg[extra]==1.2``), and a trailing environment marker
    (``pkg==1.2;python_version>"3"`` -- everything after the first ``;`` is stripped, as is
    anything after a ``#`` comment). ``operator``/``version`` are ``None`` when the line has no
    exact-or-ranged version specifier (an unpinned/bare requirement). Never raises -- any
    unparseable/garbage input degrades to ``("", None, None)``."""
    try:
        if not isinstance(line, str):
            return ("", None, None)
        text = line.split(";", 1)[0]
        text = text.split("#", 1)[0]
        text = text.strip()
        if not text:
            return ("", None, None)
        match = _REQ_RE.match(text)
        if not match:
            return (text, None, None)
        name = (match.group(1) or "").strip()
        operator = match.group(2)
        version = match.group(3)
        if not name:
            return ("", None, None)
        if operator and version:
            return (name, operator, version.strip())
        return (name, None, None)
    except Exception:
        return ("", None, None)


def _version_tuple(version: str) -> tuple:
    """Best-effort dotted-version -> comparable int tuple (``"1.2.3"`` -> ``(1, 2, 3)``);
    a non-numeric segment contributes ``0`` rather than raising."""
    parts = []
    for segment in re.split(r"[.\-+]", version or ""):
        digits = re.match(r"\d+", segment)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts) if parts else (0,)


# A SMALL, DATED, EXPLICITLY-NON-EXHAUSTIVE curated table of genuinely well-known
# package-version advisories, as of 2026-07. Each entry names the first version that FIXES
# the issue described (any pinned version strictly below ``below`` is flagged). Kept
# deliberately small -- only entries with a widely-documented public advisory this table's
# author is confident about, never a guess dressed up as a fact.
KNOWN_VULNERABLE: dict = {
    "pyyaml": {
        "below": "5.4",
        "id": "CVE-2020-14343-class",
        "note": ("versions before 5.4 default to a loader (`yaml.load`/`full_load`) that can "
                 "construct arbitrary Python objects from untrusted YAML -- use `safe_load` "
                 "regardless, but pin >=5.4 for the hardened default"),
    },
    "jinja2": {
        "below": "2.11.3",
        "id": "CVE-2020-28493",
        "note": "regex denial-of-service in the `urlize` filter on crafted input; fixed in 2.11.3",
    },
    "flask": {
        "below": "2.3.2",
        "id": "CVE-2023-30861",
        "note": ("session cookie data could be disclosed to a shared/caching proxy under a "
                 "specific configuration; fixed in 2.3.2"),
    },
    "requests": {
        "below": "2.20.0",
        "id": "CVE-2018-18074",
        "note": "leaks the Proxy-Authorization header on a cross-origin HTTPS redirect; fixed in 2.20.0",
    },
    "urllib3": {
        "below": "1.24.2",
        "id": "CVE-2019-11324",
        "note": "improper certificate validation under a specific proxy configuration; fixed in 1.24.2",
    },
    "cryptography": {
        "below": "3.3.2",
        "id": "CVE-2020-36242",
        "note": "a memory-safety issue processing large inputs in the OpenSSL bindings; fixed in 3.3.2",
    },
}


def pip_audit_available() -> bool:
    """Honest placeholder: this module never shells out to `pip-audit`/OSV over the network
    (Tenet 2 -- $0/offline/storage-light). Always returns ``False`` today; a future opt-in,
    explicitly-invoked pass could flip this once such a path is deliberately built and gated
    (not silently added here)."""
    return False


def dependency_security_findings(package_names: "list | None") -> dict:
    """Offline, advisory-only dependency-security signal over a list of requirement strings
    (as returned by ``harness.system_finalize._detect_dependencies``'s ``package_names`` --
    either lines from an existing ``requirements.txt`` or bare detected-import names).

    For each entry: (a) UNPINNED (no exact ``==`` version) -> a ``"warn"``/``"unpinned"``
    finding (its real installed version is unknowable at build time, so no security claim can
    honestly be made either way -- pin it to enable a check); (b) pinned AND matching a
    :data:`KNOWN_VULNERABLE` entry's affected-version predicate -> a ``"warn"``/
    ``"known-advisory"`` finding; (c) otherwise (pinned, not in the small table) -> no finding
    -- this is NOT a clean bill of health, just "nothing in our small table flagged it" (the
    honest ``note`` below says so explicitly). Never raises -- a garbage entry is skipped, not
    fatal to the whole scan."""
    findings: list = []
    try:
        for raw in package_names or []:
            try:
                name, operator, version = parse_requirement(raw)
                if not name:
                    continue
                if operator != "==" or not version:
                    findings.append({
                        "package": name,
                        "severity": "warn",
                        "kind": "unpinned",
                        "message": ("version not verifiable at build time -- pin an exact "
                                    "version (`==`) to enable a security check"),
                    })
                    continue
                entry = KNOWN_VULNERABLE.get(name.lower())
                if not entry:
                    continue
                try:
                    if _version_tuple(version) < _version_tuple(entry["below"]):
                        findings.append({
                            "package": name,
                            "severity": "warn",
                            "kind": "known-advisory",
                            "message": (f"{name} {version} is below the fixed version "
                                        f"{entry['below']} -- {entry['note']} ({entry['id']})"),
                        })
                except Exception:
                    continue
            except Exception:
                continue
    except Exception:
        pass
    return {
        "findings": findings,
        "note": ("Offline, illustrative check only -- a small, high-confidence curated table "
                 "(not a complete CVE database). A full audit of the real installed dependency "
                 "tree requires an opt-in pip-audit/OSV pass, deliberately NOT run by default "
                 "here (network + tool install, against this project's $0/offline/storage-light "
                 "constraints)."),
        "advisory_table_date": "2026-07",
    }

# #EXT-037-REQ-17 End
