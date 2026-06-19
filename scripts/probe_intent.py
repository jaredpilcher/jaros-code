"""First honest measurement of the generative spine: run build_from_intent on the
intent tasks and print self_pass vs oracle_pass (the un-gameable intent-fidelity)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.intent_loop import build_from_intent  # noqa: E402

tasks = [json.loads(p.read_text()) for p in sorted((ROOT / "evals" / "intent_tasks").glob("*.json"))]
which = sys.argv[1] if len(sys.argv) > 1 else None
for t in tasks:
    if which and t["id"] != which:
        continue
    print(f"\n===== {t['id']} (tier {t['tier']}) =====", flush=True)
    r = build_from_intent(t, max_iters=3, verbose=True)
    print(f"  -> self_pass={r.self_pass}  oracle_pass={r.oracle_pass}  [{r.note}]", flush=True)
