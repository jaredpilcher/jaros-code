"""EXT-036 TASK-5: system-level repair — drive a built system from shipped -> DONE (REQ-5).

OFFLINE — no live model. A stub `llm` (same `.complete(LlmRequest) -> .text` convention as
`test_ext036_system_builder.py`'s `_CannedLlm`) returns CANNED responses keyed off distinctive
prompt substrings, including the new "SYSTEM ACCEPTANCE REPAIR" targeted-fix prompt. This proves
the repair-loop WIRING (feed failure -> targeted fix -> syntax-gate -> re-assemble -> re-run the
full checklist -> bounded rounds) composes correctly and is honest about failures, without ever
reaching the Jetson.
"""

from __future__ import annotations

import os
import re

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import build_system, syntax_ok

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

# both operations wrong initially -> two failing acceptance checks to repair
CALC_BROKEN = "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a + b\n"
# a correct calc.py (used for the already-done test -- no repair should ever be invoked)
CALC_CORRECT = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
# add fixed, sub still wrong (sub still returns a + b)
CALC_ADD_FIXED = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b\n"
# a "fix" for sub that never actually fixes it (still returns a + b)
CALC_SUB_STILL_BROKEN = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b\n"
# a "fix" that SWAPS which check passes: fixes sub, but incidentally breaks the
# previously-passing add (this is the exact regression the architect reproduced -- same
# unmet COUNT, different unmet SET, which the old count-only guard silently accepted)
CALC_SWAP_BREAKS_ADD = "def add(a, b):\n    return a * b\n\n\ndef sub(a, b):\n    return a - b\n"

CHECKLIST = """[
  {"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"},
  {"name": "subtracts correctly", "code": "from calc import sub\\nassert sub(5, 2) == 3\\n"}
]"""

CHECKLIST_ONE = """[
  {"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"}
]"""

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")
_FAILING_CHECK_RE = re.compile(r"FAILING CHECK: (.+)")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedRepairLlm:
    """Routes `.complete()` calls by prompt stage: plan / initial module build / acceptance
    checklist / targeted SYSTEM ACCEPTANCE REPAIR (keyed by the failing check's name, so a
    "never fixes it" check can be modeled distinctly from a "gets fixed" one)."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, checklist=CHECKLIST,
                 repair_fixes: dict[str, str] | None = None) -> None:
        self.plan = plan
        self.module_first = module_first or {"calc.py": CALC_BROKEN}
        self.checklist = checklist
        # check-name -> the full module content the canned repair proposes for that check
        self.repair_fixes = repair_fixes or {}
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "SYSTEM ACCEPTANCE REPAIR" in prompt:
            m = _FAILING_CHECK_RE.search(prompt)
            check_name = m.group(1).strip() if m else None
            code = self.repair_fixes.get(check_name)
            if code is None:
                return _Resp("not json at all")
            return _Resp('{"module": "calc.py", "code": %s}' % _json_str(code))
        if "SYNTAX ERROR" in prompt:
            return _Resp("")   # unused in these tests -- canned fixes are always valid syntax
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


def _json_str(s: str) -> str:
    import json
    return json.dumps(s)


# --- (a) repair FIXES the module -> done True after 1 round -----------------------------

def test_repair_fixes_module_reaches_done_after_one_round(tmp_path):
    llm = _CannedRepairLlm(checklist=CHECKLIST_ONE,
                            module_first={"calc.py": CALC_BROKEN},
                            repair_fixes={"adds correctly": CALC_CORRECT})
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert result["repairs"], "repairs should record the attempted/applied fix"
    assert all(r["round"] == 1 for r in result["repairs"])
    assert result["repairs"][0]["check"] == "adds correctly"
    assert result["repairs"][0]["applied"] is True
    assert result["repairs"][0]["module"] == "calc.py"
    # the assembled module on disk reflects the applied fix
    assert (tmp_path / "built" / "calc.py").read_text().strip() == CALC_CORRECT.strip()
    assert syntax_ok(result["modules"]["calc.py"])[0] is True
    # exactly one SYSTEM ACCEPTANCE REPAIR call was made
    repair_prompts = [p for p in llm.prompts if "SYSTEM ACCEPTANCE REPAIR" in p]
    assert len(repair_prompts) == 1


# --- (b) repair NEVER fixes it -> stays done False, bounded at exactly max_repair rounds --

def test_repair_that_never_fixes_stays_not_done_and_is_bounded(tmp_path):
    llm = _CannedRepairLlm(
        checklist=CHECKLIST,
        module_first={"calc.py": CALC_BROKEN},
        repair_fixes={
            "adds correctly": CALC_ADD_FIXED,          # fixes add, sub still broken
            "subtracts correctly": CALC_SUB_STILL_BROKEN,  # never actually fixes sub
        },
    )
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"] == ["subtracts correctly"]
    # non-degrading: the "adds correctly" check that DID get fixed never regresses back
    assert "adds correctly" not in result["unmet"]

    # bounded: exactly max_repair (2) rounds were attempted, no more
    rounds = {r["round"] for r in result["repairs"]}
    assert rounds == {1, 2}
    for r in result["repairs"]:
        assert r["round"] <= 2

    # round 1 attempted both checks; round 2 only re-attempted the still-failing one
    round1 = [r for r in result["repairs"] if r["round"] == 1]
    round2 = [r for r in result["repairs"] if r["round"] == 2]
    assert {r["check"] for r in round1} == {"adds correctly", "subtracts correctly"}
    assert {r["check"] for r in round2} == {"subtracts correctly"}


# --- (c) already-done build -> repair skipped entirely (0 rounds) -----------------------

def test_already_done_build_skips_repair_entirely(tmp_path):
    llm = _CannedRepairLlm(checklist=CHECKLIST, module_first={"calc.py": CALC_CORRECT})
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert result["repairs"] == []
    # the repair prompt was never even constructed/sent
    assert not [p for p in llm.prompts if "SYSTEM ACCEPTANCE REPAIR" in p]


# --- non-degrading / never-raises guards --------------------------------------------------

def test_repair_never_raises_on_unparseable_fix(tmp_path):
    """The model's targeted-fix response is unparseable -> no fix applied, repair
    recorded as not-applied; since that round made no progress, the loop stops early
    (the "no infinite loop" guard) without ever raising."""
    llm = _CannedRepairLlm(checklist=CHECKLIST_ONE, module_first={"calc.py": CALC_BROKEN},
                            repair_fixes={})   # -> "not json at all" for every repair call
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"] == ["adds correctly"]
    assert result["repairs"]
    assert all(r["applied"] is False for r in result["repairs"])
    # a no-progress round stops the loop early (well within the max_repair=2 bound)
    assert {r["round"] for r in result["repairs"]} == {1}


# --- (e) REAL non-degrading: a fix that swaps which check fails is REJECTED, not accepted -

def test_repair_that_swaps_regression_is_reverted_not_accepted(tmp_path):
    """The exact case the architect reproduced: the targeted fix for the one failing check
    ("subtracts correctly") returns a COMPLETE module that does fix sub, but incidentally
    breaks the already-passing "adds correctly" check. Unmet COUNT stays the same (1 -> 1)
    across the swap, which the old count-only guard (`len(unmet) >= before`) silently
    accepted. The SET-based guard must catch this: the round is REJECTED, the module write
    reverted to its pre-round content, and the ORIGINAL still-failing check ("subtracts
    correctly") remains the reported unmet -- "adds correctly" must never regress."""
    llm = _CannedRepairLlm(
        checklist=CHECKLIST,
        # add already correct, sub still wrong -> only "subtracts correctly" starts unmet
        module_first={"calc.py": CALC_ADD_FIXED},
        repair_fixes={"subtracts correctly": CALC_SWAP_BREAKS_ADD},
    )
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is False
    # NOT the silent swap ("adds correctly" must NOT be the reported unmet check)
    assert result["unmet"] == ["subtracts correctly"]
    assert "adds correctly" not in result["unmet"]

    # the module write for the bad round was reverted, not left as the swapped content
    assert result["modules"]["calc.py"].strip() == CALC_ADD_FIXED.strip()
    assert (tmp_path / "built" / "calc.py").read_text().strip() == CALC_ADD_FIXED.strip()

    # the rejected attempt is recorded honestly: NOT applied, and NOT silently dropped
    assert result["repairs"], "the rejected round's attempt should still be recorded"
    swap_attempt = next(r for r in result["repairs"] if r["check"] == "subtracts correctly")
    assert swap_attempt["applied"] is False
    assert swap_attempt.get("reverted"), "the record must show the fix was reverted, not accepted"

    # re-deriving from the (reverted) module content proves "adds correctly" still passes
    ns: dict = {}
    exec(compile(result["modules"]["calc.py"], "calc.py", "exec"), ns)
    assert ns["add"](1, 2) == 3
