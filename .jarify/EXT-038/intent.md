# Intent

This spec exists to give the product the web-research capability the Prime Directive names as
capability (a): the ability to read current, correct official documentation, framework/library
APIs, and evolving protocols before implementing against them, rather than guessing from stale
training memory. But the Prime Directive also names this plane "the single biggest honesty attack
surface," so this spec is built guards-first: the safety envelope lands BEFORE the fetch code, and
the read-only fetch capability must run inside it. The guards are an eval-leak HARD-DISABLE (all
research categorically OFF during any eval/measurement run, fail-closed, forceable across process
boundaries), an untrusted-content wrapper that fences fetched text as DATA-ONLY to neutralize
prompt-injection before it reaches any reasoning prompt, and egress gating (default-deny
allow-list). The fetch itself is GET-only, size/timeout/redirect-capped, SSRF-hardened, and always
returns wrapped text.

It converges toward the Prime Directive's honesty commitment (Tenet 3) — one leaked fetch of a
held-out benchmark's public GitHub source would invalidate the number and our credibility, so the
lock must be provably airtight, not trust-based — and reconciles with Tenet 2: read-only research
is information retrieval, not inference, so every reasoning call still runs on the local Jetson
model at $0. Two-plane discipline holds throughout: every mechanism here is deterministic
execution-plane logic with zero model calls.
