"""Continual honesty audit (EXT-007 / REQ-5).

Mechanically catches the ways a self-improving system lies to itself, so the owner's
"keep it absolutely honest" rule is enforced by code, not just judgement:

- CRITICAL: a run that solved tasks with ZERO local-model calls (results not actually
  produced by gemma2:2b — a bug or a shortcut).
- MISLEADING: reporting a tiny/non-representative suite (e.g. a 1-2 task verify run)
  as if it were the headline number.
- STAGNATION: the full-suite pass rate is flat across recent runs — activity without
  capability improvement (this is exactly what hid the 67% plateau).
- UNUSED: agents/tools that exist but never fire (orphans), inflating the census.

The supervisor runs this every cycle and must ACT on flags (fix CRITICAL, change
approach on STAGNATION), never paper over them.
"""

from __future__ import annotations

REP_MIN_TASKS = 10          # below this, a suite is not representative
STAGNATION_WINDOW = 3       # runs
STAGNATION_EPS = 0.03       # < 3 percentage-points spread == flat


def audit(scorecard: dict, history: list[dict]) -> list[dict]:
    """Return a list of {level, code, message} honesty flags (possibly empty)."""
    flags: list[dict] = []
    total = scorecard.get("total", 0)
    solved = scorecard.get("solved", 0)
    mc = scorecard.get("modelCalls") or {}

    # CRITICAL: solved work with no model calls -> not really gemma2:2b.
    if total > 0 and solved > 0 and not mc.get("count"):
        flags.append({"level": "CRITICAL", "code": "no-model-calls",
                      "message": f"{solved} solved but modelCalls.count=0 — results not produced by the local model"})

    # MISLEADING: a tiny suite is not a representative capability number.
    if 0 < total < REP_MIN_TASKS:
        flags.append({"level": "MISLEADING", "code": "tiny-suite",
                      "message": f"suite has only {total} tasks (<{REP_MIN_TASKS}); do not report it as the headline"})

    # STAGNATION: full-suite pass rate flat across the recent window.
    fulls = [r for r in history if r.get("total", 0) >= REP_MIN_TASKS and "passRate" in r]
    if len(fulls) >= STAGNATION_WINDOW:
        rates = [round(r["passRate"], 4) for r in fulls[-STAGNATION_WINDOW:]]
        if max(rates) - min(rates) < STAGNATION_EPS:
            flags.append({"level": "STAGNATION", "code": "flat-passrate",
                          "message": f"full-suite pass rate flat at {[round(x*100) for x in rates]}% over last "
                                     f"{STAGNATION_WINDOW} runs — change the approach, don't add more plumbing"})

    # UNUSED: orphan tools/agents inflate the census without doing work.
    usage = scorecard.get("toolUsage") or {}
    wiring = scorecard.get("wiringUsage") or {}
    cen = scorecard.get("census") or {}
    if cen:
        tools_fired = len({t for t in usage if t != "advance"})
        agents_fired = len({e.split(" -> ")[0] for e in wiring} - {"orchestrator"})
        orphan_tools = max(0, cen.get("tools", 0) - tools_fired)
        orphan_agents = max(0, cen.get("agents", 0) - agents_fired)
        if orphan_tools or orphan_agents:
            flags.append({"level": "UNUSED", "code": "orphans",
                          "message": f"~{orphan_tools} tools and ~{orphan_agents} agents never fired this run — "
                                     "wire them in or prune (counts must reflect USED components)"})
    return flags


def format_flags(flags: list[dict]) -> str:
    if not flags:
        return "Honesty audit: clean (no flags)."
    return "\n".join(f"[{f['level']}] {f['code']}: {f['message']}" for f in flags)
