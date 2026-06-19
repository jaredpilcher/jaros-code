"""EXT-002 agent contract tests with a deterministic fake LLM.

We verify the agents' parsing + Decision-emission contracts WITHOUT calling
gemma2:2b, so the suite is fast and deterministic. A separate live smoke test
(test_live_smoke.py, opt-in) exercises the real model.

Agents live in .jaros-data/agents (not a package); we load each by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from jaros.llm import LlmResponse

AGENTS_DIR = Path(__file__).resolve().parents[1] / ".jaros-data" / "agents"


def _load_agent(filename: str):
    path = AGENTS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"agent_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLlm:
    """Deterministic LlmClient stub returning a canned response."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, req) -> LlmResponse:
        return LlmResponse(text=self._text, model="fake")


# --- REQ-1 editor ----------------------------------------------------------

def test_editor_emits_apply_patch():
    mod = _load_agent("editor_agent.py")
    reply = "<<<OLD\nx = 1\nOLD>>>\n<<<NEW\nx = 2\nNEW>>>"
    agent = mod.build(FakeLlm(reply))
    [d] = agent.decide({"path": "f.py", "content": "x = 1\n", "instruction": "set x to 2"})
    assert d.type == "code.apply_patch"
    assert d.payload == {"path": "f.py", "old": "x = 1", "new": "x = 2"}


def test_editor_unparseable_is_honest_fail():
    mod = _load_agent("editor_agent.py")
    agent = mod.build(FakeLlm("I cannot do that."))
    [d] = agent.decide({"path": "f.py", "content": "x = 1\n", "instruction": "nope"})
    assert d.type == "advance"
    assert d.payload["events"] == ["start", "fail"]


# --- REQ-2 commander -------------------------------------------------------

def test_commander_emits_shell_exec():
    mod = _load_agent("commander_agent.py")
    agent = mod.build(FakeLlm("```\npython -m pytest -q\n```"))
    [d] = agent.decide({"task": "run the tests"})
    assert d.type == "shell.exec"
    assert d.payload["command"] == "python -m pytest -q"


def test_commander_passes_cwd():
    mod = _load_agent("commander_agent.py")
    agent = mod.build(FakeLlm("ls"))
    [d] = agent.decide({"task": "list", "cwd": "/tmp"})
    assert d.payload["cwd"] == "/tmp"


# --- REQ-3 test-reader -----------------------------------------------------

def test_test_reader_pass():
    mod = _load_agent("test_reader_agent.py")
    agent = mod.build(FakeLlm("PASS"))
    [d] = agent.decide({"output": "1 passed"})
    assert d.payload["events"] == ["start", "complete"]
    assert d.payload["verdict"] == "pass"


def test_test_reader_defaults_to_fail_when_ambiguous():
    mod = _load_agent("test_reader_agent.py")
    agent = mod.build(FakeLlm("hmm not sure"))
    [d] = agent.decide({"output": "..."})
    assert d.payload["events"] == ["start", "fail"]
