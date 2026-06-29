---
id: EXT-029
title: Cross-Model Collaborative Solve
status: covered
priority: high
implementation:
  - file: harness/collaborative_solve.py
    ranges:
      - - 60
        - 173
      - - 247
        - 744
  - file: tests/test_collaborative_solve.py
    ranges:
      - - 1
        - 452
---

Cross-model collaborative solve — the cheapest form of multi-model collaboration:
DRAFT -> CRITIQUE -> REVISE across two complementary models, with the DETERMINISTIC
TEST as the final judge. Models collaborate to GENERATE; the test SELECTS — never
model-as-judge for selection (same gate principle as EXT-021 REQ-6).

Targets the hard multi-step-repo class where both gemma 4 2B and qwen2.5-coder-3B
independently fail (0/8 baseline). Hypothesis: qwen (stronger code structure) +
gemma (stronger intent reasoning) together may crack tasks neither can alone.

Connection to issue #33 (open team-discussion = the richer form): this spec is the
base case — one-shot draft->critique->revise. Issue #33 explores multi-round
structured debate; collaborative_solve is the prerequisite proof-of-concept.

### [REQ-1] Draft -> critique -> revise loop (test-gated)

`harness/collaborative_solve.py` exposes `collaborative_solve(problem, *, draft_fn,
critique_fn, revise_fn, test_fn, max_rounds=2) -> dict` — the core loop, all
callables INJECTABLE for offline testability.

Loop semantics:
- `draft_fn(problem) -> str`: generate first candidate code.
- `test_fn(problem, candidate_code) -> {"passed": bool, ...}`: deterministic gate.
  If passed -> return `{solved:True, code, rounds:0, winner:"draft"}`.
- else loop up to `max_rounds`:
  - `critique_fn(problem, candidate_code, test_result) -> str`: short critique /
    alternative-approach text. NEVER selects or ranks — generates only.
  - `revise_fn(problem, candidate_code, critique) -> str`: revised code.
  - `test_fn(problem, revised) -> {"passed": bool}`: if passed return
    `{solved:True, code, rounds:r, winner:"collab"}`.
- Return `{solved:False, code:last, rounds, winner:None, attempts:[...]}` if none pass.
- `attempts` records `{round, draft, critique, revised}` per round for inspection.

HONEST: `test_fn` is the SOLE arbiter of `solved`. critique_fn / revise_fn only
generate; they never decide. Model-as-judge is forbidden.

#### Acceptance Criteria
- [ ] `collaborative_solve` importable from `harness.collaborative_solve`
- [ ] Draft passes immediately: `solved=True`, `rounds=0`, `winner="draft"`,
      `critique_fn` and `revise_fn` NOT called, `attempts=[]`
- [ ] Draft fails, round-1 revise passes: `solved=True`, `rounds=1`, `winner="collab"`,
      `attempts` has 1 entry with `draft`, `critique`, `revised` keys
- [ ] All rounds fail: `solved=False`, `winner=None`, `len(attempts)==max_rounds`
- [ ] test_fn sole arbiter: model "claims" success but test_fn=False -> `solved=False`
- [ ] max_rounds bounds the loop: revise_fn called EXACTLY `max_rounds` times
- [ ] `code` field on all-fail is the LAST revised code (not the original draft)

### [REQ-2] Batched Jetson factory and active-hours probe protocol

`_make_jetson_fns(draft_model, critique_model, revise_model, manager_url, *,
swap_fn=None, llm_fn=None) -> tuple[Callable, Callable, Callable]` — factory that
returns `(draft_fn, critique_fn, revise_fn)` for production Jetson use.

BATCHING DESIGN: each returned function assumes the correct model is ALREADY LOADED.
The PROBE RUNNER (not the factory fns) controls model swaps in batches:
    1. swap_fn(draft_model)    # 1 swap total
    2. draft ALL n tasks
    3. swap_fn(critique_model) # 1 swap total
    4. critique ALL n tasks
    5. swap_fn(revise_model)   # 1 swap total
    6. revise ALL n tasks
Total swaps = 2 * max_rounds + 1 (vs 2 * max_rounds * n for naive per-task swapping).

`collab_probe(n=6)` — entry stub for the active-hours run: loads n hard bigbar [fail]
tasks, runs the BATCHED collaborative solve (qwen drafts, gemma critiques, qwen revises)
with the `_run_nodes` oracle as test_fn, restores gemma after; reports cracked X/n
vs the 0/8 baseline.

Invoke (active hours, Jetson running):
    python -m harness.collaborative_solve --n 6

#### Acceptance Criteria
- [ ] `_make_jetson_fns` importable and callable with injectable `swap_fn`/`llm_fn`
- [ ] Returns a 3-tuple of callables `(draft_fn, critique_fn, revise_fn)`
- [ ] `swap_fn` and `llm_fn` are injectable (offline tests pass no-ops)
- [ ] `collab_probe(n)` is documented as active-hours only; no live Jetson call
      from tests
- [ ] `run_collab_probe` prints honest summary with cracked X/n and the 0/8 baseline
- [ ] Batching design documented in module docstring (swap count analysis)
