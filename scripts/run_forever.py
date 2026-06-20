"""Continuous, always-on jaros-code runner (EXT-005 / REQ-7).

Runs FOREVER: perpetually exercises the harness over the eval suite on local
gemma2:2b, regenerates the convergence report, and writes a heartbeat after every
cycle — the always-on engine that keeps producing fresh metrics. Fault-isolated: any
cycle error is logged and the loop keeps going. Safe by construction: it only calls
the local model and runs the eval (pytest in throwaway temp dirs) — no network, no
host mutation outside the gitignored artifacts dir.

The Claude supervisor loop (ScheduleWakeup) reads the heartbeat this writes, pushes
reports, and makes the actual code improvements — so this can run continuously while
improvements land between its cycles (picked up automatically on the next cycle,
since agents/tools are re-read each run).

Run it detached so it persists:
    python scripts/run_forever.py        # foreground (Ctrl-C to stop)
Tune with env: JCODE_MAX_ITERS (default 2), JCODE_CYCLE_PAUSE_S (default 20).
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Inference now runs on the Jetson (small Gemma 4 via llama.cpp), NOT Ollama. Override
# with env if the device IP/port changes.
os.environ.setdefault("JCODE_LLM_BACKEND", "llamacpp")
os.environ.setdefault("LLAMACPP_HOST", "http://192.168.1.183:8000")
os.environ.setdefault("LLAMACPP_MODEL", "gemma-4-e2b")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ARTIFACTS = ROOT / ".jaros-data" / "artifacts" / "eval"
LOG = ARTIFACTS / "run_forever.log"
HEARTBEAT = ARTIFACTS / "heartbeat.json"


def _log(msg: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {msg}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    from harness.eval_runner import run_suite
    from harness.report import write_report

    from harness.llamacpp_client import health

    max_iters = int(os.environ.get("JCODE_MAX_ITERS", "3"))
    pause = int(os.environ.get("JCODE_CYCLE_PAUSE_S", "20"))
    backend = os.environ.get("JCODE_LLM_BACKEND", "llamacpp")
    model = os.environ.get("LLAMACPP_MODEL") or os.environ.get("OLLAMA_MODEL", "?")
    _log(f"run_forever START pid={os.getpid()} backend={backend} model={model} "
         f"max_iters={max_iters} pause={pause}s")

    def _endpoint_ready() -> bool:
        """Health-gate: when on llama.cpp (the Jetson), don't burn cycles while the device
        is moving/rebooting — wait for it to answer, writing a 'waiting' heartbeat so the
        supervisor sees the runner is alive but the endpoint is down."""
        if backend != "llamacpp":
            return True
        h = health()
        if h.get("ok"):
            return True
        HEARTBEAT.write_text(json.dumps({
            "cycle": cycle, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "alive": True, "endpointUp": False, "endpoint": h.get("host"),
            "note": f"waiting for inference endpoint ({h.get('error', 'down')})",
        }, indent=2), encoding="utf-8")
        _log(f"endpoint down ({h.get('host')}) — waiting for the Jetson to come back")
        return False

    cycle = 0
    while True:
        cycle += 1
        if not _endpoint_ready():
            cycle -= 1            # don't count a skipped cycle
            time.sleep(15)
            continue
        t0 = time.time()
        try:
            sc = run_suite(max_iters=max_iters, verbose=False)
            rep = write_report()
            HEARTBEAT.write_text(json.dumps({
                "cycle": cycle,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "alive": True,
                "passRate": sc["passRate"],
                "solved": sc["solved"],
                "total": sc["total"],
                "frontierTier": sc.get("frontierTier"),
                "ci": rep.get("ci"),
                "ciWidthPts": rep.get("ciWidthPts"),
                "headline": rep.get("headline"),
                "lastCycleSec": round(time.time() - t0, 1),
            }, indent=2), encoding="utf-8")
            _log(f"cycle {cycle} OK ({round(time.time()-t0)}s): {rep.get('headline')}")
        except Exception as exc:  # never let one cycle kill the forever loop
            _log(f"cycle {cycle} ERROR: {exc!r}\n{traceback.format_exc()}")
        time.sleep(pause)


if __name__ == "__main__":
    raise SystemExit(main())
