"""EXT-002/REQ-6 + EXT-001/REQ-12: config specialist agent + json.check tool +
loop dispatcher. Deterministic (fake LLM) where a model would be involved."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from jaros.core import create_decision
from jaros.llm import LlmResponse

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".jaros-data" / "agents"
TOOLS = ROOT / ".jaros-data" / "tools"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"m_{path.stem}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeLlm:
    def __init__(self, text):
        self._t = text

    def complete(self, req):
        return LlmResponse(text=self._t, model="fake")


def test_json_check_valid_and_invalid():
    tool = getattr(_load(TOOLS / "json_check_tool.py"), "JsonCheckTool")()
    assert tool.execute(create_decision(id="a", source="t", type="json.check",
                                        payload={"text": '{"a": 1}'}))["valid"] is True
    bad = tool.execute(create_decision(id="b", source="t", type="json.check",
                                       payload={"text": '{"a": 1'}))
    assert bad["valid"] is False and bad["error"]


def test_config_editor_emits_write_file():
    mod = _load(AGENTS / "config_editor_agent.py")
    agent = mod.build(FakeLlm('<<<FILE\n{"port": 9090}\nFILE>>>'))
    [d] = agent.decide({"path": "config.json", "content": '{"port": 8080}',
                        "instruction": "set port 9090"})
    assert d.type == "code.write_file"
    assert '9090' in d.payload["content"]


def test_loop_dispatches_config_files_to_config_editor():
    # The deterministic dispatcher routes by target type (EXT-007/REQ-6).
    from harness.coding_loop import select_editor_agent
    assert select_editor_agent("config.json") == "config_editor_agent.py"
    assert select_editor_agent("app.yaml") == "config_editor_agent.py"
    assert select_editor_agent("calc.py") == "rewriter_agent.py"
    assert select_editor_agent("calc.py", "editor_agent.py") == "editor_agent.py"  # override respected
