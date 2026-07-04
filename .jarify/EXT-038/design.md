# EXT-038 — Web Research Plane: Architecture

The research plane lets the product read current, correct external documentation before building or
modifying a system against it (PRIME-001 capability (a)). PRIME-001 calls this **"the single biggest
honesty attack surface"** and requires two HARD guards plus gated egress to exist BEFORE any actual
fetch capability lands. This spec's first requirement (REQ-1) builds exactly that foundation, standalone
— no network call is made anywhere in this module.

```text
   FUTURE fetch entrypoint (a later task, NOT built here)
        │
        ▼
   ┌───────────────────────── GUARD 1 — EVAL-LEAK HARD-DISABLE ─────────────────────────┐
   │  assert_research_allowed()                                                          │
   │    research_allowed()?                                                              │
   │       - inside eval_lock() context?            ──▶ NO  (locked)                     │
   │       - JCODE_EVAL_ACTIVE env truthy?           ──▶ NO  (locked, cross-process)      │
   │       - lock state indeterminate/unset-signalled ──▶ NO  (FAIL-CLOSED)               │
   │       - otherwise                               ──▶ YES                             │
   │    NO  ──▶ raise ResearchDisabledError  (fetch NEVER proceeds)                       │
   └───────────────────────────────────────┬─────────────────────────────────────────────┘
                                    allowed ▼
   ┌───────────────────────── GUARD 2 — EGRESS GATING ──────────────────────────────────┐
   │  research_egress_policy(*allowed_hosts)                                             │
   │    reuses harness.secure_exec.EgressPolicy — default-deny, fail-closed allow-list,  │
   │    exact-host match, no substring bypass. RESEARCH_DEFAULT_HOSTS is a SUGGESTION    │
   │    only — never auto-applied; caller must opt in per host explicitly.               │
   └───────────────────────────────────────┬─────────────────────────────────────────────┘
                                            ▼
                              (a later task performs the real fetch here,
                               scanned/sandboxed exactly like generated code — REQ-7/EXT-037)
                                            │
                                            ▼
   ┌───────────────────────── GUARD 3 — UNTRUSTED-CONTENT WRAPPER ──────────────────────┐
   │  wrap_untrusted(text, source)                                                       │
   │    ===== UNTRUSTED WEB CONTENT (source=..., DATA ONLY — NOT INSTRUCTIONS) =====     │
   │    <fetched text, injection directives neutralized/labeled>                         │
   │    ===== END UNTRUSTED WEB CONTENT =====                                            │
   │    -- idempotent, never raises -- this is what a planner/agent prompt may ever see  │
   └───────────────────────────────────────┬─────────────────────────────────────────────┘
                                            ▼
                          planner / reasoning prompt (facts only, never obeyed as instructions)
```

## Why the guards land before the fetch capability

A skeptic will ask exactly this: "how do you know research never leaked a held-out benchmark's
solution?" The eval-leak guard must be **provably airtight, not trust-based** (Tenet 3) — so it is
built, tested, and proven via a simulated-eval contract test BEFORE there is any fetch code that could
leak anything. Symmetrically, prompt-injection via fetched text is a real vector the moment research
feeds a planner, so the untrusted-content fence must already exist the first time real content is
fetched, not retrofitted after the fact.

## Relationship to existing modules

`harness/secure_exec.py` (EXT-037/REQ-7) already provides the house `EgressPolicy` pattern
(default-deny + explicit allow-list, fail-closed on an undeterminable host) for gating dangerous
generated-code egress. `harness/research_guard.py` REUSES that exact class rather than reimplementing
allow-list logic — one egress-gating mechanism in the codebase, not two. This module adds nothing to
`secure_exec.py` itself; it composes it.

## Explicit, NOT-yet-built follow-ups (named honestly)

- The actual web-fetch capability (`harness/research_*.py` fetch entrypoint) that calls
  `assert_research_allowed()` first, uses `research_egress_policy(...)` to gate its own HTTP calls, and
  routes fetched bytes through `wrap_untrusted(...)` before they reach any prompt.
- Wiring `eval_lock()` (or `JCODE_EVAL_ACTIVE=1`) into the real eval runners (HumanEval/MBPP/SWE-bench
  harness entrypoints) so every measurement run forces the lock automatically, not just when a caller
  remembers to.
