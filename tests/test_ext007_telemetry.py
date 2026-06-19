"""EXT-007 REQ-4 wiring-telemetry tests (deterministic, no model)."""

from __future__ import annotations

import uuid

from jaros.core import create_decision

from harness.coding_loop import Runtime, reset_tool_usage, tool_usage


def test_tool_usage_counts_fired_decisions(tmp_path):
    reset_tool_usage()
    rt = Runtime(data_dir=tmp_path)
    f = tmp_path / "w.py"
    rt.apply(create_decision(id=f"w-{uuid.uuid4().hex}", source="t",
                             type="code.write_file", payload={"path": str(f), "content": "x = 1\n"}))
    rt.apply(create_decision(id=f"s-{uuid.uuid4().hex}", source="t",
                             type="py.symbols", payload={"path": str(f)}))
    usage = tool_usage()
    assert usage.get("code.write_file") == 1
    assert usage.get("py.symbols") == 1


def test_reset_clears_usage(tmp_path):
    reset_tool_usage()
    assert tool_usage() == {}
