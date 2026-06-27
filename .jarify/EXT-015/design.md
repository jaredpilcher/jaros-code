# EXT-015 Design — Plan-then-code decomposition

## Research Basis

'Strategic Decomposition & Filtering for SLMs' showed a 1.5B model lifted +30% relative by:
1. Generating a natural-language implementation strategy first
2. A DETERMINISTIC filter cleaning the strategy (filtering > diversity)
3. Writing code FROM the filtered plan

The two-plane split is the key design insight: the 2B generates the plan (model plane),
but the cleaning MUST be deterministic (execution plane) because small models cannot
reliably improve their own scaffold.

## Architecture

```text
                 ┌──────────────────────────────────────────────────────┐
                 │  behavioral_solve_jaros(plan=True)                   │
                 │                                                      │
  intent+context │  Grain 1: gherkin_agent                             │
  ─────────────► │    └─ Decision: code.write_file (.gherkin)          │
                 │                                                      │
                 │  Grain 2: test_writer_agent                         │
                 │    └─ Decision: code.write_file (.py tests)         │
                 │                                                      │
                 │  Grain 2b (opt-in, plan=True only):                 │
                 │    plan_agent ──► strategy_filter_tool              │
                 │    [model plane]   [execution plane, deterministic]  │
                 │    └─ Decision: code.write_file (.plan)             │
                 │         filtered_strategy injected into intent ▼    │
                 │                                                      │
                 │  Grain 3: code_agent (intent + filtered_strategy)   │
                 │    └─ Decision: code.write_file (.py code)          │
                 │                                                      │
                 │  Fix-loop: shell.exec → feedback → code_agent       │
                 └──────────────────────────────────────────────────────┘

  plan=False (default):  Grain 2b is SKIPPED entirely.
                         Intent to code_agent is unchanged.
                         Byte-identical to pre-EXT-015 behavior.
```

## strategy_filter_tool (execution plane, deterministic)

```text
  Raw strategy text
         │
         ▼
  Phase 1: Remove fenced code blocks (```...``` multi-line regex)
         │
         ▼
  Per-line pass:
    strip if: starts with 'Example:', '>>>', '# '  (contamination)
    strip if: starts with 4+ spaces or 'def '/'return '  (code)
    strip if: matches boilerplate patterns ('Here is...', etc.)
    KEEP if: numbered step (^\d+\.\s+), bulleted (^[-*]\s+),
             or contains algorithmic keywords (check/handle/edge case/...)
         │
         ▼
  cleaned = join(kept lines)
  if empty: return original (graceful no-op)
         │
         ▼
  Cleaned strategy text
```

## Two-Plane Placement (PRIME-001 Tenet 1 + 2)

| Component              | Plane       | Rationale                                         |
|------------------------|-------------|---------------------------------------------------|
| plan_agent             | Model       | Judgement: what are the implementation steps?     |
| strategy_filter_tool   | Execution   | Deterministic cleaning — no judgement needed      |
| gherkin_agent          | Model       | Judgement: what behavior must the change satisfy? |
| code_agent             | Model       | Judgement: how to implement the plan+spec?        |
| Runtime.apply          | Execution   | Gate + log every host effect                      |

## Measurement Command

Default (EXT-013 jaros-native baseline):
```
python -m harness.commit_replay <repo> --gherkin-loop --jaros --n 37
```

Plan-then-code (EXT-015):
```
python -m harness.commit_replay <repo> --gherkin-loop --jaros --plan --n 37
```

Compare the two Wilson CI bands to determine whether plan-then-code lifts the score on the
held-out 37-task eval.  HONEST: both use intent-only (hidden oracle never seen during solve).
