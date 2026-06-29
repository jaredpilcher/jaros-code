# Implementation Tasks

### [TASK-1] Build harness/collaborative_solve.py

Implement the cross-model collaborative solve module with the core loop, Jetson
factory, and active-hours probe entry point.

#### Steps
1. Create `harness/collaborative_solve.py` with module docstring covering: concept
   (draft->critique->revise, test-gated), honest note (test_fn sole arbiter, no
   model-as-judge), batching design (swap count analysis), and active-hours usage.
2. Implement `collaborative_solve(problem, *, draft_fn, critique_fn, revise_fn,
   test_fn, max_rounds=2) -> dict`:
   - Call `draft_fn(problem)` -> candidate. Call `test_fn(problem, candidate)`.
   - If `passed` -> return `{solved:True, code, rounds:0, winner:"draft", attempts:[]}`.
   - Loop up to `max_rounds`: call `critique_fn(problem, candidate, test_result)`,
     then `revise_fn(problem, candidate, critique)`, then `test_fn(problem, revised)`.
   - Each round record `{round, draft, critique, revised}` appended to `attempts`.
   - If any round passes -> return `{solved:True, code, rounds:r, winner:"collab", attempts}`.
   - Exhausted -> return `{solved:False, code:last_revised, rounds, winner:None, attempts}`.
   - Wrap in `# #EXT-029-REQ-1 Start` / `# #EXT-029-REQ-1 End`.
3. Implement `_build_critique_prompt(subject, name, candidate_code, test_failure_info,
   context)` -> str: 3-5 sentence critique prompt for the reviewer model.
4. Implement `_build_revise_prompt(subject, name, candidate_code, critique, context)`
   -> str: revision prompt embedding the critique as context for the coder model.
5. Implement `_http_swap(manager_url) -> Callable[[str], None]`: returns a callable
   that POSTs to `{manager_url}/serve` with `{"model": model_id}` to swap models.
   Documents the batching note (swap once per PHASE, not per task).
6. Implement `_make_jetson_fns(draft_model, critique_model, revise_model, manager_url,
   *, swap_fn=None, llm_fn=None) -> tuple[Callable, Callable, Callable]`:
   - `draft_fn(problem)` calls qwen_code (qwen instruct-direct) with problem's
     `subject`, `name`, `context` fields.
   - `critique_fn(problem, code, test_result)` calls the LLM with a critique prompt.
   - `revise_fn(problem, code, critique)` calls qwen_code with critique embedded in
     context.
   - `swap_fn` / `llm_fn` are injectable (None -> live Jetson path).
   - Docstring documents batching design: caller swaps per PHASE, not per fn call.
   - Wrap `_make_jetson_fns` + `collab_probe` + `run_collab_probe` in
     `# #EXT-029-REQ-2 Start` / `# #EXT-029-REQ-2 End`.
7. Implement `collab_probe(n=6)` as thin entry stub delegating to `run_collab_probe`.
8. Implement `run_collab_probe(n)`: loads bigbar [fail] tasks, runs the batched
   3-phase probe (draft ALL / critique ALL / revise ALL), scores with `_run_nodes`
   oracle, restores gemma, prints honest summary with cracked X/n and Wilson95 CI.
9. Add `__main__` argparse block: `--n` arg, calls `run_collab_probe`.

#### Implements
- [REQ-1] Draft -> critique -> revise loop (test-gated)
- [REQ-2] Batched Jetson factory and active-hours probe protocol

### [TASK-2] Write tests/test_collaborative_solve.py

Write offline pytest tests verifying the collaborative solve module. No Jetson, no
LLM, no Docker. All callables injected as mocks.

#### Steps
1. Create `tests/test_collaborative_solve.py`.
2. Syntax smoke test: `ast.parse(collaborative_solve.py)` — must not raise.
3. Import smoke test: all public symbols (`collaborative_solve`, `_make_jetson_fns`,
   `_build_critique_prompt`, `_build_revise_prompt`, `_http_swap`, `collab_probe`,
   `run_collab_probe`) importable at module level.
4. `_make_fns` helper: returns `(draft_fn, critique_fn, revise_fn, test_fn,
   crit_calls, rev_calls)` with configurable `pass_codes`, `critiques`,
   `revise_codes` lists.
5. Test (a): `test_draft_passes_round0` — draft returns passing code; assert
   `solved=True`, `rounds=0`, `winner="draft"`, `attempts=[]`, `critique_fn` and
   `revise_fn` NOT called.
6. Test (b): `test_draft_fails_revise_passes_round1` — draft fails, round-1 revised
   passes; assert `solved=True`, `rounds=1`, `winner="collab"`, `len(attempts)==1`,
   attempt record has `draft`/`critique`/`revised` keys.
7. Test (c): `test_all_rounds_fail` — all `test_fn` calls return `passed=False`;
   assert `solved=False`, `winner=None`, `len(attempts)==max_rounds`.
8. Test (d): `test_test_fn_sole_arbiter` — critique says "I fixed it!" + revise
   emits a comment "# MODEL CLAIMS THIS IS CORRECT"; but `test_fn` always returns
   `passed=False`; assert `solved=False`.
9. Test (e): `test_max_rounds_bounds_loop` — count revise calls; assert exactly
   `max_rounds` times.
10. Additional tests: `winner` field correctness (`"draft"` / `"collab"` / `None`);
    `attempts` empty on draft-pass; `len(attempts)` matches rounds on collab win;
    multi-round win at round 2; `max_rounds=0` produces no revise calls; `code` field
    is the LAST revised code on all-fail (not the original draft).

#### Implements
- [REQ-1] Draft -> critique -> revise loop (test-gated)
- [REQ-2] Batched Jetson factory and active-hours probe protocol
