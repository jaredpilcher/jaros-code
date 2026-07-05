"""EXT-036 TASK-37 (REQ-26): acceptance-completeness / done-honesty fix (task #118).

MEASURED PROBLEM (2026-07-05): `_derive_acceptance_checklist(spec, mods, llm)` proposes
checks via the MODEL, so the checklist VARIES in completeness for the IDENTICAL sentence --
a single datastore build derived 3 checks, another draw of the SAME sentence derived only 1.
`build_system_best_of_k` then EARLY-EXITS on whichever draw derived the fewest/easiest
self-checks and reports `done=True` on a sparse 1-check bar -- NOT real correctness. The model
was also independently found to systematically MISS a 'usage'/CLI-help check.

THE FIX: a DETERMINISTIC MINIMUM checklist (`_minimum_acceptance`), derived from the spec
sentence + the built module API alone (NO model call, so it is IDENTICAL for the same input
every time), that the model's own proposals can only ADD TO
(`_compose_acceptance_checklist`) -- never shrink below. `build_system` and
`build_system_best_of_k`'s `_score_build_attempt` both now score against this COMPOSED,
minimum-inclusive bar.

OFFLINE -- no live model. Canned/fake `llm` stubs only (same `.complete(LlmRequest) -> .text`
convention as every other EXT-036 test file).
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    build_system,
    build_system_best_of_k,
    _compose_acceptance_checklist,
    _extract_command_tokens,
    _minimum_acceptance,
    _minimum_entry_filename,
)

DATASTORE_SPEC = (
    "A tiny notes datastore CLI in main.py: supports 'add <text>' and 'list' commands, "
    "each read one per line from stdin, printing the result of each on its own line."
)

DATASTORE_PLAN = {
    "modules": [
        {"name": "main.py", "responsibility": "notes datastore CLI: add/list over stdin",
         "exports": [{"name": "add_note", "signature": "def add_note(text):"},
                     {"name": "list_notes", "signature": "def list_notes():"},
                     {"name": "main", "signature": "def main():"}],
         "imports": []}
    ],
    "entrypoint": "main.py",
    "acceptance": "add/list commands work over stdin",
}


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Routes `.complete()` by prompt stage, mirroring every other EXT-036 stub. Configurable
    per-tier checklist responses so tests can exercise "the model derives fewer/more checks
    than the deterministic minimum"."""

    def __init__(self, *, plan=None, module_first=None,
                 checklist_first=None, checklist_strict=None, checklist_subprocess=None) -> None:
        self.plan = plan if plan is not None else json.dumps(DATASTORE_PLAN)
        self.module_first = module_first or {}
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
            return _Resp("not json at all")
        if "COMPLETE Python module" in prompt:
            import re
            m = re.search(r"module `([^`]+)`", prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


# --- (unit) _extract_command_tokens ------------------------------------------------------

def test_extract_command_tokens_finds_quoted_and_verb_tokens():
    toks = _extract_command_tokens(DATASTORE_SPEC)
    assert "add" in toks
    assert "list" in toks


def test_extract_command_tokens_conservative_on_a_plain_sentence():
    # no quoted commands, no allow-listed verbs -- must NOT hallucinate a command
    assert _extract_command_tokens("A tiny calculator module with add(a, b), used by a CLI.") \
        in ([], ["add"])   # "add(a, b)" -- "add" is a legitimate allow-listed verb token


def test_extract_command_tokens_never_raises_on_bad_input():
    assert _extract_command_tokens(None) == []
    assert _extract_command_tokens("") == []
    assert _extract_command_tokens(123) == []


# --- (unit) _minimum_entry_filename -------------------------------------------------------

def test_minimum_entry_filename_prefers_plan_entrypoint():
    mods = DATASTORE_PLAN["modules"]
    assert _minimum_entry_filename(mods, DATASTORE_PLAN) == "main.py"


def test_minimum_entry_filename_falls_back_to_main_py_convention():
    mods = [{"name": "helper.py", "exports": []}, {"name": "main.py", "exports": []}]
    assert _minimum_entry_filename(mods, None) == "main.py"


def test_minimum_entry_filename_never_raises_on_bad_input():
    assert _minimum_entry_filename([], None) is None
    assert _minimum_entry_filename(None, None) is None
    assert _minimum_entry_filename(None, {"entrypoint": 123}) is None


# --- (core) the minimum ALWAYS includes usage + one-per-detected-command + smoke ----------

def test_minimum_always_includes_usage_and_smoke_and_detected_commands():
    mods = DATASTORE_PLAN["modules"]
    checks = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    names = [c["name"] for c in checks]
    assert any(n.startswith("smoke:") for n in names)
    assert any("usage/--help" in n for n in names)
    assert any("'add'" in n for n in names)
    assert any("'list'" in n for n in names)


def test_minimum_is_empty_only_when_there_are_no_modules_at_all():
    assert _minimum_acceptance(DATASTORE_SPEC, [], DATASTORE_PLAN) == []
    assert _minimum_acceptance(DATASTORE_SPEC, None, None) == []


def test_minimum_never_raises_on_malformed_plan_or_mods():
    assert _minimum_acceptance(None, [{"name": "x.py"}], "not a dict") == \
        _minimum_acceptance(None, [{"name": "x.py"}], None)


# --- (core) deterministic + stable across repeated calls (same sentence -> same minimum) --

def test_minimum_is_deterministic_across_repeated_calls():
    mods = DATASTORE_PLAN["modules"]
    a = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    b = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    assert a == b   # byte-identical -- no model call, no randomness


# --- (core) the model's proposals AUGMENT, never SHRINK, the minimum ----------------------

def test_composed_checklist_is_never_sparser_than_the_minimum():
    mods = DATASTORE_PLAN["modules"]
    llm_zero = _CannedLlm(checklist_first="[]", checklist_strict="[]", checklist_subprocess="[]")
    llm_rich = _CannedLlm(checklist_first=json.dumps([
        {"name": "extra check 1", "code": "assert 1 == 1\n"},
        {"name": "extra check 2", "code": "assert 2 == 2\n"},
        {"name": "extra check 3", "code": "assert 3 == 3\n"},
    ]))
    sparse = _compose_acceptance_checklist(DATASTORE_SPEC, mods, llm_zero, DATASTORE_PLAN)
    rich = _compose_acceptance_checklist(DATASTORE_SPEC, mods, llm_rich, DATASTORE_PLAN)
    minimum = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)

    # BOTH draws are measured against a bar that is never sparser than the minimum, no matter
    # how few (or many) self-checks the model happened to derive on that draw.
    assert len(sparse) >= len(minimum)
    assert len(rich) >= len(minimum)
    minimum_names = {c["name"] for c in minimum}
    assert minimum_names <= {c["name"] for c in sparse}
    assert minimum_names <= {c["name"] for c in rich}
    # the model's extra proposals AUGMENT -- rich draw has strictly MORE checks than sparse
    assert len(rich) > len(sparse)


def test_composed_checklist_dedups_a_model_proposal_identical_to_a_minimum_check():
    mods = DATASTORE_PLAN["modules"]
    minimum = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    dup_check = json.dumps([{"name": minimum[0]["name"], "code": minimum[0]["code"]}])
    llm = _CannedLlm(checklist_first=dup_check)
    composed = _compose_acceptance_checklist(DATASTORE_SPEC, mods, llm, DATASTORE_PLAN)
    # no double-count: total length is exactly the minimum's (the "duplicate" model proposal
    # contributed nothing new)
    assert len(composed) == len(minimum)


def test_composed_checklist_never_raises_when_the_model_call_raises():
    class _RaisingLlm:
        def complete(self, request):
            raise RuntimeError("boom")

    mods = DATASTORE_PLAN["modules"]
    composed = _compose_acceptance_checklist(DATASTORE_SPEC, mods, _RaisingLlm(), DATASTORE_PLAN)
    minimum = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    # the deterministic minimum survives even when the model is completely unreachable
    assert composed == minimum


# --- (end to end) a build that self-derives only 1 check is STILL scored against the full,
# minimum-inclusive bar -- a genuinely broken primary command flips `done` to False even
# though the model itself proposed nothing that would have caught it --------------------

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

# BROKEN: crashes on a fresh run (reads the store before ever creating it) -- the notes-
# sqlite-cli bug CLASS, reproduced generically.
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

# a SINGLE trivial self-derived check the model happens to propose on this draw -- passes
# the executable-check filter but never actually exercises the broken `add` branch.
ONE_TRIVIAL_MODEL_CHECK = json.dumps([{"name": "module imports", "code": "import main\n"}])


def test_a_build_that_self_derives_only_one_trivial_check_still_gets_scored_against_the_full_bar(tmp_path):
    """THE CORE FIX (task #118): even though the model proposed only ONE trivially-passing
    self-check (an import that never exercises the broken `add` command), the DETERMINISTIC
    minimum's 'add' command check independently catches the crash -- `done` is honestly
    False, not a hollow pass on the sparse 1-check bar."""
    llm = _CannedLlm(plan=CLI_PLAN, module_first={"main.py": ADD_WITHOUT_INIT_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(CLI_SPEC, tmp_path / "broken_cli", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"]
    # the trivial self-check itself passed (proving it's not JUST that check failing) --
    # it's the deterministic minimum's own 'add' check that caught the real bug.
    assert "module imports" not in result["unmet"]
    assert any("'add'" in u for u in result["unmet"])


FIXED_CLI = (
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


def test_no_new_false_negative_for_a_genuinely_working_cli_scored_only_by_the_minimum(tmp_path):
    """VALUE-PRESERVING: the SAME composed bar reports `done=True` once the CLI is genuinely
    fixed -- the minimum floor never introduces a false negative for working behavior."""
    llm = _CannedLlm(plan=CLI_PLAN, module_first={"main.py": FIXED_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(CLI_SPEC, tmp_path / "fixed_cli", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


# --- (end to end) best-of-k selects on the FULL (minimum-inclusive) bar -------------------

class _AttemptAwareLlm:
    """The FIRST `build_system()` invocation this llm serves ships the BROKEN CLI and derives
    only the one trivial self-check that would (falsely) look like a pass; every SUBSEQUENT
    invocation ships the FIXED CLI. Attempt boundaries tracked by counting 'build PLAN' calls
    (exactly one per `build_system()` invocation)."""

    def __init__(self) -> None:
        self.attempt = -1
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            self.attempt += 1
            return _Resp(CLI_PLAN)
        broken = self.attempt == 0
        if "SYNTAX ERROR" in prompt or "COMPLETE Python module" in prompt:
            return _Resp(ADD_WITHOUT_INIT_CLI if broken else FIXED_CLI)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(ONE_TRIVIAL_MODEL_CHECK)
        return _Resp("")


def test_best_of_k_selects_on_the_full_bar_not_the_sparse_self_checklist(tmp_path):
    """best-of-k must NOT early-exit on attempt 1 just because its single self-derived check
    happens to pass -- the deterministic minimum (task #118) genuinely fails on the broken
    CLI, so best-of-k must run the second attempt and land the FIXED system."""
    root = tmp_path / "built"
    llm = _AttemptAwareLlm()
    result = build_system_best_of_k(CLI_SPEC, root, llm=llm, k=2)

    assert result["attempts_run"] == 2   # did NOT early-exit on attempt 1's sparse pass
    assert result["done"] is True
    assert (root / "main.py").read_text(encoding="utf-8").strip() == FIXED_CLI.strip()
