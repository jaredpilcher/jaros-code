"""jcode — the jaros-code operator CLI (EXT-003 / EXT-004 seed).

Runs the bounded edit->test->judge loop on a target file using the gemma2:2b agent
fleet and deterministic tools. Claude-Code-like transcript.

  python scripts/jcode.py fix <file> --instruction "..." --test "pytest -q"
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

from harness.coding_loop import fix_loop  # noqa: E402


def main() -> int:
    # No args -> Claude-Code-like interactive slash-command REPL.
    if len(sys.argv) == 1:
        from harness.cli import repl
        return repl()

    parser = argparse.ArgumentParser(prog="jcode", description="jaros-code coding harness")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fix = sub.add_parser("fix", help="iterate edit->test->judge until tests pass")
    fix.add_argument("target", help="file to edit")
    fix.add_argument("--instruction", "-i", required=True, help="what to change")
    fix.add_argument("--test", "-t", required=True, help="shell command that runs the tests")
    fix.add_argument("--max-iters", "-n", type=int, default=4)
    fix.add_argument("--cwd", default=None, help="working dir for the test command")
    args = parser.parse_args()

    if args.cmd == "fix":
        res = fix_loop(args.target, args.instruction, args.test,
                       max_iters=args.max_iters, cwd=args.cwd)
        return 0 if res.success else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
