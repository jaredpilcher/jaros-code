# EXT-041 — Design

## Problem

PRIME-001 now measures parity against **the whole Claude Code CLI product**, not just how well
the model solves tasks. `docs/GAP-MAP.md`'s "## Product-surface parity" section already lists the
16 feature rows (#12-27), each with a `state` (`unmeasured`/`probed`/`lever-named`/...), a
one-line honest current jcode state, and a next lever — but that table lives only as prose in a
markdown doc: there is no queryable score, no ranked attack list, and no way to see it at the REPL.
This spec turns those rows into a small, structured, deterministic instrument.

## Mechanism

```
docs/GAP-MAP.md                     harness/product_parity.py
"## Product-surface parity"   ──►   PARITY_ROWS: list[ProductParityRow]
rows #12-27 (id, feature,           (id, feature, state, current_state, next_lever)
 current honest state,                       │
 next lever)                                 │
   ▲ re-sync monthly                         ▼
   │ (LAST_SYNCED marker)              score(rows) -> ParityScore
   │                                     { pct, n_works, n_partial, n_missing,
   │                                       ranked_attack_list }
   │                                          │
   │                                          ▼
   │                                    render(rows) -> str
   │                                     (readable table, works first for
   │                                      context, then the ranked attack list)
   │                                          │
   │                                          ▼
   └──────────────────────────────  harness/cli.py :: cmd_parity()
                                       "/parity"  (mirrors cmd_status wiring
                                       + /help listing, EXT-040 pattern)
```

- **`ProductParityRow`** — a small dataclass: `id: int`, `feature: str`,
  `state: Literal["works", "partial", "missing"]`, `current_state: str` (one honest sentence,
  transcribed from GAP-MAP), `next_lever: str`. Kept as a plain module-level list
  (`PARITY_ROWS`) so a future monthly re-sync is a simple, reviewable diff — no hidden config
  format, no external file to keep in lock-step.
- **`score(rows=PARITY_ROWS)`** — deterministic aggregate: `works=1.0`, `partial=0.5`,
  `missing=0.0` per row, averaged into a percentage; counts each state; builds a **ranked attack
  list** of the non-`works` rows ordered by the stated impact (rows already appear in GAP-MAP's own
  rough impact order — sessions/headless/memory first — so the ranking is "keep GAP-MAP's stated
  order," a simple, honest, and stated ordering rather than an invented score). Never raises: an
  empty or malformed row list degrades to `pct=0.0` and empty lists, not an exception.
- **`render(rows=PARITY_ROWS)`** — a fixed-width text table (id, feature, state, one-line current
  state) plus a footer summarizing `score()`'s aggregate and the top of the ranked attack list.
  Pure string formatting; never raises.
- **`LAST_SYNCED`** — a `"YYYY-MM-DD"` constant plus a module docstring noting the checklist must
  be re-audited against the official Claude Code docs (code.claude.com/docs) monthly, since Claude
  Code is a moving target — new features become new rows, changed features update `state`.
- **`/parity`** — a `cmd_parity` method on the CLI class, registered exactly like `cmd_status`
  (EXT-040's `/status` wiring is the precedent): dynamic dispatch already routes `/parity` to
  `cmd_parity` via `getattr(self, "cmd_" + head[1:])` (no separate registration table exists in
  `harness/cli.py` — see EXT-040's REQ-1 pattern), so wiring is: (1) add the method, (2) add one
  line to the module docstring's command list so `/help` lists it.

## Two-plane / honesty

Purely deterministic execution-plane code (Tenet 1) — `PARITY_ROWS`, `score()`, and `render()`
never call a model; they encode facts the supervisor already measured and recorded in GAP-MAP.
Per Tenet 3, the row `state`/`current_state` values MUST match GAP-MAP's honest assessment at
authoring time (today: mostly `missing`/`partial`, a few `lever-named`/`probed` mapped down to
`partial`) — inflating a row to `works` without a matching GAP-MAP entry is a Tenet-3 violation.
`score()`/`render()` never raise, mirroring EXT-040's observability discipline: an instrument that
can crash the REPL it's reporting on is worse than no instrument.

## Out of scope (this task)

Building the actual product-surface features (sessions/resume, MCP client, hooks, etc.) is NOT
part of this spec — this spec is the *scoreboard*, not the *work*. Automating the monthly
docs re-sync (e.g. a scheduled agent that diffs the official docs) is also out of scope; `LAST_SYNCED`
is a manual marker for now.
