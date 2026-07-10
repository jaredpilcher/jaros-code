"""Modify+grade ONE real-systems MODIFY task in an isolated subprocess, printing a single
RESULT_JSON line. Mirrors realsys_build_one.py (EXT-060 REQ-7/REQ-8) so the canonical
scoreboard's MODIFY half is killable exactly like its CREATE half -- a pathological
modify_system draw can't wedge the whole run. Pure gemma, leaves-OFF.

Usage: python .jaros-data/realsys_modify_one.py <modify-task-name>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.real_systems_suite import (  # noqa: E402
    REAL_SYSTEMS_MODIFY_TASKS,
    run_real_systems_modify_suite,
)
from harness.coding_loop import build_llm  # noqa: E402


def main():
    name = sys.argv[1]
    task = next(t for t in REAL_SYSTEMS_MODIFY_TASKS if t.name == name)
    llm = build_llm()
    try:
        out = run_real_systems_modify_suite([task], llm=llm)
        r = out["results"][0]
        rec = {"name": name, "accepted": bool(r.get("accepted")),
               "applied": bool(r.get("applied")), "note": str(r.get("note"))[:160]}
    except Exception as e:  # noqa: BLE001
        rec = {"name": name, "accepted": False, "applied": False,
               "note": f"ERR {type(e).__name__}: {e}"[:160]}
    print("RESULT_JSON:" + json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
