# EXT-008 — From-Intent Build Loop (the generative spine)

EXT-003 repairs; EXT-008 *creates*. The difference is where "correct" comes from. In
repair, correctness is handed to us as a failing test. Here the harness must derive it
from intent — and we must prove it derived the *right* one without letting it grade its
own homework.

```text
  build_from_intent(task)            task = {intent, target, signature, oracle_test(hidden)}
  ─────────────────────────────────────────────────────────────────────────────────────
   stub      = signature -> `raise NotImplementedError`         (deterministic seed)
   d_tests   = test-writer.decide({intent, signature})          Gemma 4 2B (e2b) — GENERATIVE
   Runtime.apply(d_tests) -> code.write_file(test_module)        deterministic tool writes
   res       = fix_loop(target, intent, pytest)                 EXT-003 implements vs SELF tests
   self_pass = res.success
   ── score in a FRESH dir the agents never touch ──
   oracle_pass = run(impl + hidden oracle_test) == green
```

## Why the hidden oracle matters

A 2B (or any model) writing both tests and code can satisfy itself trivially. The oracle
is the un-gameable check: the agents never see it, so they cannot shape code or tests to
pass it. Three outcomes carry distinct meaning:

```text
   self_pass  oracle_pass   meaning
   ─────────  ───────────   ───────────────────────────────────────────────
      ✗            ✗        unsolved — could not even satisfy its own tests
      ✓            ✗        MISREAD INTENT — convinced itself, built the wrong thing
      ✓            ✓        genuine — understood intent and implemented it
```

The `self ✓ / oracle ✗` quadrant is the most valuable signal we have for the generative
gap: it is exactly where a thin harness would *claim* success. Driving its rate down —
by better test-writer grains, criteria decomposition, and clarifying-question grains —
is the work of closing the distance to Claude-Code-on-Opus-4.8 on *generative* tasks,
not just repair.

## Plane placement here

Generative ≠ all-model. The seed stub, the file writes, the test runs, and the oracle
scoring are deterministic (Tenets 1 & 3); only the test-writing and the implementation
edits are Gemma 4 2B (`e2b`). As grains fail, plane-placement triage applies as everywhere:
push what the 2B cannot do (e.g. enumerating edge cases mechanically) into tools, keep
what it can (phrasing an assertion, choosing a structure) as tiny agents.
