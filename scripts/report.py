"""Print the jaros-code convergence report (EXT-005 / REQ-6).

  python scripts/report.py            # print markdown report + write REPORT.md
  python scripts/report.py --headline # print only the phone-sized headline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.report import write_report  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(prog="report")
    p.add_argument("--headline", action="store_true", help="print only the one-line headline")
    args = p.parse_args()
    rep = write_report()
    print(rep["headline"] if args.headline else rep["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
