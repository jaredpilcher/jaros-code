"""EXT-036 TASK-7: modification from a sentence — modify_system, regression-gated (REQ-14).

Owner-emphasized: not just CREATE but MODIFY an existing system from a sentence ("add median
to the CSV CLI"). Composes the CREATE pipeline's PROVEN pieces (``syntax_ok``,
``_derive_acceptance_checklist``, ``_run_check``) with TASK-5's non-degrading revert pattern.
The HONESTY core (Tenet 3): a modification must PRESERVE existing behavior — a change that
regresses a previously-passing check is REVERTED (disk + dict), never accepted.

OFFLINE — no live model. A stub `llm` (same `.complete(LlmRequest) -> .text` convention as
every other EXT-036 stub) returns CANNED responses keyed off distinctive prompt substrings:
"MODIFICATION TARGET" (which module(s) to change), "APPLY MODIFICATION" (the regenerated
module body), "ACCEPTANCE CHECKS" (both the BASELINE derivation, keyed on "SPEC: existing
system", and the best-effort NEW-behavior derivation, keyed on the mod sentence itself being
present in the prompt), and "SYNTAX ERROR" (the shared syntax-repair loop).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import modify_system

MOD_SENTENCE = "add a mul(a, b) function to calc.py"

CALC_ORIGINAL = "def add(a, b):\n    return a + b\n"
# a clean modification: adds mul(a, b), add(a, b) untouched -> existing check still passes
CALC_WITH_MUL = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
# a "modification" that adds mul but ALSO breaks add -> must be reverted
CALC_MUL_BREAKS_ADD = "def add(a, b):\n    return a * b\n\n\ndef mul(a, b):\n    return a * b\n"

BASELINE_CHECKLIST = (
    '[{"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"}]'
)
NEW_BEHAVIOR_CHECKLIST = (
    '[{"name": "multiplies correctly", "code": "from calc import mul\\nassert mul(2, 3) == 6\\n"}]'
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedModifyLlm:
    """Routes `.complete()` by prompt stage: IDENTIFY target / APPLY MODIFICATION (the
    regenerated body) / syntax repair / the two ACCEPTANCE-CHECKS derivations (baseline vs.
    best-effort new-behavior, distinguished by whether the mod sentence itself appears in the
    prompt -- the baseline call's `spec` is the literal "existing system")."""

    def __init__(self, *, target='["calc.py"]', modified=CALC_WITH_MUL,
                 baseline_checklist=BASELINE_CHECKLIST, new_checklist=NEW_BEHAVIOR_CHECKLIST,
                 syntax_repair="") -> None:
        self.target = target
        self.modified = modified
        self.baseline_checklist = baseline_checklist
        self.new_checklist = new_checklist
        self.syntax_repair = syntax_repair
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp(self.target)
        if "APPLY MODIFICATION" in prompt:
            return _Resp(self.modified)
        if "SYNTAX ERROR" in prompt:
            return _Resp(self.syntax_repair)
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")   # stricter-retry never needed in these tests
        if "ACCEPTANCE CHECKS" in prompt:
            if MOD_SENTENCE in prompt:
                return _Resp(self.new_checklist)
            return _Resp(self.baseline_checklist)
        return _Resp("")


# --- (a) a clean modification: existing checks still pass -> applied=True ------------------

def test_clean_modification_preserves_existing_behavior_and_applies(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedModifyLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is True
    assert result["regressed"] == []
    assert result["modules"]["calc.py"].strip() == CALC_WITH_MUL.strip()
    assert (root / "calc.py").read_text().strip() == CALC_WITH_MUL.strip()
    # best-effort new-behavior check derived from the mod sentence genuinely passes
    assert result["new_behavior_ok"] is True

    # both the baseline check ("adds correctly") and the new-behavior derivation ran
    identify_prompts = [p for p in llm.prompts if "MODIFICATION TARGET" in p]
    assert len(identify_prompts) == 1
    apply_prompts = [p for p in llm.prompts if "APPLY MODIFICATION" in p and "`calc.py`" in p]
    assert len(apply_prompts) == 1


# --- (b) a modification that BREAKS an existing check -> reverted, applied=False -----------

def test_regressing_modification_is_reverted_not_applied(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedModifyLlm(modified=CALC_MUL_BREAKS_ADD)
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is False
    assert result["regressed"] == ["adds correctly"]
    assert result["new_behavior_ok"] is False
    # modules restored to their PRE-MOD content, both in the returned dict and on disk
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert (root / "calc.py").read_text() == CALC_ORIGINAL
    assert result["note"]
    assert "revert" in result["note"].lower() or "regress" in result["note"].lower()


def test_regressing_modification_never_runs_new_behavior_check(tmp_path):
    """A reverted modification is never granted a "new behavior confirmed" -- the regression
    gate short-circuits before the best-effort new-behavior derivation is even attempted."""
    root = tmp_path / "sys"
    llm = _CannedModifyLlm(modified=CALC_MUL_BREAKS_ADD)
    modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)
    assert not [p for p in llm.prompts if "ACCEPTANCE CHECKS" in p and MOD_SENTENCE in p]


# --- (c) never raises on unparseable model output -------------------------------------------

def test_unparseable_target_never_raises_and_makes_no_change(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedModifyLlm(target="not json at all")
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is False
    assert result["regressed"] == []
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert (root / "calc.py").read_text() == CALC_ORIGINAL
    assert "note" in result


def test_unparseable_regenerated_body_never_raises_and_makes_no_change(tmp_path):
    """The target is identified fine, but the model's regenerated module is unparseable
    garbage AND the syntax-repair loop also never fixes it -> no syntactically valid change
    -> applied=False, original content untouched, never raises."""
    root = tmp_path / "sys"
    llm = _CannedModifyLlm(modified="this is not ) python at all (:", syntax_repair="still ( not python")
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is False
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert (root / "calc.py").read_text() == CALC_ORIGINAL


def test_out_of_range_target_name_is_ignored_never_raises(tmp_path):
    """The model names a module that doesn't exist in the system -> filtered out (never a
    fabricated target); no target survives -> applied=False, never raises."""
    root = tmp_path / "sys"
    llm = _CannedModifyLlm(target='["ghost.py"]')
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)
    assert result["applied"] is False
    assert result["modules"] == {"calc.py": CALC_ORIGINAL}


def test_uses_build_llm_when_llm_is_none(tmp_path, monkeypatch):
    llm = _CannedModifyLlm()
    monkeypatch.setattr("harness.coding_loop.build_llm", lambda: llm)
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, tmp_path / "sys", llm=None)
    assert result["applied"] is True
    assert llm.prompts


# --- CLI wiring (/modifysystem) -------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Mirrors the other EXT-036 test files: never touch the real .jaros-data/sessions/."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


def test_cli_modifysystem_uses_last_built_dir_and_reports_result(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    built_dir = tmp_path / "built"
    built_dir.mkdir()
    (built_dir / "calc.py").write_text(CALC_ORIGINAL, encoding="utf-8")

    seen: dict = {}

    def fake_modify_system(modules, sentence, root, *, llm=None):
        seen["modules"] = modules
        seen["sentence"] = sentence
        seen["root"] = root
        return {"modules": modules, "applied": True, "regressed": [], "new_behavior_ok": True,
                "note": "applied — existing behavior preserved"}

    monkeypatch.setattr("harness.system_builder.modify_system", fake_modify_system)
    cli = JcodeCli()
    cli._last_built_dir = built_dir
    out = cli.dispatch(f"/modifysystem {MOD_SENTENCE}")

    assert "applied" in out
    assert "NOT applied" not in out
    assert seen["sentence"] == MOD_SENTENCE
    assert seen["root"] == built_dir
    assert seen["modules"] == {"calc.py": CALC_ORIGINAL}


def test_cli_modifysystem_explicit_dir_overrides_last_built(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "mod.py").write_text("def f():\n    pass\n", encoding="utf-8")

    seen: dict = {}

    def fake_modify_system(modules, sentence, root, *, llm=None):
        seen["root"] = root
        return {"modules": modules, "applied": False, "regressed": ["x"], "new_behavior_ok": False,
                "note": "modification regressed existing behavior — reverted: x"}

    monkeypatch.setattr("harness.system_builder.modify_system", fake_modify_system)
    cli = JcodeCli()
    cli._last_built_dir = tmp_path / "not_this_one"
    out = cli.dispatch(f"/modifysystem {other_dir} :: {MOD_SENTENCE}")

    assert seen["root"] == other_dir
    assert "NOT applied" in out
    assert "regressed" in out.lower()


def test_cli_modifysystem_no_last_built_dir_gives_usage(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch(f"/modifysystem {MOD_SENTENCE}")
    assert "no system to modify" in out.lower()


def test_cli_modifysystem_usage_message_on_empty_arg(tmp_path, monkeypatch):
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/modifysystem   ")
    assert "usage" in out.lower()


def test_cli_buildsystem_command_unaffected_by_modifysystem_addition(tmp_path, monkeypatch):
    """The pre-existing /buildsystem is untouched by the /modifysystem addition."""
    from harness.cli import JcodeCli

    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/buildsystem   ")
    assert "usage: /buildsystem" in out
