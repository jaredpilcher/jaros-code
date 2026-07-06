# Daily-driver suite — THE parity instrument (PURSUIT §2.1 / EXT-005 REQ-13)

The headline scoreboard number: **how much of what Claude Code does for a working
engineer can jaros-code do, end-to-end, on the Jetson.** Frequency-weighted by real
usage; deterministic oracles only; dev/holdout split (holdout read ≤1×/week).

> Status: **live** (2026-07-06). The runner (`harness/daily_driver.py`) is built and routes
> all 8 categories; the suite is 29 tasks (19 original + a 10-task hard tier, §"Task count +
> difficulty tiers" below) with a frozen `holdout/` split. This is the real, current headline
> instrument — see `.jaros-data/artifacts/dd_fullrun.json` for the last full-split read.

## Category taxonomy + weights (PURSUIT §2.1 — target ~100 tasks)

| category | weight | oracle type | oracle mechanism |
|----------|-------:|-------------|------------------|
| `navigate` (navigate/explain) | 20 | **answer** | CLI answers a question; check answer vs `expect` (set/exact/regex) |
| `edit` (bounded single-file) | 20 | **pytest** | provided failing test goes green after the edit |
| `fix` (fix-failing-test) | 15 | **pytest** | failing test → green (bug in provided code) |
| `write-tests` | 10 | **pytest×2** | authored tests PASS vs correct impl AND FAIL vs a provided mutant |
| `refactor` | 10 | **pytest** | pre-existing tests stay green (behavior preserved) + structural check |
| `build-module` | 10 | **held-out pytest** | from-intent build; HELD-OUT oracle tests pass (never shown; EXT-005 REQ-10) |
| `multi-file` | 10 | **pytest** | tests spanning ≥2 files go green |
| `ops` (git/shell) | 5 | **state-check** | a shell/git op produces a checkable repo state (deterministic assertion) |

Weighted pass rate = Σ(weightᵢ · passRateᵢ) / Σweightᵢ. Reported per-category AND weighted;
Wilson-CI per category; the weighted number is the headline.

## Task schema (extends the proven `evals/coding_tasks` format — reuse, don't diverge)

```jsonc
{
  "id": "nav_callers_of_parse",
  "category": "navigate",           // NEW: one of the categories above
  "split": "dev",                    // NEW: "dev" | "holdout"
  "instruction": "...",              // what the operator asks the CLI
  "files": { "path": "content" },    // setup: written into a fresh temp dir
  // ORACLE — exactly one of:
  "test_cmd": "python -m pytest -q", // pytest oracle (edit/fix/refactor/multi-file/write-tests/build)
  "oracle": {                        // answer/state oracle (navigate/ops)
    "type": "answer",                // "answer" | "state"
    "match": "set",                  // "set" | "exact" | "regex"
    "expect": ["load_config", "reload"]
  }
}
```

Design rules (honesty, Tenet 3):
- **Deterministic oracles only.** No LLM-graded answers. navigate questions must have an
  exact checkable answer (a set of names, a line number, a path) — never "explain X" free-form.
- **Held-out oracle for build-module** is never written into the build dir or shown to any
  agent (EXT-005 REQ-10 generative-metric discipline).
- **write-tests double gate**: the authored tests must pass on the correct impl AND fail on
  the provided mutant — proving the tests actually catch the bug, not vacuous.
- **dev/holdout split** per task; the holdout half is read ≤1×/week and never tuned against.

## Runner (to build — extends `harness/eval_runner.run_task_list`)

Route by `category`: pytest-oracle categories reuse `fix_loop`/`build_from_intent`; `answer`
oracle asks the CLI and checks the extracted answer; `state` oracle runs the op and asserts
repo state. Emits per-category + weighted pass rate into the scoreboard. Jaros-native, gated.

## Seed tasks (this dir) — validate the two novel oracle types before building the runner
- `dev/nav_callers_of.json` — `navigate` / answer-oracle (the new type; the crux).
- `dev/edit_clamp.json` — `edit` / pytest-oracle (reuses proven infra; sanity anchor).

## Task count + difficulty tiers (grown 2026-07-06, docs/GAP-MAP.md #51)

MEASURED 2026-07-06 (`.jaros-data/artifacts/dd_fullrun.json`): the original 19-task dev-only
split scored 19/19 = 100% weighted with gemma — SATURATED, no longer discriminating (every task
passed, so it can't show a real capability gap vs Claude Code). The suite was grown with a
**hard tier** of 10 realistic-difficulty tasks in the highest-weight categories, honestly
authored (whether gemma passes is measured, not engineered):

| category | seed tasks | + hard tier | total |
|----------|-----------:|------------:|------:|
| `navigate` | 1 | — | 1 |
| `edit` | 2 | — | 2 |
| `fix` | 6 | 3 | 9 |
| `write-tests` | 2 | — | 2 |
| `refactor` | 2 | 2 | 4 |
| `build-module` | 2 | 2 | 4 |
| `multi-file` | 2 | 3 | 5 |
| `ops` | 2 | — | 2 |
| **total** | **19** | **10** | **29** |

Hard-tier tasks are prefixed `fix_hard_*` / `mfx_hard_*` / `refactor_hard_*` / `build_hard_*` and
require multi-line/multi-hop reasoning rather than a single-line bug: a root cause reached only
by tracing a 3-function call chain (`fix`), a shared root cause in a low-level file used by two
independent callers or a 3-hop import chain (`multi-file`), a rename that must reach a recursive
self-call or avoid a confusable distractor name while preserving behavior (`refactor`), and a
multi-edge-case stateful class — a sliding-window rate limiter, an LRU cache (`build-module`).

**`holdout/` is FROZEN** (2026-07-06): 4 of the 10 hard tasks (one per category above) live under
`evals/daily_driver/holdout/` and are never tuned against — read at most ~1×/week per the design
rule below, so `load_daily_tasks()` (which loads `dev/` + `holdout/` by default) reports an honest
held-out number alongside the dev number in the `bySplit` field of the scorecard.
