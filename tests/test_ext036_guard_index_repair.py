"""EXT-036 TASK-49 (REQ-39): deterministic module-body repair for a length-guard /
constant-index contradiction.

MEASURED BUG (repro `.jaros-data/artifacts/kv_diag.log`, the `cli.py` section): the
kv-store-ttl `set` handler gemma writes is
``if command == "set": if len(parts) == 3: key = parts[1]; value = parts[2]; ttl =
int(parts[3]); ...`` -- but ``set <key> <value> <ttl>`` splits into 4 tokens, so
``len(parts) == 3`` is always False and every ``set`` SILENTLY NO-OPS (0/3 Get/Delete
behavioral checks fail). The guard is internally self-contradictory with its own body: it
requires ``len(parts) == 3`` yet indexes ``parts[3]`` (needs ``len(parts) >= 4``).
``build_system``'s bounded acceptance-driven repair loop (REQ-5) already fed this failure
back for 2 rounds live and gemma could not fix it -- `repair_guard_index_mismatch` is the
deterministic tool that closes it.

Offline, no live model, no network: this file tests the pure AST function directly, a real
(guarded) subprocess run proving the fix is BEHAVIORALLY genuine (not just textual), and the
`build_system` wiring via a canned llm stub (the same convention as
`tests/test_ext035_sibling_import_repair.py`).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from harness.system_builder import build_system, repair_guard_index_mismatch

# #EXT-036-REQ-39 Start

# --- (a) the EXACT measured repro: captured cli.py / store.py -----------------------------

CLI_BUGGY = textwrap.dedent('''\
    import store
    import sys
    from store import InMemoryStore

    def main():
        store = InMemoryStore()

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if not parts:
                continue

            command = parts[0]

            if command == "set":
                if len(parts) == 3:
                    key = parts[1]
                    value = parts[2]
                    try:
                        ttl = int(parts[3])
                        store.set(key, value, ttl)
                    except ValueError:
                        # Ignore malformed set command if TTL is not an integer
                        pass
            elif command == "get":
                if len(parts) == 2:
                    key = parts[1]
                    result = store.get(key)
                    print(result)
            elif command == "delete":
                if len(parts) == 2:
                    key = parts[1]
                    result = store.delete(key)
                    print(result)

    if __name__ == "__main__":
        main()
''')

STORE_SRC = textwrap.dedent('''\
    import time

    class InMemoryStore:
        def __init__(self):
            self.store = {}

        def set(self, key, value, ttl_seconds):
            if ttl_seconds <= 0:
                self.store[key] = (value, 0)
            else:
                expiry_time = time.time() + ttl_seconds
                self.store[key] = (value, expiry_time)

        def get(self, key):
            if key not in self.store:
                return "none"
            value, expiry_time = self.store[key]
            if expiry_time == 0:
                return "none"
            current_time = time.time()
            if current_time >= expiry_time:
                return "none"
            return value

        def delete(self, key):
            if key in self.store:
                del self.store[key]
                return "ok"
            return "ok"
''')


def _run_cli(root, stdin_text: str) -> str:
    """Real (guarded, bounded) subprocess run of `root/cli.py`, mirroring
    `harness/multi_file.py::_run`'s pattern. Returns stdout."""
    proc = subprocess.run(
        [sys.executable, "cli.py"],
        cwd=str(root),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.stdout


def test_measured_buggy_guard_is_repaired_to_consistent_len_4(tmp_path):
    repaired = repair_guard_index_mismatch(CLI_BUGGY)
    assert repaired != CLI_BUGGY
    assert "if len(parts) == 4:" in repaired
    # the rest of the module is untouched -- only the one guard constant changed.
    assert repaired.replace("len(parts) == 4", "len(parts) == 3") == CLI_BUGGY


def test_repaired_module_still_compiles():
    repaired = repair_guard_index_mismatch(CLI_BUGGY)
    compile(repaired, "cli.py", "exec")  # must not raise


def test_repaired_module_genuinely_stops_no_opping_set(tmp_path):
    """Behavioral, not textual: a REAL subprocess run of the repaired module actually
    persists a `set`, where the original buggy module genuinely does not (a regression
    oracle proving this is a genuine fix, not a coincidental pass)."""
    (tmp_path / "store.py").write_text(STORE_SRC, encoding="utf-8")

    (tmp_path / "cli.py").write_text(CLI_BUGGY, encoding="utf-8")
    buggy_out = _run_cli(tmp_path, "set foo bar 100\nget foo\n")
    assert buggy_out.strip() == "none"  # confirms the repro is real, not a test artifact

    repaired = repair_guard_index_mismatch(CLI_BUGGY)
    (tmp_path / "cli.py").write_text(repaired, encoding="utf-8")
    fixed_out = _run_cli(tmp_path, "set foo bar 100\nget foo\n")
    assert fixed_out.strip() == "bar"


# --- (b) 8+ valid/ambiguous fixtures: BYTE-IDENTICAL, never touched -----------------------

def test_already_consistent_guard_unchanged():
    code = "if len(parts) == 4:\n    x = parts[3]\n"
    assert repair_guard_index_mismatch(code) == code


def test_guard_on_different_name_than_indexed_unchanged():
    code = "if len(a) == 3:\n    x = b[3]\n"
    assert repair_guard_index_mismatch(code) == code


def test_negative_index_unchanged():
    code = "if len(x) == 3:\n    y = x[-1]\n"
    assert repair_guard_index_mismatch(code) == code


def test_variable_index_unchanged():
    code = "if len(x) == 3:\n    y = x[i]\n"
    assert repair_guard_index_mismatch(code) == code


def test_slice_index_unchanged():
    code = "if len(x) == 3:\n    y = x[1:3]\n"
    assert repair_guard_index_mismatch(code) == code


def test_no_length_guard_unchanged():
    code = "y = x[5]\n"
    assert repair_guard_index_mismatch(code) == code


def test_index_confined_to_else_branch_unchanged():
    code = "if len(x) == 2:\n    pass\nelse:\n    y = x[5]\n"
    assert repair_guard_index_mismatch(code) == code


def test_compound_boolean_guard_unchanged():
    code = "if len(x) == 3 and flag:\n    y = x[5]\n"
    assert repair_guard_index_mismatch(code) == code


def test_open_ended_gt_guard_unchanged():
    """`len(x) > 3` admits an UNBOUNDED-above set of lengths -- some admitted length
    (e.g. 11) always leaves index 10 reachable, so this is never a PROVABLE, guard-wide
    contradiction -- must never be touched."""
    code = "if len(x) > 3:\n    y = x[10]\n"
    assert repair_guard_index_mismatch(code) == code


def test_open_ended_gte_guard_unchanged():
    code = "if len(x) >= 3:\n    y = x[10]\n"
    assert repair_guard_index_mismatch(code) == code


# --- (c) <, <=, != and their reversed operand forms ----------------------------------------

def test_lt_guard_repaired_to_minimal_consistent_constant():
    code = "if len(x) < 4:\n    y = x[3]\n"
    repaired = repair_guard_index_mismatch(code)
    assert repaired == "if len(x) < 5:\n    y = x[3]\n"


def test_lte_guard_repaired_to_minimal_consistent_constant():
    code = "if len(x) <= 2:\n    y = x[3]\n"
    repaired = repair_guard_index_mismatch(code)
    assert repaired == "if len(x) <= 4:\n    y = x[3]\n"


def test_lt_guard_reversed_operand_form_repaired():
    code = "if 4 > len(x):\n    y = x[3]\n"
    repaired = repair_guard_index_mismatch(code)
    assert repaired == "if 5 > len(x):\n    y = x[3]\n"


def test_lte_guard_reversed_operand_form_repaired():
    code = "if 2 >= len(x):\n    y = x[3]\n"
    repaired = repair_guard_index_mismatch(code)
    assert repaired == "if 4 >= len(x):\n    y = x[3]\n"


def test_ne_guard_never_touched():
    code = "if len(x) != 3:\n    y = x[10]\n"
    assert repair_guard_index_mismatch(code) == code


def test_ne_guard_reversed_never_touched():
    code = "if 3 != len(x):\n    y = x[10]\n"
    assert repair_guard_index_mismatch(code) == code


def test_multiple_independent_guards_both_repaired_positions_stay_valid():
    """Two separate contradictory guards in one module -- proves the edit-application order
    (rightmost-first by absolute offset) doesn't corrupt an earlier edit's position."""
    code = (
        "if len(a) == 2:\n"
        "    x = a[4]\n\n"
        "if len(b) == 1:\n"
        "    y = b[9]\n"
    )
    repaired = repair_guard_index_mismatch(code)
    assert "if len(a) == 5:" in repaired
    assert "if len(b) == 10:" in repaired
    compile(repaired, "multi.py", "exec")  # still syntactically valid


# --- (d) never raises -----------------------------------------------------------------------

def test_never_raises_on_none():
    assert repair_guard_index_mismatch(None) is None


def test_never_raises_on_empty_string():
    assert repair_guard_index_mismatch("") == ""


def test_never_raises_on_malformed_python():
    code = "def f(:\n    this is not python\n"
    assert repair_guard_index_mismatch(code) == code


# --- build_system wiring: the exact defect is repaired as part of a real build --------------

SPEC = ("A key-value store CLI with TTL support: reads set/get/delete commands from stdin, "
        "in a file named main.py.")

PLAN_JSON = """{
  "modules": [
    {"name": "store.py", "responsibility": "in-memory TTL key-value store",
     "exports": [{"name": "InMemoryStore", "signature": "class InMemoryStore:"}], "imports": []},
    {"name": "cli.py", "responsibility": "stdin-driven set/get/delete CLI",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["store.py"]}
  ],
  "entrypoint": "cli.py",
  "acceptance": "python cli.py reads set/get/delete commands from stdin"
}"""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Minimal canned llm (mirrors `tests/test_ext035_sibling_import_repair.py::_CannedLlm`).
    `cli.py`'s canned body is the MEASURED buggy shape and is syntactically valid, so it is
    never touched by the syntax-repair loop -- only this task's wiring can fix it."""

    def __init__(self) -> None:
        self.modules = {"store.py": STORE_SRC, "cli.py": CLI_BUGGY}

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")  # this test is wiring-focused, not acceptance-focused
        if "COMPLETE Python module" in prompt:
            for name, code in self.modules.items():
                if f"module `{name}`" in prompt:
                    return _Resp(code)
            return _Resp("")
        return _Resp("")


def test_build_system_repairs_the_measured_guard_defect(tmp_path):
    root = tmp_path / "built"
    llm = _CannedLlm()

    result = build_system(SPEC, root, llm=llm)

    fixed_cli = result["modules"]["cli.py"]
    assert "if len(parts) == 4:" in fixed_cli
    assert "if len(parts) == 3:" not in fixed_cli

    on_disk = (root / "cli.py").read_text(encoding="utf-8")
    assert "if len(parts) == 4:" in on_disk


def test_build_system_leaves_a_correct_guard_untouched(tmp_path):
    root = tmp_path / "built"
    llm = _CannedLlm()
    llm.modules["cli.py"] = CLI_BUGGY.replace("len(parts) == 3", "len(parts) == 4")

    result = build_system(SPEC, root, llm=llm)

    fixed_cli = result["modules"]["cli.py"]
    assert fixed_cli.count("len(parts) == 4") == 1
    assert "len(parts) == 3" not in fixed_cli

# #EXT-036-REQ-39 End
