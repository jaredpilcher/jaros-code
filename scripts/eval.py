"""Run the jaros-code convergence eval suite (EXT-005).

  python scripts/eval.py [--max-iters N] [--verbose] [--trend]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JAROS_LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.eval_runner import history, run_suite  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(prog="eval", description="jaros-code convergence eval")
    p.add_argument("--max-iters", "-n", type=int, default=3)
    p.add_argument("--verbose", "-v", action="store_true", help="show each task's transcript")
    p.add_argument("--trend", action="store_true", help="print the recorded pass-rate trend and exit")
    args = p.parse_args()

    if args.trend:
        rows = history()
        if not rows:
            print("no eval history yet")
            return 0
        print("\n pass-rate trend (toward 100% = Claude-Code on Opus-4.8)")
        for row in rows:
            pct = int(row["passRate"] * 100)
            suite = row.get("suite", "authored")
            print(f"   {row['timestamp'][:19]}  {suite:<10} {row['solved']}/{row['total']}  {pct:>3}%  {row['model']}")
        print()
        return 0

    run_suite(max_iters=args.max_iters, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
