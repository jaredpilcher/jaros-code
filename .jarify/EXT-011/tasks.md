# Implementation Tasks

### [TASK-1] Reproducible Docker environment and BRUTAL commit-mining filter

Evaluation runs against a single real repo (`more-itertools`) inside a pinned Docker image
with pinned Python and test dependencies, so the same test command yields the same result
run after run with no host-Python drift. On top of that reproducible base, commit history
is walked and filtered brutally: a commit is only kept when it touches
`more_itertools/*.py` AND its touched tests are validated to fail at the parent and pass at
the commit; everything else (merges, dependency bumps, formatting, renames, generated/data/
doc-only commits, and commits whose message under-specifies the change) is dropped with a
reason, and a drop ledger (`{reason: count}`) is emitted with no silent truncation.

#### Steps
1. Run all test execution for the eval inside a pinned Docker image (pinned Python
   version + test dependencies) in `harness/commit_replay.py`, so the same command produces
   the same result across runs regardless of the host environment.
2. Walk repository history and select commits touching `more_itertools/*.py`.
3. For each candidate commit, validate — not assume — that its touched tests fail at the
   parent commit and pass at the commit itself, by actually checking out and running both
   states in the Docker environment.
4. Drop merges, dependency bumps, pure formatting/whitespace changes, renames, generated
   code, data/doc-only commits, and commits whose message under-specifies the change (the
   diff carries information the message lacks), logging a reason for each drop.
5. Emit a drop ledger of `{reason: count}` alongside the surviving task list so the
   denominator is transparent and nothing is silently truncated.

#### Implements
- [REQ-1] Reproducible environment (the hard part)
- [REQ-2] Commit mining + BRUTAL filter

### [TASK-2] Red→green oracle and honest baseline reporting

A commit counts as solved only when the harness's change makes the previously-failing
touched test(s) pass without regressing any previously-passing test in the touched file —
never by comparing against the original commit's diff. The raw pass@1 is reported with a
Wilson 95% confidence interval and the drop ledger from TASK-1, so every published number is
reproducible and re-derivable.

#### Steps
1. Implement the oracle check in `harness/commit_replay.py`: mark a commit solved only when
   the touched test(s) fail at the parent and pass after the harness's change is applied.
2. Verify no previously-passing test in the touched file regresses as a side effect of the
   harness's change.
3. Never compare the harness's output against the original commit's diff — the oracle is
   red→green test outcomes only.
4. Report the raw real-repo pass@1 (no additional jigs applied) together with a Wilson 95%
   confidence interval and the TASK-1 drop ledger, so the published number is fully
   re-derivable.

#### Implements
- [REQ-3] Oracle = red→green, never diff-match
- [REQ-4] Honest baseline + Wilson CI

### [TASK-3] Convergence loop with generalization gating and easy→hard/held-out ordering

Each failure drives a DISCOVER → author-a-deterministic-jig → generalization-gate cycle:
the supervisor probes the raw model output to name the failed grain, authors a test-gated
jig, and only integrates it if it lifts the pass rate on held-out commits of the same class
it never saw (otherwise it is reverted as memorization). Surviving commits are ordered
easy→hard by a difficulty proxy and split into a dev set (for jig-building) and a held-out
set (for gating), partitioned by commit so nothing leaks.

#### Steps
1. On each observed failure, probe the raw model output and name the specific failed grain
   in `harness/commit_replay.py`'s supervisory loop.
2. Author a deterministic, test-gated jig targeting the diagnosed failure class.
3. Gate every new jig against held-out commits of the same class it was never tuned on;
   integrate it as a permanent layer only if it lifts the held-out pass rate.
4. Revert any jig that is net-negative or fails to lift the held-out rate (treat that as
   memorization, not generalization).
5. Order surviving commits by a difficulty proxy (lines/files touched, hunk count) so
   primitive cases precede hard cases, and split them by commit into a dev set (jig-building)
   and a held-out set (generalization-gating), ensuring no commit appears in both.

#### Implements
- [REQ-5] Convergence loop + generalization gate
- [REQ-6] Easy→hard ordering

### [TASK-4] Robust self-test execution — per-test timeout + guaranteed container cleanup

The self-test runner (`_run_selftests`), which executes the 2B's Gherkin-derived
scaffolding tests inside Docker, guarantees container cleanup under every exit condition —
normal completion, subprocess timeout, or an unhandled exception — so a hung self-test
container never orphans and burns CPU indefinitely.

#### Steps
1. Launch each `_run_selftests` container with an explicit, unique `--name` derived from
   `uuid4()` in `harness/commit_replay.py` (lines 439-481), so it can be targeted for
   cleanup regardless of host-process state.
2. On `subprocess.TimeoutExpired`, explicitly call `docker kill <name>` then
   `docker rm -f <name>` before returning `(False, "timeout")`, rather than relying on
   `--rm` alone (which does not fire if the host `docker run` process itself is killed
   mid-run).
3. Wrap the whole invocation in a `finally` block that unconditionally calls
   `docker rm -f <name>` for belt-and-suspenders cleanup on every exit path.
4. Implement `_docker_force_remove` to swallow all errors (a container that is already gone
   is treated as a no-op) so cleanup itself never raises.
5. Pass `--stop-timeout 5` to Docker so the container's stop grace period is bounded, and
   enforce a wall-clock timeout (~25-120s) at every call site, treating a timed-out
   self-test as a fail without stalling the eval.

#### Implements
- [REQ-7] Robust self-test execution — per-test timeout + guaranteed container cleanup

### [TASK-5] Robust oracle red-green execution — per-test timeout + guaranteed container cleanup

The oracle runner (`_run_nodes` / `_run_nodes_fb`), which scores a candidate against the
repo's actual hidden tests, guarantees the same container cleanup discipline as TASK-4 so
an infinite-loop candidate can never orphan a container and stall the whole eval (observed
live as bug #15: an orphaned `infallible_newton` container had to be killed manually).

#### Steps
1. Launch each `_run_nodes` / `_run_nodes_fb` container with an explicit, unique
   `--name jaros_oracle_<uuid4-hex[:12]>` in `harness/commit_replay.py` (lines 114-144,
   284-311), so it can be targeted for cleanup regardless of host-process state.
2. Pass `--stop-timeout 5` to Docker to bound the container's stop grace period.
3. On `subprocess.TimeoutExpired`, call `_docker_force_remove(cname)` before returning,
   scoring the timed-out candidate's nodes as red (all fail) so the eval proceeds normally.
4. Wrap the invocation in a `finally` block that unconditionally calls
   `_docker_force_remove(cname)` on every exit path (normal, timeout, exception).
5. Enforce a wall-clock timeout (default 180s, caller-overridable) on every invocation.

#### Implements
- [REQ-8] Robust oracle red-green execution — per-test timeout + guaranteed container cleanup

### [TASK-6] Multi-repo 100+ task big-bar corpus

The original 37-task more-itertools bar is too small for a real delta to clear the noise
floor (observed 4 false parities on the same bar). The corpus is expanded past 100 tasks by
mining deeper more-itertools history (skip=800, skip=1200, disjoint from the existing dev
set) and adding validated toolz tasks, unified behind a repo-aware task loader and multi-repo
runner.

#### Steps
1. Mine deeper more-itertools history (`skip=800`, `skip=1200`) using the same red→green
   validity bar as the original 37-task set, keeping the slices disjoint from the existing
   dev set (`more-itertools_valid_tasks.json` = skip=0..799).
2. Extract validated tasks from `pytoolz/toolz` using the same commit-mining pipeline.
3. Implement `tasks_corpus(repos_dir, bar)` in `harness/commit_replay.py` (lines 1276-1365,
   1379-1447) to load and merge all validated task JSONs, stamping each with `"repo"` for
   multi-repo routing, and deduplicating by SHA across slices; `bar="standard"` stays
   backward-compatible, returning only the original 37-task file.
4. Implement `run_gherkin_jaros_multi(repos_dir, tasks)` to route each task to the correct
   repo `Path` and run `attempt_gherkin_jaros` per task, printing per-task results and a
   Wilson CI summary.
5. Replace hardcoded `"tests/"` checkout paths in `validate_redgreen` and every `attempt_*`
   function with `_spec(repo)["test"]`, so toolz tasks use `toolz/tests/` instead of the
   more-itertools-only path.
6. Add `corpus_counts(repos_dir)` (per-repo task-count breakdown), a `--bar big` flag, and a
   `--tag <name>` flag (for naming deep-history-slice output JSON) to the `commit_replay`
   `__main__` CLI.

#### Implements
- [REQ-9] Multi-repo 100+ task eval bar (bigger, less-noisy)

### [TASK-7] Agentic big-bar A/B arm (orchestrator vs deterministic)

`run_gherkin_jaros_multi` gains an `agentic: bool` toggle so the same 100+ task big bar can
run either the deterministic Jaros-native fix-loop or the 2B-judge orchestrator
(`behavioral_solve_agentic`) as its sole driver, holding the Gherkin grains, self-tests,
repair tools, and red→green oracle identical between arms for an honest comparison.

#### Steps
1. Add an `agentic: bool = False` parameter to `run_gherkin_jaros_multi` in
   `harness/commit_replay.py` (lines 1412-1414, 1419-1428, 1502-1524).
2. When `agentic=False`, route each task to `attempt_gherkin_jaros` (Runtime-gated,
   hash-chain logged, deterministic) — unchanged from TASK-6's default behavior.
3. When `agentic=True`, route each task to `attempt_gherkin(..., agentic=True)` (the 2B-judge
   orchestrator), reusing the same Gherkin/self-test/repair tooling so only the driver
   differs.
4. Print the active arm (`DETERMINISTIC-JAROS` vs `AGENTIC-ORCHESTRATOR`) in the result
   banner and before the run starts, for unambiguous log reading.
5. Add `--agentic` to the `commit_replay` `__main__` `--bar big --gherkin-loop --jaros` CLI
   path to activate the orchestrator arm.

#### Implements
- [REQ-10] Agentic big-bar A/B arm (orchestrator vs deterministic, honest comparison)
