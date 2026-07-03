"""EXT-036 TASK-4: productionize the sentence-to-system pipeline (REQ-1/REQ-3/REQ-4).

OFFLINE — no live model. A stub `llm` (any object exposing `.complete(LlmRequest) -> .text`,
the same convention as `harness.repo_memory`'s `_StubLlm`) returns CANNED responses keyed off
distinctive substrings in each stage's prompt (the "build PLAN" planner prompt, the
"COMPLETE Python module `<name>`" per-module build/repair prompts, the "ACCEPTANCE CHECKS"
checklist prompt) — mirroring how the PROVEN probes (`.jaros-data/s2s_build_probe.py`,
`.jaros-data/s2s_doneness_probe.py`) actually call the model, without ever reaching the
Jetson. Live-model end-to-end behavior for this exact pipeline shape is already proven by
those probes; this file proves the *harness wiring* (plan -> build -> assemble -> acceptance)
composes correctly and is honest about failures — a fresh live-model re-measurement of this
exact production module has not been re-run here.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import build_system, syntax_ok, validate_plan

SPEC = "A tiny two-module system: a helper module that adds two numbers, and a CLI that prints the sum."

PLAN_JSON = """{
  "modules": [
    {"name": "helper.py", "responsibility": "define add(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []},
    {"name": "cli.py", "responsibility": "CLI entrypoint that prints the sum",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["helper.py"]}
  ],
  "entrypoint": "cli.py",
  "acceptance": "python cli.py prints 3"
}"""

HELPER_BROKEN = "def add(a, b)\n    return a + b\n"          # missing colon -> SyntaxError
HELPER_FIXED = "def add(a, b):\n    return a + b\n"
CLI_OK = (
    "from helper import add\n\n\n"
    "def main():\n    print(add(1, 2))\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)

CHECKLIST_PASSING = """[
  {"name": "adds correctly", "code": "from helper import add\\nassert add(1, 2) == 3\\n"}
]"""

CHECKLIST_ONE_FAILING = """[
  {"name": "adds correctly", "code": "from helper import add\\nassert add(1, 2) == 3\\n"},
  {"name": "wrong expectation", "code": "from helper import add\\nassert add(1, 2) == 999\\n"}
]"""

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Routes each `.complete()` call to a canned response based on the prompt's stage
    (plan / per-module build / per-module repair / acceptance checklist) — mirrors the
    `.complete(LlmRequest) -> .text` shape every other EXT-036 stub uses."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, module_repair=None,
                 checklist=CHECKLIST_PASSING) -> None:
        self.plan = plan
        self.module_first = module_first or {"helper.py": HELPER_BROKEN, "cli.py": CLI_OK}
        self.module_repair = module_repair or {"helper.py": HELPER_FIXED}
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
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_repair.get(name, ""))
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


# --- validate_plan / syntax_ok (small deterministic-plane units) -----------------------

def test_validate_plan_accepts_coherent_plan():
    import json
    assert validate_plan(json.loads(PLAN_JSON)) == []


def test_validate_plan_flags_unknown_import():
    plan = {"modules": [{"name": "a.py", "exports": [{"name": "f", "signature": "def f():"}],
                          "imports": ["ghost.py"]}],
            "entrypoint": "a.py", "acceptance": "x"}
    defects = validate_plan(plan)
    assert any("unknown" in d for d in defects)


def test_syntax_ok_true_for_valid_false_for_broken():
    assert syntax_ok("def f():\n    return 1\n")[0] is True
    assert syntax_ok("def f(\n    return 1\n")[0] is False


# --- (1) full pipeline: plans -> builds -> assembles -> runs the checklist -------------

def test_full_pipeline_returns_expected_dict(tmp_path):
    root = tmp_path / "built"
    llm = _CannedLlm()
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert set(result["modules"]) == {"helper.py", "cli.py"}
    assert result["plan"]["entrypoint"] == "cli.py"

    # ASSEMBLED onto disk
    assert (root / "helper.py").is_file()
    assert (root / "cli.py").is_file()
    # the acceptance checklist temp artifact never lingers
    assert not (root / "_s2s_acceptance_check.py").exists()


def test_full_pipeline_builds_leaves_first(tmp_path):
    """cli.py imports helper.py -> helper.py must be built (and available as sibling
    context) before cli.py."""
    llm = _CannedLlm()
    build_system(SPEC, tmp_path / "built", llm=llm)
    build_prompts = [p for p in llm.prompts if "COMPLETE Python module" in p and "SYNTAX ERROR" not in p]
    helper_idx = next(i for i, p in enumerate(build_prompts) if "`helper.py`" in p)
    cli_idx = next(i for i, p in enumerate(build_prompts) if "`cli.py`" in p)
    assert helper_idx < cli_idx
    # the CLI build prompt is given helper.py's already-written source as sibling context
    assert "already-written helper.py" in build_prompts[cli_idx]


def test_never_raises_on_unparseable_plan(tmp_path):
    llm = _CannedLlm(plan="not json at all")
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is False
    assert result["done"] is False
    assert "note" in result


def test_never_raises_on_incoherent_plan(tmp_path):
    bad_plan = """{"modules": [{"name": "a.py", "exports": [], "imports": []}],
                    "entrypoint": "ghost.py", "acceptance": "x"}"""
    llm = _CannedLlm(plan=bad_plan)
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is False
    assert result["done"] is False
    assert "coherence" in result["note"]


def test_uses_build_llm_when_llm_is_none(tmp_path, monkeypatch):
    """`llm=None` falls through to `harness.coding_loop.build_llm()` (mirrors the
    `_generate_tests` convention) — verified WITHOUT reaching a real model."""
    llm = _CannedLlm()
    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: llm)
    result = build_system(SPEC, tmp_path / "built", llm=None)
    assert result["shipped"] is True
    assert llm.prompts   # the injected build_llm() stand-in was actually used


# --- (2) syntax-gate + repair path ------------------------------------------------------

def test_syntax_gate_and_repair_path(tmp_path):
    """helper.py's canned FIRST body has a SyntaxError; the canned repair response is
    valid -> the module still ends up compiling and assembled."""
    root = tmp_path / "built"
    llm = _CannedLlm()   # module_first["helper.py"] = HELPER_BROKEN (missing colon)
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True
    assert result["modules"]["helper.py"].strip() == HELPER_FIXED.strip()
    assert syntax_ok(result["modules"]["helper.py"])[0] is True
    # exactly one SYNTAX ERROR repair round-trip happened for helper.py
    repair_prompts = [p for p in llm.prompts if "SYNTAX ERROR" in p and "`helper.py`" in p]
    assert len(repair_prompts) == 1
    # cli.py needed no repair at all (its canned first body is already valid)
    assert not [p for p in llm.prompts if "SYNTAX ERROR" in p and "`cli.py`" in p]


def test_module_still_broken_after_bounded_repair_fails_shipping(tmp_path):
    llm = _CannedLlm(module_first={"helper.py": HELPER_BROKEN, "cli.py": CLI_OK},
                      module_repair={"helper.py": HELPER_BROKEN})   # repair never fixes it
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is False
    assert result["done"] is False
    assert "syntax gate" in result["note"]
    # repair was attempted up to the bound (2), not retried forever
    repair_prompts = [p for p in llm.prompts if "SYNTAX ERROR" in p and "`helper.py`" in p]
    assert len(repair_prompts) == 2


# --- (3) failing acceptance check -> done=False + unmet lists it -----------------------

def test_failing_acceptance_check_marks_not_done(tmp_path):
    root = tmp_path / "built"
    llm = _CannedLlm(checklist=CHECKLIST_ONE_FAILING)
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True   # the system itself built + assembled fine
    assert result["done"] is False     # but an acceptance check genuinely failed
    assert result["unmet"] == ["wrong expectation"]
    assert "adds correctly" not in result["unmet"]


def test_no_acceptance_checklist_derived_is_not_done(tmp_path):
    llm = _CannedLlm(checklist="not a json list")
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"] == ["no acceptance checklist derived"]


# --- CLI wiring (/buildsystem) -----------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Mirrors the other EXT-036 test files: never touch the real .jaros-data/sessions/."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


def test_cli_buildsystem_reports_shipped_done_unmet(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    seen: dict = {}

    def fake_build_system(spec, root, *, llm=None):
        seen["spec"] = spec
        seen["root"] = root
        return {"modules": {"helper.py": "code", "cli.py": "code"},
                "shipped": True, "done": False, "unmet": ["some check"],
                "plan": {"entrypoint": "cli.py"}, "note": "NOT DONE — unmet: some check"}

    monkeypatch.setattr("harness.system_builder.build_system", fake_build_system)
    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny CLI that adds two numbers")
    assert "shipped" in out
    assert "NOT done" in out
    assert "some check" in out
    assert "helper.py" in out and "cli.py" in out
    assert seen["spec"] == "a tiny CLI that adds two numbers"


def test_cli_buildsystem_usage_message_on_empty_arg(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/buildsystem   ")
    assert "usage" in out.lower()


def test_cli_build_command_unaffected_by_buildsystem_addition(tmp_path, monkeypatch):
    """The pre-existing /build (single-function behavioral solve) is untouched — a
    different command from the new /buildsystem."""
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/build")
    assert "usage: /build <func_name> <intent>" in out
