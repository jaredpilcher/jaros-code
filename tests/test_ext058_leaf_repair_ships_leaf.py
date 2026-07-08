"""EXT-058 TASK-7: offline (no model call) tests closing a MEASURED Tenet-3 false-done in the
leaf-repair adopt block of ``harness.system_builder.build_system`` (REQ-3).

MEASURED BUG: when leaf-repair adopted a verified leaf it wrote ``main.py`` (the leaf) into
``root`` and flipped ``done=True``, but left the free-form build's OTHER already-written files
(e.g. ``cli.py``, ``store.py``) on disk in ``root``, and left the returned ``plan`` as the
free-form plan (whose ``entrypoint`` names a free-form module, not ``main.py``). Acceptance was
graded against a CLEAN throwaway ``cand_root`` holding only the leaf, so ``done=True`` -- but the
SHIPPED ``root`` still ran the buggy free-form entrypoint. The leaf itself was correct in
isolation; the adopt step just failed to make the shipped artifact match what was graded.

This file proves the fix's honesty invariants:
  1. After a genuine leaf adopt, ``root`` on disk contains ONLY ``main.py`` (every stale
     free-form module is stripped), the returned ``plan["entrypoint"] == "main.py"``, and the
     REAL, independent ``kv-store-ttl-cli`` task oracle run against the SHIPPED ``root`` passes.
  2. FAIL SAFE: when the belt-and-suspenders re-verification against ``root`` itself does not
     pass (simulated here by forcing checks against the real build ``root`` to fail, while the
     throwaway ``cand_root`` legitimately passes), the adopt is rolled back byte-for-byte --
     ``root``/``built``/``plan``/``done`` are left exactly as the free-form result. No
     half-swapped root, no false-done.

Uses the REAL, unmodified ``graph_dsl.LEAF_LIBRARY["ttl-store"]`` (TASK-5's real-seconds
``time.time()``-based ``TTL_STORE_LEAF``) as the adopted leaf throughout -- it genuinely earns
admission against this file's real-seconds-worded spec (EXT-056/TASK-10's ``_ttl_convention``
fix), so no monkeypatch of ``graph_dsl.LEAF_LIBRARY`` is needed; ``harness/graph_dsl.py`` is never
modified by this file.

Entirely offline and deterministic: no `llm`/model call anywhere in this file (every `llm` is a
canned stub), no on-Jetson build.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness import graph_dsl
from harness import system_builder
from harness.system_builder import build_system
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-3 Start

# --- fixtures ------------------------------------------------------------------------------

# A self-authored ttl-store spec, deliberately the SAME wording convention as
# `tests/test_ext058_leaf_repair.py`'s own `LEAF_REPAIR_SPEC` (fingerprints as `ttl-store` via
# the plain "time-to-live"/"TTL" keyword hit `adt_oracle.classify_confident` looks for).
LEAF_REPAIR_SPEC = (
    "Write a single-file Python CLI program named main.py, an in-memory cache with "
    "per-key expiry (time-to-live / TTL). Invoked as `python main.py` with no "
    "arguments, it consumes commands one per stdin line until EOF and immediately "
    "prints each command's result, in the same order. Commands: `set <key> <value> "
    "<ttl>` saves value under key for ttl seconds (a ttl of 0 means already expired) "
    "and prints `ok`; `get <key>` prints the live value or `none`; `delete <key>` "
    "removes the key and prints `ok`. Include an `if __name__ == \"__main__\":` "
    "block that runs this."
)

# A MULTI-MODULE free-form plan -- the bug report's exact shape: the entrypoint is NOT
# `main.py`, and there is at least one OTHER module file the free-form build wrote alongside it
# (a stray, unused `store.py`, standing in for the measured `cli.py`/`store.py`/
# `data_manager.py` leftovers).
_MULTI_MODULE_PLAN_JSON = """{
  "modules": [
    {"name": "store.py", "responsibility": "placeholder data holder (unused)",
     "exports": [{"name": "Store", "signature": "class Store:"}], "imports": []},
    {"name": "cli.py", "responsibility": "ttl cache CLI entrypoint",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "cli.py",
  "acceptance": "ttl semantics"
}"""

# A stray free-form module the (buggy) build wrote but never actually used -- must be stripped
# from `root` once a verified leaf is adopted.
_DECOY_STORE_MODULE = '''\
class Store:
    """Unused placeholder -- a stray free-form file the leaf adopt must strip from root."""
'''

# The free-form ENTRYPOINT: syntactically fine, never crashes, but silently IGNORES the ttl
# entirely -- a key set with any ttl (including 0) never expires. Fails only the ADT
# differential-oracle check (a genuine semantic bug), never a crash/usage check. Self-contained
# (does not import `store.py`) so import-wiring auto-stitching stays a no-op.
_BROKEN_TTL_CLI_ENTRYPOINT = '''\
import sys


def main():
    store = {}
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0]
        if cmd == "set" and len(parts) == 4:
            key, value, ttl = parts[1], parts[2], int(parts[3])
            store[key] = value  # BUG: ttl is ignored entirely, nothing ever expires
            print("ok")
        elif cmd == "get" and len(parts) == 2:
            value = store.get(parts[1])
            print(value if value is not None else "none")
        elif cmd == "delete" and len(parts) == 2:
            store.pop(parts[1], None)
            print("ok")


if __name__ == "__main__":
    main()
'''


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _MultiModuleLeafRepairLlm:
    """Canned `llm` for the multi-module free-form scenario: always plans the SAME two-module
    plan (`store.py` + `cli.py`, entrypoint `cli.py`), proposes an EMPTY acceptance checklist (so
    the composed checklist is exactly the deterministic minimum), and builds each module's body
    from `module_bodies` by matching the module name embedded in `BUILD_PROMPT`
    ("Write the COMPLETE Python module `<name>` ...")."""

    def __init__(self, module_bodies: dict) -> None:
        self.module_bodies = module_bodies

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(_MULTI_MODULE_PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        if "COMPLETE Python module" in prompt:
            for name, code in self.module_bodies.items():
                if f"`{name}`" in prompt:
                    return _Resp(code)
            return _Resp("")
        return _Resp("")


def _kv_store_ttl_task():
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == "kv-store-ttl-cli")


def _multi_module_llm():
    return _MultiModuleLeafRepairLlm(
        {"store.py": _DECOY_STORE_MODULE, "cli.py": _BROKEN_TTL_CLI_ENTRYPOINT})


# --- (1) a genuine leaf adopt SHIPS exactly the leaf -----------------------------------------

def test_leaf_adopt_strips_stale_free_form_files_and_points_plan_at_the_leaf():
    expected_leaf_code = graph_dsl.LEAF_LIBRARY["ttl-store"]

    with tempfile.TemporaryDirectory(prefix="ext058_ships_leaf_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=_multi_module_llm())

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "leaf:ttl-store"

        # (a) root on disk contains ONLY main.py -- the stale free-form files (cli.py, store.py)
        # are stripped, never left for a downstream entrypoint/import to accidentally pick up.
        on_disk = sorted(p.name for p in root.glob("*.py"))
        assert on_disk == ["main.py"], on_disk
        assert (root / "main.py").read_text(encoding="utf-8") == expected_leaf_code
        assert result["modules"] == {"main.py": expected_leaf_code}

        # (b) the returned plan's entrypoint points at the leaf -- not the now-deleted,
        # stale free-form entrypoint (`cli.py`).
        assert result["plan"] == {"entrypoint": "main.py", "modules": [{"name": "main.py"}]}

        # (c) the REAL, independent kv-store-ttl-cli task oracle -- run against the SHIPPED
        # root -- passes (no reimplemented grading logic, reuses system_suite's own checks).
        task = _kv_store_ttl_task()
        results = [_run_single_check(c, root, result.get("plan"), PY) for c in task.checks]
        assert all(results), results


# --- (2) fail-safe: an adopt that fails to re-verify on ROOT is rolled back byte-for-byte -----

def test_leaf_adopt_rolls_back_when_root_reverification_fails(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="ext058_ships_leaf_failsafe_") as tmp:
        root = Path(tmp) / "built"

        # Simulate the belt-and-suspenders re-verification failing against the SHIPPED root
        # (while the leaf legitimately passes on its own throwaway cand_root) -- any check run
        # against the real build root always fails; every other directory (incl. cand_root) is
        # graded for real. This is the ONLY thing monkeypatched -- `build_system`,
        # `graph_dsl.dsl_to_system`, and `_minimum_acceptance` all run their real, unmodified
        # code.
        real_run_check = system_builder._run_check

        def _run_check_root_always_fails(check_root, check):
            if Path(check_root) == root:
                return False
            return real_run_check(check_root, check)

        monkeypatch.setattr(system_builder, "_run_check", _run_check_root_always_fails)

        result = build_system(LEAF_REPAIR_SPEC, root, llm=_multi_module_llm())

        assert result["done"] is False
        assert result.get("build_path") == "free-form"
        assert result["unmet"]

        # root is restored to the EXACT pre-adopt free-form state -- no half-swapped root, no
        # orphaned leaf main.py left behind, no adopted-but-broken leaf.
        on_disk = sorted(p.name for p in root.glob("*.py"))
        assert on_disk == ["cli.py", "store.py"], on_disk
        assert (root / "cli.py").read_text(encoding="utf-8") == result["modules"]["cli.py"]
        assert (root / "store.py").read_text(encoding="utf-8") == result["modules"]["store.py"]
        assert not (root / "main.py").exists()

        # the returned plan is still the free-form plan (never repointed at a leaf that never
        # actually shipped).
        assert result["plan"]["entrypoint"] == "cli.py"
# #EXT-058-REQ-3 End
