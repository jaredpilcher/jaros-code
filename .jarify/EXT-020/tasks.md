# EXT-020 Tasks

## TASK-1 — Build decomp_probe.py and offline tests

**Status:** done

#### Implements
- REQ-1 (Two-Phase Decompose-then-Implement Flow)
- REQ-2 (Honest Oracle Scoring and Reporting)

#### Steps
1. Create `harness/decomp_probe.py` with:
   - `_g_plan()` — temp=0 plan generation (REQ-1)
   - `_g_code_from_plan()` — temp=0 implement with plan scaffolding + indentation-repair (REQ-1)
   - `_core_decomp_probe()` — pure inner loop, injectable stubs, apples-to-apples greedy comparison (REQ-1)
   - `probe_task_decomp()` — git setup/teardown mirroring passk_probe (REQ-2)
   - `run_decomp_probe()` — entry point, task loading, summary table, VERDICT (REQ-2)
2. Create `tests/test_decomp_probe.py` — 10 offline tests verifying plan-feed-through, oracle-score-only invariant, file restoration, per_target population
3. Create `.jarify/EXT-020/` spec (requirements.md, design.md, index.json)
4. Add traceability anchors and update index.json
