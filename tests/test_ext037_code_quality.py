"""EXT-037 / REQ-8 (TASK-12) -- ``harness.code_quality``: a deterministic, stdlib-only ADVISORY
code-quality signal over model-generated systems, answering the owner's open question "are we
checking the actual code it's writing for quality?" (previously honestly NO).

Offline, deterministic -- no live model, no network, no third-party deps (no ruff/radon/
pyflakes; none are installed and none are added by this task). The load-bearing assertions are
that ``harness.system_builder.build_system`` now carries a ``quality`` field, and that a
deliberately-smelly-but-WORKING generated system still returns ``done=True`` -- proving the
signal is genuinely advisory, never a gate.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.code_quality import QualityReport, assess_quality
from harness.system_builder import _result, build_system

# #EXT-037-REQ-8 Start

# --------------------------------------------------------------------------------------------
# (1) McCabe cyclomatic complexity -- a HAND-COMPUTED known value.
# --------------------------------------------------------------------------------------------

# Hand-computed McCabe CC = 1 (base)
#   + 1 If(a>0) + 1 For + 1 If(i%2==0) + 1 If(elif a<0, parsed as a nested If in orelse)
#   + 1 While + 1 ExceptHandler(ValueError) + 1 Assert
#   + 2 comprehension-ifs (`if i > 2 if i < 8` -> one comprehension node, ifs=[.., ..])
#   + 2 BoolOp-extra-values (`a and b and c` -> 3 values -> 2 extra branch points)
#   + 1 IfExp (`a if b else c`)
#   + 2 With-items (`with open(...) as f, open(...) as g:` -> 2 withitem nodes)
# = 1 + (1+1+1+1+1+1+1+2+2+1+2) = 1 + 14 = 15
KNOWN_CC_FUNCTION = """
def sample(a, b, c):
    if a > 0:
        for i in range(b):
            if i % 2 == 0:
                print(i)
    elif a < 0:
        while b > 0:
            b -= 1
    try:
        assert c > 0
    except ValueError:
        pass
    x = [i for i in range(10) if i > 2 if i < 8]
    y = a and b and c
    z = a if b else c
    with open("f") as f, open("g") as g:
        pass
    return x, y, z
"""
KNOWN_CC = 15


def test_mccabe_complexity_hand_computed_value():
    report = assess_quality({"sample.py": KNOWN_CC_FUNCTION})
    functions = report.per_file["sample.py"]["functions"]
    assert len(functions) == 1
    assert functions[0]["name"] == "sample"
    assert functions[0]["complexity"] == KNOWN_CC
    assert report.max_complexity == KNOWN_CC
    assert report.worst_function == "sample.py:sample"
    # exactly at the HIGH_COMPLEXITY_THRESHOLD (15) -- not > 15, so NOT flagged as a smell.
    assert not any(s["category"] == "high_complexity" for s in report.smells)


# --------------------------------------------------------------------------------------------
# (2) Each structural smell detector fires on a positive example AND stays silent on clean code.
# --------------------------------------------------------------------------------------------

BARE_EXCEPT_BAD = "def f():\n    try:\n        pass\n    except:\n        pass\n"
BARE_EXCEPT_CLEAN = "def f():\n    try:\n        pass\n    except ValueError:\n        pass\n"


def test_bare_except_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": BARE_EXCEPT_BAD})
    assert any(s["category"] == "bare_except" for s in bad.smells)
    assert bad.ok is False   # bare_except is a CRITICAL smell

    clean = assess_quality({"m.py": BARE_EXCEPT_CLEAN})
    assert not any(s["category"] == "bare_except" for s in clean.smells)
    assert clean.ok is True


SWALLOW_BAD = "def f():\n    try:\n        pass\n    except Exception:\n        pass\n"
SWALLOW_CLEAN = "def f():\n    try:\n        pass\n    except Exception as exc:\n        log(exc)\n"


def test_swallowed_exception_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": SWALLOW_BAD})
    assert any(s["category"] == "swallowed_exception" for s in bad.smells)
    assert bad.ok is False   # swallowed_exception is a CRITICAL smell

    clean = assess_quality({"m.py": SWALLOW_CLEAN})
    assert not any(s["category"] == "swallowed_exception" for s in clean.smells)
    assert clean.ok is True


MUTABLE_DEFAULT_BAD = "def f(items=[]):\n    return items\n"
MUTABLE_DEFAULT_CLEAN = "def f(items=None):\n    return items if items is not None else []\n"


def test_mutable_default_arg_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": MUTABLE_DEFAULT_BAD})
    assert any(s["category"] == "mutable_default_arg" for s in bad.smells)
    # NOT a critical category -- advisory only, ok stays True.
    assert bad.ok is True

    clean = assess_quality({"m.py": MUTABLE_DEFAULT_CLEAN})
    assert not any(s["category"] == "mutable_default_arg" for s in clean.smells)


STAR_IMPORT_BAD = "from os import *\n\n\ndef f():\n    return 1\n"
STAR_IMPORT_CLEAN = "from os import path\n\n\ndef f():\n    return 1\n"


def test_star_import_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": STAR_IMPORT_BAD})
    assert any(s["category"] == "star_import" for s in bad.smells)
    assert bad.ok is True   # not a critical category

    clean = assess_quality({"m.py": STAR_IMPORT_CLEAN})
    assert not any(s["category"] == "star_import" for s in clean.smells)


def _long_function_code(n_lines: int = 85) -> str:
    body = "".join(f"    x_{i} = {i}\n" for i in range(n_lines))
    return "def longfn():\n" + body + "    return 0\n"


def test_long_function_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": _long_function_code(85)})
    assert any(s["category"] == "long_function" for s in bad.smells)

    clean = assess_quality({"m.py": "def shortfn():\n    return 0\n"})
    assert not any(s["category"] == "long_function" for s in clean.smells)


def _many_ifs_code(n: int = 20) -> str:
    body = "".join(f"    if x == {i}:\n        pass\n" for i in range(n))
    return "def manyifs(x):\n" + body + "    return x\n"


def test_high_complexity_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": _many_ifs_code(20)})  # CC = 1 + 20 = 21 > 15
    assert any(s["category"] == "high_complexity" for s in bad.smells)

    clean = assess_quality({"m.py": "def simplefn(x):\n    return x + 1\n"})
    assert not any(s["category"] == "high_complexity" for s in clean.smells)


DEEP_NEST_BAD = (
    "def deepnest(x):\n"
    "    if x:\n"
    "        if x:\n"
    "            if x:\n"
    "                if x:\n"
    "                    if x:\n"
    "                        if x:\n"
    "                            pass\n"
    "    return x\n"
)


def test_deep_nesting_smell_fires_and_is_silent_on_clean_code():
    bad = assess_quality({"m.py": DEEP_NEST_BAD})   # 6 levels deep > 5
    assert any(s["category"] == "deep_nesting" for s in bad.smells)

    clean = assess_quality({"m.py": "def shallow(x):\n    if x:\n        return x\n    return 0\n"})
    assert not any(s["category"] == "deep_nesting" for s in clean.smells)


# --------------------------------------------------------------------------------------------
# (3) assess_quality on genuinely clean code -> empty smells + ok=True.
# --------------------------------------------------------------------------------------------

CLEAN_SYSTEM = {
    "helper.py": "def add(a, b):\n    return a + b\n",
    "cli.py": (
        "from helper import add\n\n\n"
        "def main():\n    print(add(1, 2))\n\n\n"
        "if __name__ == '__main__':\n    main()\n"
    ),
}


def test_assess_quality_clean_code_has_no_smells_and_is_ok():
    report = assess_quality(CLEAN_SYSTEM)
    assert isinstance(report, QualityReport)
    assert report.smells == []
    assert report.ok is True
    assert report.max_complexity >= 1
    assert set(report.per_file) == {"helper.py", "cli.py"}


def test_assess_quality_never_raises_on_garbage_input():
    assert assess_quality(None).ok is True
    assert assess_quality(12345).ok is True
    assert assess_quality({"broken.py": "def f(:\n    pass\n"}).ok is True   # unparseable, skipped


# --------------------------------------------------------------------------------------------
# (4)/(5) build_system wiring: `quality` field is present, AND advisory-not-gating (a
# deliberately-smelly-but-WORKING generated system still returns done=True).
# --------------------------------------------------------------------------------------------

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

# Syntactically valid, WORKING (adds correctly) -- but carries a deliberate `bare_except`
# smell around code that never actually raises, so the checklist still passes.
HELPER_SMELLY_BUT_WORKING = (
    "def add(a, b):\n"
    "    try:\n"
    "        return a + b\n"
    "    except:\n"
    "        pass\n"
)
CLI_OK = (
    "from helper import add\n\n\n"
    "def main():\n    print(add(1, 2))\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)
CHECKLIST_PASSING = """[
  {"name": "adds correctly", "code": "from helper import add\\nassert add(1, 2) == 3\\n"}
]"""

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Minimal canned-response stub mirroring the ``.complete(LlmRequest) -> .text`` convention
    used across every other EXT-036/EXT-037 offline `system_builder` test."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, checklist=CHECKLIST_PASSING) -> None:
        self.plan = plan
        self.module_first = module_first or {"helper.py": HELPER_SMELLY_BUT_WORKING, "cli.py": CLI_OK}
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
            return _Resp("")   # never needed -- canned modules are already syntactically valid
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


def test_build_system_result_carries_quality_field(tmp_path):
    """A normal (clean) fake-llm build now carries a populated, advisory `quality` field."""
    spec = "A tiny two-module system: helper + CLI that prints the sum."
    llm = _CannedLlm(module_first={"helper.py": "def add(a, b):\n    return a + b\n", "cli.py": CLI_OK})
    result = build_system(spec, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["quality"] is not None
    assert result["quality"]["ok"] is True
    assert result["quality"]["smells"] == []
    assert set(result["quality"]["per_file"]) == {"helper.py", "cli.py"}


def test_smelly_but_working_build_still_reports_done_true_advisory_not_gating(tmp_path):
    """THE LOAD-BEARING PROOF (REQ-8): a deliberately-smelly (bare `except:`) but genuinely
    WORKING generated system still ships and passes -- `quality.ok` is False (a critical smell
    fired) while `done` stays True. The quality signal NEVER gates the build."""
    root = tmp_path / "built"
    llm = _CannedLlm()   # module_first defaults to HELPER_SMELLY_BUT_WORKING
    result = build_system(
        "A tiny two-module system: a helper that adds two numbers, and a CLI that prints the sum.",
        root, llm=llm,
    )

    assert result["shipped"] is True
    assert result["done"] is True                     # ADVISORY: smelly code still ships/passes
    assert result["unmet"] == []
    assert result["quality"] is not None
    assert result["quality"]["ok"] is False            # bare_except IS flagged...
    assert any(s["category"] == "bare_except" for s in result["quality"]["smells"])
    # ...but it never touched `done`/`unmet`/`shipped` -- purely additive.


# --------------------------------------------------------------------------------------------
# (6) `_result`'s omitted `quality` kwarg keeps every pre-existing caller byte-compatible.
# --------------------------------------------------------------------------------------------

def test_result_omitted_quality_defaults_to_none_byte_compatible():
    out = _result(modules={"a.py": "x = 1\n"}, shipped=True, done=True, note="ok")
    assert out["quality"] is None
    # every other pre-existing field is untouched by this task
    assert out["modules"] == {"a.py": "x = 1\n"}
    assert out["shipped"] is True
    assert out["done"] is True
    assert out["unmet"] == []
    assert out["security"] is None
# #EXT-037-REQ-8 End
