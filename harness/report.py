"""Operator metrics report (EXT-005 / REQ-6).

Summarizes convergence with metrics that get BETTER (pass rate, per-tier, frontier)
and MORE ACCURATE over time: the pass rate carries a Wilson 95% confidence interval
that tightens as the suite grows, plus a coverage section showing measurement breadth
increasing (tasks, tiers, real benchmarks). Renders markdown + a phone-sized headline.
"""

from __future__ import annotations

import glob
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".jaros-data" / "artifacts" / "eval"
HISTORY = ARTIFACTS / "history.jsonl"
REPORT_MD = ARTIFACTS / "REPORT.md"
AGENTS_DIR = ROOT / ".jaros-data" / "agents"
TOOLS_DIR = ROOT / ".jaros-data" / "tools"
EVALS_DIR = ROOT / "evals" / "coding_tasks"
SPECS_DIR = ROOT / ".jarify"

# The swarm goal (PRIME-001): hundreds -> thousands -> tens of thousands.
SWARM_GOAL = 10000


def census() -> dict:
    """Count the system's agents, tools, eval tasks, and specs. Success is visible
    only as these COUNTS rising (toward the swarm goal) with improving quality."""
    def count_py(d: Path) -> int:
        return len([p for p in d.glob("*.py") if not p.name.startswith("_")]) if d.exists() else 0
    return {
        "agents": count_py(AGENTS_DIR),
        "tools": count_py(TOOLS_DIR),
        "evals": len(list(EVALS_DIR.glob("*.json"))) if EVALS_DIR.exists() else 0,
        "specs": len([p for p in SPECS_DIR.glob("EXT-*") if p.is_dir()]) if SPECS_DIR.exists() else 0,
    }


def wilson_interval(solved: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for a pass proportion. Width shrinks as total grows —
    this is what makes the parity estimate *more accurate over time*."""
    if total == 0:
        return (0.0, 1.0)
    p = solved / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (max(0.0, center - half), min(1.0, center + half))


def _latest_scorecard() -> dict | None:
    files = sorted(glob.glob(str(ARTIFACTS / "scorecard-*.json")))
    if not files:
        return None
    return json.loads(Path(files[-1]).read_text(encoding="utf-8"))


def _trend(n: int = 8) -> list[dict]:
    if not HISTORY.is_file():
        return []
    rows = [json.loads(x) for x in HISTORY.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows[-n:]


def build_report() -> dict:
    sc = _latest_scorecard()
    trend = _trend()
    if sc is None:
        return {"headline": "no eval run yet — run scripts/eval.py", "markdown": "_No eval has run yet._"}

    solved, total = sc["solved"], sc["total"]
    lo, hi = wilson_interval(solved, total)
    pct = round(100 * sc["passRate"])
    ci_w = round(100 * (hi - lo))
    tiers = sorted(sc.get("perTier", {}), key=int)
    suites = sorted({r.get("suite", "authored") for r in trend} | {sc.get("suite", "authored")})
    has_real = "humaneval" in suites

    # Growth census: counts must rise over time (with quality). Compare to the
    # earliest recorded census so the owner sees agents/tools/evals increasing.
    now_c = census()
    first_c = next((r["census"] for r in trend if isinstance(r.get("census"), dict)), None)

    def _delta(key: str) -> str:
        if not first_c:
            return ""
        d = now_c[key] - first_c.get(key, 0)
        return f" (+{d})" if d > 0 else (f" ({d})" if d < 0 else " (=)")

    headline = (f"jaros-code A{now_c['agents']} T{now_c['tools']} E{now_c['evals']} | "
                f"{solved}/{total}={pct}% (CI {round(lo*100)}-{round(hi*100)}%) "
                f"frontier t{sc.get('frontierTier')} | vs Opus4.8=100%")[:199]

    lines = []
    lines.append(f"# jaros-code convergence report")
    lines.append(f"_generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ·  model {sc['model']}_\n")
    lines.append(f"## Capability (improving)")
    lines.append(f"- **Pass rate: {solved}/{total} = {pct}%**  (95% CI {round(lo*100)}–{round(hi*100)}%, ±{ci_w//2}pts)")
    lines.append(f"- Target = Claude Code on Opus 4.8 = **100%**")
    lines.append(f"- Frontier tier (focus here): **{sc.get('frontierTier')}**" +
                 ("  ⚠️ suite TOO EASY" if sc.get("tooEasy") else ""))
    for t in tiers:
        td = sc["perTier"][t]
        lines.append(f"  - tier {t}: {td['solved']}/{td['total']}  ({round(td['passRate']*100)}%)")
    lines.append(f"\n## Growth toward the swarm (must increase, with quality)")
    lines.append(f"- **Agents: {now_c['agents']}{_delta('agents')}**  ·  "
                 f"**Tools: {now_c['tools']}{_delta('tools')}**  ·  "
                 f"**Evals: {now_c['evals']}{_delta('evals')}**  ·  Specs: {now_c['specs']}{_delta('specs')}")
    lines.append(f"- Goal: hundreds → thousands → tens of thousands "
                 f"(swarm target ~{SWARM_GOAL:,} agents/tools/evals). Prune what doesn't help; net up.")
    mc = sc.get("modelCalls") or {}
    if mc.get("count"):
        avg = round(mc["totalLatencySec"] / mc["count"], 2) if mc["count"] else 0
        lines.append(f"\n## Local model calls (proof gemma2:2b is doing the work)")
        lines.append(f"- **{mc['model']} calls this run: {mc['count']}**  (avg {avg}s/call, last {mc.get('lastCall')})")
        lines.append(f"- Tail `.jaros-data/artifacts/eval/model_calls.log` to watch calls stream live.")

    wiring = sc.get("wiringUsage") or {}
    usage = sc.get("toolUsage") or {}
    lines.append(f"\n## Wiring usage (must be USED by agents; no orphans)")
    if wiring:
        ranked = sorted(wiring.items(), key=lambda kv: -kv[1])
        lines.append(f"- **Wirings actually fired: {len(wiring)} distinct agent→tool edges**")
        for edge, n in ranked:
            lines.append(f"  - {edge}  ({n})")
    # Orphans: components that exist but never fired this run -> wire in or prune.
    tools_fired = {t for t in usage if t != "advance"}
    orphan_tools = max(0, now_c["tools"] - len(tools_fired))
    sources_fired = {e.split(" -> ")[0] for e in wiring} - {"orchestrator"}
    lines.append(f"- Tools fired: {len(tools_fired)}/{now_c['tools']}  ·  agent sources firing: {len(sources_fired)}/{now_c['agents']}")
    lines.append(f"- **Orphans (exist but never fired): ~{orphan_tools} tools, "
                 f"~{max(0, now_c['agents'] - len(sources_fired))} agents** — wire them in or prune (owner rule).")

    lines.append(f"\n## Measurement accuracy (tightening)")
    lines.append(f"- Tasks measured: **{total}**  ·  tiers: **{len(tiers)}**  ·  CI width: **{ci_w}pts** (smaller = more accurate)")
    lines.append(f"- Real public benchmark included: **{'yes (HumanEval)' if has_real else 'not yet'}**")
    lines.append(f"- More tasks + real benchmarks → narrower CI → a more trustworthy parity number.")
    lines.append(f"\n## Trend (last {len(trend)} runs)")
    for r in trend:
        lines.append(f"- {r['timestamp'][:19]}  {r.get('suite','authored'):<9} {r['solved']}/{r['total']}  {round(r['passRate']*100)}%")

    md = "\n".join(lines) + "\n"
    return {
        "headline": headline, "markdown": md,
        "passRate": sc["passRate"], "solved": solved, "total": total,
        "ci": [round(lo, 4), round(hi, 4)], "ciWidthPts": ci_w,
        "frontierTier": sc.get("frontierTier"), "tooEasy": sc.get("tooEasy"),
        "tasks": total, "tiers": len(tiers), "hasRealBenchmark": has_real,
        "perTier": sc.get("perTier", {}),
        "census": now_c,
    }


def write_report() -> dict:
    rep = build_report()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(rep["markdown"], encoding="utf-8")
    return rep
