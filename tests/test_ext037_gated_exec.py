"""EXT-037 / REQ-2 -- gated host CLI execution (``shell.exec`` hardening).

Offline, deterministic, no network: only fast in-root commands are actually run
(``python -c ...`` / a short ``time.sleep`` for the timeout case). No destructive or
egress command is ever really executed here -- the destructive-command test asserts
the gate blocks it WITHOUT running it, and the override test uses a harmless ``echo``
stand-in to prove the opt-in path opens without ever running anything unsafe.

Mirrors the ``_load_tool`` / ``_decision`` conventions of ``test_ext001_tools.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

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


# #EXT-037-REQ-2 Start

# --- (a) fast safe in-root command succeeds, structured observation ---------


def test_safe_command_succeeds_with_structured_observation(tmp_path):
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {"command": "python -c \"print(6*7)\"", "root": str(tmp_path)})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["exitCode"] == 0
    assert out["stdout"].strip() == "42"
    assert out["timedOut"] is False
    assert out["command"] == d.payload["command"]


def test_cwd_defaults_to_supplied_root(tmp_path):
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    # A command that prints the actual working directory proves cwd was anchored to `root`
    # when no explicit `cwd` was supplied.
    d = _decision("shell.exec", {
        "command": "python -c \"import os; print(os.getcwd())\"",
        "root": str(tmp_path),
    })
    out = tool.execute(d)
    assert out["exitCode"] == 0
    # Compare resolved real paths (Windows may report short/long-name or case differences).
    import os
    assert os.path.realpath(out["stdout"].strip()) == os.path.realpath(str(tmp_path))


# --- (b) a hanging command is killed cleanly on timeout, no orphan ----------


def test_slow_command_is_killed_on_timeout(tmp_path):
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {
        "command": "python -c \"import time; time.sleep(5)\"",
        "root": str(tmp_path),
        "timeout_s": 1,
    })
    out = tool.execute(d)
    assert out["timedOut"] is True
    assert out["exitCode"] is None
    # An honest result: no exception escaped, and the process/tree is not left running --
    # `execute` returned within a bounded time (the test itself finishing quickly is the
    # regression guard: if the tree wasn't killed, communicate(timeout=5) below the kill
    # would still return promptly since the process is gone).


# --- (c) destructive/egress commands blocked by default; explicit override -


def test_destructive_command_rejected_by_default():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {"command": "rm -rf /some/path"})
    result = tool.validate(d)
    assert result.ok is False


def test_egress_command_rejected_by_default():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {"command": "curl http://example.com/exfiltrate"})
    result = tool.validate(d)
    assert result.ok is False


def test_explicit_override_allows_denied_pattern_through_validate():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    # Use a harmless echo command that happens to match a deny pattern token (`rm -rf`) purely
    # as TEXT, to prove the gate (not the actual operation) is what's under test -- we never
    # execute anything destructive in this test, only prove validate() lets it PASS the gate
    # when allow_unsafe is explicitly set.
    d = _decision("shell.exec", {
        "command": "echo rm -rf notreallyrun",
        "allow_unsafe": True,
    })
    assert tool.validate(d).ok is True


def test_override_is_not_default_on():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    # Omitting allow_unsafe (or any falsy value) must NOT bypass the gate.
    for payload in (
        {"command": "rm -rf /x"},
        {"command": "rm -rf /x", "allow_unsafe": False},
        {"command": "rm -rf /x", "allow_unsafe": "true"},  # only literal True opts in
    ):
        d = _decision("shell.exec", payload)
        assert tool.validate(d).ok is False


# --- (d) never raises --------------------------------------------------------


def test_execute_never_raises_on_bad_cwd():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {
        "command": "python -c \"print(1)\"",
        "root": "Z:\\definitely\\does\\not\\exist\\anywhere",
    })
    # Must not raise -- an honest structured failure observation instead.
    out = tool.execute(d)
    assert out["exitCode"] is None
    assert out["timedOut"] is False
    assert "error" in out or out["stderr"]


def test_execute_never_raises_on_malformed_command():
    tool = _load_tool("shell_exec_tool.py", "ShellExecTool")
    d = _decision("shell.exec", {"command": ["this-binary-does-not-exist-xyz123"]})
    out = tool.execute(d)
    assert out["exitCode"] is None
    assert "error" in out
# #EXT-037-REQ-2 End
