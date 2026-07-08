"""EXT-036 TASK-19: deterministic plan-repair for the MEASURED single-module /
mismatched-entrypoint coherence defect (REQ-1).

MEASURED ROOT CAUSE (`.jaros-data/diag_residuals.py`, 2026-07-03): 4 of 5 creation-suite
residuals fail identically -- gemma's plan lists exactly ONE logic module (e.g.
`calculator.py`) but sets `entrypoint: "main.py"` (the sentence's pinned entrypoint
convention, see TASK-15), and `validate_plan` correctly rejects the plan
("entrypoint not a listed module") -> 0 modules built -> not shipped, even though the
model clearly intends `main.py` as the entrypoint and just named its single module
descriptively.

OFFLINE -- no live model. Follows `tests/test_ext036_system_builder.py`'s `_CannedLlm`
pattern (a stub `llm` exposing `.complete(LlmRequest) -> .text`, routed by distinctive
prompt substrings), no network.
"""

from __future__ import annotations

import os
import re

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import build_system, _repair_plan_entrypoint, validate_plan

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Minimal canned llm mirroring `_CannedLlm` in `test_ext036_system_builder.py`: routes
    on the plan / per-module build / checklist prompt stage. Module bodies + checklist are
    keyed by whatever name the (possibly plan-repaired) sole module ends up with."""

    def __init__(self, *, plan: str, module_code: str = "", checklist: str = "[]") -> None:
        self.plan = plan
        self.module_code = module_code
        self.checklist = checklist
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "SYNTAX ERROR" in prompt:
            return _Resp(self.module_code)
        if "COMPLETE Python module" in prompt:
            return _Resp(self.module_code)
        return _Resp("")


SPEC = "A tiny one-file CLI that prints 'hi'."

# A single logic-named module, entrypoint pinned to main.py -- NOT among the module names.
SINGLE_MODULE_MISMATCHED_PLAN = """{
  "modules": [
    {"name": "calculator.py", "responsibility": "prints hi",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py prints hi"
}"""

# entrypoint already matches the sole module -- nothing to repair.
SINGLE_MODULE_COHERENT_PLAN = """{
  "modules": [
    {"name": "main.py", "responsibility": "prints hi",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py prints hi"
}"""

# two modules, neither is the stated entrypoint -- ambiguous, must NOT be silently repaired.
MULTI_MODULE_MISMATCHED_PLAN = """{
  "modules": [
    {"name": "calculator.py", "responsibility": "does math",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []},
    {"name": "cli.py", "responsibility": "CLI wrapper",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["calculator.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py prints hi"
}"""

RUNNABLE_MODULE = (
    "def main():\n    print('hi')\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)


# --- (a) _repair_plan_entrypoint unit behavior ------------------------------------------

def test_repair_renames_sole_mismatched_module_to_entrypoint():
    import json
    plan = json.loads(SINGLE_MODULE_MISMATCHED_PLAN)
    repaired, note = _repair_plan_entrypoint(plan)
    assert repaired["modules"][0]["name"] == "main.py"
    assert repaired["entrypoint"] == "main.py"
    assert note == "plan-repair: renamed sole module calculator.py -> main.py"
    # coherent after repair
    assert validate_plan(repaired) == []


def test_repair_is_noop_when_entrypoint_already_listed():
    import json
    plan = json.loads(SINGLE_MODULE_COHERENT_PLAN)
    before = json.loads(SINGLE_MODULE_COHERENT_PLAN)
    repaired, note = _repair_plan_entrypoint(plan)
    assert note is None
    assert repaired == before


def test_repair_does_not_touch_multi_module_mismatched_plan():
    import json
    plan = json.loads(MULTI_MODULE_MISMATCHED_PLAN)
    before = json.loads(MULTI_MODULE_MISMATCHED_PLAN)
    repaired, note = _repair_plan_entrypoint(plan)
    assert note is None
    assert repaired == before
    # still incoherent -- validate_plan must still catch it (no regression, no silent guess)
    defects = validate_plan(repaired)
    assert any("entrypoint" in d for d in defects)


def test_repair_never_raises_on_malformed_plan_shapes():
    assert _repair_plan_entrypoint(None) == (None, None)
    assert _repair_plan_entrypoint({}) == ({}, None)
    assert _repair_plan_entrypoint({"modules": [], "entrypoint": "main.py"}) == (
        {"modules": [], "entrypoint": "main.py"}, None)
    assert _repair_plan_entrypoint({"modules": "not a list", "entrypoint": "main.py"}) == (
        {"modules": "not a list", "entrypoint": "main.py"}, None)
    assert _repair_plan_entrypoint({"modules": [None], "entrypoint": "main.py"}) == (
        {"modules": [None], "entrypoint": "main.py"}, None)
    # entrypoint not a string
    plan = {"modules": [{"name": "a.py"}], "entrypoint": 5}
    assert _repair_plan_entrypoint(plan) == (plan, None)
    # entrypoint empty string
    plan2 = {"modules": [{"name": "a.py"}], "entrypoint": ""}
    assert _repair_plan_entrypoint(plan2) == (plan2, None)
    # module with no name at all -- nothing safe to rename
    plan3 = {"modules": [{"exports": []}], "entrypoint": "main.py"}
    assert _repair_plan_entrypoint(plan3) == (plan3, None)


# --- (b)/(c)/(d) end-to-end through build_system ------------------------------------------

def test_single_module_mismatched_entrypoint_builds_and_ships(tmp_path):
    """The MEASURED defect: without the repair this plan would be rejected with
    'entrypoint not a listed module' and 0 modules built. With the repair it's coherent and
    the build proceeds to ship."""
    llm = _CannedLlm(plan=SINGLE_MODULE_MISMATCHED_PLAN, module_code=RUNNABLE_MODULE,
                      checklist="[]")
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert "coherence" not in (result.get("note") or "")
    assert set(result["modules"]) == {"main.py"}
    assert result["plan"]["entrypoint"] == "main.py"
    assert result["plan_repair"] == "plan-repair: renamed sole module calculator.py -> main.py"
    assert (tmp_path / "built" / "main.py").is_file()


def test_already_coherent_plan_is_unchanged(tmp_path):
    llm = _CannedLlm(plan=SINGLE_MODULE_COHERENT_PLAN, module_code=RUNNABLE_MODULE,
                      checklist="[]")
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["plan_repair"] == ""
    assert set(result["modules"]) == {"main.py"}


def test_multi_module_wired_dag_mismatched_entrypoint_now_builds(tmp_path):
    """TASK-47 generalization (MEASURED 2026-07-07 on todo-list-cli): the wired-DAG multi-
    module shape (cli.py imports calculator.py, entrypoint main.py) is NO LONGER rejected.
    The multi-module entrypoint repair now ADDS main.py importing the ROOT module (cli.py),
    so the plan is coherent and the build proceeds to ship -- the exact fix for the
    todo-list build that was writing 0 files."""
    llm = _CannedLlm(plan=MULTI_MODULE_MISMATCHED_PLAN, module_code=RUNNABLE_MODULE,
                      checklist="[]")
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert "coherence" not in (result.get("note") or "")
    assert result["plan_repair"] == (
        "plan-repair: added missing entrypoint module main.py importing roots ['cli.py']")
    assert set(result["modules"]) == {"calculator.py", "cli.py", "main.py"}
    assert (tmp_path / "built" / "main.py").is_file()


def test_build_system_never_raises_with_edge_case_plans(tmp_path):
    for plan_json in (
        "not json at all",
        '{"modules": [], "entrypoint": "main.py", "acceptance": "x"}',
        '{"modules": [{"name": "a.py", "exports": [{"name": "f", "signature": "def f():"}]}], '
        '"entrypoint": 5, "acceptance": "x"}',
    ):
        llm = _CannedLlm(plan=plan_json, module_code=RUNNABLE_MODULE, checklist="[]")
        result = build_system(SPEC, tmp_path / f"built_{hash(plan_json) & 0xffff}", llm=llm)
        assert isinstance(result, dict)
        assert "shipped" in result and "done" in result and "plan_repair" in result
