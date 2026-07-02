"""EXT-008 REQ-4: multi-module dependency support in the build + oracle env.

Proves _run_oracle writes caller-supplied dependency modules into the (otherwise
isolated) oracle temp dir, so an implementation that imports an already-built
sibling module passes its held-out oracle instead of ImportError-ing. Offline —
no model call; exercises _run_oracle directly with canned strings.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.intent_loop import _run_oracle  # noqa: E402


# #EXT-008-REQ-4 Start
def test_oracle_passes_with_deps_and_fails_without():
    dep_src = "def helper():\n    return 42\n"
    impl = "from depmod import helper\n\ndef compute():\n    return helper()\n"
    oracle_test = "from usesdep import compute\n\n\ndef test():\n    assert compute() == 42\n"

    assert _run_oracle("usesdep", "usesdep.py", impl, oracle_test,
                        "python -m pytest -q", deps={"depmod.py": dep_src}) is True
    assert _run_oracle("usesdep", "usesdep.py", impl, oracle_test,
                        "python -m pytest -q") is False
# #EXT-008-REQ-4 End
