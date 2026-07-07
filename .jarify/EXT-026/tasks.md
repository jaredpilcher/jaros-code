# Implementation Tasks

### [TASK-1] Three-layer maximal-help prompt

For each target function, a single prompt stacks three deepening layers — retrieved
context, a worked example from a different task, and an explicit decomposition plan —
combined with the visible failing test and the current function, then sent to the model at
temp=0 to produce a corrected implementation, piped through the proven indentation-repair
layer. A pure helper exposes the assembled prompt for offline inspection without an LLM
call.

#### Steps
1. Implement `_build_maxhelp_prompt()` in `harness/maximal_help_probe.py` (lines 39-286) to
   assemble Layer 1 (`enriched_file_context` from `repo_context.py` — direct-dependency
   helper signatures + small bodies, not the whole file), Layer 2 (a worked before/after
   example plus commit intent from a different corpus task, via `_build_worked_example()`),
   and Layer 3 (a numbered step-by-step decomposition plan from `_g_plan`, from
   `harness/decomp_probe.py`), all visible in the composed prompt text alongside the visible
   failing test and current function.
2. Implement `_build_worked_example()` to pick the first corpus task whose sha differs from
   the target and has one cleanly changed function, ensuring the target task's own
   oracle/solution is never included in the prompt.
3. Implement `_g_code_maxhelp()` to call `_build_maxhelp_prompt`, send the result to the LLM
   at temp=0, and apply the existing indentation-repair layer to the reply.
4. Implement `_core_maxhelp_probe()` as a pure inner loop (no git I/O) that is fully testable
   offline via injectable stubs for generation and the worked-example source.

#### Implements
- [REQ-1] Three-Layer Maximal-Help Prompt

### [TASK-2] Honest oracle scoring

Every maximal-help implementation is scored via the hidden oracle (`_run_nodes` red→green),
called only after generation completes — score-only, never shown to the model — with
git setup/teardown mirroring `passk_probe` and `decomp_probe`.

#### Steps
1. Implement `probe_task_maxhelp` in `harness/maximal_help_probe.py` (lines 290-419) to
   checkout the parent commit plus the commit's tests before building the three-layer prompt
   (TASK-1), mirroring the git setup/teardown pattern used by `passk_probe` and
   `decomp_probe`.
2. Call the hidden oracle only after generation, never before or during, so scoring never
   influences the prompt.
3. Accept a `_worked_example` parameter of `"auto"` (build from corpus via
   `_build_worked_example`), `None` (no example layer), or a pre-built dict (for offline
   tests that must avoid any git calls).
4. Restore repo files to the parent state after the probe completes, whether it passed or
   failed, and skip tasks with no target functions or more than 4 targets (matching the caps
   used by the other probes).

#### Implements
- [REQ-2] Honest Oracle Scoring

### [TASK-3] Entry point and verdict reporting

`run_maximal_help(n=6)` loads the first N hard `[fail]` tasks from `bigbar_jaros.txt` (via
the shared `_parse_fail_shas`/`_resolve_tasks` helpers), probes each with the maximal-help
strategy, and prints a summary table with a Wilson CI and an explicit verdict comparing the
result against the known raw 0/8 baseline.

#### Steps
1. Implement `run_maximal_help(n=6)` in `harness/maximal_help_probe.py` (lines 423-570),
   loading tasks via `_parse_fail_shas` and `_resolve_tasks` (shared with EXT-019/EXT-020)
   from `bigbar_jaros.txt`.
2. Probe each task with `probe_task_maxhelp` (TASK-2), printing per-task cracked/not-cracked
   progress as the run proceeds.
3. Print an overall summary table with a Wilson95 CI, followed by an explicit verdict:
   "HARNESS-DEEPENING HELPS" when more than 0 tasks are cracked, or "DOES NOT HELP, route to
   decorrelated model" when 0 are cracked.
4. Wire a `--n N` CLI argument (default 6) so `python -m harness.maximal_help_probe --n 6`
   runs the probe end to end.

#### Implements
- [REQ-3] Entry Point and Verdict Reporting
