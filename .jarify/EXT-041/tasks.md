# Implementation Tasks

### [TASK-1] Build the Product-Parity Checklist instrument

Build the deterministic Product-Parity Checklist instrument that turns `docs/GAP-MAP.md`'s
"## Product-surface parity" table (rows #12-27) into a scoreable, testable, `/parity`-renderable
structure.

#### Steps
1. Create `harness/product_parity.py`: a `ProductParityRow` dataclass (`id: int`, `feature: str`,
   `state: str` in `{"works","partial","missing"}`, `current_state: str`, `next_lever: str`) and a
   module-level `PARITY_ROWS: list[ProductParityRow]` transcribed honestly from GAP-MAP rows
   #12-27 (sessions, headless/piping, memory hierarchy, custom commands/skills, hooks,
   permissions, MCP client, subagents, checkpoint/rewind, interrupt-and-steer, context management,
   background runs, terminal UX, install/health, multimodal, deferred surfaces). Add a `score(rows=PARITY_ROWS)`
   function returning an aggregate percentage (works=1.0, partial=0.5, missing=0.0) plus
   `n_works`/`n_partial`/`n_missing` counts and a ranked attack list (the missing/partial rows in
   GAP-MAP's stated order). Add a `render(rows=PARITY_ROWS)` function producing a readable table +
   summary string. Add a `LAST_SYNCED = "2026-07-04"` constant and a module docstring documenting
   the monthly re-sync duty against the official Claude Code docs. Every public function must
   swallow its own errors and never raise.
2. Add a `cmd_parity` method to the CLI class in `harness/cli.py` that imports and calls
   `harness.product_parity.render()`, mirroring the existing `cmd_status` registration pattern
   (dynamic `cmd_<name>` dispatch — no separate registration table needed); add a `/parity` line
   to the module docstring's command list so `/help` lists it.
3. Write `tests/test_ext041_product_parity.py` covering: all 16 rows (#12-27) present with valid
   ids; `score()` computes the correct aggregate for a known works/partial/missing mix; every row's
   `state` is one of the three valid enum values; `render()` returns a non-empty string containing
   every feature name; the ranked attack list surfaces the missing/partial rows (not the `works`
   ones); `score()`/`render()` never raise on an empty or malformed row list. All tests
   deterministic — no model/gemma calls.

#### Implements
- [REQ-1] Product-Parity Checklist instrument
