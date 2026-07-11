"""EXT-036 TASK-86 (REQ-71): syntax-gate SINGLE-FILE RESCUE — don't abort the whole
`build_system` run just because one planned module fails the bounded per-module syntax
gate; fall through to the SAME single-file rescue REQ-43 already uses, and if THAT passes
its own syntax gate, keep going through the normal assembly/acceptance/repair flow instead
of returning an early failure.

MEASURED (2026-07-11, url-shortener-http-service): a fresh gemma draw frequently emits ONE
unparseable module the bounded syntax repair can't fix, wasting a fully-plannable system at
the syntax-gate abort. OFFLINE — no live model. Mirrors the mocking convention the sibling
REQ-43 single-file-retry tests use (`tests/test_ext036_system_builder.py`'s `_CannedLlm`):
a stub `llm` (`.complete(LlmRequest) -> .text`) keyed off distinctive prompt substrings.
"""
# #EXT-036-REQ-71 Start
from __future__ import annotations

import os
import re

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import build_system

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")

SPEC = "A tiny CLI that prints the sum of 1 and 2."

# A 2-module plan (helper.py, a leaf with no imports, built FIRST by the topological
# order; cli.py depends on it and is built second) -- helper.py is the module that will
# permanently fail its syntax gate below, so the module-build loop never even reaches
# cli.py (the loop `break`s before that).
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

# Missing colon -> a genuine, PERSISTENT SyntaxError -- the canned repair response below
# reproduces the exact same broken code, so it never becomes syntax-clean within
# MAX_REPAIR_ATTEMPTS, guaranteeing the module-build loop's `if not ok:` branch fires.
HELPER_BROKEN = "def add(a, b)\n    return a + b\n"

# A genuinely valid, self-contained single-file rescue candidate (no `helper` import at
# all -- this is what `_build_single_file`'s clean, plan-free prompt is meant to produce).
SINGLE_FILE_OK = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def main():\n    print(add(1, 2))\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)

# A single-file candidate that is ALSO permanently syntactically broken (for the
# rescue-also-fails test).
SINGLE_FILE_BROKEN = "def main(\n    pass\n"

CHECKLIST_FOR_SINGLE_FILE = """[
  {"name": "prints 3", "code": "import subprocess, sys\\nresult = subprocess.run([sys.executable, 'cli.py'], capture_output=True, text=True, timeout=20)\\nassert result.stdout.strip() == '3', result.stdout + result.stderr\\n"}
]"""

# A clean, all-modules-pass plan/build used by the non-degrading test below.
CLEAN_HELPER_OK = "def add(a, b):\n    return a + b\n"
CLEAN_CLI_OK = (
    "from helper import add\n\n\n"
    "def main():\n    print(add(1, 2))\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)
CHECKLIST_FOR_CLEAN_BUILD = """[
  {"name": "adds correctly", "code": "from helper import add\\nassert add(1, 2) == 3\\n"}
]"""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _RescueLlm:
    """Routes each `.complete()` call by distinctive prompt substring, same convention as
    `test_ext036_system_builder.py`'s `_CannedLlm` -- extended to distinguish the PLAN
    module-build path (`BUILD_PROMPT`/`REPAIR_PROMPT`, both use `` module `<name>` ``) from
    the single-file rescue's OWN clean prompt (`SINGLE_FILE_PROMPT`, unique marker text)."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, module_repair=None,
                 single_file_first="", single_file_repair="", checklist=CHECKLIST_FOR_SINGLE_FILE):
        self.plan = plan
        self.module_first = module_first or {}
        self.module_repair = module_repair or {}
        self.single_file_first = single_file_first
        self.single_file_repair = single_file_repair
        self.checklist = checklist
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "COMPLETE, correct Python program in ONE file" in prompt:
            return _Resp(self.single_file_first)
        if "SYNTAX ERROR" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            if name == "main.py":
                return _Resp(self.single_file_repair)
            return _Resp(self.module_repair.get(name, ""))
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


def _sf_prompt_count(llm: _RescueLlm) -> int:
    return sum(1 for p in llm.prompts if "COMPLETE, correct Python program in ONE file" in p)


def test_syntax_gate_rescue_fires_ships_and_reaches_a_real_acceptance_verdict(tmp_path):
    """Core REQ-71 behavior: `helper.py` never becomes syntax-clean (even after the bounded
    repair rounds), so the module-build loop would previously ABORT the whole build with a
    "failed the syntax gate" note. Instead, the single-file rescue fires, produces a
    genuinely valid, genuinely-passing single file, and the build reaches a REAL DONE
    acceptance verdict -- `build_path` records the rescue, `note` never mentions the old
    abort, and the shipped `modules` is the rescued single file."""
    llm = _RescueLlm(
        module_first={"helper.py": HELPER_BROKEN},
        module_repair={"helper.py": HELPER_BROKEN},   # stays broken every repair round
        single_file_first=SINGLE_FILE_OK,
        single_file_repair=SINGLE_FILE_OK,             # already clean -- repair never needed
        checklist=CHECKLIST_FOR_SINGLE_FILE,
    )

    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []
    assert result["build_path"] == "single-file-syntax-rescue"
    assert "failed the syntax gate after" not in result["note"]
    # `_strip_fences` trims the canned reply's trailing whitespace, same as every real
    # model call -- compare on stripped content, mirroring the REQ-43 sibling tests.
    assert result["modules"] == {"cli.py": SINGLE_FILE_OK.strip()}
    # The rescued file was actually written to disk and genuinely runs.
    assert (tmp_path / "built" / "cli.py").read_text(encoding="utf-8") == SINGLE_FILE_OK.strip()
    assert not (tmp_path / "built" / "helper.py").exists()
    # The rescue fires AT MOST ONCE (the module-build loop `break`s and is never re-entered).
    assert _sf_prompt_count(llm) == 1


def test_syntax_gate_rescue_also_failing_syntax_returns_honest_failure(tmp_path):
    """When the single-file rescue candidate ITSELF never becomes syntax-clean either, the
    build honestly fails (no crash, no false-done) with a note explaining BOTH attempts
    failed -- never silently swallowed, never a false pass."""
    llm = _RescueLlm(
        module_first={"helper.py": HELPER_BROKEN},
        module_repair={"helper.py": HELPER_BROKEN},
        single_file_first=SINGLE_FILE_BROKEN,
        single_file_repair=SINGLE_FILE_BROKEN,   # stays broken too
    )

    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is False
    assert result["done"] is False
    assert "single-file rescue produced no usable module either" in result["note"]
    assert "helper.py" in result["note"]
    # The rescue is attempted exactly once even though it, too, fails.
    assert _sf_prompt_count(llm) == 1


def test_syntax_gate_rescue_rejects_blank_output_as_a_false_done_guard(tmp_path):
    """HONESTY GUARD: a blank/whitespace-only single-file reply is syntactically "valid"
    (an empty module compiles) but is NOT a genuine rescue -- adopting it would trivially
    satisfy the deterministic minimum's import-only smoke check against an empty file, a
    false-done surface this task must not open. An empty rescue reply is treated the SAME
    as a syntax-gate failure: honest failure, never silently adopted."""
    llm = _RescueLlm(
        module_first={"helper.py": HELPER_BROKEN},
        module_repair={"helper.py": HELPER_BROKEN},
        single_file_first="   \n  \n",   # blank -- syntactically valid, semantically nothing
        single_file_repair="   \n  \n",
    )

    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is False
    assert result["done"] is False
    assert "single-file rescue produced no usable module either" in result["note"]


def test_syntax_gate_rescue_never_fires_on_a_clean_build_non_degrading(tmp_path):
    """NON-DEGRADING: a build whose modules all pass the syntax gate on the first try never
    reaches the rescue branch at all -- `build_path` stays the pre-existing "free-form"
    default and the rescue's own prompt is never sent, byte-identical to before this task."""
    llm = _RescueLlm(
        module_first={"helper.py": CLEAN_HELPER_OK, "cli.py": CLEAN_CLI_OK},
        checklist=CHECKLIST_FOR_CLEAN_BUILD,
    )

    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["build_path"] == "free-form"
    assert result["modules"] == {"helper.py": CLEAN_HELPER_OK.strip(), "cli.py": CLEAN_CLI_OK.strip()}
    assert _sf_prompt_count(llm) == 0


def test_syntax_gate_rescue_never_raises_and_does_not_loop(tmp_path):
    """Robustness: even a maximally-degenerate llm (every call returns an empty string,
    including the plan itself) never raises and never hangs -- `build_system` returns a
    normal (unshipped) result dict, and the module-build loop is never re-entered (there is
    no plan/modules at all, so the rescue branch is never even reached here)."""
    class _EmptyLlm:
        def complete(self, request):
            return _Resp("")

    result = build_system(SPEC, tmp_path / "built", llm=_EmptyLlm())

    assert result["shipped"] is False
    assert result["done"] is False
    assert isinstance(result["note"], str) and result["note"]
# #EXT-036-REQ-71 End
