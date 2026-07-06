"""EXT-036 TASK-44: iterative REPLAN-AS-MODIFICATION build recovery (REQ-34, owner idea,
roadmap 57e8341).

When `_repair_system`'s targeted per-check patch still leaves a build NOT DONE,
`build_system(..., replan_on_failure=True)` steps back and treats the remaining gap as a
MODIFICATION: it describes where the system actually landed vs the spec's target, applies the
fix via the existing MODIFICATION plane (`modify_system`), re-checks the FULL acceptance
checklist, and iterates up to `MAX_REPLAN_ROUNDS` times -- convergence-gated exactly like
`_repair_system`'s non-degrading floor (made STRICTER: only a STRICT reduction in the unmet
COUNT with no regression to any previously-passing check is accepted).

OFFLINE -- no live model. A canned `llm` (same `.complete(LlmRequest) -> .text` convention as
`test_ext036_system_repair.py`) drives the full `build_system` pipeline for the end-to-end
proof; the convergence-gate/boundedness/regression properties of `_replan_as_modification`
itself are proven directly with a stubbed `modify_system` (monkeypatched), exactly as the task
brief allows ("a canned modify_system ... that returns modules fixing them").
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.system_builder as system_builder
from harness.system_builder import build_system


def _bust_cache(root) -> None:
    """Test-only mitigation for a PRE-EXISTING artifact of the acceptance-check runner: each
    check runs in a FRESH subprocess (`_run_acceptance_cmd`), so rapid successive rewrites of
    the SAME module filename with no real delay between them (offline canned-llm rounds, no
    model latency) can land within the same wall-clock second -- CPython's timestamp-based
    `.pyc` cache then serves STALE bytecode to a later subprocess (reproducible with a bare
    write/import/rewrite/import script; unrelated to REQ-34's own convergence logic, and
    negligible in live use where real model latency separates rounds by seconds). Clearing
    `__pycache__` after a rewrite forces the next subprocess to compile the CURRENT source."""
    shutil.rmtree(Path(root) / "__pycache__", ignore_errors=True)


@pytest.fixture(autouse=True)
def _bust_bytecode_cache_after_every_write(monkeypatch):
    """Applies the mitigation above to every module write made through `_jailed_write` (the
    write path `build_system`/`_repair_system`/`modify_system` all use), for the tests below
    that drive the REAL pipeline end-to-end."""
    orig_write = system_builder._jailed_write

    def _write_then_bust(root, name, content, runtime=None):
        result = orig_write(root, name, content, runtime)
        _bust_cache(root)
        return result

    monkeypatch.setattr(system_builder, "_jailed_write", _write_then_bust)


SPEC = "A tiny calculator module with add(a, b) and sub(a, b)."

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

# both operations wrong initially -> two failing acceptance checks
CALC_BROKEN = "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a + b\n"
# a correct calc.py -- what the canned replan/modify fix produces
CALC_CORRECT = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
# add already correct, sub still wrong (only "subtracts correctly" is unmet)
CALC_ADD_FIXED = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b\n"
# a "fix" that regresses: sub now correct, but add is now BROKEN (a swap)
CALC_SWAP_BREAKS_ADD = "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a - b\n"

CHECKLIST = """[
  {"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"},
  {"name": "subtracts correctly", "code": "from calc import sub\\nassert sub(5, 2) == 3\\n"}
]"""

CHECKLIST_ONE = """[
  {"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"}
]"""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedReplanLlm:
    """Routes `.complete()` by prompt stage: plan / initial module build / acceptance
    checklist / SYSTEM ACCEPTANCE REPAIR (the `_repair_system` stage, kept a permanent no-op
    here so the REPLAN stage below is actually exercised) / the MODIFICATION-plane prompts
    (`modify_system`'s `_identify_targets`/`_regenerate_module`)."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, checklist=CHECKLIST,
                 replan_targets='["calc.py"]', replan_fix=CALC_CORRECT) -> None:
        self.plan = plan
        self.module_first = module_first or {"calc.py": CALC_BROKEN}
        self.checklist = checklist
        self.replan_targets = replan_targets
        self.replan_fix = replan_fix
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        # MODIFICATION-plane prompts are checked FIRST and specifically: the modification
        # SENTENCE they embed is `_replan_as_modification`'s own request text, which itself
        # contains a "FAILING ACCEPTANCE CHECKS" section -- so a later, more generic
        # "ACCEPTANCE CHECKS" substring check must never shadow these.
        if "MODIFICATION TARGET" in prompt:
            return _Resp(self.replan_targets)
        if "APPLY MODIFICATION" in prompt:
            return _Resp(self.replan_fix)
        # the TOP-LEVEL build's own acceptance-checklist derivation (real SPEC text) --
        # anchored precisely so it never matches a NESTED derivation call whose `spec`
        # argument happens to be a longer string that merely CONTAINS this SPEC text
        # (e.g. `_replan_as_modification`'s own modification request).
        if prompt.startswith(f"SPEC: {SPEC}\nThe system will expose"):
            return _Resp(self.checklist)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")   # modify_system's internal baseline/new-behavior derivations
        if "SYSTEM ACCEPTANCE REPAIR" in prompt:
            return _Resp("not json at all")   # `_repair_system` never fixes anything here
        if "SYNTAX ERROR" in prompt:
            return _Resp("")   # unused -- canned fixes below are always valid syntax
        if "COMPLETE Python module" in prompt:
            import re
            m = re.search(r"module `([^`]+)`", prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


# ---------------------------------------------------------------------------------------
# 1. FIXES: replan reduces unmet (to 0) and reaches DONE, through the full build_system.
# ---------------------------------------------------------------------------------------

def test_replan_fixes_reduces_unmet_and_reaches_done(tmp_path):
    llm = _CannedReplanLlm(module_first={"calc.py": CALC_BROKEN}, checklist=CHECKLIST,
                            replan_targets='["calc.py"]', replan_fix=CALC_CORRECT)
    result = build_system(SPEC, tmp_path / "built", llm=llm, replan_on_failure=True)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert "replan-as-modification: 1 round(s), unmet 2->0" in result["note"]
    assert (tmp_path / "built" / "calc.py").read_text().strip() == CALC_CORRECT.strip()

    # the MODIFICATION-plane was genuinely invoked (not a no-op)
    assert any("MODIFICATION TARGET" in p for p in llm.prompts)
    assert any("APPLY MODIFICATION" in p for p in llm.prompts)


def test_replan_never_invoked_when_already_done(tmp_path, monkeypatch):
    """`replan_on_failure=True` with an already-DONE build never touches `modify_system` --
    the recovery is a NO-OP when there's nothing to recover."""
    calls = {"n": 0}

    def _spy(*_a, **_kw):
        calls["n"] += 1
        raise AssertionError("modify_system must never be called for an already-done build")

    monkeypatch.setattr(system_builder, "modify_system", _spy)
    llm = _CannedReplanLlm(module_first={"calc.py": CALC_CORRECT}, checklist=CHECKLIST)
    result = build_system(SPEC, tmp_path / "built", llm=llm, replan_on_failure=True)

    assert result["done"] is True
    assert calls["n"] == 0


# ---------------------------------------------------------------------------------------
# 2. BYTE-IDENTICAL WHEN OFF: replan_on_failure=False (the default) is a complete no-op.
# ---------------------------------------------------------------------------------------

def test_replan_off_by_default_is_byte_identical(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _spy(*_a, **_kw):
        calls["n"] += 1
        raise AssertionError("modify_system must never be called when replan_on_failure=False")

    monkeypatch.setattr(system_builder, "modify_system", _spy)

    llm_default = _CannedReplanLlm(module_first={"calc.py": CALC_BROKEN}, checklist=CHECKLIST_ONE)
    result_default = build_system(SPEC, tmp_path / "built_default", llm=llm_default)

    llm_explicit = _CannedReplanLlm(module_first={"calc.py": CALC_BROKEN}, checklist=CHECKLIST_ONE)
    result_explicit = build_system(SPEC, tmp_path / "built_explicit", llm=llm_explicit,
                                    replan_on_failure=False)

    assert calls["n"] == 0
    assert result_default == result_explicit
    assert result_default["shipped"] is True
    assert result_default["done"] is False
    assert result_default["unmet"] == ["adds correctly"]
    assert "replan" not in result_default["note"]


# ---------------------------------------------------------------------------------------
# 3. NO ORACLE LEAK: the modification request never carries a hidden expected-output value.
# ---------------------------------------------------------------------------------------

def test_replan_request_never_leaks_hidden_expected_output(tmp_path):
    root = tmp_path / "sys"
    root.mkdir()
    built = {"calc.py": "def add(a, b):\n    return a + b + 1\n"}   # broken: add(1,2) == 4
    (root / "calc.py").write_text(built["calc.py"], encoding="utf-8")

    # the check's own CODE embeds a sentinel that is NEVER surfaced by the check's real run
    # error (a bare `raise SystemExit(1)` prints nothing to stdout/stderr) -- so any leak of
    # the sentinel into the modification request could only come from including the check's
    # CODE itself, which `_build_replan_request` must never do.
    checks = [{
        "name": "adds correctly",
        "code": ("expected = 999  # ORACLE_SENTINEL_HIDDEN_EXPECTED\n"
                  "from calc import add\n"
                  "if add(1, 2) != expected:\n"
                  "    raise SystemExit(1)\n"),
    }]
    unmet = ["adds correctly"]

    request = system_builder._build_replan_request(SPEC, root, built, checks, unmet)

    assert "ORACLE_SENTINEL_HIDDEN_EXPECTED" not in request
    assert "999" not in request
    # it DOES carry the spec, the current module source, and the failing check's NAME
    assert SPEC in request
    assert "def add" in request
    assert "adds correctly" in request


# ---------------------------------------------------------------------------------------
# 4. CONVERGENCE GATE: bounded to MAX_REPLAN_ROUNDS, never regresses, stops on no progress.
# ---------------------------------------------------------------------------------------

def _mod_source(fixed: set) -> str:
    lines = []
    for i in range(1, 5):
        val = i if i in fixed else 0
        lines.append(f"def f{i}():\n    return {val}\n")
    return "\n".join(lines)


_BOUND_CHECKS = [
    {"name": f"c{i}", "code": f"from mod import f{i}\nassert f{i}() == {i}\n"}
    for i in range(1, 5)
]


def test_replan_bounded_to_max_rounds_no_regression(tmp_path, monkeypatch):
    """A canned `modify_system` that fixes exactly ONE more check per round (never
    regressing an already-fixed one) is bounded to `MAX_REPLAN_ROUNDS` (3): with 4 checks
    starting unmet, only 3 get fixed within the bound -- the loop STOPS at the bound, not
    because it ran out of things to fix."""
    root = tmp_path / "sys"
    root.mkdir()
    initial_src = _mod_source(set())
    (root / "mod.py").write_text(initial_src, encoding="utf-8")
    built = {"mod.py": initial_src}
    unmet = [c["name"] for c in _BOUND_CHECKS]

    calls = {"n": 0}

    def _fake_modify(modules, mod_sentence, root_, *, llm=None, runtime=None):
        calls["n"] += 1
        new_src = _mod_source(set(range(1, calls["n"] + 1)))
        Path(root_, "mod.py").write_text(new_src, encoding="utf-8")
        _bust_cache(root_)
        return {"modules": {"mod.py": new_src}, "applied": True, "regressed": [],
                "new_behavior_ok": True, "note": "ok"}

    monkeypatch.setattr(system_builder, "modify_system", _fake_modify)

    new_built, new_unmet, rounds_run = system_builder._replan_as_modification(
        "spec", root, built, _BOUND_CHECKS, unmet, None)

    assert calls["n"] == 3
    assert rounds_run == 3
    assert sorted(new_unmet) == ["c4"]
    assert "c1" not in new_unmet and "c2" not in new_unmet and "c3" not in new_unmet


def test_replan_no_improvement_stops_without_progress(tmp_path, monkeypatch):
    """A canned `modify_system` that makes NO change at all -> the loop stops after round 1
    (no infinite loop), returning the same best-so-far state."""
    root = tmp_path / "sys"
    root.mkdir()
    (root / "calc.py").write_text(CALC_ADD_FIXED, encoding="utf-8")
    built = {"calc.py": CALC_ADD_FIXED}
    checks = [
        {"name": "adds correctly", "code": "from calc import add\nassert add(1, 2) == 3\n"},
        {"name": "subtracts correctly", "code": "from calc import sub\nassert sub(5, 2) == 3\n"},
    ]
    unmet = ["subtracts correctly"]

    calls = {"n": 0}

    def _fake_no_progress(modules, mod_sentence, root_, *, llm=None, runtime=None):
        calls["n"] += 1
        return {"modules": dict(modules), "applied": False, "regressed": [],
                "new_behavior_ok": False, "note": "no change"}

    monkeypatch.setattr(system_builder, "modify_system", _fake_no_progress)

    new_built, new_unmet, rounds_run = system_builder._replan_as_modification(
        "spec", root, built, checks, unmet, None)

    assert calls["n"] == 1        # tried once, then stopped -- never looped to the bound
    assert rounds_run == 0        # no round was ACCEPTED (no strict improvement)
    assert new_unmet == ["subtracts correctly"]
    assert new_built["calc.py"].strip() == CALC_ADD_FIXED.strip()
    assert (root / "calc.py").read_text().strip() == CALC_ADD_FIXED.strip()


def test_replan_regression_is_rejected_and_reverted(tmp_path, monkeypatch):
    """A canned `modify_system` that fixes the failing check but SWAPS in a regression on a
    previously-passing one is REJECTED -- reverted to pre-round content, disk + dict, and the
    ORIGINAL still-failing check remains the reported unmet (never the swapped one)."""
    root = tmp_path / "sys"
    root.mkdir()
    (root / "calc.py").write_text(CALC_ADD_FIXED, encoding="utf-8")
    built = {"calc.py": CALC_ADD_FIXED}
    checks = [
        {"name": "adds correctly", "code": "from calc import add\nassert add(1, 2) == 3\n"},
        {"name": "subtracts correctly", "code": "from calc import sub\nassert sub(5, 2) == 3\n"},
    ]
    unmet = ["subtracts correctly"]   # only sub is unmet; add already passes

    calls = {"n": 0}

    def _fake_regress(modules, mod_sentence, root_, *, llm=None, runtime=None):
        calls["n"] += 1
        Path(root_, "calc.py").write_text(CALC_SWAP_BREAKS_ADD, encoding="utf-8")
        _bust_cache(root_)
        return {"modules": {"calc.py": CALC_SWAP_BREAKS_ADD}, "applied": True, "regressed": [],
                "new_behavior_ok": True, "note": "ok"}

    monkeypatch.setattr(system_builder, "modify_system", _fake_regress)

    new_built, new_unmet, rounds_run = system_builder._replan_as_modification(
        "spec", root, built, checks, unmet, None)

    assert rounds_run == 0
    assert new_unmet == ["subtracts correctly"]
    assert "adds correctly" not in new_unmet
    assert new_built["calc.py"].strip() == CALC_ADD_FIXED.strip()
    assert (root / "calc.py").read_text().strip() == CALC_ADD_FIXED.strip()


def test_replan_never_raises_on_modify_system_exception(tmp_path, monkeypatch):
    """A `modify_system` call that raises never propagates -- the loop just stops and
    returns the best-seen state so far."""
    root = tmp_path / "sys"
    root.mkdir()
    (root / "calc.py").write_text(CALC_ADD_FIXED, encoding="utf-8")
    built = {"calc.py": CALC_ADD_FIXED}
    checks = [
        {"name": "adds correctly", "code": "from calc import add\nassert add(1, 2) == 3\n"},
        {"name": "subtracts correctly", "code": "from calc import sub\nassert sub(5, 2) == 3\n"},
    ]
    unmet = ["subtracts correctly"]

    def _raising(*_a, **_kw):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(system_builder, "modify_system", _raising)

    new_built, new_unmet, rounds_run = system_builder._replan_as_modification(
        "spec", root, built, checks, unmet, None)

    assert rounds_run == 0
    assert new_unmet == ["subtracts correctly"]
    assert new_built == built
