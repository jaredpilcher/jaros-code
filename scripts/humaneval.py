"""Run the real HumanEval benchmark through the jaros-code harness (EXT-005/REQ-5).

  python scripts/humaneval.py [--limit N] [--max-iters N] [--verbose]

Requires evals/benchmarks/HumanEval.jsonl (see harness/humaneval.py for how to get it).
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

from harness.humaneval import run_humaneval  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(prog="humaneval")
    p.add_argument("--limit", "-l", type=int, default=20, help="number of problems (0 = all)")
    p.add_argument("--max-iters", "-n", type=int, default=3)
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()
    try:
        run_humaneval(limit=(None if args.limit == 0 else args.limit),
                      max_iters=args.max_iters, verbose=args.verbose)
    except FileNotFoundError as exc:
        print(exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
