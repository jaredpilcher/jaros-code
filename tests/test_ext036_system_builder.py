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

import json
import os
import re

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    build_system,
    build_system_governed,
    syntax_ok,
    validate_plan,
    _run_check,
)

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


def test_unparseable_checklist_falls_back_to_smoke_and_still_reaches_done(tmp_path):
    """TASK-6 (REQ-2 refinement): an unparseable model checklist no longer strands a
    genuinely-working system at "no acceptance checklist derived" -- the robust
    derivation retries once, then falls back to a deterministic SMOKE checklist (every
    module imports + exposes its API), which a real working build passes. See
    `tests/test_ext036_acceptance.py` for the dedicated TASK-6 coverage (filtering,
    stricter retry, and the smoke fallback's honest pass/fail on working vs. broken
    systems)."""
    llm = _CannedLlm(checklist="not a json list")
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


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


# --- (4) TASK-25 (REQ-22): web-service builds are HONESTLY HTTP-verified ----------------
# `harness/server_oracle.py` is wired into `build_system`'s acceptance step: a DETECTED
# web service must be gated on a real `serve_and_check` pass, never the stdout/smoke path.
# fastapi + uvicorn are installed in this environment (see tests/test_ext036_server_oracle.py);
# guarded with `pytest.importorskip` per-test so the rest of this file never depends on them.

WEB_SPEC = ("A tiny FastAPI web service in a single module with one GET /health endpoint "
            "that returns JSON {\"status\": \"ok\"}.")

FASTAPI_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "FastAPI service exposing GET /health",
     "exports": [{"name": "app", "signature": "app = FastAPI()"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "GET /health returns {\\"status\\": \\"ok\\"}"
}"""

FASTAPI_MAIN_OK = '''
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}
'''

FASTAPI_MAIN_BROKEN = '''
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "bad"}
'''

HTTP_CHECKLIST_JSON = """[
  {"method": "GET", "path": "/health", "status": 200, "json_contains": {"status": "ok"}}
]"""


class _WebCannedLlm:
    """Same `.complete(LlmRequest) -> .text` convention as `_CannedLlm`, but routes the
    NEW HTTP-endpoint-checklist prompt (REQ-22/TASK-25) too, keyed on its distinctive
    "HTTP ENDPOINT CHECKS" substring (never overlapping the stdout-checklist's
    "ACCEPTANCE CHECKS" keying — the two prompts are never confused)."""

    def __init__(self, *, plan=FASTAPI_PLAN_JSON, module_first=None,
                 http_checklist=HTTP_CHECKLIST_JSON) -> None:
        self.plan = plan
        self.module_first = module_first or {"main.py": FASTAPI_MAIN_OK}
        self.http_checklist = http_checklist
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "HTTP ENDPOINT CHECKS" in prompt:
            return _Resp(self.http_checklist)
        if "SYNTAX ERROR" in prompt or "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


def test_web_service_detected_and_http_verified_done_true(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    llm = _WebCannedLlm()
    result = build_system(WEB_SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True, result["note"]
    assert result["unmet"] == []
    assert "HTTP-verified" in result["note"]
    # the real app was actually assembled onto disk (not a hollow import-only pass)
    assert (tmp_path / "built" / "main.py").is_file()


def test_web_service_broken_endpoint_genuinely_fails_control(tmp_path):
    """CONTROL proving the pass above is REAL: the exact same flow with a BROKEN app
    (the endpoint returns the wrong JSON) must genuinely fail — not a coincidental pass."""
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    llm = _WebCannedLlm(module_first={"main.py": FASTAPI_MAIN_BROKEN})
    result = build_system(WEB_SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True          # the app still builds + imports fine
    assert result["done"] is False            # but the endpoint genuinely returns the wrong body
    assert result["unmet"]
    assert "GET /health" in result["unmet"][0]


def test_web_service_no_derivable_http_checks_is_honest_not_hollow(tmp_path):
    """HONESTY: a detected web service with NO derivable http_checks must NOT hollow-pass
    via the old import-only `_smoke_checklist` — it must report `done=False` with a clear
    "not HTTP-verified" note, even though the app itself builds fine (`shipped=True`)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    llm = _WebCannedLlm(http_checklist="not a json list at all")
    result = build_system(WEB_SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is False
    assert "not HTTP-verified" in result["note"]
    assert any("not HTTP-verified" in u for u in result["unmet"])


def test_non_web_cli_build_regression_unaffected_by_web_wiring(tmp_path):
    """REGRESSION: a normal non-web CLI build (the pre-existing `_CannedLlm` fixture) is
    completely unchanged by the REQ-22 wiring — `detect_web_service` finds nothing in a
    plain helper+CLI system, so it still falls through to the stdout/smoke acceptance path
    exactly as before, with the exact same done/shipped outcome as the original test."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert "HTTP-verified" not in result["note"]
    # none of the HTTP-checklist prompt was ever issued for a non-web system
    assert not [p for p in llm.prompts if "HTTP ENDPOINT CHECKS" in p]


# --- (5) TASK-27 (REQ-23): build_system_governed -- the GOVERNED build path -------------
# MEASURED failure this fixes (`harness/coherence_suite.py`): `build_system` on an
# 11-requirement kvdb-cli SHIPPED but reported `done=True` while silently dropping ONE
# requirement (`incr`), because the code AND its own self-derived acceptance checklist come
# from the SAME prompt and share the same blind spot. `build_system_governed` fixes this with
# an INDEPENDENTLY-decomposed requirement list (a separate model call, made before any code
# exists) as the spec-of-record; `done` is judged ONLY against that list.
#
# The fake llm here mirrors the incr defect at small scale: a single-module calculator plan
# (`main.py` with `add`/`sub`/`mul`) whose FIRST build drops `mul` -- exactly one of three
# independently-decomposed requirements -- while `build_system`'s own (deliberately narrow)
# acceptance checklist only exercises `add`, so the underlying build still ships/dones
# normally, hiding the drop from anything that isn't independently checking every requirement.

SPEC_GOV = ("A tiny calculator module main.py exposing add(a, b), sub(a, b), and mul(a, b), "
            "each returning the correct arithmetic result.")

GOVERNED_DECOMPOSE_JSON = """[
  {"req_id": "add", "description": "add(a,b) returns a+b",
   "check": "import main\\nassert main.add(2, 3) == 5\\n"},
  {"req_id": "sub", "description": "sub(a,b) returns a-b",
   "check": "import main\\nassert main.sub(5, 3) == 2\\n"},
  {"req_id": "mul", "description": "mul(a,b) returns a*b",
   "check": "import main\\nassert main.mul(3, 4) == 12\\n"}
]"""

GOV_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "calculator: add/sub/mul",
     "exports": [{"name": "add", "signature": "def add(a, b):"},
                 {"name": "sub", "signature": "def sub(a, b):"},
                 {"name": "mul", "signature": "def mul(a, b):"}],
     "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "add/sub/mul work"
}"""

# GOVERNED_BUILD_CHECKLIST only ever exercises `add` -- mirroring the MEASURED defect where
# `build_system`'s own narrow self-derived checklist shares the blind spot with the code and
# so does NOT itself catch the dropped `mul` requirement (it still ships+dones normally).
GOVERNED_BUILD_CHECKLIST = """[{"name": "adds", "code": "import main\\nassert main.add(1, 2) == 3\\n"}]"""

MAIN_MISSING_MUL = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "if __name__ == '__main__':\n    pass\n"
)

MAIN_WITH_MUL = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    "if __name__ == '__main__':\n    pass\n"
)

# A "bad" repair: adds the requested `mul` but silently DROPS `sub` -- the swap-regression
# shape the non-degrading guard must catch (mirrors TASK-5's dedicated regression test).
MAIN_MUL_DROPS_SUB = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    "if __name__ == '__main__':\n    pass\n"
)


class _GovernedCannedLlm:
    """Routes each `.complete()` call by the GOVERNED prompt's distinctive marker (the
    decompose call, `build_system`'s own plan/module/checklist prompts, and the governed
    re-ground repair call) -- mirrors `_CannedLlm`'s `.complete(LlmRequest) -> .text`
    convention. `repair_response` may be a plain string (every repair call gets the same
    canned fix) to exercise both a genuinely-fixing repair and a budget-exhausting one."""

    def __init__(self, *, decompose=GOVERNED_DECOMPOSE_JSON, plan=GOV_PLAN_JSON,
                 module_first=MAIN_MISSING_MUL, repair_response=MAIN_WITH_MUL,
                 checklist=GOVERNED_BUILD_CHECKLIST) -> None:
        self.decompose = decompose
        self.plan = plan
        self.module_first = module_first
        self.repair_response = repair_response
        self.checklist = checklist
        self.repair_calls = 0
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "GOVERNED-BUILD DECOMPOSE" in prompt:
            return _Resp(self.decompose)
        if "GOVERNED-BUILD REPAIR" in prompt:
            self.repair_calls += 1
            return _Resp('{"module": "main.py", "code": %s}' % json.dumps(self.repair_response))
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "SYNTAX ERROR" in prompt or "COMPLETE Python module" in prompt:
            return _Resp(self.module_first)
        return _Resp("")


def test_governed_lift_from_n_minus_1_to_n(tmp_path):
    """THE CORE LIFT TEST: the underlying (ungoverned) build genuinely drops one of three
    independently-decomposed requirements (mirroring the measured `incr`-dropping defect);
    `build_system_governed` LIFTS coherence from (N-1)/N to N/N via its one re-ground repair
    round -- proving the whole point of this task."""
    # CONTROL: prove the plain, ungoverned `build_system` really does drop `mul` -- only
    # 2 of the 3 independently-decomposed requirements hold against its output, even though
    # `build_system` itself reports shipped=True/done=True (its own narrow checklist never
    # notices the drop).
    plain = build_system(SPEC_GOV, tmp_path / "plain", llm=_GovernedCannedLlm())
    assert plain["shipped"] is True
    assert plain["done"] is True   # build_system's OWN (narrow) checklist is fooled
    reqs = json.loads(GOVERNED_DECOMPOSE_JSON)
    plain_met = sum(1 for r in reqs if _run_check(tmp_path / "plain", {"code": r["check"]}))
    assert plain_met == 2   # add + sub hold, mul is silently missing -- the measured defect

    # GOVERNED: the SAME fake llm, but build_system_governed independently verifies all 3
    # and repairs the drop -- reaching full coherence.
    llm = _GovernedCannedLlm()
    result = build_system_governed(SPEC_GOV, tmp_path / "governed", llm=llm)
    assert result["shipped"] is True
    assert result["requirements_total"] == 3
    assert result["requirements_met"] == 3
    assert result["done"] is True
    assert result["unmet"] == []
    assert result["rounds"] == 1
    assert llm.repair_calls == 1
    assert (tmp_path / "governed" / "main.py").read_text().strip() == MAIN_WITH_MUL.strip()


def test_governed_repair_regression_is_caught_and_reverted(tmp_path):
    """ANTI-REGRESSION: a repair round that fixes `mul` but silently BREAKS a previously-met
    requirement (`sub`) must be REJECTED -- the met-count never decreases, and `done` reflects
    the true independently-verified state, never a hollow pass."""
    llm = _GovernedCannedLlm(repair_response=MAIN_MUL_DROPS_SUB)
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm, max_repair=2)

    assert result["done"] is False
    assert result["requirements_met"] == 2          # never regresses below the pre-repair 2/3
    assert result["unmet"] == ["mul"]                # still honestly missing mul, not "mul+sub"
    # the regressing round's write was REVERTED -- main.py is back to its pre-round content
    assert (tmp_path / "built" / "main.py").read_text().strip() == MAIN_MISSING_MUL.strip()
    assert result["modules"]["main.py"].strip() == MAIN_MISSING_MUL.strip()


def test_governed_honesty_never_done_when_repair_budget_exhausted(tmp_path):
    """HONESTY: when the repair never actually fixes the unmet requirement, `done` stays
    False with the unmet requirement honestly listed -- never a false `done=True`."""
    llm = _GovernedCannedLlm(repair_response=MAIN_MISSING_MUL)   # repair changes nothing
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm, max_repair=2)

    assert result["done"] is False
    assert result["unmet"] == ["mul"]
    assert result["requirements_met"] == 2
    assert result["shipped"] is True


def test_governed_never_raises_when_no_requirements_decomposed(tmp_path):
    """HONESTY: an unparseable/empty decompose response never fabricates a requirement list
    -- an honest failure, never raises."""
    llm = _GovernedCannedLlm(decompose="not a json list at all")
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm)

    assert result["shipped"] is False
    assert result["done"] is False
    assert result["requirements_total"] == 0
    assert "decompose" in result["note"] or "no requirements" in result["note"]


def test_governed_build_system_itself_is_untouched(tmp_path):
    """CONFIRM: `build_system`'s own existing behavior (the ORIGINAL fixture/spec used
    throughout this file) is byte-identical -- `build_system_governed` is additive only."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    result = build_system(SPEC, root, llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert set(result["modules"]) == {"helper.py", "cli.py"}
