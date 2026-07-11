"""EXT-037 / REQ-17 (TASK-21) -- ``harness.dep_advisory``: offline, illustrative,

ADVISORY-only third-party dependency-security signal (Phase 2, follows the stdlib-only
Phase 1 in ``harness.stdlib_safety`` / REQ-16). Fully offline/deterministic -- no network,
no vendored CVE database.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.dep_advisory import (  # noqa: E402
    KNOWN_VULNERABLE,
    dependency_security_findings,
    parse_requirement,
    pip_audit_available,
)

# #EXT-037-REQ-17 Start


# --- parse_requirement ----------------------------------------------------------------


def test_parse_requirement_pinned_exact():
    assert parse_requirement("flask==2.0.1") == ("flask", "==", "2.0.1")


def test_parse_requirement_bare_name():
    assert parse_requirement("pyyaml") == ("pyyaml", None, None)


def test_parse_requirement_range_specifier_is_not_exact_pin():
    name, operator, version = parse_requirement("requests>=2.0")
    assert name == "requests"
    assert operator == ">="
    assert version == "2.0"


def test_parse_requirement_extras_and_environment_marker():
    name, operator, version = parse_requirement('pkg[extra]==1.2;python_version>"3"')
    assert name == "pkg"
    assert operator == "=="
    assert version == "1.2"


def test_parse_requirement_never_raises_on_junk_input():
    assert parse_requirement("") == ("", None, None)
    assert parse_requirement("   ") == ("", None, None)
    assert parse_requirement(None) == ("", None, None)  # type: ignore[arg-type]
    assert parse_requirement(12345) == ("", None, None)  # type: ignore[arg-type]
    assert parse_requirement("###just a comment") == ("", None, None)
    assert parse_requirement(";;;===") == ("", None, None)


# --- dependency_security_findings ------------------------------------------------------


def test_dependency_security_findings_flags_unpinned_dependency():
    result = dependency_security_findings(["pyyaml"])
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["kind"] == "unpinned"
    assert findings[0]["package"] == "pyyaml"
    assert findings[0]["severity"] == "warn"


def test_dependency_security_findings_flags_known_vulnerable_pinned_version():
    assert "pyyaml" in KNOWN_VULNERABLE
    result = dependency_security_findings(["pyyaml==5.3"])
    findings = result["findings"]
    assert len(findings) == 1
    assert findings[0]["kind"] == "known-advisory"
    assert findings[0]["package"] == "pyyaml"
    assert findings[0]["severity"] == "warn"
    assert "5.3" in findings[0]["message"]


def test_dependency_security_findings_no_finding_for_safe_pinned_version():
    # flask's KNOWN_VULNERABLE threshold is below 2.3.2 -- a version above that is clean.
    result = dependency_security_findings(["flask==2.3.3"])
    assert result["findings"] == []


def test_dependency_security_findings_note_mentions_offline_and_limited_scope():
    result = dependency_security_findings(["flask==2.3.3"])
    note = result["note"].lower()
    assert "offline" in note
    assert ("not a complete" in note) or ("illustrative" in note)
    assert result["advisory_table_date"]


def test_dependency_security_findings_never_raises_on_junk_input():
    result = dependency_security_findings(None)
    assert result["findings"] == []
    result = dependency_security_findings([])
    assert result["findings"] == []
    result = dependency_security_findings([None, 123, "", "   ", "###!!!==="])  # type: ignore[list-item]
    assert isinstance(result["findings"], list)


def test_dependency_security_findings_mixed_list():
    result = dependency_security_findings(["flask==2.3.3", "pyyaml==5.3", "numpy"])
    kinds = sorted((f["package"], f["kind"]) for f in result["findings"])
    assert ("numpy", "unpinned") in kinds
    assert ("pyyaml", "known-advisory") in kinds
    assert not any(pkg == "flask" for pkg, _ in kinds)


def test_pip_audit_available_is_honestly_false_by_default():
    assert pip_audit_available() is False


# #EXT-037-REQ-17 End
