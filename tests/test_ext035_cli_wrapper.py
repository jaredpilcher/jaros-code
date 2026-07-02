"""EXT-035 REQ-1 — deterministic CLI-wrapper synthesizer.

Offline, no model calls. Verifies harness.cli_wrapper.synthesize_cli produces
a runnable wrapper via pure AST-derived string synthesis.
"""

import subprocess
import sys

import pytest

from harness.cli_wrapper import synthesize_cli

# #EXT-035-REQ-1 Start

STATSLIB_SRC = '''\
def stats(nums):
    return f"count={len(nums)} sum={sum(nums)} mean={round(sum(nums)/len(nums),1)} min={min(nums)} max={max(nums)}"
'''


def _write_statslib(tmp_path):
    fixture = tmp_path / "statslib.py"
    fixture.write_text(STATSLIB_SRC, encoding="utf-8")
    return fixture


def test_synthesize_cli_ints_runs_and_prints_correct_line(tmp_path):
    fixture = _write_statslib(tmp_path)

    wrapper = synthesize_cli(str(fixture), "stats", arg_mode="ints")

    assert "from statslib import stats" in wrapper
    assert "\nimport stats\n" not in wrapper
    assert "import statslib\n" not in wrapper

    cli_path = tmp_path / "cli.py"
    cli_path.write_text(wrapper, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(cli_path.resolve()), "3", "1", "4", "1", "5"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "count=5 sum=14 mean=2.8 min=1 max=5"


def test_synthesize_cli_import_line_is_from_import_not_bare_import(tmp_path):
    fixture = _write_statslib(tmp_path)
    wrapper = synthesize_cli(str(fixture), "stats", arg_mode="ints")
    lines = wrapper.splitlines()
    assert "from statslib import stats" in lines
    assert "import stats" not in lines


def test_synthesize_cli_raises_when_entry_func_missing(tmp_path):
    fixture = _write_statslib(tmp_path)
    with pytest.raises(ValueError, match="nonexistent_func"):
        synthesize_cli(str(fixture), "nonexistent_func")


def test_synthesize_cli_strings_arg_mode(tmp_path):
    echo_src = '''\
def echo(args):
    return " ".join(args)
'''
    fixture = tmp_path / "echolib.py"
    fixture.write_text(echo_src, encoding="utf-8")

    wrapper = synthesize_cli(str(fixture), "echo", arg_mode="strings")
    assert "from echolib import echo" in wrapper

    cli_path = tmp_path / "cli.py"
    cli_path.write_text(wrapper, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(cli_path.resolve()), "hello", "world"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "hello world"


def test_synthesize_cli_raw_arg_mode(tmp_path):
    count_src = '''\
def count(args):
    return len(args)
'''
    fixture = tmp_path / "countlib.py"
    fixture.write_text(count_src, encoding="utf-8")

    wrapper = synthesize_cli(str(fixture), "count", arg_mode="raw")
    assert "from countlib import count" in wrapper

    cli_path = tmp_path / "cli.py"
    cli_path.write_text(wrapper, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(cli_path.resolve()), "a", "b", "c"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "3"

# #EXT-035-REQ-1 End
