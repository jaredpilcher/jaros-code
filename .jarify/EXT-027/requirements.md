---
id: EXT-027
title: Verified-solution memory (a memory form, kill-test-gated)
status: covered
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

- [x] Kill-test protocol documented (above) and runnable in active hours
- [x] Kill-test result recorded faithfully (lift OR non-result) in this spec
- [x] Default solve path NOT modified until confirmed reproducible lift

**KILL-TEST RESULT 2026-07-02 (NON-RESULT — injection NOT adopted).** Ran an A/B on HumanEval[:25]
(temp=0, zero variance; `.jaros-data/req2_killtest.py`): baseline `solve_pass1` vs `solve_pass1` with
`recall_similar` + `inject_verified_example` prepending a VERIFIED worked example. Store = the 10 dev-task
verified solutions captured via REQ-3 (no HumanEval leakage — recall's honesty invariant excludes the
target, and HumanEval sources aren't in the store). RESULT: **base 22/25 (88.0%) vs mem-inject 23/25
(92.0%), delta +1, recall_fired 25/25.** The +1 is WITHIN the Wilson95 noise band at N=25 and does NOT
meet the adoption bar (≥+2pp AND outside the overlap AND held-out-reproducible). Injection fired on every
problem, so the mechanism was genuinely exercised — verified-memory injection did not clearly lift pass@1.
Consistent with the prior behavior-keyed-RAG NEGATIVE (the 2-3B bottleneck is REASONING, not examples);
also an 88% HumanEval ceiling leaves little headroom. VERDICT: hypothesis not confirmed; `inject_verified_example`
stays UNWIRED from the default solve (capture-only REQ-3 remains on). Revisit only if a fuller/harder-matched
store + a lower-ceiling bar shows a reproducible ≥+2pp lift. Kill-fast-log-the-negative: logged, moving on.

### [REQ-3] Auto-capture verified solves into the store (the flywheel corpus — start NOW)

`record_verified` (REQ-1) is fully built + tested but WIRED NOWHERE — nothing calls it, so the
store is a fully-functional ORPHAN and the corpus is empty. THE PURSUIT (§9.4/§7) requires
capturing every test-verified solve immediately: it is the self-distillation training corpus and
the experience-recall (L4) memory, and it only grows if capture exists — retroactive harvest is
lossy. CRITICAL DISTINCTION from REQ-2: this is CAPTURE (persistence only), NOT injection. Capture
changes NO solve prompt and NO output — it is pure recording, so it is NOT gated by the REQ-2
kill-test (which gates only `inject_verified_example` into the default solve). Wire capture on;
keep injection gated.

#### Acceptance Criteria
- [x] `harness/daily_driver.run_daily` calls `record_verified` for each SOLVED code-producing task
  (edit/fix/build-module/multi-file), capturing `{source: the original buggy file / spec, code: the
  winning solution content, problem_class: from the task category, model}` — best-effort, never
  raising, never affecting the task's pass/fail or the scorecard
- [x] Navigate/answer tasks (no code artifact) are NOT captured; UNSOLVED tasks are NOT captured
- [x] `record_verified` is capture-only: no `recall_similar`/`inject_verified_example` is wired into
  any solve prompt (injection stays REQ-2-kill-test-gated; default solve unchanged)
- [x] Offline test: `run_daily` with a stubbed solve records store entries for solved code tasks
  (monkeypatched `record_verified`, assert called with the right shape for solved-not-unsolved),
  no live model; full suite green

**Status: DONE** (implemented in `harness/daily_driver.py` + `harness/intent_loop.py`
[`IntentResult.code`, needed to expose the built module content for build-module capture];
`tests/test_ext027_autocapture.py` — capture verified offline, no recall/inject wired)

### [REQ-4] Auto-capture verified SWE-bench solves via a solve-pipeline callback (the hard-task flywheel fuel)

REQ-3 captures the SATURATING daily-driver solves, but the flywheel's most valuable fuel is the HARD
external-bar resolves (SWE-bench). Those flow through `harness/swebench_live.py::solve_gated` /
`solve_with_repair`, which run the REAL test as the selector — the exact moment a candidate is
test-VERIFIED. A clean two-plane hook lets that path capture without coupling `swebench_live` to
`solution_memory`: an optional `on_verified` callback fired ONLY when a candidate passes the real
test gate (NOT the self-consistency fallback, which is unverified). The SWE-bench driver supplies a
callback that calls `record_verified`. Capture-only (per REQ-3's distinction): changes no prompt, no
output, no returned diff; not REQ-2-kill-test-gated. This makes hard resolves accumulate as
distillation/recall fuel — the sustaining mechanism named in docs/GAP-MAP.md #2 (empty-store blocker).

#### Acceptance Criteria
- [x] `solve_gated` gains an optional `on_verified: Callable[[str], None] | None = None`; it is invoked
  with the winning diff EXACTLY in the test-PASS branch (the `if passed:` path), BEFORE returning —
  never on the self-consistency fallback (unverified) and never when nothing applies (`""`)
- [x] `solve_with_repair` gains the same `on_verified` param, invoked with the passing diff when a
  solve or repair round passes the gated test (the verified moment), never on the give-up return
- [x] `on_verified` is best-effort: wrapped so a raising callback NEVER changes the returned diff or
  breaks the solve (mirrors `record_verified`'s never-raise contract); defaults to `None` (no-op) so
  all existing callers are byte-for-byte unaffected (backward compatible)
- [x] Offline tests (`tests/test_ext027_swebench_capture.py`, NO live model, canned `gen_fn`/`run_test_fn`):
  (a) a spy `on_verified` fires with the passing diff when `run_test_fn` returns pass; (b) it does NOT
  fire when no candidate passes (self-consistency fallback path); (c) a raising `on_verified` does not
  change the returned diff. Full suite stays green.

**Status: DONE** (implemented in this session — `harness/swebench_live.py` gained a
`_notify_verified` best-effort helper plus `on_verified` params on `solve_gated` and
`solve_with_repair`, invoked only at the real-test-verified moment; `on_verified=None` is the
default so all existing callers are unaffected; `tests/test_ext027_swebench_capture.py` (10 new
tests, offline, canned gen_fn/run_test_fn) proves fire-on-pass, no-fire-on-self-consistency-fallback,
no-fire-on-empty/give-up, raising-callback-is-swallowed, and default-None backward compatibility;
full suite 1122 passed)
