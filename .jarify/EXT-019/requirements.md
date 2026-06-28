---
id: EXT-019
title: pass@k latent-capability probe
status: covered
priority: high
implementation:
  - file: harness/passk_probe.py
    ranges:
      - - 1
        - 290
  - file: tests/test_passk_probe.py
    ranges:
      - - 1
        - 200
---

### [REQ-1] Blind k-sample scoring against the hidden oracle

For each task from the [fail] set of bigbar_jaros.txt: build the Gherkin solve
context ONCE at temp=0 (mirroring `attempt_gherkin_jaros` up to g_code), then
draw k independent code samples at temperature T. Apply each sample and score it
with the hidden oracle (`_run_nodes` red->green). The oracle is used SOLELY for
scoring — it is NEVER shown to the model or used to select/guide any sample. The
k samples are blind.

Report per task: greedy_pass (temp=0, 1-shot, informational), n_passed/k, passk
(any sample passed). Report overall: pass@1 (0 by definition for [fail] tasks),
pass@k, Wilson95 CI.

#### Acceptance Criteria
- [ ] `_parse_fail_shas(bigbar_text, n)` extracts the first n sha prefixes marked [fail].
- [ ] `_resolve_tasks(fail_shas, corpus)` maps 8-char sha prefixes to corpus task dicts; deduplicates.
- [ ] `_core_probe(targets, orig, gherkins, task, repo, k, temp, timeout, generate_fn, oracle_fn)` is the testable inner sampling loop: runs 1 greedy + k blind samples, restores files between samples, returns {greedy_pass, n_passed, passk, k}.
- [ ] `probe_task` wraps `_core_probe` with git setup/teardown (mirrors `attempt_gherkin_jaros` up to g_code); accepts `_generate_fn` and `_oracle_fn` for offline testing.
- [ ] Oracle is called AFTER each sample is generated, never before or during generation.
- [ ] Files are restored to parent state between samples.
- [ ] Tasks with no targets or >4 targets are skipped (consistent with existing harness).
- [ ] The probe uses the robust Docker oracle functions `_run_nodes` (tree-kill + cleanup).

### [REQ-2] CLI entry point, summary reporting, and honest labelling

A `run_probe(n, k, temp)` function (and `__main__` argparse) runs the probe over
the first n [fail] tasks, prints per-task progress, and prints a final summary
table distinguishing pass@1 (known 0), greedy pass, and pass@k with Wilson95 CI.
The decisive interpretation (latent capability vs no signal) is printed honestly.

#### Acceptance Criteria
- [ ] `python -m harness.passk_probe --tasks 15 --k 20 --temp 0.8` runs without error (Jetson required for real run).
- [ ] Default args: --tasks 15, --k 20, --temp 0.8.
- [ ] Summary table prints per-task SHA, passk, n_passed/k, greedy, subject.
- [ ] Summary footer prints pass@1=0%, greedy%, pass@k%, Wilson95 CI.
- [ ] Verdict banner distinguishes strong signal (>=20%), weak signal (>0%), no signal (0%).
- [ ] "HONEST: oracle score-only" is printed in the run header.
