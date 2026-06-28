# EXT-020 Design: Decomposition Probe

## Purpose

EXT-019 (pass@k) established that the 2B cannot generate the hard tasks even
with k=20 blind samples — the bottleneck is generation, not selection.
EXT-020 tests the last structural lever: **explicit, granular decomposition**.

The key question: if we give the 2B a detailed numbered implementation plan
(DECOMPOSE), does it then crack tasks it could not generate whole (IMPLEMENT)?

- If yes: the bottleneck was REASONING/PLANNING (which decomposition offloads).
  Next step is to productionize decompose->implement as a default harness path.
- If no (both decomp and greedy = 0): the bottleneck is CODING ITSELF.
  No amount of planning helps if the model cannot write the code.

## Two-Plane Placement

All three steps are in the REASONING plane (model calls):
- `_g_plan()` — model authors the plan
- `_g_code_from_plan()` — model implements following the plan
- Indentation repair — EXECUTION plane (deterministic, after generation)

The hidden oracle (`_run_nodes`) is EXECUTION plane — deterministic Docker tests.

## Flow Diagram

```text
  bigbar_jaros.txt            tasks corpus
       |                           |
  [_parse_fail_shas]    [_resolve_tasks]
       |___________________________|
                    |
       [probe_task_decomp]   <- per task (mirrors probe_task from EXT-019)
                    |
       [git checkout parent + commit tests]
                    |
       [g_gherkin]  <- behavior spec at temp=0 (same as EXT-019)
                    |
     +--------------+--------------+
     |                             |
  GREEDY BASELINE            DECOMPOSITION
  (no plan)                        |
     |                        [_g_plan]
     |                   granular numbered plan
     |                       temp=0
     |                             |
  [implement_fn("")]          [_g_code_from_plan]
  no plan scaffolding         plan as scaffolding
  temp=0                      temp=0
     |                             |
  [indentation repair]     [indentation repair]
     |                             |
  [_apply_func]            [_apply_func]
     |                             |
  [_run_nodes]  SCORE-ONLY   [_run_nodes]  SCORE-ONLY
  ORACLE (never shown to      ORACLE (never shown to
  model during generation)    model during generation)
     |                             |
  greedy_pass: bool          decomp_pass: bool
     |___________________________|
                    |
              [Summary table]
              decomp vs greedy
              VERDICT: HELPS or NO GAIN
```

## Honesty Invariants

- The hidden oracle (`_run_nodes red->green`) is NEVER shown to the model.
- The plan is generated BEFORE implementation (no oracle feedback between steps).
- `_core_decomp_probe` is pure (no git I/O) and fully testable offline via
  injectable stubs for plan_fn, implement_fn, and oracle_fn.

## Runtime Estimate

~8 tasks * 3 LLM calls (gherkin + plan + implement) * ~30s/call ≈ 12 minutes.
No Docker for this probe (oracle is the only Docker touch, same as EXT-019).
