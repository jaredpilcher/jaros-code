"""EXT-037 / REQ-3 -- environment tools (python detect, venv create/install/pin).

Offline, deterministic, no network: venv creation uses stdlib ``ensurepip`` (bundled
wheels, no PyPI access) and ``pip freeze`` only lists already-installed local
packages. The dependency-INSTALL tool is exercised via ``dry_run: true`` so the
suite never hits PyPI -- it proves the venv-scoped pip command is constructed
correctly and that a real (non-dry-run) install is refused when it would need a
missing venv or a global-scope flag, without ever performing a network install.

Mirrors the ``_load_tool``/``_decision`` conventions of ``test_ext037_gated_exec.py``.
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

from _envtools import global_install_flag, venv_python_path  # noqa: E402

# #EXT-037-REQ-3 Start


def _load_tool(filename: str, classname: str):
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, classname)()


def _decision(dtype: str, payload):
    return create_decision(id=f"t-{dtype}", source="test", type=dtype, payload=payload)


# --- (a) env.python_detect ---------------------------------------------------


def test_python_detect_finds_a_runnable_interpreter():
    tool = _load_tool("python_detect_tool.py", "PythonDetectTool")
    d = _decision("env.python_detect", {})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["available"] is True
    assert out["found"], "expected at least one detected interpreter"
    assert out["primary"]["path"]
    assert out["primary"]["version"]  # e.g. "Python 3.11.4"


def test_python_detect_never_raises_on_bogus_candidates():
    tool = _load_tool("python_detect_tool.py", "PythonDetectTool")
    d = _decision("env.python_detect", {"candidates": ["definitely-not-a-real-interpreter-xyz"]})
    out = tool.execute(d)
    assert out["available"] is False
    assert out["found"] == []
    assert out["primary"] is None


# --- (b) env.venv_create ------------------------------------------------------


def test_venv_create_makes_a_real_venv_in_temp_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_create_tool.py", "VenvCreateTool")
    d = _decision("env.venv_create", {"root": str(root)})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["created"] is True
    assert out["pythonExists"] is True
    assert os.path.isfile(out["pythonPath"])
    # The venv directory itself must genuinely live inside root.
    assert os.path.realpath(out["venvPath"]).startswith(os.path.realpath(str(root)))


def test_venv_create_rejects_path_escaping_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_create_tool.py", "VenvCreateTool")
    d = _decision("env.venv_create", {"root": str(root), "venv_path": "../escaped_venv"})
    result = tool.validate(d)
    assert result.ok is False
    assert "root" in (result.reason or "").lower()
    assert not (tmp_path / "escaped_venv").exists()


def test_venv_create_rejects_missing_root():
    tool = _load_tool("venv_create_tool.py", "VenvCreateTool")
    d = _decision("env.venv_create", {"root": "Z:\\definitely\\not\\a\\real\\dir\\xyz"})
    assert tool.validate(d).ok is False


# --- helper: build a real venv once per test that needs one -------------------


def _make_venv(tmp_path) -> tuple[Path, dict]:
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_create_tool.py", "VenvCreateTool")
    d = _decision("env.venv_create", {"root": str(root)})
    out = tool.execute(d)
    assert out["created"] is True
    return root, out


# --- (c) env.venv_install ------------------------------------------------------


def test_venv_install_dry_run_builds_venv_scoped_pip_command(tmp_path):
    root, venv_out = _make_venv(tmp_path)
    tool = _load_tool("venv_install_tool.py", "VenvInstallTool")
    d = _decision("env.venv_install", {
        "root": str(root), "package": "requests==2.31.0", "dry_run": True,
    })
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["installed"] is False
    assert out["dryRun"] is True
    expected_python = venv_python_path(os.path.join(str(root), ".venv"))
    assert os.path.realpath(out["command"][0]) == os.path.realpath(expected_python)
    assert out["command"][1:4] == ["-m", "pip", "install"]
    assert out["command"][-1] == "requests==2.31.0"


def test_venv_install_validate_blocks_global_scope_flags():
    tool = _load_tool("venv_install_tool.py", "VenvInstallTool")
    for flag in ("--user", "--target=/tmp/x", "--system", "--break-system-packages"):
        d = _decision("env.venv_install", {
            "root": "irrelevant", "package": "requests", "extra_args": [flag], "dry_run": True,
        })
        result = tool.validate(d)
        assert result.ok is False, f"expected {flag!r} to be blocked"


def test_venv_install_validate_blocks_flag_disguised_as_package():
    tool = _load_tool("venv_install_tool.py", "VenvInstallTool")
    d = _decision("env.venv_install", {"root": "irrelevant", "package": "--user", "dry_run": True})
    assert tool.validate(d).ok is False


def test_venv_install_refuses_missing_venv_without_dry_run(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_install_tool.py", "VenvInstallTool")
    d = _decision("env.venv_install", {"root": str(root), "package": "requests"})
    result = tool.validate(d)
    assert result.ok is False
    assert "venv" in (result.reason or "").lower()


def test_venv_install_rejects_venv_path_escaping_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_install_tool.py", "VenvInstallTool")
    d = _decision("env.venv_install", {
        "root": str(root), "venv_path": "../escaped", "package": "requests", "dry_run": True,
    })
    result = tool.validate(d)
    assert result.ok is False
    assert "root" in (result.reason or "").lower()


def test_global_install_flag_helper():
    assert global_install_flag(["--verbose"]) is None
    assert global_install_flag(["--user"]) == "--user"
    assert global_install_flag(["--target=/x"]) == "--target=/x"
    assert global_install_flag(None) is None


# --- (d) env.venv_pin ----------------------------------------------------------


def test_venv_pin_writes_root_jailed_requirements_from_real_freeze(tmp_path):
    root, _ = _make_venv(tmp_path)
    tool = _load_tool("venv_pin_tool.py", "VenvPinTool")
    d = _decision("env.venv_pin", {"root": str(root)})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["written"] is True
    assert out["source"] == "freeze"
    req_path = Path(out["requirementsPath"])
    assert req_path.exists()
    assert os.path.realpath(str(req_path)).startswith(os.path.realpath(str(root)))
    # pip freeze against a fresh venv is deterministic-ish but at minimum runs cleanly
    # (may be empty or list pip itself depending on the ensurepip bundle).
    assert isinstance(req_path.read_text(encoding="utf-8"), str)


def test_venv_pin_explicit_packages_no_freeze_needed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_pin_tool.py", "VenvPinTool")
    d = _decision("env.venv_pin", {"root": str(root), "packages": ["requests==2.31.0", "click==8.1.7"]})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["written"] is True
    assert out["source"] == "explicit"
    content = Path(out["requirementsPath"]).read_text(encoding="utf-8")
    assert "requests==2.31.0" in content
    assert "click==8.1.7" in content


def test_venv_pin_rejects_requirements_path_escaping_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_pin_tool.py", "VenvPinTool")
    d = _decision("env.venv_pin", {
        "root": str(root), "packages": ["x"], "requirements_path": "../escaped_reqs.txt",
    })
    result = tool.validate(d)
    assert result.ok is False
    assert "root" in (result.reason or "").lower()
    assert not (tmp_path / "escaped_reqs.txt").exists()


def test_venv_pin_refuses_freeze_without_existing_venv(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("venv_pin_tool.py", "VenvPinTool")
    d = _decision("env.venv_pin", {"root": str(root)})
    result = tool.validate(d)
    assert result.ok is False
    assert "venv" in (result.reason or "").lower()


# --- (e) never raises ----------------------------------------------------------


def test_venv_create_execute_never_raises_on_bad_root():
    tool = _load_tool("venv_create_tool.py", "VenvCreateTool")
    d = _decision("env.venv_create", {"root": "Z:\\nope\\nope\\nope"})
    out = tool.execute(d)
    assert out["created"] is False
    assert "error" in out


def test_venv_pin_execute_never_raises_on_bad_root():
    tool = _load_tool("venv_pin_tool.py", "VenvPinTool")
    d = _decision("env.venv_pin", {"root": "Z:\\nope\\nope\\nope", "packages": ["x"]})
    out = tool.execute(d)
    # requirements_path resolves relative to a nonexistent root; writing should
    # either fail structurally or succeed by creating the dir -- either way, no
    # uncaught exception reaches the caller.
    assert isinstance(out, dict)
    assert "written" in out
# #EXT-037-REQ-3 End
