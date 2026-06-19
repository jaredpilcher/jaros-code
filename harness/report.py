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

    headline = (f"jaros-code {solved}/{total}={pct}% (95% CI {round(lo*100)}-{round(hi*100)}%) "
                f"frontier t{sc.get('frontierTier')} | gemma2:2b vs Opus4.8=100%")[:199]

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
    }


def write_report() -> dict:
    rep = build_report()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(rep["markdown"], encoding="utf-8")
    return rep
