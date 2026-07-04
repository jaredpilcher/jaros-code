# Design — Real-world robustness

## Overview

EXT-010 is a hardening spec, not a feature spec: the authored evals run on clean, small,
synthetic tasks and cannot surface the failure modes that only appear on REAL repos and REAL
(malformed) input. Dogfooding jaros-code against its own repo and against edge-case input found
six such defects — crashes on unhandled exceptions, spurious "suite not green" from too-tight
timeouts, mis-parsed CLI arguments, mis-scored `test_*`-named tasks, a fault-localizer broken
under process-cwd isolation, and non-minimal diffs. Each fix touches only the failure/edge path;
the 161-test CI stays green because behavior on the authored evals is unchanged.

## Where each robustness fix lives

```text
        REAL repo / REAL input  ─────────────────────────────────┐
                                                                  │
   ┌──────────────────────────── failure & edge paths ───────────┼───────────┐
   │                                                              ▼           │
   │  REQ-1  no unhandled crash                                              │
   │     multi_file._run ─────── catch TimeoutExpired → non-green (not crash)│
   │     agent_loop run-action ─ timeout guard                              │
   │     agentic_eval._pytest_passes ─ timeout guard                       │
   │     cli.handle ─────────── guarded in REPL (survive) + one-shot (exit1)│
   │                                                                        │
   │  REQ-2  usable test-gating on slow real suites                        │
   │     test-run timeout: 30s → 120s default, env JCODE_TEST_TIMEOUT_S    │
   │     (fix / build / rename / move all gate on the real ~47s suite)     │
   │                                                                        │
   │  REQ-3  CLI arg parsing matches intent                                │
   │     cli  /files, /grep ── peel a trailing arg only if it's a real path│
   │                           (else treat the whole phrase as the pattern)│
   │                                                                        │
   │  REQ-4  correct scoring for test_* entry points                       │
   │     mbpp.py / humaneval.py ─ run pytest <file>::<node> explicitly     │
   │                           so `from solution import test_x` isn't       │
   │                           collected & called argless                   │
   │                                                                        │
   │  REQ-5  fault localization under cwd isolation                        │
   │     multi_file.candidate_files ─ seed import-closure BFS at            │
   │                           root/Path(test_file).name (not process cwd)  │
   │                           → cross-file assertion faults localize       │
   │                                                                        │
   │  REQ-6  minimal-diff pass (Claude-Code-parity clean diffs)            │
   │     multi_file.multi_file_fix ─ snapshot originals; on all-green,      │
   │                           delta-debug: revert each kept edit, re-test; │
   │                           drop it if still green → minimal edit set    │
   └────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                161-test CI stays GREEN (authored-eval behavior unchanged)
```

## Minimal-diff (REQ-6) delta-debugging flow

```text
   multi_file_fix reaches all-green with kept edits {E1 … En}
                         │
        snapshot original repo contents (before any edit)
                         │
        for each kept edit Ek in reverse-kept order:
                         │
             revert Ek's file to original ──► re-run test_cmd
                         │
              ┌──────────┴───────────┐
        still all-green?          suite fails?
              │                       │
        Ek redundant →          Ek necessary →
        keep reverted,          restore fixed content,
        add to `dropped`        keep in `fixed`
              └──────────┬───────────┘
                         ▼
        repo ends all-green with MINIMAL necessary edit set
        (returned dict: solved=True, fixed=[…], dropped=[…])
```

## Key design points

- **Failure-path only.** Every change is on a timeout/exception/edge branch; the happy path and
  the authored evals are byte-unchanged, which is why the full suite stays green.
- **Isolation-correctness (REQ-5).** The whole multi-file capability silently returned `[]` on any
  isolated run (every eval, every SWE-bench/daily-driver run) because the closure seed was read
  relative to the process cwd. Rooting the walk at `root` is a deterministic two-plane fix — no
  model involved — that unblocks the capability without changing scoring.
- **Deterministic minimization (REQ-6).** The minimal-diff pass is pure test-gated delta-debugging
  with no model call; the invariant is that the repo always ends all-green with no necessary edit
  dropped (each drop is re-verified by a green run), and it is a no-op when only one edit was kept.
- **Serves Tenets 5 and 3.** Never crashing the operator is UX (Tenet 5); the fact that only
  dogfooding — not the authored suite — could catch these is the honesty case (Tenet 3).
