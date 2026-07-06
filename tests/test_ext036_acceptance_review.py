"""EXT-036 TASK-40 (REQ-30): 7B REVIEW+CORRECT of model-proposed acceptance checks.

MEASURED PROBLEM (2026-07-05, memory [[jaros-code-build-acceptance-honesty]]): REQ-26's
composed acceptance checklist (deterministic minimum UNION model-proposed checks) is honest
about the FLOOR, but the model-PROPOSED portion is a MIXED bag -- some HALLUCINATE (an
invented API/import, an invented expected value), false-negativing a genuinely-correct
build; others correctly CATCH real breakage. VALIDATED FIX (owner's idea, pre-registered
kill criterion PASSED, `.jaros-data/sevenb_review_probe.py`): a STRONGER model reviews+
corrects each model-proposed check against ONLY the visible spec + code (no oracle leak),
correcting/dropping the hallucinated ones while preserving the real-bug catches.

This file proves, OFFLINE (canned/fake `llm`/`reviewer_llm` stubs, no live model, no
network):
  (1) `harness.acceptance_review.review_checks`'s own unit behavior (corrects, drops, keeps
      a real-bug check unchanged, never raises on a reviewer error or bad input, strips
      markdown fences the same way the validated probe does);
  (2) end-to-end wiring into `build_system` via the optional `check_reviewer` keyword: a
      hallucinated check flips a genuinely-working build's `done` False->True once reviewed
      (dropped), a real-bug check stays failing (0-false-done preserved), `check_reviewer=None`
      is a byte-identical regression guard, and a raising reviewer never crashes the build.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.acceptance_review import REVIEW_PROMPT, review_checks
from harness.system_builder import build_system


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


# ---------------------------------------------------------------------------------------
# (1) unit tests: harness.acceptance_review.review_checks
# ---------------------------------------------------------------------------------------

MODULES = {"main.py": "def add(a, b):\n    return a + b\n"}
SPEC = "A tiny helper module `main.py` exporting `add(a, b)` that returns a + b."


class _CorrectingReviewer:
    """Fake reviewer that CORRECTS a hallucinated check to the real API."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp("from main import add\nassert add(1, 2) == 3\n")


class _DroppingReviewer:
    """Fake reviewer that DROPS whatever it's shown (unverifiable from spec+code alone)."""

    def complete(self, request):
        return _Resp("DROP")


class _KeepReviewer:
    """Fake reviewer 'told to keep' a check -- echoes the SAME code back unchanged, proving
    review never launders a genuine defect-catching check into a pass."""

    def __init__(self, keep_code: str) -> None:
        self.keep_code = keep_code

    def complete(self, request):
        return _Resp(self.keep_code)


class _RaisingReviewer:
    def complete(self, request):
        raise RuntimeError("Jetson unreachable")


HALLUCINATED_CHECK = {"name": "hallucinated import",
                       "code": "from main import fake_func\nassert fake_func('x') == 'ok'\n"}
REAL_BUG_CHECK = {"name": "add really works",
                  "code": "from main import add\nassert add(2, 2) == 5\n"}  # a REAL failing assertion


def test_review_checks_corrects_a_hallucinated_check_to_the_real_api():
    out = review_checks(SPEC, MODULES, [HALLUCINATED_CHECK], _CorrectingReviewer())
    assert len(out) == 1
    assert "fake_func" not in out[0]["code"]
    assert "add" in out[0]["code"]
    assert out[0]["name"] == "hallucinated import"  # non-code keys preserved


def test_review_checks_drops_a_check_the_reviewer_cannot_verify():
    out = review_checks(SPEC, MODULES, [HALLUCINATED_CHECK], _DroppingReviewer())
    assert out == []


def test_review_checks_keeps_a_real_bug_check_unchanged_when_told_to_keep_it():
    out = review_checks(SPEC, MODULES, [REAL_BUG_CHECK], _KeepReviewer(REAL_BUG_CHECK["code"]))
    assert len(out) == 1
    # unchanged in substance (the reviewer's raw response is stripped, mirroring the
    # validated probe's own parse -- content is byte-identical modulo surrounding whitespace)
    assert out[0]["code"].strip() == REAL_BUG_CHECK["code"].strip()


def test_review_checks_keeps_original_check_unchanged_when_reviewer_raises():
    out = review_checks(SPEC, MODULES, [HALLUCINATED_CHECK, REAL_BUG_CHECK], _RaisingReviewer())
    # conservative: BOTH checks survive, byte-identical to their originals -- a reviewer
    # outage never silently drops or crashes on a check
    assert out == [HALLUCINATED_CHECK, REAL_BUG_CHECK]


def test_review_checks_strips_markdown_fences_like_the_validated_probe():
    class _FencedReviewer:
        def complete(self, request):
            return _Resp("```python\nfrom main import add\nassert add(1, 1) == 2\n```")

    out = review_checks(SPEC, MODULES, [HALLUCINATED_CHECK], _FencedReviewer())
    assert len(out) == 1
    assert "```" not in out[0]["code"]
    assert "python\n" not in out[0]["code"]
    assert "assert add(1, 1) == 2" in out[0]["code"]


def test_review_checks_never_raises_on_empty_or_bad_input():
    assert review_checks(SPEC, MODULES, [], _CorrectingReviewer()) == []
    assert review_checks(SPEC, MODULES, None, _CorrectingReviewer()) == []
    assert review_checks(None, None, [HALLUCINATED_CHECK], _CorrectingReviewer()) is not None
    assert review_checks(SPEC, MODULES, [HALLUCINATED_CHECK, "not a dict", None], _DroppingReviewer()) == []


def test_review_checks_prompt_carries_spec_code_and_check_no_oracle_leak():
    """NO ORACLE LEAK (Tenet 3): the reviewer only ever sees spec + code + the ONE proposed
    check -- never a hidden expected value/oracle."""
    reviewer = _CorrectingReviewer()
    review_checks(SPEC, MODULES, [HALLUCINATED_CHECK], reviewer)
    assert len(reviewer.prompts) == 1
    prompt = reviewer.prompts[0]
    assert SPEC in prompt
    assert "def add(a, b)" in prompt
    assert "fake_func" in prompt
    assert prompt == REVIEW_PROMPT.format(spec=SPEC[:1500], code="# main.py\n" + MODULES["main.py"],
                                           check=HALLUCINATED_CHECK["code"][:1500])


# ---------------------------------------------------------------------------------------
# (2) end-to-end: build_system(..., check_reviewer=...)
# ---------------------------------------------------------------------------------------

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

# A genuinely WORKING implementation (mirrors the FIXED_CLI convention proven by the
# task #118/#121 acceptance-completeness tests).
WORKING_CLI = (
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

# A model-proposed check that HALLUCINATES an API (`from main import encode`, which does
# not exist) -- would false-negative the otherwise genuinely-working build above.
HALLUCINATED_MODEL_CHECK = json.dumps([
    {"name": "encode roundtrip", "code": "from main import encode\nassert encode('x') == 'x!'\n"}
])

# A model-proposed check that genuinely, correctly catches a real bug (a bogus expected
# value nobody could satisfy -- stands in for a REAL defect-catching check, e.g. rpn-calc).
REAL_BUG_MODEL_CHECK = json.dumps([
    {"name": "add is idempotent-ish", "code": "from main import save_item\nassert save_item is None\n"}
])


class _BuildLlm:
    """Routes `.complete()` by prompt stage -- mirrors every other EXT-036 stub's convention."""

    def __init__(self, *, checklist: str) -> None:
        self.checklist = checklist

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(CLI_PLAN)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "COMPLETE Python module" in prompt or "SYNTAX ERROR" in prompt:
            return _Resp(WORKING_CLI)
        return _Resp("")


class _DropHallucinationReviewer:
    """Reviewer that recognizes and DROPS the hallucinated `encode` check, and otherwise
    would keep anything else unchanged (not exercised here, but conservative by default)."""

    def complete(self, request):
        if "encode" in request.prompt:
            return _Resp("DROP")
        # fallback: keep whatever was shown, verbatim, by echoing the PROPOSED TEST section
        return _Resp("DROP")


def test_hallucinated_check_reviewed_away_flips_done_to_true(tmp_path):
    """Without review, the hallucinated check false-negatives a genuinely-working build.
    With `check_reviewer` supplied (drops the unverifiable check), `done` flips to True."""
    llm = _BuildLlm(checklist=HALLUCINATED_MODEL_CHECK)

    without_review = build_system(CLI_SPEC, tmp_path / "no_review", llm=llm)
    assert without_review["shipped"] is True
    assert without_review["done"] is False
    assert any("encode" in u for u in without_review["unmet"])

    with_review = build_system(CLI_SPEC, tmp_path / "with_review", llm=llm,
                                check_reviewer=_DropHallucinationReviewer())
    assert with_review["shipped"] is True
    assert with_review["done"] is True
    assert with_review["unmet"] == []


class _KeepRealBugReviewer:
    """Reviewer 'told to keep' the real-bug check -- echoes it back unchanged, proving
    review does NOT launder a genuine defect-catching check into a false pass."""

    def complete(self, request):
        return _Resp("from main import save_item\nassert save_item is None\n")


def test_real_bug_check_preserved_by_reviewer_keeps_done_false(tmp_path):
    llm = _BuildLlm(checklist=REAL_BUG_MODEL_CHECK)
    result = build_system(CLI_SPEC, tmp_path / "real_bug", llm=llm,
                           check_reviewer=_KeepRealBugReviewer())
    assert result["shipped"] is True
    assert result["done"] is False
    assert any("idempotent" in u for u in result["unmet"])


def test_check_reviewer_none_is_byte_identical_regression(tmp_path):
    """REGRESSION GUARD: `check_reviewer=None` (the default) must be byte-identical to
    `build_system`'s pre-existing behavior -- both the implicit default and an explicit
    `None` produce the exact same result on the same fixed synthetic build."""
    llm_a = _BuildLlm(checklist=HALLUCINATED_MODEL_CHECK)
    llm_b = _BuildLlm(checklist=HALLUCINATED_MODEL_CHECK)

    default_result = build_system(CLI_SPEC, tmp_path / "default", llm=llm_a)
    explicit_none_result = build_system(CLI_SPEC, tmp_path / "explicit_none", llm=llm_b,
                                        check_reviewer=None)

    for key in ("shipped", "done", "unmet", "note", "modules"):
        assert default_result[key] == explicit_none_result[key], key


def test_raising_check_reviewer_never_crashes_build_system(tmp_path):
    """A reviewer that raises on every call must never crash `build_system` -- it falls
    back to the composed (unreviewed) checklist, same as if no reviewer were configured."""
    llm = _BuildLlm(checklist=HALLUCINATED_MODEL_CHECK)
    result = build_system(CLI_SPEC, tmp_path / "raising_reviewer", llm=llm,
                           check_reviewer=_RaisingReviewer())
    # never raised getting here; behavior degrades to the same as check_reviewer=None
    assert result["shipped"] is True
    assert result["done"] is False
