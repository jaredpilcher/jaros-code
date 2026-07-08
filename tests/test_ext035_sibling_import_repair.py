"""EXT-035 REQ-3 (TASK-5): wire `resolve_imports` into `build_system`'s own multi-module
BUILD/ASSEMBLE path.

MEASURED REPRO 2026-07-08 (a clean gemma `build_system` run): a 3-module `todo-list-cli`
build wrote `command_processor.py` starting `class CommandProcessor(DataManager):` with NO
`from data_manager import DataManager` -> `NameError: name 'DataManager' is not defined` at
import of `command_processor` -> every acceptance check fails rc=1 -> 0/3. gemma's LOGIC was
correct; it just omitted one cross-module import. `resolve_imports` (harness/import_wiring.py)
already handles this exact shape (a base-class reference is an `ast.Name` Load node caught by
`_used_names`); the bug was that `build_system` never ran it over its own generated modules.

Offline, no live model — a canned `.complete(LlmRequest) -> .text` stub (the same convention
as `tests/test_ext036_system_builder.py::_CannedLlm`) drives the plan/build stages.
"""

from __future__ import annotations

import importlib
import re
import sys

import pytest

from harness.import_wiring import resolve_imports
from harness.system_builder import build_system

# #EXT-035-REQ-3 Start

# --- the exact MEASURED repro shapes ----------------------------------------------------

DATA_MANAGER_SRC = (
    "class DataManager:\n"
    "    def __init__(self):\n"
    "        self.items = []\n"
)

COMMAND_PROCESSOR_MISSING_IMPORT = (
    "class CommandProcessor(DataManager):\n"
    "    def __init__(self):\n"
    "        super().__init__()\n"
)

DEP_EXPORTS = {"data_manager": ["DataManager"]}


def test_raw_repro_raises_nameerror_without_the_fix():
    """Ground truth: the model's raw (un-repaired) module genuinely fails at import time --
    proves the MEASURED repro is real, not a test artifact."""
    with pytest.raises(NameError):
        exec(compile(COMMAND_PROCESSOR_MISSING_IMPORT, "command_processor.py", "exec"), {})


def test_resolve_imports_injects_missing_baseclass_import():
    fixed = resolve_imports(COMMAND_PROCESSOR_MISSING_IMPORT, DEP_EXPORTS)
    assert "from data_manager import DataManager" in fixed
    assert "class CommandProcessor(DataManager):" in fixed


def test_resolve_imports_fixed_module_imports_cleanly():
    """The fixed source genuinely imports without a NameError (compile/exec), given
    `data_manager` resolvable the normal Python way (via `sys.modules`)."""
    fixed = resolve_imports(COMMAND_PROCESSOR_MISSING_IMPORT, DEP_EXPORTS)

    import types
    fake_data_manager = types.ModuleType("data_manager")

    class DataManager:
        def __init__(self):
            self.items = []

    fake_data_manager.DataManager = DataManager
    sys.modules["data_manager"] = fake_data_manager
    try:
        ns: dict = {}
        exec(compile(fixed, "command_processor.py", "exec"), ns)  # must not raise
        assert "CommandProcessor" in ns
        instance = ns["CommandProcessor"]()
        assert isinstance(instance, DataManager)
    finally:
        sys.modules.pop("data_manager", None)


def test_already_imported_module_is_unchanged_idempotent():
    code = (
        "from data_manager import DataManager\n\n\n"
        "class CommandProcessor(DataManager):\n"
        "    pass\n"
    )
    fixed = resolve_imports(code, DEP_EXPORTS)
    assert fixed == code
    assert fixed.count("from data_manager import DataManager") == 1


def test_unrelated_name_not_exported_by_any_sibling_left_alone():
    code = (
        "class CommandProcessor(DataManager):\n"
        "    def helper(self):\n"
        "        return frobnicate()\n"
    )
    fixed = resolve_imports(code, DEP_EXPORTS)
    # the genuine sibling import is still injected...
    assert "from data_manager import DataManager" in fixed
    # ...but nothing was invented for `frobnicate`, which no sibling exports.
    import_lines = [ln for ln in fixed.splitlines() if ln.startswith(("import ", "from "))]
    assert not any("frobnicate" in ln for ln in import_lines)


# --- build_system wiring: dep_exports derived from ALL sibling BUILD output -------------

SPEC = ("A tiny todo-list CLI: a data-manager module holding items, a command-processor "
        "module that extends it, and a main entrypoint.")

PLAN_JSON = """{
  "modules": [
    {"name": "data_manager.py", "responsibility": "hold todo items",
     "exports": [{"name": "DataManager", "signature": "class DataManager:"}], "imports": []},
    {"name": "command_processor.py", "responsibility": "process commands, extends DataManager",
     "exports": [{"name": "CommandProcessor", "signature": "class CommandProcessor(DataManager):"}],
     "imports": ["data_manager.py"]},
    {"name": "main.py", "responsibility": "CLI entrypoint",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["command_processor.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py runs and processes a command"
}"""

MAIN_OK = (
    "from command_processor import CommandProcessor\n\n\n"
    "def main():\n"
    "    cp = CommandProcessor()\n"
    "    print('ok')\n\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Minimal canned llm (mirrors `tests/test_ext036_system_builder.py::_CannedLlm`'s
    prompt-stage-substring routing convention). `command_processor.py`'s canned body is the
    MEASURED buggy shape -- no `from data_manager import DataManager` -- and is syntactically
    valid, so it is never touched by the syntax-repair loop; the ONLY thing that can fix it is
    the wiring under test."""

    def __init__(self) -> None:
        self.modules = {
            "data_manager.py": DATA_MANAGER_SRC,
            "command_processor.py": COMMAND_PROCESSOR_MISSING_IMPORT,
            "main.py": MAIN_OK,
        }
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")  # this test is wiring-focused, not acceptance-focused
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.modules.get(name, ""))
        return _Resp("")


def _import_fresh(root, name):
    """Import `name` from `root` guaranteed fresh (no stale sys.modules cache)."""
    sys.modules.pop(name, None)
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(root))


def test_build_system_injects_missing_sibling_import(tmp_path):
    """The actual wiring bug fix: build_system's multi-module BUILD/ASSEMBLE step must run
    resolve_imports over EVERY generated module with dep_exports derived from ALL sibling
    modules generated in THIS build -- not just the plan-declared `deps` path
    build_from_intent already handled."""
    root = tmp_path / "built"
    llm = _CannedLlm()

    result = build_system(SPEC, root, llm=llm)

    # confirm the bug shape was genuinely exercised (the canned body has no import) --
    # otherwise this test would prove nothing.
    assert "from data_manager import DataManager" not in COMMAND_PROCESSOR_MISSING_IMPORT

    fixed_command_processor = result["modules"]["command_processor.py"]
    assert "from data_manager import DataManager" in fixed_command_processor

    # ASSEMBLED onto disk with the fix applied (not the raw buggy body)
    on_disk = (root / "command_processor.py").read_text(encoding="utf-8")
    assert "from data_manager import DataManager" in on_disk

    # and it genuinely imports cleanly now -- the exact MEASURED failure mode
    try:
        cp_mod = _import_fresh(root, "command_processor")
        assert hasattr(cp_mod, "CommandProcessor")
    finally:
        sys.modules.pop("command_processor", None)
        sys.modules.pop("data_manager", None)


def test_build_system_leaves_correct_sibling_import_unchanged(tmp_path):
    """Idempotent through the full pipeline: a module that ALREADY has the correct sibling
    import is not touched (no duplicate import line)."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    llm.modules["command_processor.py"] = (
        "from data_manager import DataManager\n\n\n" + COMMAND_PROCESSOR_MISSING_IMPORT
    )

    result = build_system(SPEC, root, llm=llm)

    fixed = result["modules"]["command_processor.py"]
    assert fixed.count("from data_manager import DataManager") == 1


def test_build_system_does_not_invent_import_for_unrelated_name(tmp_path):
    """A module referencing a name NO sibling exports gets no spurious import -- the
    resolver stays conservative through the full build_system wiring, not just in isolation."""
    root = tmp_path / "built"
    llm = _CannedLlm()
    llm.modules["command_processor.py"] = (
        "class CommandProcessor(DataManager):\n"
        "    def helper(self):\n"
        "        return frobnicate()\n"
    )

    result = build_system(SPEC, root, llm=llm)

    fixed = result["modules"]["command_processor.py"]
    assert "from data_manager import DataManager" in fixed
    import_lines = [ln for ln in fixed.splitlines() if ln.startswith(("import ", "from "))]
    assert not any("frobnicate" in ln for ln in import_lines)

# #EXT-035-REQ-3 End
