"""EXT-036 TASK-6: robust executable-acceptance derivation (REQ-2 refinement).

MEASURED (docs/GAP-MAP.md): systems SHIP to several modules but report ``done=False``
because the model's proposed acceptance checklist is weak -- vague/"conceptual" prose
that never asserts anything, or an unparseable/empty checklist ("no acceptance checklist
derived"). This proves the fix is ROBUST without ever letting a broken system pass:
  (a) a vague/"conceptual" check is deterministically FILTERED out, never run as-is;
  (b) an unparseable/all-vague first attempt triggers exactly ONE stricter retry, then a
      deterministic SMOKE fallback when even that yields nothing executable;
  (c) the smoke fallback genuinely PASSES a working system and genuinely FAILS a broken
      one (Tenet 3 -- proves it is a real gate, not a manufactured pass);
  (d) an empty checklist never counts as ``done``.

OFFLINE -- no live model. A stub `llm` (same `.complete(LlmRequest) -> .text` convention
as `test_ext036_system_builder.py`'s `_CannedLlm`) returns CANNED responses keyed off
distinctive prompt substrings, including the new stricter-retry prompt's "RUNNABLE PYTHON
CODE" marker.
"""

from __future__ import annotations

import json
import os
import re

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    build_system,
    _derive_acceptance_checklist,
    _is_executable_check,
    _smoke_checklist,
)

SPEC = "A tiny calculator module with add(a, b), used by a CLI."

# a two-export single-module plan -- enough to exercise the smoke fallback's multi-assert path
PLAN_JSON = """{
  "modules": [
    {"name": "calc.py", "responsibility": "define add(a, b) and sub(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"},
                 {"name": "sub", "signature": "def sub(a, b):"}],
     "imports": []}
  ],
  "entrypoint": "calc.py",
  "acceptance": "add and sub compute correctly"
}"""

# a single-export plan -- used for the working/broken smoke-fallback pass/fail proof
SIMPLE_PLAN = """{
  "modules": [
    {"name": "calc.py", "responsibility": "define add(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []}
  ],
  "entrypoint": "calc.py",
  "acceptance": "add works"
}"""

CALC_WORKING = "def add(a, b):\n    return a + b\n"
# syntactically valid (passes the syntax gate) but raises at IMPORT time -- a genuinely
# broken system, not just a missing attribute
CALC_BROKEN_IMPORT = "def add(a, b):\n    return a + b\n\n\nraise RuntimeError('boom')\n"

VAGUE_CHECKLIST = '[{"name": "conceptual", "code": "the system should add numbers correctly"}]'

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Routes `.complete()` calls by prompt stage: plan / per-module build / the FIRST
    acceptance-checklist prompt / the stricter RETRY prompt (detected by its distinctive
    "RUNNABLE PYTHON CODE" marker, checked BEFORE the generic "ACCEPTANCE CHECKS"
    substring since the strict prompt also contains that phrase) / system repair (always
    unparseable here -- these tests are about DERIVATION, not repair)."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None,
                 checklist_first=None, checklist_strict=None) -> None:
        self.plan = plan
        self.module_first = module_first or {"calc.py": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"}
        self.checklist_first = checklist_first
        self.checklist_strict = checklist_strict
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp(self.checklist_strict if self.checklist_strict is not None else "[]")
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist_first if self.checklist_first is not None else "[]")
        if "SYSTEM ACCEPTANCE REPAIR" in prompt:
            return _Resp("not json at all")   # repair never applies in these derivation tests
        if "SYNTAX ERROR" in prompt:
            return _Resp("")   # unused -- canned module bodies are always valid syntax
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


# --- (unit) _is_executable_check ---------------------------------------------------------

def test_is_executable_check_requires_parseable_python_and_a_real_assert():
    assert _is_executable_check("assert 1 == 1\n") is True
    assert _is_executable_check("from calc import add\nassert add(1, 2) == 3\n") is True
    assert _is_executable_check("this is not python (:") is False           # unparseable
    assert _is_executable_check("x = 1\nprint(x)\n") is False               # parses, no assert
    assert _is_executable_check("# conceptually, addition should work") is False
    assert _is_executable_check("") is False
    assert _is_executable_check(None) is False


# --- (unit) _smoke_checklist ---------------------------------------------------------------

def test_smoke_checklist_empty_when_no_modules():
    assert _smoke_checklist([]) == []


def test_smoke_checklist_asserts_every_export_is_present():
    mods = json.loads(PLAN_JSON)["modules"]
    checks = _smoke_checklist(mods)
    assert len(checks) == 1
    assert checks[0]["name"].startswith("smoke:")
    code = checks[0]["code"]
    assert "import calc" in code
    assert "hasattr(calc, 'add')" in code
    assert "hasattr(calc, 'sub')" in code
    # the smoke check is itself a real executable check (Tenet 3: it must actually run)
    assert _is_executable_check(code) is True


# --- (a) a vague/"conceptual" model check is FILTERED out, never run as-is ---------------

def test_vague_conceptual_check_is_filtered_out():
    mods = json.loads(PLAN_JSON)["modules"]
    llm = _CannedLlm(checklist_first=json.dumps([
        {"name": "conceptual", "code": "the module should add and subtract correctly"},
        {"name": "real assert", "code": "from calc import add\nassert add(1, 2) == 3\n"},
    ]))
    checks = _derive_acceptance_checklist(SPEC, mods, llm)
    assert [c["name"] for c in checks] == ["real assert"]
    # the real check survived on the FIRST attempt -- no stricter retry was needed
    acceptance_prompts = [p for p in llm.prompts if "ACCEPTANCE CHECKS" in p]
    assert len(acceptance_prompts) == 1


# --- (b) unparseable/zero-executable -> ONE stricter retry, then smoke fallback ----------

def test_all_vague_first_attempt_triggers_one_stricter_retry_that_succeeds():
    mods = json.loads(PLAN_JSON)["modules"]
    llm = _CannedLlm(
        checklist_first=VAGUE_CHECKLIST,
        checklist_strict=json.dumps([{"name": "adds", "code": "from calc import add\nassert add(1, 2) == 3\n"}]),
    )
    checks = _derive_acceptance_checklist(SPEC, mods, llm)
    assert [c["name"] for c in checks] == ["adds"]
    acceptance_prompts = [p for p in llm.prompts if "ACCEPTANCE CHECKS" in p]
    assert len(acceptance_prompts) == 2   # exactly one retry, not more
    strict_prompts = [p for p in llm.prompts if "RUNNABLE PYTHON CODE" in p]
    assert len(strict_prompts) == 1


def test_unparseable_first_and_strict_falls_back_to_deterministic_smoke():
    mods = json.loads(PLAN_JSON)["modules"]
    llm = _CannedLlm(checklist_first="not json at all", checklist_strict="still not json")
    checks = _derive_acceptance_checklist(SPEC, mods, llm)
    assert len(checks) == 1
    assert checks[0]["name"].startswith("smoke:")
    assert "hasattr(calc, 'add')" in checks[0]["code"]
    # exactly one retry was attempted before falling back -- not an unbounded loop
    acceptance_prompts = [p for p in llm.prompts if "ACCEPTANCE CHECKS" in p]
    assert len(acceptance_prompts) == 2


def test_all_vague_on_both_attempts_falls_back_to_deterministic_smoke():
    mods = json.loads(PLAN_JSON)["modules"]
    llm = _CannedLlm(checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST)
    checks = _derive_acceptance_checklist(SPEC, mods, llm)
    assert len(checks) == 1
    assert checks[0]["name"].startswith("smoke:")


# --- (c) the smoke fallback genuinely PASSES a working system, genuinely FAILS a broken one --

def test_smoke_fallback_passes_a_working_system(tmp_path):
    llm = _CannedLlm(plan=SIMPLE_PLAN, module_first={"calc.py": CALC_WORKING},
                      checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST)
    result = build_system(SPEC, tmp_path / "working", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


def test_smoke_fallback_fails_a_broken_system_no_false_pass(tmp_path):
    """`calc.py`'s canned body compiles fine (passes the syntax gate) but raises at IMPORT
    time -- a genuinely broken system. The smoke fallback must FAIL for real, proving the
    filter/fallback never manufacture a false pass (Tenet 3)."""
    llm = _CannedLlm(plan=SIMPLE_PLAN, module_first={"calc.py": CALC_BROKEN_IMPORT},
                      checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST)
    result = build_system(SPEC, tmp_path / "broken", llm=llm)
    assert result["shipped"] is True         # built + assembled fine (syntax-gate only)
    assert result["done"] is False           # but the system genuinely does not run
    assert result["unmet"]                   # the smoke check is honestly reported unmet


# --- (d) an empty checklist never counts as done ------------------------------------------

def test_empty_checklist_never_counts_as_done(tmp_path, monkeypatch):
    import harness.system_builder as sb

    llm = _CannedLlm(plan=SIMPLE_PLAN, module_first={"calc.py": CALC_WORKING})
    monkeypatch.setattr(sb, "_derive_acceptance_checklist", lambda spec, mods, llm: [])
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"] == ["no acceptance checklist derived"]
