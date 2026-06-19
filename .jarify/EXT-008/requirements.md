---
id: EXT-008
title: From-Intent Build Loop (the generative spine)
status: partial
priority: high
implementation:
  - file: harness/intent_loop.py
    ranges:
      - - 1
        - 110
  - file: .jaros-data/agents/test_writer_agent.py
    ranges:
      - - 1
        - 80
---

This spec serves **Tenets 1, 3, 4 & 5** of PRIME-001. EXT-003's repair loop only
exercises the regime where the spec is already given to us as a failing test — it fixes
existing code. That is necessary but it is *not* "tell the harness what you want and get
a working system." This spec adds the **generative spine**: turn a natural-language
intent into a working implementation with NO test handed to us, and measure — honestly,
un-gameably — whether the result actually meets the intent.

The dishonesty risk is explicit: a system that writes both its own tests and its own
code can write a trivially-passing test and declare victory. We defeat that with a
**hidden oracle** — a held-out test the harness never shows any agent, used only to
score. The gap between "passes its own tests" and "passes the oracle" is the real,
un-gameable measure of intent comprehension (Tenet 3).

### [REQ-1] Test-writer grain (intent → checkable tests)

A single-purpose `test-writer` agent turns an intent + target signature into pytest
assertions and hands a `code.write_file` Decision to the tool plane. It only defines
"correct"; it never implements. This is the judgement Claude Code makes when it writes
a test before code, decomposed to a grain a 2B can attempt.

#### Acceptance Criteria
- [ ] Emit runnable pytest code: the function import plus a `def test_*` with asserts
- [ ] Strip markdown/chatter; guarantee the import line; emit nothing (a fail advance)
      when no real test function was produced
- [ ] Persist tests only through the deterministic `code.write_file` tool (no direct I/O)

### [REQ-2] From-intent build loop with hidden-oracle scoring

`build_from_intent` seeds a signature stub, has the test-writer write the tests,
implements against them via the EXT-003 `fix_loop`, then scores the final
implementation against a held-out oracle test in a fresh directory.

#### Acceptance Criteria
- [ ] Report two metrics: `self_pass` (own tests) and `oracle_pass` (held-out oracle)
- [ ] The oracle test is never placed in the build dir or shown to any agent
- [ ] Run everything (tests, oracle) through the Runtime's deterministic tools
- [ ] Distinguish "self-only (misread intent)" from "self+oracle" from "unsolved"

### [REQ-3] Diversity of sand (future)

The mountain needs many grain *types*, not many copies of one. This spec is the first
generative grain; planned siblings: a criteria/spec agent (intent → acceptance bullets),
a signature/interface agent, and a family of repair specialists (import, type, API
misuse) alongside the EXT-003 boundary repair. Each is proven by from-intent evals whose
oracle pass-rate climbs over time.
