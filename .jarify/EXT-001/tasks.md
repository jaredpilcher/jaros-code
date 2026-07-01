# Implementation Tasks — EXT-001 Deterministic Execution-Plane Tool Primitives

### [TASK-1] code.search_replace — resilient SEARCH/REPLACE tool (delegating to the proven matcher)

Add the resilient block-edit execution-plane tool for REQ-13 — the Jaros-native counterpart to the
proven SWE-bench editor — WITHOUT re-implementing the match logic (single source of truth, Tenet 3).
Offline-testable; no network / Jetson / Docker (inject file content on disk in a tmp path).

#### Steps
1. Add `.jaros-data/tools/search_replace_tool.py` with a `SearchReplaceTool` class:
   `NAME = "code.search_replace"`, a `validate(decision) -> ValidationResult`, and an
   `execute(decision, **collaborators) -> dict`. Mirror `apply_patch_tool.py`'s structure and imports
   (`from jaros.core.decision_gate import ValidationResult`, the `_codesafety.unsafe_reason` gate).
2. `validate`: reject a payload without a non-empty `path` string or without both `search` and
   `replace` strings; run `unsafe_reason(payload["replace"])` and reject unsafe generated code with the
   same message shape as `code.apply_patch`.
3. `execute`: read the file (UTF-8), then call `harness.swebench_live.apply_search_replace(content,
   search, replace)` — do NOT re-implement the matching. If it returns `None` (no tier matched), raise
   a clear `RuntimeError("code.search_replace: no search/replace tier matched")` (never a silent no-op).
   On success, write the result back (`newline="\n"`) and return
   `{"tool": NAME, "path": path, "applied": True, "created": False, "bytesBefore": ..., "bytesAfter": ...}`.
   Add the repo root to `sys.path` (mirror `locate_agent.py`) so `harness.swebench_live` imports cleanly.
4. Add `tests/test_ext001_search_replace.py` (offline): (a) an exact-match edit applies and returns
   `applied=True` with correct byte counts; (b) a block with trailing-whitespace drift still applies
   (rstrip-tolerant tier); (c) a block whose surrounding lines are hallucinated but the changed line is
   verbatim still applies (difflib line-level tier); (d) a payload missing `search`/`replace` is rejected
   by `validate`; (e) an unmatchable edit raises (no silent no-op). Use a real tmp file on disk. Run the
   full suite green.

#### Implements
- [REQ-13] code.search_replace — apply a RESILIENT SEARCH/REPLACE edit

### [TASK-2] code.search_replace — end-to-end two-plane coverage through the Runtime

Strengthen REQ-13 coverage: exercise `code.search_replace` through the REAL Jaros Runtime two-plane
path (agent-emitted inert Decision → `Runtime.apply` → deterministic tool effect + DecisionLog entry +
replay), not only as an isolated unit. This proves the wiring that unit tests cannot — the tool's
registration via `load_custom_tools`, the `NAME`/payload contract match between an emitting agent and
the tool, gate rejection, and Tenet-3 logging/replay. Fully offline (no model / Jetson / Docker):
mirror the existing `tests/test_ext013_jaros_ops.py` pattern (`Runtime(data_dir=tmp_path)`,
`create_decision`, `rt.apply`).

#### Steps
1. Add `tests/test_ext001_search_replace_e2e.py`. Mirror `tests/test_ext013_jaros_ops.py`: build
   `Runtime(data_dir=tmp_path)` (from `harness.coding_loop`), ensure the tools dir is loaded
   (`load_custom_tools` / the same fixture the ops test uses so `code.search_replace` is registered).
2. Test (a): write a fixture file into `tmp_path`, `create_decision(type="code.search_replace",
   payload={path, search, replace})` for an exact-match edit, `rt.apply(decision)`, assert the file on
   disk now contains `replace` and not `search`, and that a `code.search_replace` entry is in the
   DecisionLog. Test (b): the same through the Runtime but with a rstrip-drift `search` (resilient tier
   still applies end-to-end). Test (c): the gate/tool path surfaces a clear error for an unmatchable
   edit (assert `rt.apply` raises, mirroring the ops test's rejection assertions). Test (d): a payload
   missing `search`/`replace` is rejected by the gate before any file write.
3. Do NOT modify the tool or any agent — this task is TEST-ONLY (pure coverage). Run the full suite green.

#### Implements
- [REQ-13] code.search_replace — apply a RESILIENT SEARCH/REPLACE edit (end-to-end Runtime coverage)
