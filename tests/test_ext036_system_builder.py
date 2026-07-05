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
    build_system_best_of_k,
    syntax_ok,
    validate_plan,
    _decompose_requirements,
    _verify_requirement,
    _repair_plan_dangling_imports,
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

# #EXT-037-REQ-7 Start
# --- EXT-037 / REQ-7 fixtures: secure_exec scan-gate + sandboxed acceptance execution ---

# A syntactically valid `helper.py` (same `add` export the plan expects) that ALSO contains
# a dangerous SUBPROCESS/SHELL operation -- the shape `harness.secure_exec.scan_code` must
# classify as a violation and refuse to run.
HELPER_DANGEROUS = (
    "import os\n\n\n"
    "def add(a, b):\n    os.system('echo pwned')\n    return a + b\n"
)

# A checklist whose check code asserts a host secret env var is ABSENT from the acceptance
# subprocess -- passes only when harness.secure_exec's env-scrub is actually live.
CHECKLIST_ENV_SCRUB = """[
  {"name": "env scrubbed", "code": "import os\\nassert os.environ.get('JCODE_TEST_SECRET_TOKEN') is None\\n"}
]"""
# #EXT-037-REQ-7 End

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


# --- TASK-34 (REQ-1): stdlib imports must not be flagged as "unknown" dangling references --

def test_validate_plan_exempts_stdlib_import():
    """MEASURED bug: a module listing a stdlib import (e.g. `sqlite3`) in its `imports` was
    flagged 'imports unknown' because `sqlite3` is not a planned LOCAL module name -> the whole
    plan was rejected as incoherent, blocking any system with a stdlib import in a non-entry
    module (e.g. the notes-sqlite-cli DATASTORE_SLICE task)."""
    plan = {"modules": [
        {"name": "database.py", "responsibility": "sqlite-backed storage",
         "exports": [{"name": "save", "signature": "def save(x):"}], "imports": ["sqlite3"]},
    ], "entrypoint": "database.py", "acceptance": "x"}
    defects = validate_plan(plan)
    assert not any("unknown" in d for d in defects)


def test_validate_plan_exempts_common_stdlib_and_dotted_imports():
    plan = {"modules": [
        {"name": "a.py", "responsibility": "does stuff",
         "exports": [{"name": "f", "signature": "def f():"}],
         "imports": ["os", "json", "datetime", "os.path"]},
    ], "entrypoint": "a.py", "acceptance": "x"}
    defects = validate_plan(plan)
    assert not any("unknown" in d for d in defects)


def test_validate_plan_still_flags_dangling_local_import():
    """VALUE-PRESERVING: a genuinely-missing LOCAL module (neither listed nor stdlib) must
    still be flagged -- the stdlib exemption must not neuter the check's ability to catch a
    real dangling reference."""
    plan = {"modules": [
        {"name": "a.py", "responsibility": "does stuff",
         "exports": [{"name": "f", "signature": "def f():"}], "imports": ["helpers"]},
    ], "entrypoint": "a.py", "acceptance": "x"}
    defects = validate_plan(plan)
    assert any("imports unknown 'helpers'" in d for d in defects)


def test_validate_plan_accepts_valid_local_cross_module_import():
    plan = {"modules": [
        {"name": "b.py", "responsibility": "helper",
         "exports": [{"name": "g", "signature": "def g():"}], "imports": []},
        {"name": "a.py", "responsibility": "uses b",
         "exports": [{"name": "f", "signature": "def f():"}], "imports": ["b.py"]},
    ], "entrypoint": "a.py", "acceptance": "x"}
    defects = validate_plan(plan)
    assert not any("unknown" in d for d in defects)


# --- TASK-36 (REQ-1): deterministic plan-repair for DANGLING LOCAL imports -------------
# MEASURED live (2026-07-04, 6/6 identical draws): the notes-sqlite-cli task's plan
# deterministically lists a local import (e.g. `database`) that was never added as its own
# module -> `validate_plan` correctly rejects the whole plan ("imports unknown 'database'")
# -> 0 modules built -> 0 accept. Deterministic (not model-variance) -> best-of-k can't help
# -> a deterministic plan-repair is the lever, mirroring `_repair_plan_entrypoint` (TASK-19).

DANGLING_LOCAL_IMPORT_PLAN = {
    "modules": [
        {"name": "cli.py", "responsibility": "CLI commands for notes",
         "exports": [{"name": "main", "signature": "def main():"}],
         "imports": ["database", "sqlite3"]},
        {"name": "main.py", "responsibility": "entrypoint dispatch",
         "exports": [{"name": "main", "signature": "def main():"}], "imports": ["cli.py"]},
    ],
    "entrypoint": "main.py",
    "acceptance": "python main.py add buy milk; python main.py list shows buy milk",
}


def test_repair_adds_missing_module_for_dangling_local_import():
    """(1) a module importing an unlisted LOCAL module `database` -> after repair,
    `database.py` is a listed module and validate_plan yields NO 'imports unknown
    database' defect."""
    import copy
    plan = copy.deepcopy(DANGLING_LOCAL_IMPORT_PLAN)
    repaired, note = _repair_plan_dangling_imports(plan)
    names = [m["name"] for m in repaired["modules"]]
    assert "database.py" in names
    assert note is not None and "database.py" in note
    defects = validate_plan(repaired)
    assert not any("unknown 'database'" in d for d in defects)


def test_repair_leaves_stdlib_imports_untouched():
    """(2) a plan importing sqlite3/os (stdlib) is UNCHANGED by the repair -- no bogus
    module added, stdlib stays exempt."""
    plan = {"modules": [
        {"name": "a.py", "responsibility": "does stuff",
         "exports": [{"name": "f", "signature": "def f():"}],
         "imports": ["sqlite3", "os"]},
    ], "entrypoint": "a.py", "acceptance": "x"}
    import copy
    before = copy.deepcopy(plan)
    repaired, note = _repair_plan_dangling_imports(plan)
    assert note is None
    assert repaired == before
    assert len(repaired["modules"]) == 1


def test_repair_is_noop_on_already_coherent_plan():
    """(3) a plan importing a genuinely-listed local module is unchanged (idempotent,
    no-op on coherent plans)."""
    import copy
    plan = json.loads(PLAN_JSON)
    before = copy.deepcopy(plan)
    repaired, note = _repair_plan_dangling_imports(plan)
    assert note is None
    assert repaired == before
    # running it again (idempotent) is still a no-op
    repaired2, note2 = _repair_plan_dangling_imports(repaired)
    assert note2 is None
    assert repaired2 == before


def test_repair_added_module_passes_validate_plan_module_shape():
    """(4) the repaired plan actually passes validate_plan's module-shape checks
    (exports present/well-formed) for the newly-added module."""
    import copy
    plan = copy.deepcopy(DANGLING_LOCAL_IMPORT_PLAN)
    repaired, _ = _repair_plan_dangling_imports(plan)
    added = next(m for m in repaired["modules"] if m["name"] == "database.py")
    assert added["exports"]
    for e in added["exports"]:
        assert "(" in e["signature"] or "class" in e["signature"]
    defects = validate_plan(repaired)
    assert not any("no exports" in d for d in defects)
    assert not any("bad signature" in d for d in defects)
    # entrypoint/DAG/acceptance axes remain coherent too
    assert defects == []


def test_repair_never_raises_on_malformed_plan_shapes():
    assert _repair_plan_dangling_imports(None) == (None, None)
    assert _repair_plan_dangling_imports({}) == ({}, None)
    assert _repair_plan_dangling_imports({"modules": []}) == ({"modules": []}, None)
    assert _repair_plan_dangling_imports({"modules": "nope"}) == ({"modules": "nope"}, None)
    assert _repair_plan_dangling_imports({"modules": [None]}) == ({"modules": [None]}, None)
    plan = {"modules": [{"name": "a.py", "imports": "nope"}]}
    assert _repair_plan_dangling_imports(plan) == (plan, None)


def test_full_pipeline_repairs_dangling_import_and_ships(tmp_path):
    """End-to-end through build_system: without the repair this plan would be REJECTED
    ('imports unknown database') and 0 modules built. With the repair it's coherent and the
    build proceeds to ship all THREE modules (cli.py, main.py, and the newly-added
    database.py)."""
    plan_json = json.dumps(DANGLING_LOCAL_IMPORT_PLAN)
    llm = _CannedLlm(plan=plan_json,
                      module_first={"cli.py": CLI_OK, "main.py": CLI_OK},
                      checklist="[]")
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert "coherence" not in (result.get("note") or "")
    assert set(result["modules"]) == {"cli.py", "main.py", "database.py"}
    assert "database.py" in result["plan_repair"]
    assert (tmp_path / "built" / "database.py").is_file()


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

    def fake_build_system(spec, root, *, llm=None, runtime=None):
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


# --- (5) TASK-27/TASK-28 (REQ-23): build_system_governed -- the GOVERNED build path -----
# MEASURED failure this fixes (`harness/coherence_suite.py`): `build_system` on an
# 11-requirement kvdb-cli SHIPPED but reported `done=True` while silently dropping ONE
# requirement (`incr`), because the code AND its own self-derived acceptance checklist come
# from the SAME prompt and share the same blind spot. `build_system_governed` fixes this with
# an INDEPENDENTLY-decomposed requirement list (a separate model call, made before any code
# exists) as the spec-of-record; `done` is judged ONLY against that list.
#
# TASK-28 hardens this against THREE live-caught defects: (A) gemma may emit the decompose
# list as ONE JSON ARRAY PER LINE rather than one combined array; (B) gemma's `check` must be
# a BLACK-BOX CLI check (argv/stdin/expect) matching the ACTUAL built system's real interface
# (a stdin-driven `python main.py` CLI) -- never an imagined import-and-assert-class API; (C) a
# decompose failure must degrade to `build_system`'s own result, never a hollow 0/0.
#
# The fake llm here mirrors the incr defect at small scale: a single-module calculator CLI
# (`main.py`, reading ONE command per line from stdin: "add A B" / "sub A B" / "mul A B",
# printing the result) whose FIRST build drops the `mul` command -- exactly one of three
# independently-decomposed requirements -- while `build_system`'s own (deliberately narrow)
# acceptance checklist only exercises `add` via an import-based check, so the underlying build
# still ships/dones normally, hiding the drop from anything that isn't independently checking
# every requirement via the REAL CLI interface.

SPEC_GOV = ("A tiny calculator CLI in main.py: reads ONE command per line from stdin -- "
            "'add A B', 'sub A B', or 'mul A B' -- and prints the integer result of each on "
            "its own line.")

# BLACK-BOX (argv/stdin/expect) requirements -- the spec-of-record TASK-28 now decomposes,
# verified against the REAL `python main.py` CLI, never an imagined class API.
GOVERNED_DECOMPOSE_JSON = """[
  {"req_id": "add", "description": "add command prints the sum",
   "argv": [], "stdin": "add 2 3\\n", "expect": "5"},
  {"req_id": "sub", "description": "sub command prints the difference",
   "argv": [], "stdin": "sub 5 3\\n", "expect": "2"},
  {"req_id": "mul", "description": "mul command prints the product",
   "argv": [], "stdin": "mul 3 4\\n", "expect": "12"}
]"""

GOV_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "calculator CLI: add/sub/mul over stdin",
     "exports": [{"name": "add", "signature": "def add(a, b):"},
                 {"name": "sub", "signature": "def sub(a, b):"},
                 {"name": "mul", "signature": "def mul(a, b):"},
                 {"name": "main", "signature": "def main():"}],
     "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "add/sub/mul commands work over stdin"
}"""

# GOVERNED_BUILD_CHECKLIST only ever exercises `add` (via an IMPORT, not the CLI) -- mirroring
# the MEASURED defect where `build_system`'s own narrow self-derived checklist shares the
# blind spot with the code and so does NOT itself catch the dropped `mul` requirement (it
# still ships+dones normally). This is build_system's OWN checklist shape (unchanged by
# TASK-28 -- only the GOVERNED spec-of-record's check shape changed).
GOVERNED_BUILD_CHECKLIST = """[{"name": "adds", "code": "import main\\nassert main.add(1, 2) == 3\\n"}]"""

_CLI_DISPATCH = (
    "def main():\n"
    "    import sys\n"
    "    for line in sys.stdin:\n"
    "        line = line.strip()\n"
    "        if not line:\n"
    "            continue\n"
    "        parts = line.split()\n"
    "        cmd = parts[0]\n"
    "{body}"
    "        else:\n"
    "            print('unknown')\n"
)

# A real stdin-driven CLI missing the `mul` COMMAND (the MEASURED single-requirement drop, at
# small scale) -- `add`/`sub` both dispatch correctly. `mul(a, b)` is still DEFINED (satisfying
# a plain existence/`hasattr` check -- e.g. the REQ-26/task #118 deterministic smoke floor,
# which only knows the plan's declared exports, not real CLI behavior) but never wired into the
# stdin dispatch, so it is genuinely unreachable via the real CLI -- exactly the measured defect
# shape (a dropped DISPATCH branch, not a missing symbol), which build_system's own narrow
# (existence-only) checklist still cannot see, preserving this file's whole "build_system's own
# checklist is fooled" premise even under the new stricter deterministic minimum.
MAIN_MISSING_MUL = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    + _CLI_DISPATCH.format(
        body="        if cmd == 'add':\n            print(add(int(parts[1]), int(parts[2])))\n"
             "        elif cmd == 'sub':\n            print(sub(int(parts[1]), int(parts[2])))\n"
    )
    + "\n\nif __name__ == '__main__':\n    main()\n"
)

# The correctly-repaired CLI: `add`/`sub`/`mul` all dispatch correctly.
MAIN_WITH_MUL = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    + _CLI_DISPATCH.format(
        body="        if cmd == 'add':\n            print(add(int(parts[1]), int(parts[2])))\n"
             "        elif cmd == 'sub':\n            print(sub(int(parts[1]), int(parts[2])))\n"
             "        elif cmd == 'mul':\n            print(mul(int(parts[1]), int(parts[2])))\n"
    )
    + "\n\nif __name__ == '__main__':\n    main()\n"
)

# A "bad" repair: adds the requested `mul` dispatch but silently DROPS the `sub` dispatch --
# the swap-regression shape the non-degrading guard must catch (mirrors TASK-5's dedicated
# regression test). `sub` is still defined as a function (so build_system's own import-based
# checklist, which never calls `sub`, stays fooled) but the CLI no longer routes to it.
MAIN_MUL_DROPS_SUB = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    + _CLI_DISPATCH.format(
        body="        if cmd == 'add':\n            print(add(int(parts[1]), int(parts[2])))\n"
             "        elif cmd == 'mul':\n            print(mul(int(parts[1]), int(parts[2])))\n"
    )
    + "\n\nif __name__ == '__main__':\n    main()\n"
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


def _verified_count(build_result: dict, root, reqs: list) -> int:
    """Test helper: how many BLACK-BOX (argv/stdin/expect) requirements pass against a real
    assembled system, using the SAME `_verify_requirement` oracle `build_system_governed`
    itself uses (reuses `harness.system_suite._run_cli`/`_resolve_entry` under the hood) --
    proving the verification matches the built CLI's REAL interface, not an imagined API."""
    plan = build_result.get("plan")
    return sum(1 for r in reqs if _verify_requirement(root, plan, r)[0])


def test_governed_lift_from_n_minus_1_to_n(tmp_path):
    """THE CORE LIFT TEST: the underlying (ungoverned) build genuinely drops one of three
    independently-decomposed requirements (mirroring the measured `incr`-dropping defect);
    `build_system_governed` LIFTS coherence from (N-1)/N to N/N via its one re-ground repair
    round -- proving the whole point of this task. Verification is BLACK-BOX (argv/stdin/
    expect) against the REAL, actually-built `main.py` stdin CLI -- not an imagined
    import-and-assert-class API."""
    # CONTROL: prove the plain, ungoverned `build_system` really does drop the `mul` command
    # -- only 2 of the 3 independently-decomposed requirements hold against its REAL CLI
    # output, even though `build_system` itself reports shipped=True/done=True (its own
    # narrow import-based checklist never notices the drop).
    plain = build_system(SPEC_GOV, tmp_path / "plain", llm=_GovernedCannedLlm())
    assert plain["shipped"] is True
    assert plain["done"] is True   # build_system's OWN (narrow) checklist is fooled
    reqs = json.loads(GOVERNED_DECOMPOSE_JSON)
    plain_met = _verified_count(plain, tmp_path / "plain", reqs)
    assert plain_met == 2   # add + sub hold, mul is silently missing -- the measured defect

    # GOVERNED: the SAME fake llm, but build_system_governed independently verifies all 3
    # (BLACK-BOX, against the real CLI) and repairs the drop -- reaching full coherence.
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
    # the resulting main.py is a REAL, runnable CLI: re-verify directly via a fresh subprocess.
    assert _verified_count(result, tmp_path / "governed", reqs) == 3


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


# --- (5b) TASK-29 (REQ-23): the explicit outer NO-REGRESS FLOOR ------------------------
# A LIVE measurement (kvdb-cli, 11 requirements) caught `build_system_governed` regressing
# BELOW plain `build_system`'s own single-pass result: its repair loop chased unmet
# requirements and DAMAGED previously-working behavior, ending net WORSE. The fixtures below
# reproduce the SHAPE of that gap at small scale: the underlying build only satisfies `add`
# (baseline met=1/3), and the repair round makes things WORSE, not better -- its fix for `sub`
# regresses the whole system to satisfy NOTHING, and its fix for `mul` is syntactically
# invalid, whose syntax-repair retry then RAISES (a simulated live model/network failure),
# aborting the round mid-way -- BEFORE the round's own end-of-round regression check ever
# runs. Without an explicit, independent RE-VERIFICATION of the final on-disk state, stale
# in-memory bookkeeping could keep reporting the pre-round baseline unmet set unchanged while
# the genuinely-worse (all-broken) system ships on disk -- exactly the live-measured defect.

MAIN_ADD_ONLY = (
    "def add(a, b):\n    return a + b\n\n\n"
    + _CLI_DISPATCH.format(
        body="        if cmd == 'add':\n            print(add(int(parts[1]), int(parts[2])))\n"
    )
    + "\n\nif __name__ == '__main__':\n    main()\n"
)

# The "repair" for `sub`: valid syntax, but regresses the WHOLE system to satisfy NOTHING --
# not even `add`, which worked at baseline (the dispatch never matches any real command).
MAIN_ALL_BROKEN = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def sub(a, b):\n    return a - b\n\n\n"
    "def mul(a, b):\n    return a * b\n\n\n"
    + _CLI_DISPATCH.format(body="        if cmd == 'noop':\n            pass\n")
    + "\n\nif __name__ == '__main__':\n    main()\n"
)

# The "repair" for `mul`: syntactically INVALID (missing colon) -- forces the syntax-repair
# retry loop, which the fake llm below then fails (simulating a live model/network failure).
MUL_FIX_BAD_SYNTAX = "def mul(a, b)\n    return a * b\n"


class _FloorNoRegressLlm:
    """Fake llm for the outer NO-REGRESS FLOOR test. Routes by the same prompt markers as
    `_GovernedCannedLlm`: the INITIAL build (`build_system`'s own pipeline) only satisfies
    `add`; the repair fix for `sub` regresses the system to satisfy NOTHING; the repair fix
    for `mul` is syntactically invalid and its syntax-repair retry RAISES, aborting the round
    via exception before its own end-of-round regression check ever runs."""

    def complete(self, request):
        prompt = request.prompt
        if "GOVERNED-BUILD DECOMPOSE" in prompt:
            return _Resp(GOVERNED_DECOMPOSE_JSON)
        if "build PLAN" in prompt:
            return _Resp(GOV_PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(GOVERNED_BUILD_CHECKLIST)
        if "GOVERNED-BUILD REPAIR" in prompt and "UNMET REQUIREMENT: sub" in prompt:
            return _Resp('{"module": "main.py", "code": %s}' % json.dumps(MAIN_ALL_BROKEN))
        if "GOVERNED-BUILD REPAIR" in prompt and "UNMET REQUIREMENT: mul" in prompt:
            return _Resp('{"module": "main.py", "code": %s}' % json.dumps(MUL_FIX_BAD_SYNTAX))
        if "SYNTAX ERROR" in prompt:
            raise RuntimeError("simulated live model/network failure mid-repair")
        if "COMPLETE Python module" in prompt:
            return _Resp(MAIN_ADD_ONLY)
        return _Resp("")


def test_governed_no_regress_floor_reverts_when_repair_ends_up_worse_than_baseline(tmp_path):
    """THE FLOOR (TASK-29, the point of this task): build_system's own INITIAL output only
    satisfies 1 of 3 independently-decomposed requirements (`add`; `sub`/`mul` unmet). The
    re-ground repair round then makes things WORSE: its fix for `sub` regresses the system to
    satisfy NOTHING (not even `add` any more), and its fix for `mul` is syntactically invalid
    -- the syntax-repair retry then RAISES (simulated live failure), aborting the round via
    exception BEFORE its own end-of-round regression check ever runs. `build_system_governed`
    must NEVER return (or ship on disk) a system worse than build_system's own baseline on the
    governed requirement set -- it must REVERT to the baseline instead."""
    root = tmp_path / "floor"
    llm = _FloorNoRegressLlm()
    result = build_system_governed(SPEC_GOV, root, llm=llm, max_repair=2)

    reqs = json.loads(GOVERNED_DECOMPOSE_JSON)
    # THE FLOOR: never worse than build_system's own initial output on this check set.
    assert result["requirements_met"] == 1            # baseline's `add`-only count, NOT 0
    assert set(result["unmet"]) == {"sub", "mul"}      # the honest baseline unmet set
    assert result["shipped"] is True
    assert result["done"] is False
    assert "no-regress floor" in result["note"]
    # neither the returned dict NOR the actual files on disk are the regressed all-broken
    # main.py -- both must be the BASELINE (build_system's own) content.
    assert result["modules"]["main.py"].strip() == MAIN_ADD_ONLY.strip()
    assert root.joinpath("main.py").read_text().strip() == MAIN_ADD_ONLY.strip()
    # re-verify directly against the real (reverted) CLI -- `add` genuinely works, `sub`/`mul`
    # genuinely don't -- proving the reverted system is REALLY the baseline, not a fabrication.
    assert _verified_count(result, root, reqs) == 1


def test_governed_honesty_never_done_when_repair_budget_exhausted(tmp_path):
    """HONESTY: when the repair never actually fixes the unmet requirement, `done` stays
    False with the unmet requirement honestly listed -- never a false `done=True`."""
    llm = _GovernedCannedLlm(repair_response=MAIN_MISSING_MUL)   # repair changes nothing
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm, max_repair=2)

    assert result["done"] is False
    assert result["unmet"] == ["mul"]
    assert result["requirements_met"] == 2
    assert result["shipped"] is True


def test_governed_floor_falls_back_to_build_system_when_decompose_empty(tmp_path):
    """NO-REGRESS FLOOR (TASK-28, defect C): when decompose yields NOTHING (unparseable/empty
    model output), `build_system_governed` must NEVER regress to a degenerate 0-module/
    0-behavior result when the underlying `build_system` itself genuinely shipped something --
    it falls back to build_system's own shipped/done result, gracefully degrading rather than
    hollowing out."""
    llm = _GovernedCannedLlm(decompose="not a json list at all")
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm)

    assert result["requirements_total"] == 0
    assert "no requirements" in result["note"]
    # THE FLOOR: build_system itself ships this fixture -- governed must carry that through,
    # never falling back to a hollow shipped=False/0-module result.
    assert result["shipped"] is True
    assert result["done"] is True
    assert set(result["modules"]) == {"main.py"}
    assert result["modules"]["main.py"].strip() == MAIN_MISSING_MUL.strip()


def test_governed_never_raises_when_decompose_and_build_both_fail(tmp_path):
    """HONESTY: when decompose yields nothing AND the underlying build_system itself never
    ships (a broken plan), the floor has nothing to fall back to -- an honest shipped=False,
    never a raise, never a fabricated success."""
    llm = _GovernedCannedLlm(decompose="not a json list at all", plan="not a json plan at all")
    result = build_system_governed(SPEC_GOV, tmp_path / "built", llm=llm)

    assert result["shipped"] is False
    assert result["done"] is False
    assert result["requirements_total"] == 0


def test_decompose_requirements_parses_one_array_per_line(tmp_path):
    """PARSE ROBUSTNESS (TASK-28, defect A): live gemma was MEASURED
    (`.jaros-data/diag_decompose.py`) to emit the decompose list as ONE JSON ARRAY PER LINE --
    `[{"req_id":"R1",...}]` then `[{"req_id":"R2",...}]` on separate lines -- not one combined
    array. `_decompose_requirements` must yield ALL N requirements from this shape, not 0/1."""
    one_per_line = "\n".join(
        json.dumps([{"req_id": f"R{i}", "description": f"req {i}",
                     "argv": [], "stdin": f"cmd{i}\n", "expect": f"out{i}"}])
        for i in range(1, 6)
    )

    class _DecomposeOnlyLlm:
        def complete(self, request):
            return _Resp(one_per_line)

    reqs = _decompose_requirements("irrelevant spec", _DecomposeOnlyLlm())
    assert len(reqs) == 5
    assert {r["req_id"] for r in reqs} == {f"R{i}" for i in range(1, 6)}
    assert all(r["expect"] for r in reqs)


def test_decompose_requirements_parses_single_combined_array(tmp_path):
    """BACK-COMPAT: a single COMBINED JSON array (all N objects in one `[...]`) still parses
    correctly -- the robust extractor's fast path."""
    combined = json.dumps([
        {"req_id": "A", "description": "a", "argv": [], "stdin": "x\n", "expect": "1"},
        {"req_id": "B", "description": "b", "argv": [], "stdin": "y\n", "expect": "2"},
        {"req_id": "C", "description": "c", "argv": [], "stdin": "z\n", "expect": "3"},
    ])

    class _DecomposeOnlyLlm:
        def complete(self, request):
            return _Resp(combined)

    reqs = _decompose_requirements("irrelevant spec", _DecomposeOnlyLlm())
    assert len(reqs) == 3
    assert {r["req_id"] for r in reqs} == {"A", "B", "C"}


def test_decompose_requirements_drops_imagined_class_api_check_shape(tmp_path):
    """CHECK-INTERFACE MISMATCH GUARD (TASK-28, defect B): an old-shape decomposed requirement
    carrying an imagined import-and-assert-class `check` (no `argv`/`stdin`/`expect`) is
    correctly DROPPED by the black-box filter -- never silently misinterpreted as a valid
    black-box check."""
    imagined_api = json.dumps([
        {"req_id": "R1", "description": "set works",
         "check": "import main\nstore = main.KeyValueStore()\nstore.set('a', 1)\n"
                  "assert store.get('a') == 1\n"},
    ])

    class _DecomposeOnlyLlm:
        def complete(self, request):
            return _Resp(imagined_api)

    reqs = _decompose_requirements("irrelevant spec", _DecomposeOnlyLlm())
    assert reqs == []


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


# --- TASK-33 (REQ-25): best-of-k build-reliability wrapper -----------------------------
#
# MEASURED (median-of-3 coherence run on `harness/coherence_suite.py::HARD_SLICE`):
# single-pass `build_system` scores median coherence 1.0 (zero dropped requirements) when
# it succeeds, but suffers an occasional TOTAL BUILD FAILURE (~17%: 1/6 builds produced
# nothing runnable). `build_system_best_of_k` masks that failure rate by building the same
# spec up to `k` times and keeping the best-scoring attempt by an INDEPENDENT, freshly-run
# acceptance check. These tests use fake/canned llms only -- no live model, no network.

class _AttemptAwareLlm:
    """Best-of-k fixture: the FIRST `build_system()` invocation this llm serves produces a
    BROKEN system (`helper.py` never compiles, even through every repair attempt, so that
    attempt ships nothing checkable); every SUBSEQUENT invocation produces a fully-correct,
    fully-passing system. Attempt boundaries are tracked by counting 'build PLAN' calls --
    exactly one per `build_system()` invocation, always its first LLM call -- so this single
    stateful object correctly varies its behavior across the multiple `build_system()` calls
    `build_system_best_of_k` makes with it."""

    def __init__(self) -> None:
        self.attempt = -1
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            self.attempt += 1
            return _Resp(PLAN_JSON)
        broken = self.attempt == 0
        if "SYNTAX ERROR" in prompt or "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            if name == "helper.py":
                return _Resp(HELPER_BROKEN if broken else HELPER_FIXED)
            if name == "cli.py":
                return _Resp(CLI_OK)
            return _Resp("")
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(CHECKLIST_PASSING)
        return _Resp("")


class _AlwaysBrokenLlm:
    """Every `build_system()` invocation ships a broken `helper.py` that never compiles,
    even after every repair attempt -- for the ALL-ATTEMPTS-FAIL honesty test."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(PLAN_JSON)
        if "SYNTAX ERROR" in prompt or "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            if name == "helper.py":
                return _Resp(HELPER_BROKEN)
            if name == "cli.py":
                return _Resp(CLI_OK)
            return _Resp("")
        return _Resp("")


def test_best_of_k_masks_a_build_failure(tmp_path):
    """CORE LIFT: attempt 1 is broken/empty (0 checks pass), attempt 2 is fully correct
    (all checks pass) -- best-of-k must return the CORRECT system, proving it raises
    reliability over a single pass."""
    root = tmp_path / "built"
    llm = _AttemptAwareLlm()
    result = build_system_best_of_k(SPEC, root, llm=llm, k=2)

    assert result["done"] is True
    assert result["attempts_run"] == 2
    assert result["best_score"] > 0
    assert set(result["modules"]) == {"helper.py", "cli.py"}
    # the WORKING build actually landed on the caller's root, not a broken one
    assert (root / "helper.py").read_text(encoding="utf-8").strip() == HELPER_FIXED.strip()
    assert (root / "cli.py").is_file()


def test_best_of_k_early_exits_when_first_attempt_passes(tmp_path):
    """EARLY-EXIT: the first attempt already passes every acceptance check, so the
    remaining `k` budget is never spent."""
    root = tmp_path / "built"
    llm = _CannedLlm()   # default fixture already builds+passes fully in one call
    result = build_system_best_of_k(SPEC, root, llm=llm, k=3)

    assert result["done"] is True
    assert result["attempts_run"] == 1


def test_best_of_k_honest_when_every_attempt_fails(tmp_path):
    """ALL-FAIL HONESTY: every attempt fails to build a checkable system -- `done=False`
    with an honest note (never a fabricated pass), and the least-bad attempt is returned
    without raising."""
    root = tmp_path / "built"
    llm = _AlwaysBrokenLlm()
    result = build_system_best_of_k(SPEC, root, llm=llm, k=2)

    assert result["done"] is False
    assert result["shipped"] is False
    assert result["attempts_run"] == 2
    assert result["note"]
    assert "fail" in result["note"].lower()


def test_best_of_k_never_raises_when_llm_itself_raises(tmp_path):
    """NEVER RAISES: an llm that raises on every call degrades to an honest failed result,
    never a traceback."""
    class _RaisingLlm:
        def complete(self, request):
            raise RuntimeError("boom")

    result = build_system_best_of_k(SPEC, tmp_path / "built", llm=_RaisingLlm(), k=2)
    assert result["done"] is False
    assert result["shipped"] is False
    assert result["attempts_run"] == 2


def test_best_of_k_build_system_unaffected(tmp_path):
    """CONFIRM: plain `build_system` is byte-identical/unaffected -- `build_system_best_of_k`
    is a pure additive wrapper around it."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    result = build_system(SPEC, root, llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert set(result["modules"]) == {"helper.py", "cli.py"}


# #EXT-037-REQ-7 Start
# --- EXT-037 (TASK-10) / REQ-7: secure_exec wired into build_system's own acceptance path ---
#
# The live gap (owner-directed, 2026-07-04): `build_system`'s acceptance step ran
# model-generated code as a plain subprocess with the FULL host environment and no static
# scan. These tests prove (a) a SCAN GATE refuses to even RUN a dangerous build, (b) a clean
# build still ships/passes exactly as before now that its acceptance execution is sandboxed,
# and (c) the sandboxed acceptance run genuinely scrubs a host secret env var -- all OFFLINE,
# via the same fake-llm convention as the rest of this file.

def test_security_scan_refuses_dangerous_generated_code(tmp_path):
    """SCAN GATE (REQ-7): a build whose generated module contains a dangerous op
    (`os.system`) is REFUSED before its acceptance ever runs -- `done=False`, an honest
    SECURITY note, a populated `security` report naming the violation category, and the
    acceptance checklist is NEVER derived/executed (proving the dangerous code never ran)."""
    root = tmp_path / "built"
    llm = _CannedLlm(module_first={"helper.py": HELPER_DANGEROUS, "cli.py": CLI_OK})
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True        # assembly (files on disk) is preserved
    assert result["done"] is False
    assert "SECURITY" in result["note"]
    assert result["security"] is not None
    assert result["security"]["ok"] is False
    assert any(v.get("category") == "SUBPROCESS/SHELL" for v in result["security"]["violations"])
    # the acceptance checklist was NEVER derived -- refused BEFORE any execution was attempted
    assert not [p for p in llm.prompts if "ACCEPTANCE CHECKS" in p]
    # the acceptance-check temp artifact was never even written
    assert not (root / "_s2s_acceptance_check.py").exists()
    # the dangerous module WAS still written to disk -- only EXECUTION was withheld
    assert (root / "helper.py").is_file()


def test_clean_build_still_ships_and_passes_via_sandboxed_acceptance(tmp_path):
    """CLEAN BUILD STILL WORKS: a normal fake-llm build with no dangerous operations still
    assembles, RUNS (now via `harness.secure_exec.run_sandboxed` instead of a plain
    subprocess), and passes acceptance -- proving the scan gate + sandbox wiring doesn't
    break a normal build."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert result["security"] is None       # no refusal -- the field stays unset on a clean pass


def test_env_scrub_live_in_build_system_acceptance(tmp_path, monkeypatch):
    """ENV-SCRUB IN THE REAL PATH (REQ-7): a host secret env var is INVISIBLE to the
    sandboxed acceptance-check subprocess -- proving `harness.secure_exec`'s scrubbed
    environment is genuinely LIVE in `build_system`'s own acceptance execution, not just
    the standalone `secure_exec` test suite. Before this task, the acceptance subprocess
    inherited the FULL host environment (a plain `harness.multi_file._run` call), so this
    check would have FAILED (the secret would have been visible)."""
    monkeypatch.setenv("JCODE_TEST_SECRET_TOKEN", "super-secret-value-12345")
    root = tmp_path / "built"
    llm = _CannedLlm(checklist=CHECKLIST_ENV_SCRUB)
    result = build_system(SPEC, root, llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True    # the check asserting the secret is ABSENT actually passed
    assert result["unmet"] == []
# #EXT-037-REQ-7 End
