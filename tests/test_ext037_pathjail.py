"""EXT-037 / REQ-1 -- root-jailed filesystem writes.

Offline, deterministic, no network/Jetson/Docker: pure filesystem checks in a temp
dir. Mirrors the ``_load_tool`` / ``_decision`` conventions of
``test_ext001_tools.py`` / ``test_ext001_search_replace.py``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from jaros.core import create_decision

TOOLS_DIR = Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from _pathjail import PathEscapeError, path_escape_reason, path_jail  # noqa: E402

# #EXT-037-REQ-1 Start


def _load_tool(filename: str, classname: str):
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, classname)()


def _decision(dtype: str, payload):
    return create_decision(id=f"t-{dtype}", source="test", type=dtype, payload=payload)


# --- (a) path_jail: in-root accept -----------------------------------------

def test_path_jail_accepts_in_root_relative_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    resolved = path_jail(str(root), "sub/file.py")
    assert Path(resolved) == Path(os.path.realpath(str(root / "sub" / "file.py")))


def test_path_jail_accepts_in_root_absolute_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "a.py"
    resolved = path_jail(str(root), str(target))
    assert Path(resolved) == Path(os.path.realpath(str(target)))


# --- (b) path_jail: escapes rejected ----------------------------------------

def test_path_jail_rejects_dotdot_escape(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(PathEscapeError):
        path_jail(str(root), "../outside.py")


def test_path_jail_rejects_outside_absolute_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "elsewhere.py"
    with pytest.raises(PathEscapeError):
        path_jail(str(root), str(outside))


def test_path_jail_rejects_symlink_escape(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    link = root / "link_out"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(PathEscapeError):
        path_jail(str(root), str(link / "leaked.py"))


def test_path_escape_reason_none_when_contained(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    assert path_escape_reason(str(root), "ok.py") is None


def test_path_escape_reason_string_when_escaping(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    reason = path_escape_reason(str(root), "../ok.py")
    assert isinstance(reason, str) and "escapes root" in reason


# --- (c) writer tools: root-gated validate() --------------------------------

@pytest.mark.parametrize("filename,classname,dtype,extra_payload", [
    ("write_file_tool.py", "WriteFileTool", "code.write_file", {"content": "ok\n"}),
    ("apply_patch_tool.py", "ApplyPatchTool", "code.apply_patch", {"old": "", "new": "ok\n"}),
    ("search_replace_tool.py", "SearchReplaceTool", "code.search_replace",
     {"search": "x", "replace": "y"}),
])
def test_writer_refuses_out_of_root_target(tmp_path, filename, classname, dtype, extra_payload):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.py"
    tool = _load_tool(filename, classname)
    payload = {"path": str(outside), "root": str(root), **extra_payload}
    result = tool.validate(_decision(dtype, payload))
    assert result.ok is False
    assert "root" in (result.reason or "").lower()
    assert not outside.exists()


@pytest.mark.parametrize("filename,classname,dtype,extra_payload", [
    ("write_file_tool.py", "WriteFileTool", "code.write_file", {"content": "ok\n"}),
    ("apply_patch_tool.py", "ApplyPatchTool", "code.apply_patch", {"old": "", "new": "ok\n"}),
    ("search_replace_tool.py", "SearchReplaceTool", "code.search_replace",
     {"search": "x", "replace": "y"}),
])
def test_writer_accepts_in_root_target(tmp_path, filename, classname, dtype, extra_payload):
    root = tmp_path / "proj"
    root.mkdir()
    inside = root / "inside.py"
    tool = _load_tool(filename, classname)
    payload = {"path": str(inside), "root": str(root), **extra_payload}
    result = tool.validate(_decision(dtype, payload))
    assert result.ok is True


def test_writer_dotdot_escape_refused_and_no_effect(tmp_path):
    """A ``..`` traversal target under a jailed root is refused, and the file that
    would have escaped is never created."""
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    escaping_path = str(root / ".." / "leak.py")
    result = tool.validate(_decision("code.write_file", {
        "path": escaping_path, "root": str(root), "content": "leak\n",
    }))
    assert result.ok is False
    assert not (tmp_path / "leak.py").exists()


def test_writer_omitting_root_is_unchanged(tmp_path):
    """No regression: a payload that omits 'root' entirely (the existing EXT-001
    call convention) still validates/executes exactly as before."""
    tool = _load_tool("write_file_tool.py", "WriteFileTool")
    f = tmp_path / "no_root.py"
    result = tool.validate(_decision("code.write_file", {"path": str(f), "content": "ok\n"}))
    assert result.ok is True
    out = tool.execute(_decision("code.write_file", {"path": str(f), "content": "ok\n"}))
    assert out["applied"] is True
    assert f.read_text(encoding="utf-8") == "ok\n"
# #EXT-037-REQ-1 End
