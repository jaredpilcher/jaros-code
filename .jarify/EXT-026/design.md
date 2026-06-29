# EXT-026 Design: Maximal-Help Ceiling Probe

## Purpose

This probe answers the CHEAPEST-FIRST question before adding any new roster model:
can harness-deepening alone crack the hard multi-step-repo class that both gemma and
qwen fail 0/8 raw?

If the answer is YES (any tasks cracked with maximal help) -> deepen the harness first.
If the answer is NO (still 0/N) -> confirms the hard class genuinely needs a decorrelated
model (route via EXT-021).

## Three-Layer Prompt Architecture

```text
┌─────────────────────────────────────────────────────┐
│  MAXIMAL-HELP PROMPT (one call, temp=0)             │
│                                                     │
│  COMMIT INTENT: {subject}                           │
│                                                     │
│  FAILING TEST (visible spec):                       │
│    {failing_test_src}            ← public, safe     │
│                                                     │
│  Behavior scenarios (gherkin):                      │
│    {gherkin}                                        │
│                                                     │
│  ┌── LAYER 1: RETRIEVED CONTEXT ──────────────────┐ │
│  │  enriched_file_context (direct-dep helpers)    │ │
│  │  e.g. def _helper(x): ...                     │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌── LAYER 2: WORKED EXAMPLE (different task) ────┐ │
│  │  HONEST: sha != target sha                     │ │
│  │  Before: def f(x): return x                   │ │
│  │  After:  def f(x, y=0): return x + y          │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌── LAYER 3: DECOMPOSITION PLAN ─────────────────┐ │
│  │  1. Parse args                                  │ │
│  │  2. Initialize data structure                   │ │
│  │  3. Iterate + handle edge cases                 │ │
│  │  4. Return result                               │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  Current version of `{name}`:                       │
│    {parent_src}                                     │
│                                                     │
│  → Output ONLY def {name}(...):                     │
└─────────────────────────────────────────────────────┘
                    │
                    ▼
          LLM generates code (temp=0)
                    │
                    ▼
         indentation-repair (parse-gated)
                    │
                    ▼
          _apply_func → file written
                    │
                    ▼
    _run_nodes oracle (score-only, never shown to model)
```

## Data Flow

```text
bigbar_jaros.txt ──→ _parse_fail_shas ──→ fail_shas
corpus JSON files ──→ tasks_corpus ────→ corpus
                                          │
                               _resolve_tasks ──→ fail_tasks
                                                       │
                                            ┌──────────┘
                                            │  for each task:
                                            │
                         _build_worked_example ──→ worked_example (different sha!)
                         enriched_file_context ──→ enriched_ctxs
                         g_gherkin + _g_plan ─────→ gherkins, plans
                         _test_source ────────────→ failing_tests
                                            │
                         _core_maxhelp_probe ──→ maxhelp_pass (bool)
                                            │
                                    oracle: _run_nodes
                                    (score-only, hidden)
                                            │
                                      VERDICT printed
```

## Module Structure

```text
harness/maximal_help_probe.py
├── _build_maxhelp_prompt()     ← pure, testable, builds the 3-layer prompt string
├── _g_code_maxhelp()           ← calls LLM with the maxhelp prompt, returns code
├── _build_worked_example()     ← picks a different-sha task from corpus, extracts before/after
├── _core_maxhelp_probe()       ← pure inner loop (no git I/O), injectable stubs
├── probe_task_maxhelp()        ← git setup/teardown, orchestrates the layers
└── run_maximal_help(n=6)       ← entry point, loads fails, loops, reports verdict
```

## Honesty Invariants

1. `worked_example` sha is always != target sha (enforced in `_build_worked_example`)
2. The hidden oracle (`task["redgreen"]`) is passed ONLY to `oracle_fn` — never to
   `generate_fn` or to prompt construction
3. The visible failing test IS included in the prompt — it is the public spec (checked
   out from the commit's test file), not the hidden answer
4. `oracle_fn` is called ONLY after `generate_fn` has returned — pure score-only

## Comparison to Existing Probes

| Probe | Layers | Goal |
|-------|--------|------|
| EXT-019 passk_probe | none (blind sampling k=20) | measure latent capability |
| EXT-020 decomp_probe | plan only | does planning help? |
| EXT-026 maxhelp_probe | ctx + example + plan | maximum harness help before new model |
