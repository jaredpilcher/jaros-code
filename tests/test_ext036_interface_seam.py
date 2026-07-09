"""EXT-036 REQ-41: interface ledger + AST seam check — the top generic mechanism for the
MEASURED compositional/seam-wiring failure. `_build_module` (REQ-3) already scopes FULL
SOURCE injection to a module's DIRECT imports only; this task adds (1) a compact,
signature-only LEDGER of the WHOLE module DAG injected into EVERY `_build_module` call so
the small model always sees every sibling's exact call shape (not just its direct deps'),
and (2) a deterministic, POST-ASSEMBLE AST seam check that catches a cross-module call
whose ARITY doesn't match the callee's real definition and feeds it into the existing
`_repair_system` loop as a genuinely DYNAMIC (re-verified on each run, not a static
always-fail marker) unmet check.

OFFLINE — no live model. A stub `llm` (canned `.complete(LlmRequest) -> .text`) mirrors the
convention used across `tests/test_ext036_*.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    _build_interface_ledger,
    _build_module,
    _module_import_aliases,
    _module_top_level_defs,
    _seam_check_code,
    build_system,
    check_interface_seams,
)

# #EXT-036-REQ-41 Start


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _RecordingLlm:
    """A trivial stub that always returns the same canned body and records every prompt
    it was called with — used for the `_build_module` ledger/deps unit tests below."""

    def __init__(self, response: str = "def f():\n    pass\n") -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp(self.response)


# --- (1) interface ledger: assembly correctness --------------------------------------

def test_ledger_contains_every_module_and_its_export_signatures():
    plan = {
        "modules": [
            {"name": "db.py", "responsibility": "stores notes",
             "exports": [{"name": "add", "signature": "def add(title, done):"}]},
            {"name": "helper.py", "responsibility": "unrelated helper",
             "exports": [{"name": "helper", "signature": "def helper():"}]},
            {"name": "main.py", "responsibility": "cli entrypoint",
             "exports": [{"name": "main", "signature": "def main():"}]},
        ],
    }
    ledger = _build_interface_ledger(plan)
    assert "db.py" in ledger
    assert "def add(title, done):" in ledger
    assert "helper.py" in ledger
    assert "def helper():" in ledger
    assert "main.py" in ledger
    assert "def main():" in ledger


def test_ledger_degrades_gracefully_on_missing_or_malformed_plan():
    assert _build_interface_ledger(None) == ""
    assert _build_interface_ledger({}) == ""
    assert _build_interface_ledger({"modules": []}) == ""
    assert _build_interface_ledger({"modules": [{"exports": []}]}) == ""  # no name -> skipped
    assert _build_interface_ledger("not a dict") == ""
    assert _build_interface_ledger({"modules": "not a list"}) == ""


def test_ledger_handles_modules_with_no_exports_without_crashing():
    plan = {"modules": [{"name": "empty.py", "responsibility": "nothing yet", "exports": []}]}
    ledger = _build_interface_ledger(plan)
    assert "empty.py" in ledger
    assert "no declared exports" in ledger


# --- (2) _build_module wiring: ledger + FULL SOURCE scoped to DIRECT imports only -----

def test_build_module_prompt_carries_whole_ledger_but_full_source_only_for_direct_imports():
    plan = {
        "modules": [
            {"name": "db.py", "responsibility": "stores notes",
             "exports": [{"name": "add", "signature": "def add(title, done):"}], "imports": []},
            {"name": "unrelated.py", "responsibility": "not imported by main",
             "exports": [{"name": "helper", "signature": "def helper():"}], "imports": []},
            {"name": "main.py", "responsibility": "cli entrypoint",
             "exports": [{"name": "main", "signature": "def main():"}], "imports": ["db.py"]},
        ],
    }
    main_module = plan["modules"][2]
    built = {
        "db.py": "def add(title, done):\n    return True\n",
        "unrelated.py": "def helper():\n    return 1\n",
    }
    llm = _RecordingLlm()
    _build_module("spec text", main_module, built, llm, plan=plan)

    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    # the WHOLE ledger (every module's signature, including a module main.py never imports)
    assert "def add(title, done):" in prompt
    assert "def helper():" in prompt
    assert "unrelated.py" in prompt
    # FULL SOURCE is still reserved for DIRECT imports only (db.py), never a non-imported sibling
    assert "already-written db.py" in prompt
    assert "already-written unrelated.py" not in prompt


def test_build_module_plan_none_degrades_byte_identically():
    """A module with no plan (every pre-existing caller) never gets a ledger — behavior
    unchanged from before this task."""
    m = {"name": "solo.py", "responsibility": "x",
         "exports": [{"name": "f", "signature": "def f():"}], "imports": []}
    llm = _RecordingLlm()
    code, ok = _build_module("spec", m, {}, llm)
    assert ok is True
    assert "SYSTEM INTERFACE LEDGER" not in llm.prompts[0]


def test_build_module_module_with_no_plan_exports_never_crashes():
    """Preserve current behavior when a module has no plan/exports -- degrade gracefully."""
    m = {"name": "solo.py"}
    llm = _RecordingLlm()
    code, ok = _build_module("spec", m, {}, llm, plan={"modules": []})
    assert ok is True


# --- (3) check_interface_seams: the AST post-assembly seam check ---------------------

DB_ADD_TWO_ARGS = "def add(title, done):\n    return True\n"


def test_seam_check_catches_arity_mismatch_with_concrete_message():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.add('t')\n",
        "db.py": DB_ADD_TWO_ARGS,
    }
    findings = check_interface_seams(built)
    assert len(findings) == 1
    f = findings[0]
    assert f["caller"] == "main.py"
    assert f["callee"] == "db.py"
    assert f["alias"] == "db"
    assert f["method"] == "add"
    assert f["n_args"] == 1
    assert f["min_args"] == 2
    assert "main.py calls db.add(...)" in f["message"]
    assert "db.py defines add(...)" in f["message"]
    assert "requiring 2 arg" in f["message"]


def test_seam_check_no_finding_for_correct_arity():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.add('t', False)\n",
        "db.py": DB_ADD_TWO_ARGS,
    }
    assert check_interface_seams(built) == []


def test_seam_check_flags_too_many_args_too():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.add('t', False, 'extra')\n",
        "db.py": DB_ADD_TWO_ARGS,
    }
    findings = check_interface_seams(built)
    assert len(findings) == 1
    assert findings[0]["n_args"] == 3
    assert findings[0]["max_args"] == 2


def test_seam_check_respects_defaults_and_varargs():
    built = {
        "main.py": (
            "import db\n\n\n"
            "def run():\n"
            "    db.add('t')\n"          # ok: `done` has a default
            "    db.log('a', 'b', 'c')\n"  # ok: *args is unbounded
        ),
        "db.py": (
            "def add(title, done=False):\n    return True\n\n"
            "def log(*parts):\n    return parts\n"
        ),
    }
    assert check_interface_seams(built) == []


def test_seam_check_arity_against_class_constructor():
    built = {
        "main.py": "import store\n\n\ndef run():\n    store.Store('a')\n",
        "store.py": "class Store:\n    def __init__(self, a, b):\n        pass\n",
    }
    findings = check_interface_seams(built)
    assert len(findings) == 1
    assert findings[0]["method"] == "Store"
    assert findings[0]["min_args"] == 2  # self excluded


# --- (4) conservative: never a false positive -----------------------------------------

def test_seam_check_ignores_same_module_calls():
    built = {
        "main.py": "def helper(a):\n    return a\n\n\ndef run():\n    helper(1, 2, 3)\n",
    }
    assert check_interface_seams(built) == []


def test_seam_check_ignores_stdlib_calls():
    built = {
        "main.py": "import json\n\n\ndef run():\n    json.dumps()\n",
    }
    assert check_interface_seams(built) == []


def test_seam_check_ignores_keyword_and_starred_calls():
    built = {
        "main.py": (
            "import db\n\n\n"
            "def run():\n"
            "    db.add(title='t')\n"
            "    args = ('t',)\n"
            "    db.add(*args)\n"
        ),
        "db.py": DB_ADD_TWO_ARGS,
    }
    assert check_interface_seams(built) == []


def test_seam_check_skips_dynamic_target_module_wildcard_import():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.add('t')\n",
        "db.py": "from utils import *\n\n\ndef add(title, done):\n    return True\n",
    }
    assert check_interface_seams(built) == []


def test_seam_check_skips_dynamic_target_module_getattr():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.add('t')\n",
        "db.py": "def add(title, done):\n    return True\n\n\ndef __getattr__(name):\n    return None\n",
    }
    assert check_interface_seams(built) == []


def test_seam_check_skips_call_to_unresolved_symbol_no_name_mismatch_flag():
    """A method that genuinely doesn't exist on the target is NOT flagged by this check
    (arity-only, conservative by design) -- it surfaces as a real runtime failure elsewhere."""
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.remove('t')\n",
        "db.py": DB_ADD_TWO_ARGS,
    }
    assert check_interface_seams(built) == []


def test_seam_check_skips_plain_value_target():
    built = {
        "main.py": "import db\n\n\ndef run():\n    db.CONFIG('t')\n",
        "db.py": "CONFIG = object()\n",
    }
    assert check_interface_seams(built) == []


def test_seam_check_never_raises_on_bad_input():
    assert check_interface_seams(None) == []
    assert check_interface_seams({}) == []
    assert check_interface_seams({"main.py": "def ("}) == []
    assert check_interface_seams({"main.py": 12345}) == []


# --- (5) `_module_top_level_defs` / `_module_import_aliases` unit coverage ------------

def test_module_top_level_defs_parses_functions_and_classes():
    table = _module_top_level_defs("def f(a, b=1):\n    pass\n\nclass C:\n    def __init__(self, x):\n        pass\n")
    assert table["f"] == {"kind": "function", "min_args": 1, "max_args": 2}
    assert table["C"] == {"kind": "class", "min_args": 1, "max_args": 1}


def test_module_top_level_defs_returns_none_on_syntax_error():
    assert _module_top_level_defs("def (") is None


def test_module_import_aliases_only_captures_plain_import():
    code = "import db\nimport other as o\nfrom third import X\n"
    aliases = _module_import_aliases(code, {"db", "other", "third"})
    assert aliases == {"db": "db", "o": "other"}


# --- (6) the seam check is a GENUINELY DYNAMIC re-check, not a static failure marker --

def test_seam_check_code_is_dynamic_fails_then_passes_after_a_real_fix(tmp_path):
    caller_code = "import db\n\n\ndef run():\n    db.add('t')\n\n\nif __name__ == '__main__':\n    run()\n"
    callee_bad = "def add(title, done):\n    return True\n"
    (tmp_path / "main.py").write_text(caller_code, encoding="utf-8")
    (tmp_path / "db.py").write_text(callee_bad, encoding="utf-8")

    findings = check_interface_seams({"main.py": caller_code, "db.py": callee_bad})
    assert len(findings) == 1
    script = _seam_check_code(findings[0])
    chk = tmp_path / "_chk.py"
    chk.write_text(script, encoding="utf-8")

    proc = subprocess.run([sys.executable, "_chk.py"], cwd=str(tmp_path),
                           capture_output=True, text=True, timeout=20)
    assert proc.returncode != 0, "seam check must genuinely FAIL while the mismatch stands"

    # a real repair: widen db.add's arity so the SAME call site now resolves
    callee_fixed = "def add(title, done=False):\n    return True\n"
    (tmp_path / "db.py").write_text(callee_fixed, encoding="utf-8")

    proc2 = subprocess.run([sys.executable, "_chk.py"], cwd=str(tmp_path),
                            capture_output=True, text=True, timeout=20)
    assert proc2.returncode == 0, "seam check must genuinely PASS once the mismatch is fixed"


# --- (7) end-to-end: build_system feeds a seam finding into `unmet`/the repair loop ----

_LEDGER_SPEC = "A tiny two-module program with a data module and a caller module."

_LEDGER_PLAN_JSON = """{
  "modules": [
    {"name": "db.py", "responsibility": "stores data",
     "exports": [{"name": "add", "signature": "def add(title, done):"}], "imports": []},
    {"name": "main.py", "responsibility": "caller entrypoint",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["db.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "runs without crashing"
}"""

_LEDGER_DB_CODE = "def add(title, done):\n    return True\n"
_LEDGER_MAIN_BUG = (
    "import db\n\n\n"
    "def main():\n    db.add('t')\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)
_LEDGER_MAIN_FIXED = (
    "import db\n\n\n"
    "def main():\n    db.add('t', False)\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)


class _SeamCannedLlm:
    """Routes each `.complete()` call by prompt-stage substring, mirroring
    `test_ext036_system_builder.py`'s `_CannedLlm` — the PLAN + `db.py` are always
    coherent; `main.py`'s FIRST draft has the arity bug; the repair-stage prompt
    ("SYSTEM ACCEPTANCE REPAIR") returns a genuinely-fixed `main.py`."""

    def __init__(self, main_first: str = _LEDGER_MAIN_BUG) -> None:
        self.main_first = main_first
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(_LEDGER_PLAN_JSON)
        if "SYSTEM ACCEPTANCE REPAIR" in prompt:
            return _Resp(json.dumps({"module": "main.py", "code": _LEDGER_MAIN_FIXED}))
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        if "SYNTAX ERROR" in prompt:
            return _Resp(self.main_first)
        if "COMPLETE Python module" in prompt:
            if "`db.py`" in prompt:
                return _Resp(_LEDGER_DB_CODE)
            if "`main.py`" in prompt:
                return _Resp(self.main_first)
        return _Resp("[]")


def test_build_system_seam_mismatch_enters_unmet_and_repair_fixes_it(tmp_path):
    llm = _SeamCannedLlm(main_first=_LEDGER_MAIN_BUG)
    result = build_system(_LEDGER_SPEC, tmp_path / "built", llm=llm)

    # A seam finding must have been fed into the checklist and shown up as unmet at some
    # point in this build (recorded via `repairs`, or -- if the repair converged -- via a
    # genuinely-fixed final module). Re-derive it directly from what the FIRST draft would
    # have produced, to assert the concrete diagnostic shape independent of repair timing.
    from harness.system_builder import check_interface_seams as _cis
    first_draft_findings = _cis({"db.py": _LEDGER_DB_CODE, "main.py": _LEDGER_MAIN_BUG})
    assert len(first_draft_findings) == 1
    assert first_draft_findings[0]["message"].startswith(
        "main.py calls db.add(...) [1 arg] but db.py defines add(...) requiring 2 arg")

    # The repair loop (fed the seam finding as an unmet item) should have driven the
    # build to DONE -- the SAME canned fix resolves the seam AND the minimum no-crash
    # check the arity bug also broke.
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert any(r.get("module") == "main.py" and r.get("applied") for r in result["repairs"])


def test_build_system_correct_arity_never_flagged(tmp_path):
    llm = _SeamCannedLlm(main_first=_LEDGER_MAIN_FIXED)
    result = build_system(_LEDGER_SPEC, tmp_path / "built", llm=llm)
    assert not any(str(u).startswith("seam:") for u in result["unmet"])
    assert result["repairs"] == []
# #EXT-036-REQ-41 End
