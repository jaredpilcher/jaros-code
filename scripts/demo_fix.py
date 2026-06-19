"""Self-contained, repeatable demo: gemma2:2b fixes a real bug through the harness.

Writes a fresh buggy `calc.add` (subtracts instead of adds) and a failing test into
a gitignored artifacts dir, then runs the bounded edit->test->judge loop. Proves the
full two-plane pipeline end to end on the local 2B model.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JAROS_LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.coding_loop import fix_loop  # noqa: E402

demo = ROOT / ".jaros-data" / "artifacts" / "demo"
demo.mkdir(parents=True, exist_ok=True)
(demo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
(demo / "test_calc.py").write_text(
    "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    encoding="utf-8",
)

res = fix_loop(
    target=str(demo / "calc.py"),
    instruction=(
        "The add function must return the SUM of a and b, but it currently subtracts "
        "(return a - b). Change it to return a + b so that add(2, 3) == 5."
    ),
    test_cmd=f'python -m pytest "{demo / "test_calc.py"}" -q',
    cwd=str(demo),
    max_iters=4,
)
sys.exit(0 if res.success else 1)
