"""EXT-036 TASK-45: `modify_system` can ADD new module(s), not just regenerate existing ones
(REQ-35).

Owner steer (roadmap 45508cf, task #128): `modify_system`'s `_identify_targets` only ever
names EXISTING modules -- a modification that genuinely requires a brand-new module (e.g.
"add rate-limiting" to a system with no rate-limiter module yet) could never be satisfied.
This adds the analogous NEW-module judgment (`_identify_new_modules`) + the deterministic
build path for it (`_build_new_module`, reusing the SAME syntax-gate/repair loop
`_regenerate_module` uses), wired additively into `modify_system` so the regenerate-only path
stays byte-identical whenever the model names no new module.

OFFLINE -- no live model. A stub `llm` (same `.complete(LlmRequest) -> .text` convention as
every other EXT-036 stub) routes canned responses by distinctive prompt substring:
"MODIFICATION TARGET" (existing-target identification), "APPLY MODIFICATION" (a regenerated
existing module body), "NEW-MODULE CHECK" (the new-module judgment, REQ-35), "WRITE NEW
MODULE" (a brand-new module's body, REQ-35), "SYNTAX ERROR" (the shared syntax-repair loop),
and "ACCEPTANCE CHECKS" (baseline / best-effort new-behavior derivation).
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    _identify_new_modules,
    modify_system,
)

MOD_SENTENCE = "add rate limiting to the api"

CALC_ORIGINAL = "def add(a, b):\n    return a + b\n"

RATELIMITER_CODE = (
    "_COUNTS = {}\n\n\n"
    "def allow(key, limit=3):\n"
    "    n = _COUNTS.get(key, 0)\n"
    "    if n >= limit:\n"
    "        return False\n"
    "    _COUNTS[key] = n + 1\n"
    "    return True\n"
)

BASELINE_CHECKLIST = (
    '[{"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"}]'
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedAddModuleLlm:
    """Routes `.complete()` by prompt stage. Unmatched prompts (incl. the best-effort
    new-behavior ACCEPTANCE CHECKS derivation) fall back to an empty response -- mirroring
    every other EXT-036 canned stub's default."""

    def __init__(self, *, target='[]', modified="", new_module_names='["ratelimiter.py"]',
                 new_module_code=RATELIMITER_CODE, baseline_checklist=BASELINE_CHECKLIST,
                 syntax_repair="") -> None:
        self.target = target
        self.modified = modified
        self.new_module_names = new_module_names
        self.new_module_code = new_module_code
        self.baseline_checklist = baseline_checklist
        self.syntax_repair = syntax_repair
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp(self.target)
        if "APPLY MODIFICATION" in prompt:
            return _Resp(self.modified)
        if "NEW-MODULE CHECK" in prompt:
            return _Resp(self.new_module_names)
        if "WRITE NEW MODULE" in prompt:
            return _Resp(self.new_module_code)
        if "SYNTAX ERROR" in prompt:
            return _Resp(self.syntax_repair)
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")
        if "ACCEPTANCE CHECKS" in prompt:
            # the BASELINE derivation's `spec` is the literal "existing system"; anything
            # else (the mod-sentence-keyed best-effort NEW-behavior derivation) is not
            # needed by these tests, regardless of which mod_sentence text is in play.
            if "SPEC: existing system" in prompt:
                return _Resp(self.baseline_checklist)
            return _Resp("[]")
        return _Resp("")


# --- (a) adds a new module and KEEPS it when there is no regression ------------------------

def test_adds_a_new_module_and_keeps_it_when_no_regression(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedAddModuleLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is True
    assert result["regressed"] == []
    # the new module is present both in the returned dict and genuinely written to disk
    assert result["modules"]["ratelimiter.py"].strip() == RATELIMITER_CODE.strip()
    assert (root / "ratelimiter.py").is_file()
    assert (root / "ratelimiter.py").read_text().strip() == RATELIMITER_CODE.strip()
    # the pre-existing module is untouched (this modification was purely additive)
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert "ratelimiter.py" in result["note"]

    new_module_prompts = [p for p in llm.prompts if "NEW-MODULE CHECK" in p]
    assert len(new_module_prompts) == 1
    build_prompts = [p for p in llm.prompts if "WRITE NEW MODULE" in p and "`ratelimiter.py`" in p]
    assert len(build_prompts) == 1


# --- (b) BYTE-IDENTICAL when the llm names no new module (regenerate-only unaffected) -------

def test_byte_identical_when_no_new_module_named(tmp_path):
    """When `_identify_new_modules` finds nothing (the vast majority of modifications, and
    every pre-existing EXT-036 regenerate-only test), `modify_system` behaves exactly as it
    did before this task: a clean regenerate-only modification still applies correctly, with
    no stray new-module file ever written."""
    root = tmp_path / "sys"
    llm = _CannedAddModuleLlm(
        target='["calc.py"]',
        modified="def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n",
        new_module_names="NONE",
    )
    result = modify_system({"calc.py": CALC_ORIGINAL}, "add a mul(a, b) function to calc.py",
                            root, llm=llm)

    assert result["applied"] is True
    assert result["modules"]["calc.py"].strip() == (
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    ).strip()
    assert "ratelimiter.py" not in result["modules"]
    assert not (root / "ratelimiter.py").exists()
    assert "added module" not in result["note"]


# --- (c) a regression REVERTS regenerated modules AND REMOVES the added module --------------

def test_regression_reverts_and_removes_added_module(tmp_path):
    root = tmp_path / "sys"
    # the "modification" both breaks the existing `add` AND adds a new module -- the whole
    # thing must be reverted: `calc.py` restored, `ratelimiter.py` deleted + dropped from dict.
    llm = _CannedAddModuleLlm(
        target='["calc.py"]',
        modified="def add(a, b):\n    return a * b\n",   # breaks add(1, 2) == 3
    )
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is False
    assert "adds correctly" in result["regressed"]
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert (root / "calc.py").read_text() == CALC_ORIGINAL
    # the added module is gone -- both the file AND the returned dict
    assert "ratelimiter.py" not in result["modules"]
    assert not (root / "ratelimiter.py").exists()
    assert "ratelimiter.py" in result["note"]


# --- (d) bounded to at most 3 new modules, even when the model names 5 ----------------------

def test_identify_new_modules_bounded_to_three():
    modules = {"calc.py": CALC_ORIGINAL}
    llm = _CannedAddModuleLlm(
        new_module_names='["a.py", "b.py", "c.py", "d.py", "e.py"]',
    )
    names = _identify_new_modules(modules, MOD_SENTENCE, llm)
    assert len(names) <= 3
    assert names == ["a.py", "b.py", "c.py"]


def test_modify_system_adds_at_most_three_new_modules(tmp_path):
    root = tmp_path / "sys"

    class _FiveModulesLlm(_CannedAddModuleLlm):
        def complete(self, request):
            prompt = request.prompt
            self.prompts.append(prompt)
            if "NEW-MODULE CHECK" in prompt:
                return _Resp('["a.py", "b.py", "c.py", "d.py", "e.py"]')
            if "WRITE NEW MODULE" in prompt:
                m = re.search(r"`([^`]+\.py)`", prompt)
                name = m.group(1) if m else "x.py"
                return _Resp(f"def f():\n    return '{name}'\n")
            if "ACCEPTANCE CHECKS" in prompt:
                if "SPEC: existing system" in prompt:
                    return _Resp(BASELINE_CHECKLIST)
                return _Resp("[]")
            return _Resp("")

    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=_FiveModulesLlm())
    added = set(result["modules"]) - {"calc.py"}
    assert added == {"a.py", "b.py", "c.py"}
    assert len(added) <= 3


# --- (e) ambiguity-guarded: vague/empty output -> nothing added ----------------------------

@pytest.mark.parametrize("raw", ["", "NONE", "none", "  NONE  ", "maybe a helper module?",
                                  "not json at all", "null", "{}"])
def test_identify_new_modules_ambiguity_guarded(raw):
    modules = {"calc.py": CALC_ORIGINAL}
    llm = _CannedAddModuleLlm(new_module_names=raw)
    assert _identify_new_modules(modules, MOD_SENTENCE, llm) == []


def test_identify_new_modules_filters_existing_and_malformed_names():
    modules = {"calc.py": CALC_ORIGINAL}
    llm = _CannedAddModuleLlm(
        new_module_names='["calc.py", "../evil.py", "no extension", "good.py", "good.py"]',
    )
    # "calc.py" already exists, "../evil.py"/"no extension" are not plausible bare filenames,
    # and the duplicate "good.py" is de-duplicated -- only "good.py" survives.
    assert _identify_new_modules(modules, MOD_SENTENCE, llm) == ["good.py"]


def test_modify_system_no_target_no_new_module_makes_no_change(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedAddModuleLlm(target="[]", new_module_names="NONE")
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)
    assert result["applied"] is False
    assert result["modules"] == {"calc.py": CALC_ORIGINAL}
    assert (root / "calc.py").is_file()
    assert not (root / "ratelimiter.py").exists()


# --- (f) never raises on a misbehaving llm ---------------------------------------------------

class _RaisingLlm:
    def complete(self, request):
        raise RuntimeError("the model is unreachable")


def test_identify_new_modules_never_raises_on_misbehaving_llm():
    assert _identify_new_modules({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, _RaisingLlm()) == []


def test_modify_system_never_raises_when_new_module_identification_raises(tmp_path):
    root = tmp_path / "sys"

    class _RaisesOnNewModuleOnly(_CannedAddModuleLlm):
        def complete(self, request):
            prompt = request.prompt
            self.prompts.append(prompt)
            if "NEW-MODULE CHECK" in prompt:
                raise RuntimeError("boom")
            if "MODIFICATION TARGET" in prompt:
                return _Resp('["calc.py"]')
            if "APPLY MODIFICATION" in prompt:
                return _Resp("def add(a, b):\n    return a + b\n")
            if "ACCEPTANCE CHECKS" in prompt:
                if "SPEC: existing system" in prompt:
                    return _Resp(BASELINE_CHECKLIST)
                return _Resp("[]")
            return _Resp("")

    # never raises -- the new-module identification failure degrades to [] (no new modules),
    # and the pre-existing regenerate-only flow still completes normally.
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root,
                            llm=_RaisesOnNewModuleOnly())
    assert result["applied"] is True


def test_modify_system_never_raises_when_new_module_build_raises(tmp_path):
    root = tmp_path / "sys"

    class _RaisesOnBuildOnly(_CannedAddModuleLlm):
        def complete(self, request):
            prompt = request.prompt
            self.prompts.append(prompt)
            if "NEW-MODULE CHECK" in prompt:
                return _Resp('["ratelimiter.py"]')
            if "WRITE NEW MODULE" in prompt:
                raise RuntimeError("boom")
            if "MODIFICATION TARGET" in prompt:
                return _Resp("[]")
            if "ACCEPTANCE CHECKS" in prompt:
                if "SPEC: existing system" in prompt:
                    return _Resp(BASELINE_CHECKLIST)
                return _Resp("[]")
            return _Resp("")

    # the new module fails to build (raises) -> no targets, no added modules -> honest
    # "no change made" result, never a crash.
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root,
                            llm=_RaisesOnBuildOnly())
    assert result["applied"] is False
    assert result["modules"] == {"calc.py": CALC_ORIGINAL}


# --- (g) runtime is threaded to added-module writes -----------------------------------------

class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` -- does NOT touch the filesystem itself, so
    a test using it proves the CALLER built a `code.write_file` Decision for the new module
    without depending on the real Jaros gate/executor plumbing (mirrors
    `tests/test_ext037_buildsystem_jaros_write.py::_FakeApplyRuntime`)."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        return {"tool": "code.write_file", "path": decision.payload["path"], "applied": True}


def test_runtime_is_threaded_to_added_module_writes(tmp_path):
    root = tmp_path / "sys"
    rt = _FakeApplyRuntime()
    llm = _CannedAddModuleLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm, runtime=rt)

    assert result["applied"] is True
    paths = {d.payload["path"] for d in rt.applied}
    assert any(p.endswith("ratelimiter.py") for p in paths)
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(root)
    # the FAKE runtime never actually writes to disk -- the new module genuinely went
    # THROUGH the runtime, not a raw Path.write_text alongside it.
    assert not (root / "ratelimiter.py").exists()


def test_runtime_none_is_byte_identical_for_added_module(tmp_path):
    root = tmp_path / "sys"
    llm = _CannedAddModuleLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, MOD_SENTENCE, root, llm=llm)
    assert result["applied"] is True
    assert (root / "ratelimiter.py").is_file()
