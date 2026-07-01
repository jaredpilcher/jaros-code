# Implementation Tasks — EXT-002 Single-Purpose Coding Agent Fleet

### [TASK-1] editor — opt-in resilient code.search_replace emission

Give the `editor` agent an OPT-IN path to emit the resilient `code.search_replace` Decision (EXT-001
REQ-13) instead of `code.apply_patch`, so the resilient editor has a real emitter and can FIRE in the
Jaros-native solve. STRICTLY backward-compatible (mirror EXT-013 REQ-8): default path byte-for-byte
unchanged. Fully offline-testable (canned llm); the lift measurement on the Jetson is deferred to
active hours and is NOT part of this task.

#### Steps
1. In `.jaros-data/agents/editor_agent.py::EditorBoundary.decide`, after a successful `parse_edit`
   (giving `old`, `new`), branch on `ctx.get("resilient")`:
   - When truthy: emit `create_decision(type="code.search_replace", payload={"path": path,
     "search": old, "replace": new})`.
   - When absent/falsey: emit the EXISTING `code.apply_patch` Decision (`payload={path, old, new}`)
     byte-for-byte unchanged.
   Do NOT change the prompt, `parse_edit`, or the unparseable→`advance` honest-failure path (both modes
   keep it). Tag the new branch `# #EXT-002-REQ-8` for traceability.
2. Keep the change minimal and surgical — no new prompt, no model-behavior change; only the emitted
   Decision `type`/`payload` differ, selected by the explicit opt-in flag.
3. Add `tests/test_ext002_editor_resilient.py` (offline, canned llm stub that returns a valid
   `<<<OLD ... OLD>>>/<<<NEW ... NEW>>>` block): (a) with `ctx["resilient"]=True` the emitted Decision
   is `code.search_replace` with `{path, search, replace}`; (b) WITHOUT the flag the emitted Decision is
   `code.apply_patch` with `{path, old, new}` (backward-compat); (c) unparseable output emits `advance`
   in BOTH modes. Run the full suite green.

#### Implements
- [REQ-8] editor — OPT-IN resilient SEARCH/REPLACE emission
