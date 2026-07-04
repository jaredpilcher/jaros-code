# Design — Commit-Replay Evaluation

## Overview

`harness/commit_replay.py` is the honest real-repo evaluation bar. Instead of authored
synthetic tasks, it MINES real commits from real repositories (more-itertools, toolz) and
replays them: at the parent commit the touched test(s) are RED, and a task is solved only when
the harness's own change turns them GREEN without regressing previously-passing tests in the
touched file. The oracle is red→green behavior — NEVER a diff-match against the original commit —
so the harness is free to fix the bug any way that makes the real tests pass. Everything runs
inside a pinned Docker image to eliminate host-Python drift and guarantee reproducibility, and
all container lifecycles are hardened so a hanging or infinite-loop candidate can never orphan a
container and stall the eval.

## Pipeline: mine → filter → order → split → replay → score

```text
   repo history (more-itertools, toolz)
            │
   ┌────────▼─────────┐  REQ-2  commit mining + BRUTAL filter
   │ keep commit iff:  │   drop (LOGGED, no silent truncation):
   │  (a) touches      │     merges · dep bumps · formatting/whitespace ·
   │      pkg/*.py     │     renames · generated · data/doc-only ·
   │  (b) touched test │     message under-specifies the change
   │      RED@parent   │   → drop ledger {reason: count}
   │      GREEN@commit │
   └────────┬─────────┘
            │ surviving validated tasks
   ┌────────▼─────────┐  REQ-6  easy→hard ordering + split
   │ order by proxy    │   difficulty proxy: lines/files/hunks
   │ (lines/files/hunks)│  partition BY COMMIT (no leak):
   │                   │     dev set (jig-building)  ·  held-out (gen-gate)
   └────────┬─────────┘
            │
   ┌────────▼──────────────────────┐  REQ-9  multi-repo ≥100-task big bar
   │ tasks_corpus(repos_dir, bar)  │   standard = more-itertools 37 tasks
   │  merges validated JSONs,      │   big = deeper slices (skip≥800) + toolz,
   │  stamps each task with "repo",│         disjoint from dev set, deduped by SHA
   │  dedups by SHA                │   run_gherkin_jaros_multi routes each task
   └────────┬──────────────────────┘         to its repo via _spec(repo)["test"]
            │
   ┌────────▼──────────────────────┐  REQ-10  A/B arm (differ ONLY in driver)
   │ agentic=False → attempt_       │   deterministic Jaros fix-loop
   │   gherkin_jaros (deterministic,│        (Runtime-gated, hash-chain logged)
   │   hash-chain logged)          │   vs
   │ agentic=True  → attempt_       │   2B-judge orchestrator (non-deterministic)
   │   gherkin(agentic=True)        │   same grains/self-tests/oracle → banner names arm
   └────────┬──────────────────────┘
            │
   ┌────────▼─────────┐  REQ-3  ORACLE = red→green (never diff-match)
   │  Docker (REQ-1)   │   solved iff touched test RED@parent → GREEN@change,
   │  pinned image     │   no touched-file regression
   │  pinned Python    │
   │  + test deps      │
   └────────┬─────────┘
            │
   ┌────────▼─────────┐  REQ-4  honest baseline + Wilson 95% CI
   │ raw pass@1, no    │   + drop ledger alongside (denominator transparency)
   │ new jigs, Wilson  │   every number reproducible / re-derivable
   └────────┬─────────┘
            │
   ┌────────▼───────────────────────────┐  REQ-5  convergence + generalization gate
   │ each failure → probe raw output →   │   author deterministic test-gated jig →
   │ name failed grain → author jig →    │   MUST lift held-out commits of same class
   │ gate on NEVER-SEEN held-out class   │   it never saw, else REVERT (memorization);
   └─────────────────────────────────────┘   never net-negative on held-out
```

## Container-lifecycle hardening (REQ-7 self-tests, REQ-8 oracle)

```text
   _run_selftests (REQ-7)              _run_nodes / _run_nodes_fb (REQ-8)
        │                                       │
   docker run --name jaros_selftest_<uuid>  docker run --name jaros_oracle_<uuid>
   --stop-timeout 5                         --stop-timeout 5
        │                                       │
   ┌────┴─────────────────┐              ┌──────┴───────────────┐
   │ normal │ TimeoutExpired│             │ normal │ TimeoutExpired│
   │        │  docker kill  │             │        │ _docker_force │
   │        │  + rm -f name │             │        │ _remove(cname)│
   └────┬───┴───────┬───────┘             └───┬────┴──────┬───────┘
        │           │                         │           │
        └─── finally: rm -f name ───┘         └─ finally: _docker_force_remove ─┘
        (swallows all errors — "already gone" is a no-op; wall-clock timeout enforced)
        Invariant: ZERO orphaned jaros_selftest_* / jaros_oracle_* containers on ANY exit path
```

## Key design points

- **Red→green, never diff-match (REQ-3).** The harness is judged by real test behavior, not by
  reproducing the human's exact edit — the only honest oracle for a real-repo fix.
- **Denominator transparency (REQ-2, REQ-4).** The BRUTAL filter drops anything unsolvable-in-
  principle from the message alone and LOGS every drop as a `{reason: count}` ledger reported
  beside the pass rate, so the pass@1 denominator is auditable (Tenet 3).
- **Generalization gate (REQ-5).** A jig counts only if it lifts NEVER-SEEN held-out commits of
  the same class; a jig that helps only the commits it was built on is memorization and is
  reverted — the guard against a dishonest number.
- **Bigger, less-noisy bar (REQ-9).** 37 tasks made a 1-task gap noise; the ≥100-task multi-repo
  corpus (kept strictly disjoint from the dev set) tightens the Wilson CI so a real
  deterministic-vs-agentic delta (REQ-10) is distinguishable from noise.
- **Reproducibility everywhere (REQ-1, REQ-7, REQ-8).** Pinned Docker for determinism, plus
  unique-named containers with `--stop-timeout`, explicit kill-on-timeout, and unconditional
  `finally` cleanup so no candidate can orphan a container and stall the eval.
