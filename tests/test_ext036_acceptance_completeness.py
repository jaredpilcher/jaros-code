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
    _derive_kv_roundtrip,
    _derive_roundtrip_pair,
    _extract_command_tokens,
    _has_error_marker,
    _minimum_acceptance,
    _minimum_entry_filename,
    _run_check,
)
from harness.graph_dsl import SQLITE_KV_LEAF
from harness.system_suite import ALL_CREATION_TASKS

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


# ===========================================================================================
# TASK-38 (REQ-27): behavioral acceptance honesty -- error-in-output detection + add/list
# round-trip (task #121). MEASURED PROBLEM: a datastore CLI that gracefully CATCHES its own
# exception and PRINTS it at rc=0 (no traceback at all) PASSED the pre-existing no-crash
# check while genuinely broken (add never persisted). This section proves the fix.
# ===========================================================================================

# --- (unit) _has_error_marker --------------------------------------------------------------

def test_has_error_marker_catches_the_measured_graceful_error_phrasing():
    text = ("An error occurred while listing notes: DatabaseManager.__init__() "
            "missing 1 required positional argument: 'db_path'")
    assert _has_error_marker(text) is True


def test_has_error_marker_catches_a_bare_error_prefixed_line():
    assert _has_error_marker("Error: could not open the store\n") is True
    assert _has_error_marker("Exception: boom\n") is True
    assert _has_error_marker("Traceback (most recent call last):\n  ...\n") is True


def test_has_error_marker_catches_not_found_phrase():
    assert _has_error_marker("note not found\n") is True


def test_has_error_marker_does_not_flag_argparse_style_usage_error_line():
    # argparse's own error line is PREFIXED by the program name -- never bare at line-start --
    # so it must NOT be treated as the graceful-error-print pattern this check targets.
    usage_output = (
        "usage: main.py [-h] {add,list} ...\n"
        "main.py: error: the following arguments are required: command\n"
    )
    assert _has_error_marker(usage_output) is False


def test_has_error_marker_does_not_flag_error_as_legitimate_data():
    # the word "error" appearing as ordinary DATA (not a standalone marker phrase / line-start
    # exception name) must never false-fail a genuinely-working command.
    assert _has_error_marker("Server error rate: 0.02\n") is False
    assert _has_error_marker("log: connection errors this week: 3\n") is False


def test_has_error_marker_never_raises_on_bad_input():
    assert _has_error_marker(None) is False
    assert _has_error_marker("") is False
    assert _has_error_marker(123) is False


# --- (unit) _derive_roundtrip_pair -----------------------------------------------------------

def test_derive_roundtrip_pair_finds_add_and_list():
    assert _derive_roundtrip_pair(DATASTORE_SPEC) == ("add", "list")


def test_derive_roundtrip_pair_conservative_when_only_one_side_present():
    assert _derive_roundtrip_pair("A calculator CLI with an add(a, b) function.") is None
    assert _derive_roundtrip_pair("Show all the widgets in a table.") is None


def test_derive_roundtrip_pair_none_when_neither_present():
    assert _derive_roundtrip_pair("A tiny CLI that converts Celsius to Fahrenheit.") is None


def test_derive_roundtrip_pair_never_raises_on_bad_input():
    assert _derive_roundtrip_pair(None) is None
    assert _derive_roundtrip_pair("") is None
    assert _derive_roundtrip_pair(123) is None


# --- (end to end) a CLI that gracefully catches+prints an error at rc=0 is no longer a
# hollow pass -- the strengthened minimum's error-marker check catches it ------------------

ROUNDTRIP_SPEC = (
    "A tiny command-line notes datastore in main.py: `python main.py add <text...>` adds a "
    "note and prints `added`; `python main.py list` lists every note, one per line."
)

ROUNDTRIP_PLAN = json.dumps({
    "modules": [
        {"name": "main.py",
         "responsibility": "notes datastore CLI: add persists, list shows",
         "exports": [{"name": "add_note", "signature": "def add_note(text):"},
                     {"name": "list_notes", "signature": "def list_notes():"}],
         "imports": []}
    ],
    "entrypoint": "main.py",
    "acceptance": "add persists a note, list shows it",
})

# BROKEN (the measured bug CLASS): `add_note` is a silent no-op (never persists) and
# `list_notes` gracefully catches its own internal error and PRINTS it -- rc=0, no traceback
# at all -- exactly the false-done pattern MEASURED live on notes-sqlite-cli.
GRACEFUL_ERROR_CLI = (
    "import sys\n\n"
    "def add_note(text):\n"
    "    pass  # BUG: never actually persists\n\n"
    "def list_notes():\n"
    "    try:\n"
    "        raise TypeError(\"__init__() missing 1 required positional argument: 'db_path'\")\n"
    "    except Exception as e:\n"
    "        print('An error occurred while listing notes: ' + str(e))\n\n"
    "if __name__ == '__main__':\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'add':\n"
    "        add_note(' '.join(sys.argv[2:]))\n"
    "        print('added')\n"
    "    elif len(sys.argv) > 1 and sys.argv[1] == 'list':\n"
    "        list_notes()\n"
)


def test_graceful_error_at_rc0_is_caught_and_done_is_false(tmp_path):
    """THE CORE FIX (REQ-27, task #121): a CLI that gracefully catches+prints its own error at
    exit-code 0 (no traceback, so the PRE-EXISTING no-crash check alone would have passed it)
    is now correctly caught by the strengthened error-marker check -- `done` is honestly
    False, not a hollow pass."""
    llm = _CannedLlm(plan=ROUNDTRIP_PLAN, module_first={"main.py": GRACEFUL_ERROR_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(ROUNDTRIP_SPEC, tmp_path / "graceful_error_cli", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert result["unmet"]


# WORKING: add_note genuinely persists to a real file, list_notes genuinely reads it back.
WORKING_ROUNDTRIP_CLI = (
    "import json\n"
    "import os\n"
    "import sys\n\n"
    "STORE = 'notes.json'\n\n"
    "def add_note(text):\n"
    "    data = []\n"
    "    if os.path.exists(STORE):\n"
    "        with open(STORE) as f:\n"
    "            data = json.load(f)\n"
    "    data.append(text)\n"
    "    with open(STORE, 'w') as f:\n"
    "        json.dump(data, f)\n\n"
    "def list_notes():\n"
    "    if not os.path.exists(STORE):\n"
    "        return []\n"
    "    with open(STORE) as f:\n"
    "        return json.load(f)\n\n"
    "if __name__ == '__main__':\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == 'add':\n"
    "        add_note(' '.join(sys.argv[2:]))\n"
    "        print('added')\n"
    "    elif len(sys.argv) > 1 and sys.argv[1] == 'list':\n"
    "        for n in list_notes():\n"
    "            print(n)\n"
)


def test_working_add_list_roundtrip_yields_done_true(tmp_path):
    """VALUE-PRESERVING: a REAL working add+list datastore (add persists, list genuinely
    reads it back, including the round-trip check's own sentinel) still gets `done=True` --
    the strengthened floor introduces no new false negative for genuinely-working behavior."""
    llm = _CannedLlm(plan=ROUNDTRIP_PLAN, module_first={"main.py": WORKING_ROUNDTRIP_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(ROUNDTRIP_SPEC, tmp_path / "working_roundtrip_cli", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


# ===========================================================================================
# REQ-40 (TASK-52): KEY-VALUE-aware round-trip -- fixes a MEASURED false-negative sitting
# directly beneath REQ-27's own add/list round-trip. The VERIFIED-CORRECT SQLite-kv leaf
# (`graph_dsl.SQLITE_KV_LEAF`) FAILED `_minimum_acceptance` on exactly one check --
# `minimum: 'create'+'get' round-trip persists` -- because (1) `_ADD_LIKE_WORDS` has no
# "set"/"put"/"store", so the sentence's real write verb ("set") was never matched and the
# prose word "create" was mis-picked instead, and (2) the add/list check's bare `<list>` (no
# key) structurally cannot verify a `set <key> <value>`/`get <key>` contract. This section
# proves the KEY-VALUE-aware fix.
# ===========================================================================================

# --- (unit) _derive_kv_roundtrip -----------------------------------------------------------

KV_SPEC = (
    "A tiny command-line key-value store in main.py, backed by a database file on disk. "
    "Running it as `python main.py set <key> <value>` stores value under key and prints "
    "`ok`. Running it as `python main.py get <key>` prints the stored value, or `none` if "
    "absent. A value set in one run of the program must still be retrievable via get in a "
    "completely separate later run of the program -- it must be persisted to disk, not just "
    "kept in memory for the current process."
)

KV_PLAN = json.dumps({
    "modules": [
        {"name": "main.py",
         "responsibility": "key-value store CLI: set persists to disk, get reads it back",
         "exports": [{"name": "main", "signature": "def main():"}],
         "imports": []}
    ],
    "entrypoint": "main.py",
    "acceptance": "set persists a value, get reads it back across separate runs",
})

# a stdin-driven multi-command SESSION protocol (like `kv-store-ttl-cli`/`lru-cache-cli` in
# the real held-out suite) also names both "set" and "get" as whole words, but a per-command
# subprocess invocation is the WRONG shape for it -- must NOT trigger the KV round-trip.
STDIN_SESSION_KV_SPEC = (
    "An in-memory key-value store. Running it as `python main.py` (no command-line "
    "arguments), it reads commands from standard input, one command per line, until "
    "standard input is exhausted (EOF). Supported commands: `set <key> <value>` stores it "
    "and prints ok; `get <key>` prints the value if present, or none."
)


def test_derive_kv_roundtrip_finds_set_and_get():
    assert _derive_kv_roundtrip(KV_SPEC) == ("set", "get")


def test_derive_kv_roundtrip_conservative_when_only_one_side_present():
    assert _derive_kv_roundtrip("A CLI that only supports `get <key>`.") is None
    assert _derive_kv_roundtrip("A CLI that only supports `set <key> <value>`.") is None
    assert _derive_kv_roundtrip("A calculator CLI with an add(a, b) function.") is None


def test_derive_kv_roundtrip_excludes_stdin_session_protocol():
    """The critical no-over-trigger guard: a spec that names set/get but describes a
    stdin-driven multi-command SESSION (one process, many commands) must NOT get a
    per-invocation KV round-trip check -- that shape cannot correctly verify it, and the
    spec never claims cross-process persistence for it."""
    assert _derive_kv_roundtrip(STDIN_SESSION_KV_SPEC) is None


def test_derive_kv_roundtrip_never_raises_on_bad_input():
    assert _derive_kv_roundtrip(None) is None
    assert _derive_kv_roundtrip("") is None
    assert _derive_kv_roundtrip(123) is None


def test_derive_kv_roundtrip_no_over_trigger_across_all_creation_tasks():
    """Sweep every one of the held-out suite's specs (incl. `kv-store-ttl-cli`'s and
    `lru-cache-cli`'s own set/put+get commands) and confirm the KV round-trip fires ONLY for
    the genuine `sqlite-persistent-kv-cli` spec -- no other class is disturbed."""
    matches = [t.name for t in ALL_CREATION_TASKS if _derive_kv_roundtrip(t.sentence)]
    assert matches == ["sqlite-persistent-kv-cli"]


# --- (core) the KV round-trip takes PRECEDENCE over the add/list one, never both ----------

def test_minimum_acceptance_prefers_kv_roundtrip_over_add_list_for_kv_spec():
    mods = [{"name": "main.py", "exports": [{"name": "main"}]}]
    plan = {"entrypoint": "main.py"}
    checks = _minimum_acceptance(KV_SPEC, mods, plan)
    names = [c["name"] for c in checks]
    roundtrip_names = [n for n in names if "round-trip persists" in n]
    assert roundtrip_names == ["minimum: 'set'+'get' key-value round-trip persists"]


def test_minimum_acceptance_unaffected_for_add_list_only_spec():
    """VALUE-PRESERVING: a spec that only names add/list (no set/put/store+get) still gets
    exactly the pre-existing add/list round-trip -- no regression."""
    mods = DATASTORE_PLAN["modules"]
    checks = _minimum_acceptance(DATASTORE_SPEC, mods, DATASTORE_PLAN)
    names = [c["name"] for c in checks]
    roundtrip_names = [n for n in names if "round-trip persists" in n]
    assert roundtrip_names == ["minimum: 'add'+'list' round-trip persists"]


# --- the committed SQLite-kv leaf now passes _minimum_acceptance 8/8 (was 7/8) ------------

def test_sqlite_kv_leaf_passes_minimum_acceptance_8_of_8(tmp_path):
    """MEASURED + CONFIRMED (task #131): the VERIFIED-CORRECT SQLite-kv leaf
    (`graph_dsl.SQLITE_KV_LEAF`) previously FAILED `_minimum_acceptance` on exactly one
    check (the mis-derived `'create'+'get'` add/list round-trip). With the KV-aware
    round-trip taking precedence, all 8 minimum checks now pass -- no false-done, this is a
    genuinely-persistent store passing a genuinely-verifying check."""
    task = next(t for t in ALL_CREATION_TASKS if t.name == "sqlite-persistent-kv-cli")
    mods = [{"name": "main.py", "exports": [{"name": "main"}]}]
    plan = {"entrypoint": "main.py"}
    checks = _minimum_acceptance(task.sentence, mods, plan)
    names = [c["name"] for c in checks]
    assert len(checks) == 8
    assert "minimum: 'set'+'get' key-value round-trip persists" in names
    # the OLD mis-derived add/list round-trip (which paired the prose word "create" with
    # "get") must be GONE -- the KV round-trip took precedence, not just added alongside it.
    assert not any("round-trip persists" in n and "create" in n for n in names)
    (tmp_path / "main.py").write_text(SQLITE_KV_LEAF, encoding="utf-8", newline="\n")
    results = [_run_check(tmp_path, c) for c in checks]
    assert all(results), list(zip(names, results))


# --- (end to end) build_system: a genuinely-PERSISTENT kv store -> done=True; a
# non-persistent (in-memory-only) one -> done=False, caught by the KV round-trip ----------

# genuinely persists to a JSON file on disk -- state survives a fresh process invocation.
PERSISTENT_KV_CLI = (
    "import json\n"
    "import os\n"
    "import sys\n\n"
    "STORE_FILE = 'store.json'\n\n"
    "def _load():\n"
    "    if not os.path.exists(STORE_FILE):\n"
    "        return {}\n"
    "    with open(STORE_FILE) as f:\n"
    "        return json.load(f)\n\n"
    "def main():\n"
    "    args = sys.argv[1:]\n"
    "    if not args:\n"
    "        return\n"
    "    if args[0] == 'set' and len(args) == 3:\n"
    "        data = _load()\n"
    "        data[args[1]] = args[2]\n"
    "        with open(STORE_FILE, 'w') as f:\n"
    "            json.dump(data, f)\n"
    "        print('ok')\n"
    "    elif args[0] == 'get' and len(args) == 2:\n"
    "        data = _load()\n"
    "        print(data.get(args[1], 'none'))\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

# BROKEN (non-persistent): keeps state in a module-level dict only -- a fresh subprocess
# invocation always starts with an empty store, so a `get` in a SEPARATE process can never
# see a value `set` in an earlier process. Genuinely, physically non-persistent -- not a
# fake/mocked failure.
NON_PERSISTENT_KV_CLI = (
    "import sys\n\n"
    "_STORE = {}\n\n"
    "def main():\n"
    "    args = sys.argv[1:]\n"
    "    if not args:\n"
    "        return\n"
    "    if args[0] == 'set' and len(args) == 3:\n"
    "        _STORE[args[1]] = args[2]\n"
    "        print('ok')\n"
    "    elif args[0] == 'get' and len(args) == 2:\n"
    "        print(_STORE.get(args[1], 'none'))\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


def test_persistent_kv_store_yields_done_true(tmp_path):
    llm = _CannedLlm(plan=KV_PLAN, module_first={"main.py": PERSISTENT_KV_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(KV_SPEC, tmp_path / "persistent_kv", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


def test_non_persistent_kv_store_yields_done_false(tmp_path):
    """THE CORE FIX proven end to end: a store that keeps state ONLY in memory for the
    current process genuinely FAILS the KV round-trip (two independent subprocess
    invocations can never share in-memory state) -- `done` is honestly False, not a hollow
    pass. This is a REAL, physically-verified failure, not a mocked/faked one."""
    llm = _CannedLlm(plan=KV_PLAN, module_first={"main.py": NON_PERSISTENT_KV_CLI},
                      checklist_first=ONE_TRIVIAL_MODEL_CHECK)
    result = build_system(KV_SPEC, tmp_path / "non_persistent_kv", llm=llm)
    assert result["shipped"] is True
    assert result["done"] is False
    assert any("key-value round-trip" in u for u in result["unmet"])
