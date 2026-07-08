"""EXT-058 TASK-6: offline (no model call) tests for the verified-leaf REPAIR branch wired into
``harness.system_builder.build_system`` (REQ-3's single-leaf DSL->system path made LIVE).

Covers TASK-6 step 4's three required cases:
  (a) ``graph_dsl.leaf_for_spec`` returns ``"ttl-store"`` for spec text that fingerprints the
      ttl-store CONTRACT, and ``None`` for an unrelated sum-cli/todo spec (and for a spec that
      fingerprints a DIFFERENT ADT the leaf-library has no verified template for -- earned
      membership, REQ-1).
  (b) a stubbed ``llm`` that ships a BROKEN ttl build (ttl is silently ignored, so it never
      expires) drives ``build_system`` down the leaf-repair branch, and the final result is
      ``done=True`` with ``build_path == "leaf:ttl-store"``, passing the REAL, independent
      ``kv-store-ttl-cli`` task oracle (``harness.system_suite``, reusing ``_run_single_check`` --
      no reimplemented grading logic), against the SHIPPED root (EXT-058/TASK-7).
  (d) the mirror honesty check: it can NEVER flip a broken build to done for a candidate leaf that
      does NOT actually pass the real acceptance floor.
  (c) a stubbed ``llm`` whose free-form build ALREADY passes never enters the leaf branch at all
      (``build_path == "free-form"``, byte-identical to before this task).

**Formerly a MEASURED GAP, now CLOSED (EXT-056/TASK-10, 2026-07-08):** the REAL, shipped
``graph_dsl.TTL_STORE_LEAF`` (TASK-5) is a real-time-seconds (``time.time()``) implementation, and
``adt_oracle``'s ttl-store differential oracle now DETECTS which convention a spec declares
(``_ttl_convention``) and drives the matching real-seconds probe for a spec worded like
``LEAF_REPAIR_SPEC``/``kv-store-ttl-cli`` (no ``tick`` wording) -- so the REAL, unmodified leaf now
genuinely EARNS admission; test (b) below exercises it directly, no monkeypatch/stand-in needed.
Test (d) instead proves the mirror honesty case with a deliberately still-broken CANDIDATE (the
SAME free-form bug, substituted into ``graph_dsl.LEAF_LIBRARY`` via ``monkeypatch`` so
``harness/graph_dsl.py`` itself is never modified by this file) -- it is correctly NOT adopted.

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
from harness.system_builder import build_system
from harness.system_suite import FIRST_SLICE, HARDER_SLICE, _run_single_check

PY = sys.executable

# #EXT-058-REQ-3 Start

# --- fixtures ----------------------------------------------------------------------------------

# A self-authored ttl-store spec (deliberately NOT copy-pasted from
# `system_suite.kv-store-ttl-cli`'s own sentence, which happens to contain the incidental words
# "store" and "...commands were read" -- both accidental hits in `adt_oracle`'s pre-existing
# verb-synonym table, `_ADT_VERB_SYNONYMS["ttl-store"]`, that would silently swap the driven
# command word away from "set"/"get" -- an unrelated, pre-existing wording-sensitivity in
# `adt_oracle._resolve_verbs`, not something this task touches). Fingerprints as `ttl-store` via
# the plain "time-to-live"/"TTL" keyword hit `adt_oracle.classify_confident` looks for.
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

_LEAF_REPAIR_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "ttl cache CLI",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "ttl semantics"
}"""

# A BROKEN free-form build: syntactically fine, never crashes, but silently IGNORES the ttl
# entirely -- a key set with any ttl (including 0) never expires. Fails only the ADT
# differential-oracle check (a genuine semantic bug), never a crash/usage check.
_BROKEN_TTL_CLI = '''\
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


class _LeafRepairLlm:
    """Canned `llm` (`.complete(LlmRequest) -> .text`) for the leaf-repair scenarios: always
    plans the same single-module ttl CLI, proposes an EMPTY acceptance checklist (so the composed
    checklist is exactly the deterministic minimum -- no extra model-proposed noise), and builds
    whichever module body `module_code` says."""

    def __init__(self, module_code: str) -> None:
        self.module_code = module_code

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(_LEAF_REPAIR_PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        if "COMPLETE Python module" in prompt:
            return _Resp(self.module_code)
        return _Resp("")


def _kv_store_ttl_task():
    return next(t for t in list(FIRST_SLICE) + list(HARDER_SLICE) if t.name == "kv-store-ttl-cli")


# --- (a) leaf_for_spec correctness --------------------------------------------------------------

def test_leaf_for_spec_returns_ttl_store_for_kv_store_ttl_contract_text():
    task = _kv_store_ttl_task()
    assert graph_dsl.leaf_for_spec(task.sentence) == "ttl-store"
    assert graph_dsl.leaf_for_spec(LEAF_REPAIR_SPEC) == "ttl-store"


def test_leaf_for_spec_returns_none_for_sum_cli_and_todo_specs():
    sum_spec = ("Write a single-file Python CLI in main.py: `python main.py <a> <b>` prints the "
                "sum of the two integer arguments.")
    todo_spec = "Write a simple command-line notes app that lets a user 'add' and 'list' text notes."
    assert graph_dsl.leaf_for_spec(sum_spec) is None
    assert graph_dsl.leaf_for_spec(todo_spec) is None


def test_leaf_for_spec_returns_none_for_unregistered_adt_class():
    # `classify_confident` fingerprints this as `lru`, a class `adt_oracle` supports -- but
    # `LEAF_LIBRARY` has no VERIFIED template for it (only `ttl-store`/`kv-store` are seeded, per
    # TASK-5's earned-membership rule), so `leaf_for_spec` honestly returns `None`, not `lru`.
    lru_spec = ("Build a fixed-capacity LRU (least-recently-used) cache CLI in main.py: `python "
                "main.py <capacity>` then reads commands from stdin -- 'get <key>' returns the "
                "value or 'none', 'put <key> <value>' inserts or updates the value and evicts "
                "the least-recently-used entry once the cache exceeds capacity.")
    assert graph_dsl.leaf_for_spec(lru_spec) is None


def test_leaf_for_spec_never_raises_on_malformed_input():
    assert graph_dsl.leaf_for_spec(None) is None
    assert graph_dsl.leaf_for_spec("") is None


# --- (b) a BROKEN ttl free-form build is rescued by a genuinely-earned leaf candidate -----------

def test_leaf_repair_adopts_a_genuinely_passing_leaf_candidate():
    """The REAL, unmodified ``graph_dsl.LEAF_LIBRARY["ttl-store"]`` (TASK-5's ``TTL_STORE_LEAF``,
    a real-seconds ``time.time()``-based implementation) now genuinely EARNS admission against
    ``LEAF_REPAIR_SPEC``'s real-seconds convention (EXT-056/TASK-10's ``_ttl_convention`` fix) --
    no monkeypatch/stand-in needed. Proves the leaf-repair branch adopts a genuinely-passing
    candidate AND ships EXACTLY the leaf (EXT-058/TASK-7): ``root`` on disk holds only
    ``main.py``, the returned ``plan``'s entrypoint is ``main.py``, and the independent
    ``kv-store-ttl-cli`` task oracle passes against the SHIPPED ``root`` -- no false-done."""
    expected_leaf_code = graph_dsl.LEAF_LIBRARY["ttl-store"]
    llm = _LeafRepairLlm(_BROKEN_TTL_CLI)
    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "leaf:ttl-store"
        # the adopted module is the leaf candidate, not the broken free-form one
        assert result["modules"] == {"main.py": expected_leaf_code}

        # (TASK-7) root SHIPS EXACTLY the leaf -- no stale free-form file lingers -- and the
        # returned plan's entrypoint points at it.
        assert sorted(p.name for p in root.glob("*.py")) == ["main.py"]
        assert (root / "main.py").read_text(encoding="utf-8") == expected_leaf_code
        assert result["plan"]["entrypoint"] == "main.py"

        # passes the REAL, independent kv-store-ttl-cli task oracle too (no reimplemented
        # grading logic -- reuses system_suite's own black-box checks), against the SHIPPED root.
        task = _kv_store_ttl_task()
        results = [_run_single_check(c, root, result.get("plan"), PY) for c in task.checks]
        assert all(results), results


# --- (d) honesty mirror: it can NEVER flip a broken build to done for a genuinely FAILING leaf --

def test_leaf_repair_never_falsely_adopts_a_genuinely_failing_leaf_candidate(monkeypatch):
    """Mirror honesty check (REQ-3): even when a spec fingerprints a verified leaf class, a
    CANDIDATE that does not actually pass the real acceptance floor is NEVER adopted. Stands in,
    via ``monkeypatch``, for "a leaf whose template never earned / regressed" -- substituting the
    SAME broken body as the free-form build's own bug (ttl silently ignored) into
    ``graph_dsl.LEAF_LIBRARY`` (``harness/graph_dsl.py`` itself is never modified by this file),
    so the candidate genuinely fails the real-seconds ttl-store oracle in its own throwaway
    ``cand_root`` and is correctly declined -- ``build_path`` stays ``"free-form"``, never a
    fabricated ``done=True``."""
    monkeypatch.setitem(graph_dsl.LEAF_LIBRARY, "ttl-store", _BROKEN_TTL_CLI)
    monkeypatch.setitem(graph_dsl.LEAF_LIBRARY, "kv-store", _BROKEN_TTL_CLI)

    llm = _LeafRepairLlm(_BROKEN_TTL_CLI)
    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_honest_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=llm)

        assert result["done"] is False
        assert result.get("build_path") == "free-form"
        assert result["unmet"]


# --- (c) an already-passing free-form build never enters the leaf branch -----------------------

def test_leaf_repair_branch_unreachable_for_an_already_passing_free_form_build():
    # The free-form build must pass the FULL `_minimum_acceptance` floor (including the ADT
    # differential-oracle's real-seconds ttl-store probe, EXT-056/TASK-10) on the FIRST attempt
    # so `unmet` is already empty and the leaf-repair `if unmet:` guard never even calls
    # `leaf_for_spec`. Reuses the REAL, correct `graph_dsl.LEAF_LIBRARY["ttl-store"]` template as
    # the free-form MODEL OUTPUT here (a real-seconds-correct implementation, matching
    # LEAF_REPAIR_SPEC's own convention) -- it is a free-form MODEL OUTPUT in this test, never
    # touching `graph_dsl.LEAF_LIBRARY` itself, no monkeypatch needed for this case.
    free_form_code = graph_dsl.LEAF_LIBRARY["ttl-store"]
    llm = _LeafRepairLlm(free_form_code)
    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_passing_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "free-form"
        # trailing-newline-insensitive: `_build_module`'s fence-stripping doesn't guarantee an
        # exact trailing newline is preserved, unrelated to this test's actual concern.
        assert result["modules"]["main.py"].strip() == free_form_code.strip()


def test_leaf_repair_branch_unreachable_for_a_non_leaf_spec():
    # a spec with no matching leaf (`leaf_for_spec` -> None) leaves `build_path` at its default
    # "free-form" -- proven with a plain notes CLI that ships correctly first try.
    plan = '''{
  "modules": [
    {"name": "main.py", "responsibility": "notes CLI",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "add/list notes"
}'''
    notes_cli = '''\
import sys

NOTES = []

if __name__ == "__main__":
    for line in sys.stdin:
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        if parts[0] == "add" and len(parts) == 2:
            NOTES.append(parts[1])
            print("ok")
        elif parts[0] == "list":
            for n in NOTES:
                print(n)
'''

    class _NotesLlm:
        def complete(self, request):
            prompt = request.prompt
            if "build PLAN" in prompt:
                return _Resp(plan)
            if "ACCEPTANCE CHECKS" in prompt:
                return _Resp("[]")
            if "COMPLETE Python module" in prompt:
                return _Resp(notes_cli)
            return _Resp("")

    spec = "Write a simple command-line notes app in main.py that lets a user 'add' and 'list' text notes."
    assert graph_dsl.leaf_for_spec(spec) is None

    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_nonleaf_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(spec, root, llm=_NotesLlm())
        assert result.get("build_path") == "free-form"
# #EXT-058-REQ-3 End
