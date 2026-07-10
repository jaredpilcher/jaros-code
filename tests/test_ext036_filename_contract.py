"""Offline tests for EXT-036 TASK-59 (REQ-46): deterministic spec-demanded filename/entrypoint
normalization.

No model/Jetson call anywhere in this file -- pure AST transform, exactly the shapes MEASURED in
`.jaros-data/filename_norm_probe.py` (memoize single-module rename) and
`.jaros-data/entrypoint_norm_probe.py` (INI multi-module entrypoint + `__main__` guard injection).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.filename_contract import (
    apply_filename_contract,
    demanded_filenames,
    normalize_entrypoint,
)

# --- memoize single-module case (gemma's ACTUAL emitted module: correct code, wrong filename) ---
MEMOIZE_SPEC = (
    "Build a small reusable library in a file named `memoize.py`. It must define exactly one "
    "public function named `memoize` with the signature `memoize(maxsize=128)`."
)
GEMMA_MEMOIZE_MODULES = {
    "test_memoize.py": (
        "def memoize(maxsize=128):\n"
        "    def decorator(func):\n"
        "        cache = {}\n"
        "        def wrapper(*args):\n"
        "            key = args\n"
        "            if key in cache:\n"
        "                return cache[key]\n"
        "            else:\n"
        "                result = func(*args)\n"
        "                cache[key] = result\n"
        "                return result\n"
        "        return wrapper\n"
        "    return decorator\n"
    ),
}

# --- INI cli-exact multi-module case (gemma's ACTUAL emitted modules: correct logic, no main.py,
# no __main__ guard) ---
INI_SPEC = (
    "Build a small command-line tool in a file named `main.py` that reads an INI config from "
    "stdin and prints the value of a requested key within a requested section."
)
GEMMA_INI_MODULES = {
    "config_parser.py": (
        "def parse_ini(ini_content: str) -> dict:\n"
        "    config = {}\n"
        "    current_section = None\n"
        "    for line in ini_content.splitlines():\n"
        "        line = line.strip()\n"
        "        if not line or line.startswith(';'):\n"
        "            continue\n"
        "        if line.startswith('[') and line.endswith(']'):\n"
        "            section_name = line[1:-1].strip()\n"
        "            if section_name:\n"
        "                config[section_name] = {}\n"
        "                current_section = section_name\n"
        "        elif current_section is not None and '=' in line:\n"
        "            key, value = line.split('=', 1)\n"
        "            key = key.strip()\n"
        "            value = value.strip()\n"
        "            if key:\n"
        "                config[current_section][key] = value\n"
        "    return config\n"
    ),
    "cli_handler.py": (
        "import sys\n"
        "from config_parser import parse_ini\n\n"
        "def main(args: list):\n"
        "    if len(args) != 2:\n"
        "        sys.exit(1)\n"
        "    section_name = args[0]\n"
        "    key_name = args[1]\n"
        "    try:\n"
        "        ini_content = sys.stdin.read()\n"
        "    except Exception:\n"
        "        sys.exit(1)\n"
        "    config = parse_ini(ini_content)\n"
        "    if section_name not in config:\n"
        "        sys.exit(1)\n"
        "    section_data = config[section_name]\n"
        "    if key_name not in section_data:\n"
        "        sys.exit(1)\n"
        "    value = section_data[key_name]\n"
        "    print(value)\n"
    ),
}
INI_STDIN = "[server]\nhost = localhost\nport = 8080\n[db]\nport = 5432\n"


def _run_main(modules: dict, argv: list, stdin: str):
    """Write `modules` to a temp dir and run `python main.py <argv>` with `stdin`, offline."""
    with tempfile.TemporaryDirectory(prefix="fnorm_test_") as tmp:
        root = Path(tmp)
        for fn, code in modules.items():
            (root / fn).write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "main.py", *argv],
            cwd=str(root), input=stdin, capture_output=True, text=True, timeout=15,
        )
        return proc


class TestDemandedFilenames:
    def test_parses_backtick_filename(self):
        assert demanded_filenames(MEMOIZE_SPEC) == ["memoize.py"]

    def test_parses_plain_filename(self):
        assert demanded_filenames("write it in a file named main.py please") == ["main.py"]

    def test_dedup_order_preserving(self):
        spec = "a file named `a.py` ... later also a file named `a.py` ... then a file named `b.py`"
        assert demanded_filenames(spec) == ["a.py", "b.py"]

    def test_no_demand_is_empty(self):
        assert demanded_filenames("plain prose, no filename demanded here") == []

    def test_none_or_empty_never_raises(self):
        assert demanded_filenames(None) == []
        assert demanded_filenames("") == []


class TestNormalizeEntrypointMemoize:
    def test_a_single_module_rename_and_import_works(self):
        new_mods, notes = normalize_entrypoint(GEMMA_MEMOIZE_MODULES, MEMOIZE_SPEC)
        assert "memoize.py" in new_mods
        assert "test_memoize.py" not in new_mods
        assert any("memoize.py" in n for n in notes)
        # exec + import-shape check: the renamed module defines a working memoize()
        ns = {}
        exec(new_mods["memoize.py"], ns)
        deco = ns["memoize"](maxsize=128)
        calls = []
        wrapped = deco(lambda x: calls.append(x) or x * 2)
        assert wrapped(5) == 10
        assert wrapped(5) == 10  # cached, no new call recorded below
        assert calls == [5]

    def test_never_mutates_input_dict(self):
        original = dict(GEMMA_MEMOIZE_MODULES)
        normalize_entrypoint(GEMMA_MEMOIZE_MODULES, MEMOIZE_SPEC)
        assert GEMMA_MEMOIZE_MODULES == original


class TestNormalizeEntrypointIni:
    def test_b_multi_module_entrypoint_rename_and_guard_injected(self):
        new_mods, notes = normalize_entrypoint(GEMMA_INI_MODULES, INI_SPEC)
        assert "main.py" in new_mods
        assert "cli_handler.py" not in new_mods
        assert "config_parser.py" in new_mods
        # config_parser untouched (byte-identical)
        assert new_mods["config_parser.py"] == GEMMA_INI_MODULES["config_parser.py"]
        assert "__main__" in new_mods["main.py"]
        assert "main(sys.argv[1:])" in new_mods["main.py"]
        assert any("cli_handler.py -> main.py" in n for n in notes)
        assert any("injected __main__ guard" in n for n in notes)

        proc = _run_main(new_mods, ["server", "port"], INI_STDIN)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == "8080\n"


class TestNoOpCases:
    def test_c_noop_when_demanded_file_already_present(self):
        modules = {"memoize.py": GEMMA_MEMOIZE_MODULES["test_memoize.py"]}
        new_mods, notes = normalize_entrypoint(modules, MEMOIZE_SPEC)
        assert new_mods == modules
        assert any("already present" in n for n in notes)

    def test_d_noop_ambiguous_mutually_importing_modules(self):
        modules = {
            "a.py": "import b\n\ndef fa():\n    return b.fb()\n",
            "b.py": "import a\n\ndef fb():\n    return 1\n",
        }
        new_mods, notes = normalize_entrypoint(modules, INI_SPEC)
        assert new_mods == modules
        assert any("could not resolve a unique entrypoint" in n for n in notes)

    def test_d_noop_ambiguous_two_roots(self):
        modules = {
            "shared.py": "def helper():\n    return 1\n",
            "root_one.py": "import shared\n\ndef main(args):\n    return shared.helper()\n",
            "root_two.py": "import shared\n\ndef go(args):\n    return shared.helper()\n",
        }
        new_mods, notes = normalize_entrypoint(modules, INI_SPEC)
        assert new_mods == modules
        assert any("could not resolve a unique entrypoint" in n for n in notes)

    def test_no_demand_is_noop(self):
        new_mods, notes = normalize_entrypoint(GEMMA_MEMOIZE_MODULES, "no filename demand here")
        assert new_mods == GEMMA_MEMOIZE_MODULES
        assert notes == []


class TestMainArityGuardSelection:
    def test_e_zero_param_main_gets_bare_call(self):
        modules = {"app.py": "def main():\n    print('hi')\n"}
        new_mods, notes = normalize_entrypoint(modules, "a file named `run.py`")
        assert "run.py" in new_mods
        assert "main()" in new_mods["run.py"]
        assert "main(sys.argv[1:])" not in new_mods["run.py"]
        assert any("injected __main__ guard calling main()" in n for n in notes)

    def test_positional_param_main_gets_argv_call(self):
        modules = {"app.py": "def main(args):\n    print(args)\n"}
        new_mods, notes = normalize_entrypoint(modules, "a file named `run.py`")
        assert "main(sys.argv[1:])" in new_mods["run.py"]


class TestNeverRaises:
    def test_f_unparseable_entrypoint_never_raises(self):
        modules = {"broken.py": "def main(:\n    pass\n"}
        new_mods, notes = normalize_entrypoint(modules, "a file named `run.py`")
        assert new_mods == modules
        assert any("does not parse" in n for n in notes)

    def test_none_inputs_never_raise(self):
        new_mods, notes = normalize_entrypoint(None, None)
        assert new_mods == {}
        assert notes == []

    def test_empty_modules_never_raise(self):
        new_mods, notes = normalize_entrypoint({}, MEMOIZE_SPEC)
        assert new_mods == {}


class TestApplyFilenameContract:
    def test_thin_wrapper_matches_normalize_entrypoint(self):
        new_mods, notes = apply_filename_contract(GEMMA_MEMOIZE_MODULES, MEMOIZE_SPEC)
        assert "memoize.py" in new_mods
        assert new_mods is not GEMMA_MEMOIZE_MODULES

    def test_never_raises_and_falls_back_to_input(self):
        # spec_text of an unexpected type must not blow up the wrapper
        new_mods, notes = apply_filename_contract(GEMMA_MEMOIZE_MODULES, 12345)  # type: ignore[arg-type]
        assert isinstance(new_mods, dict)
