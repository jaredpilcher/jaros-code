# EXT-027 Design: Verified-Solution Memory

## Purpose

Provide a persistent store of verified (test-gate-passing) solutions that the
harness can recall and inject as worked examples into future solve prompts,
as a potential memory-lever for similar problems.

**Caution:** The prior retrieval experiment (behavior-keyed RAG few-shot,
2026-06-XX) was a MEASURED NEGATIVE -- the reasoning bottleneck was not
addressable by examples.  This design is a cheaper, deterministic variant of
the same idea (no embedding model, no vector store, deterministic overlap score)
whose key hypothesis is that VERIFIED examples carry more signal.  The kill-test
determines whether that hypothesis holds before wiring into the default solve.

## Module Layout

```text
harness/solution_memory.py
 ├── _infer_problem_class(p, sig) -> str
 │       Explicit p["problem_class"] wins; else:
 │         is_repo_task=True  -> "multi-step-repo"
 │         is_multi_file=True -> "multi-file"
 │         else               -> "standalone-fn-gen"
 │
 ├── _sig_overlap_score(sig_a, sig_b) -> int
 │       language match:          +3
 │       fn_len_bucket match:     +2
 │       source_len_bucket match: +1
 │       has_examples match:      +1
 │       max possible:            7
 │
 ├── record_verified(problem, code, *, path) -> None   [best-effort, never raises]
 │       normalise problem -> _build_signature -> _infer_problem_class
 │       append JSONL: {ts, signature, problem_class, code, task_sample[:200]}
 │
 ├── recall_similar(problem, *, path) -> dict|None     [best-effort, never raises]
 │       normalise -> _build_signature -> _infer_problem_class -> self_sample
 │       load records from JSONL
 │       filter: same problem_class AND task_sample != self_sample (honesty)
 │       score each by _sig_overlap_score; pick highest
 │       return {code, signature, problem_class} or None
 │
 └── inject_verified_example(spec_or_context, recalled) -> str
         if recalled is None or code is empty/whitespace: return spec_or_context
         else: prepend labelled WORKED EXAMPLE block
```

## Store Format

```jsonl
{"ts": "2026-06-29T...Z", "signature": {...}, "problem_class": "standalone-fn-gen",
 "code": "def add(x, y):\n    return x + y\n", "task_sample": "def add(x, y):..."}
```

One record per line.  Append-only.  Production path:
``.jaros-data/artifacts/solution_memory.jsonl``.

## Similarity Matching (no embeddings)

```text
candidate_records
  |
  +-- filter: same problem_class
  |
  +-- filter: task_sample != self_sample[:200]  (honesty -- exclude self)
  |
  +-- score each: _sig_overlap_score(query_sig, record_sig)
  |       language (+3), fn_len_bucket (+2), source_len_bucket (+1), has_examples (+1)
  |
  +-- pick highest score -> return {code, signature, problem_class}
         or None if no candidates remain
```

The score prioritises language (3 pts) then function size (2 pts) then total
source size (1 pt) then docstring-examples presence (1 pt).  No minimum score
threshold -- if any same-class non-self record exists, it is returned (even
if the score is 0, it is the best available match for that class).

## Honesty Invariants

1. ``recall_similar`` excludes records whose ``task_sample`` matches
   ``source[:200]`` of the current problem (never recall the target's own answer).
2. The store is append-only; we never delete or overwrite records.
3. The inject block labels itself "NOT this task's answer" so the model sees it
   as a reference, not the expected output.
4. The kill-test is required before adopt; a non-result is faithfully recorded.

## Relationship to Prior Retrieval Negative

| Experiment | Retrieval key | Match algo | Result |
|------------|---------------|------------|--------|
| RAG few-shot (EXT-?) | behavior/Gherkin | nomic-embed cosine | NEGATIVE (-5pp) |
| Verified-memory (EXT-027) | verified code | deterministic sig | HYPOTHESIS |

Differences that MIGHT matter:
- RAG retrieved behaviorally similar un-verified examples; this retrieves VERIFIED ones
- RAG used an embedding model (potential noise); this uses deterministic features
- RAG added multiple examples; this adds one (lower prompt-bloat risk)

If the kill-test also shows no lift: confirms the bottleneck is reasoning, not examples,
regardless of verification status.  Record honestly and move on.

## Kill-Test Protocol

See REQ-2 for the full command sequence.  The key decision gate:

```
lift >= +2pp  AND  outside Wilson overlap  AND  reproduces on held-out slice
    -> wire inject_verified_example into default solve path
    -> update REQ-2 status to [x] in requirements.md

else
    -> leave inject unwired; update REQ-2 with negative result
    -> record result in .jarify/EXT-027/requirements.md
```
