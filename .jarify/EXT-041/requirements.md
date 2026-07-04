---
id: EXT-041
title: Product-Parity Checklist
status: covered
priority: high
implementation:
  - harness/product_parity.py
  - harness/cli.py
---

# EXT-041 — Product-Parity Checklist

**Owner/supervisor directive (2026-07-04):** parity with Claude Code is the WHOLE CLI PRODUCT, not
just how well the model solves tasks (PRIME-001 intent). `docs/GAP-MAP.md`'s "## Product-surface
parity" section (rows #12-27) lists the CC feature surface, jcode's current honest state, and the
next lever per row. This spec turns that table into a scoreable instrument.

### [REQ-1] Product-Parity Checklist instrument

Build `harness/product_parity.py`: a structured, maintainable list of the 16 product-surface rows
(#12-27) transcribed HONESTLY from `docs/GAP-MAP.md` — each row carries an id, feature name, a
`state` in `{"works", "partial", "missing"}`, a one-line honest current jcode state, and a next
lever. A `score()` function aggregates parity (works=1.0, partial=0.5, missing=0.0) into a
percentage plus `n_works`/`n_partial`/`n_missing` counts and a ranked attack list of the
missing/partial rows. A `render()` function produces a readable table/summary for a `/parity` CLI
command. A `LAST_SYNCED` date constant plus a docstring note that the checklist must be re-synced
from the official Claude Code docs monthly (Claude Code is a moving target). Wired into
`harness/cli.py` as a `/parity` command (mirroring how `/status` is registered + listed in
`/help`). Deterministic — no model calls — and never raises.

#### Acceptance Criteria
- [x] `harness/product_parity.py` defines `PARITY_ROWS` covering GAP-MAP rows #12-27 (16 rows), each with `id`, `feature`, `state`, `current_state`, `next_lever`.
- [x] Row `state`/`current_state` values are transcribed HONESTLY from GAP-MAP — most rows are `missing` or `partial` today; no row is inflated to `works` without a matching GAP-MAP entry. (Live baseline: 0 works / 10 partial / 6 missing.)
- [x] `score(rows=PARITY_ROWS)` returns the correct aggregate percentage + counts for a known state mix (works=1.0, partial=0.5, missing=0.0 weighting) and a ranked attack list of non-`works` rows.
- [x] `render(rows=PARITY_ROWS)` returns a non-empty human-readable string listing every feature row plus the aggregate score.
- [x] `LAST_SYNCED` constant + docstring documents the monthly re-sync duty against the official Claude Code docs.
- [x] `score()` and `render()` never raise, including on an empty or malformed row list.
- [x] `/parity` is wired into `harness/cli.py` (a `cmd_parity` method, dispatched like every other `cmd_*` handler) and listed in `/help`.
- [x] `tests/test_ext041_product_parity.py` covers: expected rows present, `score()` aggregate correctness, valid state enum values, non-empty `render()`, the ranked attack list, and never-raises on edge cases — deterministic, no model calls.

**Live honest baseline (2026-07-04):** aggregate parity = **31.2%** (0 works / 10 partial / 6
missing of 16 rows) — the honest starting point for this axis, to converge from, not a claim of
progress.
