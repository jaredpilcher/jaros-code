# Implementation Tasks

### [TASK-1] Blind k-sample scoring against the hidden oracle

For each task drawn from the `[fail]` set of `bigbar_jaros.txt`, the Gherkin solve context
is built once at temp=0 (mirroring `attempt_gherkin_jaros` up to `g_code`), then k
independent code samples are drawn at temperature T and each is scored blind against the
hidden oracle — the oracle is used solely for scoring after the fact, never shown to the
model or used to select/guide any sample.

#### Steps
1. Implement `_parse_fail_shas(bigbar_text, n)` in `harness/passk_probe.py` (lines 29-269)
   to extract the first n sha prefixes marked `[fail]` from the bigbar report text.
2. Implement `_resolve_tasks(fail_shas, corpus)` to map 8-char sha prefixes to corpus task
   dicts, deduplicating repeated matches.
3. Implement `_core_probe(targets, orig, gherkins, task, repo, k, temp, timeout,
   generate_fn, oracle_fn)` as the testable inner sampling loop: run one greedy sample plus
   k blind samples at temperature T, restoring files to the parent state between samples,
   and return `{greedy_pass, n_passed, passk, k}`.
4. Implement `probe_task` to wrap `_core_probe` with git setup/teardown (mirroring
   `attempt_gherkin_jaros` up to `g_code`), accepting injectable `_generate_fn` and
   `_oracle_fn` parameters for offline testing.
5. Call the oracle only after each sample is generated (never before or during generation),
   using the robust Docker oracle functions `_run_nodes` (tree-kill + cleanup, from
   EXT-011), and skip tasks with no target functions or more than 4 targets, consistent with
   the existing harness caps.

#### Implements
- [REQ-1] Blind k-sample scoring against the hidden oracle

### [TASK-2] CLI entry point, summary reporting, and honest labelling

`run_probe(n, k, temp)` and a `__main__` argparse entry run the probe over the first n
`[fail]` tasks, print per-task progress, and print a final summary table distinguishing
pass@1 (known 0 for this task set), greedy pass, and pass@k with a Wilson95 CI, together
with an honest verdict on whether the result indicates latent capability or no signal.

#### Steps
1. Implement `run_probe(n, k, temp)` in `harness/passk_probe.py` (lines 273-389) with
   default arguments `--tasks 15 --k 20 --temp 0.8`, iterating TASK-1's `probe_task` over
   the first n `[fail]` tasks and printing per-task progress.
2. Print a summary table with per-task SHA, `passk`, `n_passed/k`, `greedy`, and subject.
3. Print a summary footer reporting `pass@1=0%`, `greedy%`, `pass@k%`, and the Wilson95 CI.
4. Print a verdict banner distinguishing strong signal (>=20%), weak signal (>0%), and no
   signal (0%), plus an "HONEST: oracle score-only" line in the run header.
5. Wire a `__main__` block so `python -m harness.passk_probe --tasks 15 --k 20 --temp 0.8`
   runs end to end (Jetson required for a real run).

#### Implements
- [REQ-2] CLI entry point, summary reporting, and honest labelling
