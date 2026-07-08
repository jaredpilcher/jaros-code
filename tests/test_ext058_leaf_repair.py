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
      no reimplemented grading logic).
  (d) the mirror honesty check: it can NEVER flip a broken build to done for a leaf that hasn't
      actually earned the win -- see the "MEASURED GAP" note below.
  (c) a stubbed ``llm`` whose free-form build ALREADY passes never enters the leaf branch at all
      (``build_path == "free-form"``, byte-identical to before this task).

**MEASURED GAP (honestly disclosed, out of TASK-6's scope to fix):** the REAL, currently-shipped
``graph_dsl.TTL_STORE_LEAF`` (TASK-5) is authored against ``kv-store-ttl-cli``'s REAL-time-seconds
TTL contract and does not implement the ``tick`` command ``adt_oracle``'s ttl-store differential
oracle (wired into ``_minimum_acceptance`` since EXT-056/TASK-2) unconditionally drives (a
DIFFERENT, virtual-clock ttl-store convention). So today, the SHIPPED leaf cannot yet win this
competition -- test (d) below proves this is handled HONESTLY (the branch tries the leaf and
correctly does NOT adopt it, `build_path` stays `"free-form"`, never a false-done). Test (b)
proves TASK-6's OWN wiring (leaf_for_spec -> dsl_to_system -> re-run _minimum_acceptance -> adopt
only on a real pass) is correct by substituting, via ``monkeypatch``, a small FIXTURE template
into ``graph_dsl.LEAF_LIBRARY["ttl-store"]`` that implements BOTH conventions (the REAL
``dsl_to_system``/``leaf_for_spec``/``_minimum_acceptance``/``build_system`` code all still run
unmodified -- only the leaf-library's DATA is substituted, standing in for "a leaf that has
actually earned full membership by passing the real floor", per REQ-1's earned-membership rule).
``harness/graph_dsl.py`` itself is never modified by this file. This gap is reported to the
task's supervisor for a possible TASK-5 follow-up; it is not this task's to fix.

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

# A FIXTURE leaf template (test-local only -- `harness/graph_dsl.py` is never modified) that
# implements BOTH conventions at once: `set`/`get`/`delete` (satisfying `kv-store-ttl-cli`'s own
# black-box oracle) via a VIRTUAL clock that only advances on an explicit `tick` command
# (satisfying `adt_oracle`'s ttl-store differential-oracle convention too -- it is functionally
# identical to `adt_oracle._TtlStoreReferenceModel`, so it agrees with it by construction). Stands
# in, via `monkeypatch`, for "a leaf that has earned full membership" (REQ-1) -- proving TASK-6's
# OWN wiring (real `leaf_for_spec`/`dsl_to_system`/`_minimum_acceptance`/`build_system`) adopts a
# genuinely-passing leaf candidate correctly, independent of the separate, currently-unearned
# `TTL_STORE_LEAF` (see the module docstring's "MEASURED GAP").
_FULLY_COMPLIANT_TTL_FIXTURE = '''\
import sys


def main():
    store = {}
    now = 0
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0]
        if cmd == "set" and len(parts) == 4:
            key, value, ttl = parts[1], parts[2], int(parts[3])
            store[key] = (value, now + max(0, ttl))
            print("ok")
        elif cmd == "get" and len(parts) == 2:
            entry = store.get(parts[1])
            if entry is not None and now < entry[1]:
                print(entry[0])
            else:
                print("none")
        elif cmd == "delete" and len(parts) == 2:
            store.pop(parts[1], None)
            print("ok")
        elif cmd == "tick":
            now += 1
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

def test_leaf_repair_adopts_a_genuinely_passing_leaf_candidate(monkeypatch):
    monkeypatch.setitem(graph_dsl.LEAF_LIBRARY, "ttl-store", _FULLY_COMPLIANT_TTL_FIXTURE)
    monkeypatch.setitem(graph_dsl.LEAF_LIBRARY, "kv-store", _FULLY_COMPLIANT_TTL_FIXTURE)

    llm = _LeafRepairLlm(_BROKEN_TTL_CLI)
    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "leaf:ttl-store"
        # the adopted module is the leaf candidate, not the broken free-form one
        assert result["modules"]["main.py"] == _FULLY_COMPLIANT_TTL_FIXTURE
        assert (root / "main.py").read_text(encoding="utf-8") == _FULLY_COMPLIANT_TTL_FIXTURE

        # passes the REAL, independent kv-store-ttl-cli task oracle too (no reimplemented
        # grading logic -- reuses system_suite's own black-box checks).
        task = _kv_store_ttl_task()
        results = [_run_single_check(c, root, result.get("plan"), PY) for c in task.checks]
        assert all(results), results


# --- (d) honesty mirror: it can NEVER flip a broken build to done for an UNEARNED leaf ----------

def test_leaf_repair_never_falsely_adopts_the_currently_unearned_real_ttl_store_leaf():
    """The REAL, unmodified `graph_dsl.TTL_STORE_LEAF` (TASK-5) does not yet implement the `tick`
    command `adt_oracle`'s differential-oracle convention drives (see module docstring's MEASURED
    GAP) -- so it does not yet pass the full `_minimum_acceptance` floor. This proves the
    leaf-repair branch stays HONEST about that: it tries the real leaf and correctly declines to
    adopt it, never fabricating `done=True`."""
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
    # differential-oracle check) on the FIRST attempt so `unmet` is already empty and the
    # leaf-repair `if unmet:` guard never even calls `leaf_for_spec`. A plain real-seconds ttl
    # implementation would trip the SAME measured tick-support gap the module docstring names,
    # so `_FULLY_COMPLIANT_TTL_FIXTURE`'s dual-convention body is used here instead (it is a
    # free-form MODEL OUTPUT in this test, never touching `graph_dsl.LEAF_LIBRARY` -- no
    # monkeypatch needed for this case).
    llm = _LeafRepairLlm(_FULLY_COMPLIANT_TTL_FIXTURE)
    with tempfile.TemporaryDirectory(prefix="ext058_leafrepair_passing_") as tmp:
        root = Path(tmp) / "built"
        result = build_system(LEAF_REPAIR_SPEC, root, llm=llm)

        assert result["done"] is True
        assert result["unmet"] == []
        assert result.get("build_path") == "free-form"
        # trailing-newline-insensitive: `_build_module`'s fence-stripping doesn't guarantee an
        # exact trailing newline is preserved, unrelated to this test's actual concern.
        assert result["modules"]["main.py"].strip() == _FULLY_COMPLIANT_TTL_FIXTURE.strip()


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
