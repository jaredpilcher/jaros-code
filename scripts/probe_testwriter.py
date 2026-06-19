"""Diagnostic: what tests does the test-writer actually emit for the intent tasks?
If the tests are malformed/impossible, no implementation can pass -- that points the
next fix at the test-writer grain, not the implementer."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.coding_loop import build_llm, _load_agent  # noqa: E402

writer = _load_agent("test_writer_agent.py", build_llm())
for p in sorted((ROOT / "evals" / "intent_tasks").glob("*.json")):
    t = json.loads(p.read_text())
    module = Path(t["target"]).stem
    [d] = writer.decide({"intent": t["intent"], "module": module,
                         "func": t.get("func", module), "signature": t.get("signature", ""),
                         "test_path": f"test_{module}.py", "seed": 1})
    print(f"\n===== {t['id']} -> {d.type} =====", flush=True)
    print(d.payload.get("content", d.payload.get("note", "")), flush=True)
