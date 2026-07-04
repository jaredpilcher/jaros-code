"""Run a long command (e.g. pytest) with a live HEARTBEAT so the run is never an opaque
wedge (EXT-040 REQ-2, owner directive 2026-07-04).

The recurring "stuck" failure mode: a long ``pytest tests/`` (or a build loop) is launched,
goes silent for many minutes, and a watcher cannot tell "working" from "wedged". This runner
spawns the command as a child, waits for it in the FOREGROUND (it always blocks until the
child exits -- no backgrounding, no monitor to get lost), and meanwhile a daemon thread
updates ``harness.heartbeat`` every ``interval`` seconds with elapsed time. On completion it
records the exit code + a short output tail. A separate ``/status`` reader (or the autonomous
watcher) can then see, at any moment: "<label>: running Ns" or "<label>: done exit=0 (Ns)".

Usage (CLI):  python -m harness.run_with_heartbeat --label "full suite" -- python -m pytest tests/ -q
Returns exit code = the child's exit code, so it is a drop-in wrapper.

Deterministic execution-plane code: no model calls. Never raises on its OWN bookkeeping.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from harness import heartbeat as hb

# #EXT-040-REQ-2 Start


def run_with_heartbeat(cmd: "list[str]", *, label: str = "command", interval: float = 15.0,
                       timeout: "float | None" = None, cwd: "str | None" = None) -> dict:
    """Run ``cmd`` to completion, heartbeating every ``interval`` seconds. Returns
    ``{ok, exit_code, elapsed_s, timed_out, tail}``. Never raises: a spawn failure or timeout
    is an honest ``ok=False`` result. Always blocks until the child exits (or times out) --
    it CANNOT leave a run in an unobserved background state."""
    start = time.time()
    run_id = f"{label}-{int(start)}".replace(" ", "_")
    hb.beat(label, "START", run_id=run_id, started_at=start)

    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        hb.beat(label, f"SPAWN-FAILED: {type(exc).__name__}", run_id=run_id, started_at=start)
        return {"ok": False, "exit_code": None, "elapsed_s": 0.0,
                "timed_out": False, "tail": f"spawn failed: {exc}"}

    stop = threading.Event()

    def _pulse() -> None:
        while not stop.wait(interval):
            hb.beat(label, f"running {round(time.time() - start)}s", run_id=run_id,
                    started_at=start)

    pulse = threading.Thread(target=_pulse, name=f"hb-run-{run_id}", daemon=True)
    pulse.start()

    timed_out = False
    out = ""
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            proc.kill()
            out, _ = proc.communicate(timeout=10)
        except Exception:
            out = out or ""
    finally:
        stop.set()

    elapsed = round(time.time() - start, 1)
    code = proc.returncode
    tail = "\n".join((out or "").splitlines()[-25:])
    verdict = "TIMED-OUT" if timed_out else f"done exit={code}"
    hb.beat(label, f"{verdict} ({elapsed}s)", run_id=run_id, started_at=start)
    return {"ok": (code == 0) and not timed_out, "exit_code": code,
            "elapsed_s": elapsed, "timed_out": timed_out, "tail": tail}


def _main(argv: "list[str]") -> int:
    label = "command"
    interval = 15.0
    timeout = None
    # parse: --label X --interval N --timeout N -- <cmd...>
    rest = list(argv)
    parsed: "list[str]" = []
    while rest:
        a = rest.pop(0)
        if a == "--":
            parsed = rest
            break
        elif a == "--label" and rest:
            label = rest.pop(0)
        elif a == "--interval" and rest:
            try:
                interval = float(rest.pop(0))
            except ValueError:
                pass
        elif a == "--timeout" and rest:
            try:
                timeout = float(rest.pop(0))
            except ValueError:
                pass
        else:
            parsed = [a] + rest
            break
    if not parsed:
        print("usage: python -m harness.run_with_heartbeat --label L -- <cmd...>",
              file=sys.stderr)
        return 2
    res = run_with_heartbeat(parsed, label=label, interval=interval, timeout=timeout)
    print(res["tail"])
    print(f"[heartbeat] {label}: exit={res['exit_code']} elapsed={res['elapsed_s']}s "
          f"timed_out={res['timed_out']}")
    return int(res["exit_code"] or (1 if not res["ok"] else 0))


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
# #EXT-040-REQ-2 End
