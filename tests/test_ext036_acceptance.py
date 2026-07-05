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

TASK-35 (2026-07-04) adds a THIRD derivation tier, tried between the strict retry and the
smoke fallback: a SUBPROCESS-based check that actually spawns the system's own declared
entrypoint (``python main.py ...``) rather than importing the built module in-process.
MEASURED LIVE: the smoke fallback (import + ``hasattr`` only) reported `done=True` for a
`notes-sqlite-cli` build whose `add` command genuinely crashed on a fresh run (it wrote to
a store it never initialized) -- the smoke check never calls any exported function or
drives the module's `__main__` CLI dispatch, so it structurally cannot see this bug class.
(e) proves the new subprocess tier catches that CLASS of bug (a store-writing CLI command
that skips its own required setup) and does not introduce a false negative for the SAME
CLI once fixed; (f) proves the three PRE-EXISTING smoke-fallback tests below are
UNCHANGED -- the canned llm's default (``checklist_subprocess=None`` -> ``"[]"``) makes
the new tier a no-op continuation to the smoke fallback exactly as before this task.

OFFLINE -- no live model. A stub `llm` (same `.complete(LlmRequest) -> .text` convention
as `test_ext036_system_builder.py`'s `_CannedLlm`) returns CANNED responses keyed off
distinctive prompt substrings, including the stricter-retry prompt's "RUNNABLE PYTHON
CODE" marker and (TASK-35) the subprocess-tier prompt's "REAL SUBPROCESS" marker.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    build_system,
    _derive_acceptance_checklist,
    _is_executable_check,
    _is_subprocess_check,
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
    substring since the strict prompt also contains that phrase) / (TASK-35) the THIRD
    subprocess-checklist tier (detected by its distinctive "REAL SUBPROCESS" marker, which
    -- unlike the strict prompt -- does NOT contain "ACCEPTANCE CHECKS", so it never
    inflates the pre-existing tests' `"ACCEPTANCE CHECKS" in prompt` counts) / system
    repair (always unparseable here -- these tests are about DERIVATION, not repair)."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None,
                 checklist_first=None, checklist_strict=None, checklist_subprocess=None) -> None:
        self.plan = plan
        self.module_first = module_first or {"calc.py": "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"}
        self.checklist_first = checklist_first
        self.checklist_strict = checklist_strict
        self.checklist_subprocess = checklist_subprocess
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp(self.checklist_strict if self.checklist_strict is not None else "[]")
        if "REAL SUBPROCESS" in prompt:
            return _Resp(self.checklist_subprocess if self.checklist_subprocess is not None else "[]")
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
    """task #118 (REQ-26): `build_system`'s acceptance checklist is now the DETERMINISTIC
    MINIMUM composed (union) with whatever the model proposes -- an empty checklist is only
    possible when BOTH sides are empty. Monkeypatching both to `[]` proves the pre-existing
    invariant (an empty checklist never vacuously counts as done) still holds under the new
    composition."""
    import harness.system_builder as sb

    llm = _CannedLlm(plan=SIMPLE_PLAN, module_first={"calc.py": CALC_WORKING})
    monkeypatch.setattr(sb, "_derive_acceptance_checklist", lambda spec, mods, llm: [])
    monkeypatch.setattr(sb, "_minimum_acceptance", lambda spec, mods, plan=None: [])
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"] == ["no acceptance checklist derived"]


def test_deterministic_minimum_still_gates_when_model_checklist_is_empty(tmp_path):
    """task #118 (REQ-26): even when the MODEL derives zero usable self-checks (every tier
    unparseable/vague), the DETERMINISTIC MINIMUM (usage/--help + smoke) still gates `done`
    -- proving the minimum is a REAL floor (not a way to make `done` unconditionally False):
    a genuinely working system still passes it."""
    llm = _CannedLlm(plan=SIMPLE_PLAN, module_first={"calc.py": CALC_WORKING},
                      checklist_first="not json at all", checklist_strict="still not json",
                      checklist_subprocess="also not json")
    result = build_system(SPEC, tmp_path / "built_minimum_only", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


# --- (e) TASK-35: a SUBPROCESS-based tier catches a CLI bug the smoke fallback structurally
# cannot -- MEASURED LIVE (2026-07-04): notes-sqlite-cli's `add` command crashed on a fresh
# run (it wrote to a store it never initialized), yet build_system's smoke fallback
# (import + hasattr only, no function ever called, no `__main__` dispatch ever driven)
# reported done=True. This fixture reproduces the SAME bug CLASS generically (a CLI whose
# `add` command writes to a store it never initializes) -- not sqlite-specific. ------------

CLI_SPEC = (
    "A tiny command-line note-adder. Running it as `python main.py add <text...>` "
    "appends <text> to a persistent store and prints `added`."
)

CLI_PLAN = json.dumps({
    "modules": [
        {"name": "main.py",
         "responsibility": "CLI: `python main.py add <text>` appends to a store and prints added",
         "exports": [{"name": "save_item", "signature": "def save_item(path, item):"}],
         "imports": []}
    ],
    "entrypoint": "main.py",
    "acceptance": "add appends and prints added",
})

# BROKEN: `save_item` reads the store before ever creating it -- crashes on a fresh run,
# exactly the notes-sqlite-cli bug class (an `add` branch that skips its own required setup).
ADD_WITHOUT_INIT_CLI = (
    "import json\n"
    "import sys\n\n"
    "def load_store(path):\n"
    "    with open(path) as f:\n"
    "        return json.load(f)\n\n"
    "def save_item(path, item):\n"
    "    data = load_store(path)\n"
    "    data.append(item)\n"
    "    with open(path, 'w') as f:\n"
    "        json.dump(data, f)\n\n"
    "if __name__ == '__main__':\n"
    "    STORE = 'store.json'\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'add':\n"
    "        save_item(STORE, ' '.join(sys.argv[2:]))\n"
    "        print('added')\n"
)

# FIXED: `load_store` tolerates a store that doesn't exist yet.
ADD_WITH_INIT_CLI = (
    "import json\n"
    "import os\n"
    "import sys\n\n"
    "def load_store(path):\n"
    "    if not os.path.exists(path):\n"
    "        return []\n"
    "    with open(path) as f:\n"
    "        return json.load(f)\n\n"
    "def save_item(path, item):\n"
    "    data = load_store(path)\n"
    "    data.append(item)\n"
    "    with open(path, 'w') as f:\n"
    "        json.dump(data, f)\n\n"
    "if __name__ == '__main__':\n"
    "    STORE = 'store.json'\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'add':\n"
    "        save_item(STORE, ' '.join(sys.argv[2:]))\n"
    "        print('added')\n"
)

SUBPROCESS_CHECK_CODE = (
    "import subprocess\n"
    "import sys\n"
    "result = subprocess.run([sys.executable, 'main.py', 'add', 'hello'],\n"
    "                        capture_output=True, text=True)\n"
    "assert result.returncode == 0, result.stderr\n"
    "assert 'added' in result.stdout\n"
)

SUBPROCESS_CHECKLIST_RESPONSE = json.dumps([{"name": "cli add works", "code": SUBPROCESS_CHECK_CODE}])


# --- (unit) _is_subprocess_check ---------------------------------------------------------

def test_is_subprocess_check_requires_a_real_subprocess_call():
    assert _is_subprocess_check(SUBPROCESS_CHECK_CODE) is True
    # an in-process import/call is NOT a subprocess check, even with a real assert --
    # this is exactly the gap TASK-35 closes (an in-process call can bypass a broken
    # `__main__` CLI dispatch a real subprocess invocation would hit)
    assert _is_subprocess_check("from calc import add\nassert add(1, 2) == 3\n") is False
    assert _is_subprocess_check("not python (:") is False                 # unparseable
    assert _is_subprocess_check("import subprocess\nx = 1\n") is False    # no real assert
    assert _is_subprocess_check("") is False
    assert _is_subprocess_check(None) is False


def test_subprocess_tier_invoked_only_after_first_two_tiers_yield_nothing():
    mods = json.loads(CLI_PLAN)["modules"]
    llm = _CannedLlm(
        plan=CLI_PLAN,
        checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST,
        checklist_subprocess=SUBPROCESS_CHECKLIST_RESPONSE,
    )
    checks = _derive_acceptance_checklist(CLI_SPEC, mods, llm)
    assert [c["name"] for c in checks] == ["cli add works"]


def test_subprocess_check_catches_the_add_without_init_bug_class(tmp_path):
    """The MEASURED false-done class (2026-07-04): a CLI whose primary command crashes on
    a fresh run because it writes to a store it never initializes. The smoke fallback
    (import + hasattr only) cannot see this; a subprocess-based check that actually runs
    `python main.py add ...` correctly catches it -- `done` flips to False (closing the
    false-done, Tenet 3)."""
    llm = _CannedLlm(
        plan=CLI_PLAN, module_first={"main.py": ADD_WITHOUT_INIT_CLI},
        checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST,
        checklist_subprocess=SUBPROCESS_CHECKLIST_RESPONSE,
    )
    root = tmp_path / "broken_cli"
    result = build_system(CLI_SPEC, root, llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"]

    # independent control: a genuinely fresh subprocess invocation really does crash --
    # proves this isn't a sandbox artifact, the built system is honestly broken
    proc = subprocess.run([sys.executable, "main.py", "add", "buy", "milk"],
                           cwd=str(root), capture_output=True, text=True)
    assert proc.returncode != 0


def test_subprocess_check_passes_the_fixed_cli_no_new_false_negative(tmp_path):
    """VALUE-PRESERVING: the SAME derivation path reports `done=True` once the CLI
    correctly initializes its store -- the new tier does not introduce a false negative
    for a genuinely-working stateful CLI."""
    llm = _CannedLlm(
        plan=CLI_PLAN, module_first={"main.py": ADD_WITH_INIT_CLI},
        checklist_first=VAGUE_CHECKLIST, checklist_strict=VAGUE_CHECKLIST,
        checklist_subprocess=SUBPROCESS_CHECKLIST_RESPONSE,
    )
    result = build_system(CLI_SPEC, tmp_path / "fixed_cli", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
