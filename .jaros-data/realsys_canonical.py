"""KILLABLE CANONICAL real-systems scoreboard: runs BOTH halves (CREATE + MODIFY) of EXT-060,
each task in its own subprocess with a per-task wall-clock kill (taskkill /F /T on timeout), so
a pathological build/modify draw can never wedge the whole run -- mirrors realsys_killable.py
(CREATE-only) but adds the MODIFY half and prints the ONE tracked headline number (EXT-060
REQ-8): "CANONICAL real-systems: create X/A, modify Y/B, total (X+Y)/(A+B)".

This is the entrypoint to report from going forward -- NOT harness/system_suite.py's creation
suite, NOT harness/modification_suite.py, NOT harness/daily_driver.py (all three are demoted to
regression checks / task-shape feeders by EXT-060 REQ-7/REQ-8; see .jarify/EXT-060/intent.md).

Usage: python .jaros-data/realsys_canonical.py [N] [per_task_timeout_s]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.real_systems_suite import REAL_SYSTEMS_MODIFY_TASKS, REAL_SYSTEMS_TASKS  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
PER = int(sys.argv[2]) if len(sys.argv) > 2 else 240
PY = sys.executable
BUILD_ONE = str(ROOT / ".jaros-data" / "realsys_build_one.py")
MODIFY_ONE = str(ROOT / ".jaros-data" / "realsys_modify_one.py")


def _one(script, name):
    p = subprocess.Popen([PY, script, name], cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = p.communicate(timeout=PER)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        return {"accepted": False, "note": "KILLED (per-task wall-clock timeout)"}
    for line in (out or "").splitlines():
        if line.startswith("RESULT_JSON:"):
            return json.loads(line[len("RESULT_JSON:"):])
    return {"accepted": False, "note": "no RESULT_JSON (task crashed)"}


def _run_half(label, script, tasks):
    print(f"{label} HALF: {len(tasks)} classes x N={N} per_task_timeout={PER}s (leaves-OFF, gemma)",
          flush=True)
    acc = tot = 0
    for task in tasks:
        class_acc = 0
        for i in range(N):
            r = _one(script, task.name)
            class_acc += bool(r.get("accepted"))
            print(f"  {task.name:35s} [{i+1}/{N}] accepted={r.get('accepted')} "
                  f"note={str(r.get('note'))[:80]}", flush=True)
        acc += class_acc
        tot += N
        print(f"CLASS {task.name:35s}: pass@1 {class_acc}/{N}", flush=True)
    return acc, tot


t0 = time.time()
create_passed, create_n = _run_half("CREATE", BUILD_ONE, REAL_SYSTEMS_TASKS)
modify_passed, modify_n = _run_half("MODIFY", MODIFY_ONE, REAL_SYSTEMS_MODIFY_TASKS)
total_passed = create_passed + modify_passed
total_n = create_n + modify_n
print(
    f"CANONICAL real-systems: create {create_passed}/{create_n}, modify "
    f"{modify_passed}/{modify_n}, total {total_passed}/{total_n} "
    f"elapsed={round(time.time() - t0)}s",
    flush=True,
)
