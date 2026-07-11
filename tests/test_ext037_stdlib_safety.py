"""EXT-037 TASK-20: offline tests for the Phase-1 dependency-security gate (REQ-16) --
deprecated/dangerous stdlib use + EOL interpreter, plus the REQ-66 affordance-hint coupling.

FULLY OFFLINE -- no network, no CVE database, no live model. Mirrors the house pattern of
`tests/test_ext037_secure_exec.py` / `tests/test_ext037_code_quality.py` (each detector proven
on a crafted positive example, clean code proven silent, garbage input proven non-raising).
"""

# #EXT-037-REQ-16 Start
from __future__ import annotations

from harness.stdlib_safety import (
    DANGEROUS_AFFORDANCES,
    DEPRECATED_REMOVED,
    interpreter_eol_warning,
    is_safe_affordance,
    stdlib_safety_findings,
)


# ---------------------------------------------------------------------------
# is_safe_affordance
# ---------------------------------------------------------------------------

def test_is_safe_affordance_false_for_pickle_telnetlib_crypt():
    assert is_safe_affordance("pickle") is False
    assert is_safe_affordance("telnetlib") is False
    assert is_safe_affordance("crypt") is False


def test_is_safe_affordance_false_for_every_deprecated_removed_module():
    for mod in DEPRECATED_REMOVED:
        assert is_safe_affordance(mod) is False, mod


def test_is_safe_affordance_true_for_base64_difflib_hashlib_textwrap():
    assert is_safe_affordance("base64") is True
    assert is_safe_affordance("difflib") is True
    assert is_safe_affordance("hashlib") is True  # the module itself is fine; only md5/sha1 use is flagged
    assert is_safe_affordance("textwrap") is True


def test_dangerous_affordances_is_a_superset_of_deprecated_removed():
    assert set(DEPRECATED_REMOVED).issubset(DANGEROUS_AFFORDANCES)
    for extra in ("pickle", "marshal", "shelve"):
        assert extra in DANGEROUS_AFFORDANCES


# ---------------------------------------------------------------------------
# stdlib_safety_findings -- deprecated-module import
# ---------------------------------------------------------------------------

def test_flags_import_of_deprecated_module():
    findings = stdlib_safety_findings("import telnetlib\n")
    assert any(f["kind"] == "deprecated_module" and f["module"] == "telnetlib" for f in findings)


def test_flags_from_import_of_deprecated_module():
    findings = stdlib_safety_findings("from crypt import crypt\n")
    assert any(f["kind"] == "deprecated_module" and f["module"] == "crypt" for f in findings)


def test_deprecated_module_finding_has_severity_warn():
    findings = stdlib_safety_findings("import cgi\n")
    hit = next(f for f in findings if f["kind"] == "deprecated_module")
    assert hit["severity"] == "warn"
    assert "cgi" in hit["message"]


# ---------------------------------------------------------------------------
# stdlib_safety_findings -- dangerous-use call shapes
# ---------------------------------------------------------------------------

def test_flags_hashlib_md5():
    findings = stdlib_safety_findings("import hashlib\nhashlib.md5(x)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "hashlib.md5" for f in findings)


def test_flags_hashlib_sha1():
    findings = stdlib_safety_findings("import hashlib\nhashlib.sha1(x)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "hashlib.sha1" for f in findings)


def test_flags_subprocess_shell_true():
    findings = stdlib_safety_findings(
        "import subprocess\nsubprocess.run(c, shell=True)\n"
    )
    assert any(
        f["kind"] == "dangerous_use" and f["api"] == "subprocess.run(shell=True)"
        for f in findings
    )


def test_subprocess_without_shell_true_is_not_flagged():
    findings = stdlib_safety_findings("import subprocess\nsubprocess.run(['echo', 'hi'])\n")
    assert not any(f.get("api", "").startswith("subprocess.") for f in findings)


def test_flags_bare_eval():
    findings = stdlib_safety_findings("eval(s)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "eval" for f in findings)


def test_flags_bare_exec():
    findings = stdlib_safety_findings("exec(s)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "exec" for f in findings)


def test_flags_tempfile_mktemp():
    findings = stdlib_safety_findings("import tempfile\ntempfile.mktemp()\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "tempfile.mktemp" for f in findings)


def test_flags_pickle_loads():
    findings = stdlib_safety_findings("import pickle\npickle.loads(b)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "pickle.loads" for f in findings)


def test_flags_pickle_load():
    findings = stdlib_safety_findings("import pickle\nwith open('f','rb') as fh:\n    pickle.load(fh)\n")
    assert any(f["kind"] == "dangerous_use" and f["api"] == "pickle.load" for f in findings)


# ---------------------------------------------------------------------------
# clean / broken code -> []
# ---------------------------------------------------------------------------

def test_clean_code_returns_no_findings():
    clean = (
        "import base64\nimport difflib\n\n"
        "def encode(data: bytes) -> str:\n"
        "    return base64.b64encode(data).decode()\n"
    )
    assert stdlib_safety_findings(clean) == []


def test_syntactically_broken_code_returns_empty_list_never_raises():
    assert stdlib_safety_findings("def broken(:\n    pass\n") == []


def test_garbage_input_never_raises():
    assert stdlib_safety_findings(None) == []  # type: ignore[arg-type]
    assert stdlib_safety_findings(12345) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# interpreter_eol_warning
# ---------------------------------------------------------------------------

def test_eol_warning_for_old_interpreter():
    warning = interpreter_eol_warning((3, 7))
    assert warning is not None
    assert "3.7" in warning


def test_no_warning_for_current_interpreter():
    assert interpreter_eol_warning((3, 12)) is None


def test_no_warning_for_min_supported_exactly():
    assert interpreter_eol_warning((3, 9)) is None


def test_eol_warning_default_uses_running_interpreter():
    # Whatever this test env's interpreter is, calling with no args must never raise, and must
    # agree with an explicit pass-through of sys.version_info.
    import sys
    assert interpreter_eol_warning() == interpreter_eol_warning(sys.version_info)


def test_eol_warning_never_raises_on_garbage():
    assert interpreter_eol_warning("not-a-version") is None  # type: ignore[arg-type]
    assert interpreter_eol_warning((3,)) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# REQ-66 coupling: a spec naming a dangerous/deprecated module gets NO affordance hint
# ---------------------------------------------------------------------------

def test_spec_naming_pickle_yields_no_affordance_hint():
    from harness.system_builder import _spec_affordance_hint, spec_declared_stdlib_affordances

    sentence = "Serialize state -- the `pickle` module is allowed for this."
    # The raw extractor still finds it (pure extraction is unfiltered)...
    assert spec_declared_stdlib_affordances(sentence) == ["pickle"]
    # ...but the rendered hint must never recommend it.
    assert _spec_affordance_hint(sentence) == ""


def test_spec_naming_base64_still_yields_a_hint():
    from harness.system_builder import _spec_affordance_hint

    sentence = "Encode the payload -- the `base64` module is allowed for this."
    hint = _spec_affordance_hint(sentence)
    assert "base64" in hint
    assert hint != ""


def test_spec_naming_both_pickle_and_base64_only_recommends_base64():
    from harness.system_builder import _spec_affordance_hint

    sentence = (
        "The `pickle` module is allowed for serialization, and the `base64` module is "
        "allowed for encoding."
    )
    hint = _spec_affordance_hint(sentence)
    assert "base64" in hint
    assert "pickle" not in hint
# #EXT-037-REQ-16 End
