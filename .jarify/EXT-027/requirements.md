---
id: EXT-027
title: Verified-solution memory (a memory form, kill-test-gated)
status: partial
priority: medium
implementation:
  - file: harness/solution_memory.py
    ranges:
      - - 1
        - 170
---

### [REQ-1] Verified-solution store: record, recall, inject

A persistent JSONL store (``.jaros-data/artifacts/solution_memory.jsonl``) of
verified (test-gate-passing) solutions, with three public functions:

1. **``record_verified(problem, code, *, path=None)``** -- when a solve PASSES the
   test gate, append one JSONL line:
   ``{ts, signature, problem_class, code, task_sample}``.
   The ``signature`` reuses ``new_class_log._build_signature`` (the same deterministic
   feature schema).  ``problem_class`` is inferred from the problem dict (explicit
   ``problem_class`` field wins; otherwise derived deterministically from signature
   features: ``is_repo_task`` -> "multi-step-repo", ``is_multi_file`` -> "multi-file",
   otherwise "standalone-fn-gen").  Best-effort, never raises.

2. **``recall_similar(problem, *, path=None) -> dict|None``** -- find the most similar
   PAST verified solution by DETERMINISTIC signature match:
   (a) same ``problem_class`` (hard filter),
   (b) highest signature overlap score (language +3, fn_len_bucket +2,
       source_len_bucket +1, has_examples +1).
   HONESTY INVARIANT: exclude any record whose ``task_sample`` == the current
   problem's ``source[:200]`` (never recall the target's own answer).
   Returns ``{code, signature, problem_class}`` or ``None`` when no suitable
   match exists.  No embeddings (per the retrieval-negative caution).  Never raises.

3. **``inject_verified_example(spec_or_context, recalled) -> str``** -- format the
   recalled solution as a clearly labelled WORKED EXAMPLE block and prepend it to
   ``spec_or_context`` so the memory can change the solve prompt.
   Returns the original string unchanged when ``recalled`` is ``None`` or has no
   usable code.

#### Acceptance Criteria

- [x] ``record_verified`` appends a parseable JSONL line with all five required fields
- [x] ``record_verified`` stores the exact code string passed to it
- [x] ``record_verified`` infers ``problem_class`` from explicit field or signature features
- [x] ``record_verified`` truncates ``task_sample`` to 200 chars
- [x] ``record_verified`` is best-effort (never raises, not even for ``None`` problem)
- [x] ``recall_similar`` returns stored code for a same-class / similar-signature problem
- [x] ``recall_similar`` returns ``None`` for a dissimilar problem class
- [x] ``recall_similar`` returns ``None`` when the only same-class match IS the target problem (honesty)
- [x] ``recall_similar`` uses no embeddings (deterministic overlap score only)
- [x] ``inject_verified_example`` produces a worked-example block containing the recalled code
- [x] ``inject_verified_example`` prepends the block BEFORE the original spec/context
- [x] ``inject_verified_example`` returns the original string unchanged when recalled is None or empty

### [REQ-2] Kill-test protocol (documented; NOT run at scaffold time)

The verified-solution memory is a HYPOTHESIS to kill-test, not assume.  Prior art:
behavior-keyed RAG few-shot was a MEASURED NEGATIVE on the 2B (reasoning bottleneck,
not example bottleneck).  This memory form hypothesizes that a VERIFIED (not just
behaviorally similar) worked example carries more signal.

**Kill-test command:**

```bash
# 1. Run the honest bar WITHOUT verified-memory injection (baseline)
python -m harness.pass1_eval --n 50 --out baseline_no_memory.txt

# 2. Wire inject_verified_example into the solve prompt in pass1_eval
#    (add: recalled = recall_similar(problem); prompt = inject_verified_example(prompt, recalled))
#    Then re-run on the SAME 50 problems:
python -m harness.pass1_eval --n 50 --out baseline_with_memory.txt

# 3. Compare pass@1 honestly (same problems, same eval, temp=0):
#    WITH memory vs WITHOUT memory.  Report both numbers + Wilson95 CI.
#    ONLY adopt inject into the default solve if:
#      - Lift is >= +2pp AND outside the Wilson overlap (statistically clear)
#      - Lift reproduces on a HELD-OUT slice the memory was never tuned on
```

**Expected honest baseline:** NON-RESULT (no lift or slight regression) --
the same class of intervention as RAG failed before.  Record the result
faithfully either way.  A confirmed lift must change the SOLVE, not just
pad context (the key distinction from the RAG negative).

#### Acceptance Criteria

- [ ] Kill-test protocol documented (above) and runnable in active hours
- [ ] Kill-test result recorded faithfully (lift OR non-result) in this spec
- [ ] Default solve path NOT modified until confirmed reproducible lift
