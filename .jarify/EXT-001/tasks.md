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
