# ROADMAP — 3 weeks to a workable daily-driver CLI (2026-07-01 → 2026-07-21)

Authored from an outside review of the full history + current state (EXT-001..034,
SWE-Live slice 5/8, multi-model roster, gold-free localization). Direction for the
supervisor agent; each week's work still flows through jarify specs — this roadmap is
the map, the specs remain the law.

## The honest definition of the target (read first)

"95% of the way to Claude Code" is only meaningful with an instrument. Two different
claims must never be conflated:

- **95% of Claude Code's CAPABILITY on hard work** — NOT achievable in 3 weeks on
  Jetson-fit models. Our own measurements say so (commit-replay ~11%, SWE-Live slice
  62.5% on n=8 which will drop with n; CC-on-Opus reference on comparable bars is far
  higher). Denying this violates Tenet 3.
- **95% of everyday INTERACTIONS handled acceptably** — the daily-driver claim. Most
  real Claude Code usage is navigation, explanation, bounded edits, tests, fix-loops,
  refactors — classes we already do well or can reach. THIS is the 3-week target:
  **≥85% on a frequency-weighted daily-driver suite by Day 21 (95% = stretch), with
  honest latency numbers.**

Three headline numbers define all progress. Freeze them Day 1, re-measure weekly,
report deltas with Wilson CIs:
1. **Daily-driver task completion %** (new suite, built Day 2-3) — the CC-parity number.
2. **SWE-bench-Live %** on a 50-task stratified slice — the external hard bar.
3. **Routed-system triple**: routed vs best-single vs oracle-per-task — proves the
   multi-model system pays.
Plus a **latency budget** (p50/p95 per command class) logged on every run.

## Standing rules (all 21 days — non-negotiable)

- Every change gates on HELD-OUT data; net-negative → revert same day (existing rule).
- Holdout halves are read at most 1×/week. Dev halves freely.
- Latency is recorded on every eval run from Day 6 onward.
- `.launch/PUBLISHED.md` updated the moment any number becomes public.
- Track abort criteria are explicit below; an aborted track's days flow to CLI
  hardening (there is always more friction to fix).
- The experiment chain keeps running; this map feeds it, never idles it.

---

## WEEK 1 — Instrument the target, complete the roster, make routing pay

### Day 1 — State census + baseline freeze
- Census: exact roster + per-class profiles; wiring audit (every built lever —
  memory recall, collaborative solve, reductions, locate_* — is either WIRED into a
  default CLI path or explicitly parked; no silent orphans); current numbers.
- `git tag baseline-w0`; write `docs/BASELINE.md`. Every Week-3 claim is a delta vs
  this tag.
- Gate: census complete, no unexplained orphans.

### Day 2-3 — Build the daily-driver suite (the missing instrument; new EXT spec)
The single most important build of the three weeks. All current bars are
synthesis-centric; NOTHING measures the CLI end-to-end on the everyday interaction
distribution.
- 80 tasks executed END-TO-END through `python -m harness.cli` (not internals),
  frequency-weighted:
  navigate/explain/repo-Q&A 20% · bounded single-file edit 20% · fix-failing-test 15%
  · write tests 10% · refactor (rename/move/extract) 10% · build small module 10% ·
  multi-file small feature 10% · git/ops + misc 5%.
- Oracles: tests/AST assertions wherever possible; deterministic rubric checks
  (keywords/structure) for explain-class — NEVER a model judge (measured
  net-negative at small scale, #20/#21).
- Split 40 dev / 40 frozen holdout. Per-task latency recorded.
- Day 3 evening: BASELINE RUN, both halves. Whatever it says (expect 40-60%) is the
  honest starting distance to Claude Code.
- Gate: suite runs unattended in <2h.

### Day 3-4 (parallel) — Reasoning-model audition, marginal-coverage-FIRST
The decorrelation finding says the hard class needs a DIFFERENT distribution, not a
second coder.
- Candidates (Jetson-fit, Q4): DeepSeek-R1-Distill-Qwen-1.5B; R1-Distill-Qwen-7B-Q4
  (~4.4GB, solo-load only); Phi-4-mini-reasoning (3.8B); Qwen3-4B thinking mode
  (confirm current roster status); SmolLM3-3B.
- Protocol: run each FIRST on the roster's shared-failure set (hard-class cells +
  wrong-impl class). **Admission gate: flips ≥2 problems the entire current roster
  fails.** Only then run the full per-class profile (existing EXT-021 pipeline).
- ABORT: if no candidate flips anything, the hard class waits for
  reductions/memory — do not grind auditions.

### Day 5 — Routed-system metric (complete `eval_routed` into the honest triple)
- One harness, same tasks: (a) each single model, (b) routed, (c) oracle-best.
- Report routed−best-single (if ≤0 the router is net-negative — fix or bypass),
  routed−oracle (routing headroom vs coverage gap), router accuracy, misroute cost.
- Run on daily-driver dev half + current SWE-Live slice.
- Gate: routed ≥ best-single on both bars, else Day 6 morning is router repair.

### Day 6 — Latency + co-residency engineering
- Measure: per-model swap cost; token throughput per class at 25W (`nvpmodel -m 1`,
  measured 35-47% over 15W externally); KV-cache reuse across REPL turns.
- **Co-residency probe**: Gemma e2b Q4 (~2GB) + Qwen-coder-3B Q4 (~2GB) + KV, both
  resident in 8GB. If it fits → the common routing pair NEVER swaps. If not →
  sticky-model policy (stay on the loaded model unless class strongly demands a
  swap) + class-batching in evals.
- Speculative-decoding probe (2h timebox, only if the 7B was admitted): 1.5B draft +
  7B target via llama-speculative. Drop without ceremony if not trivially working.
- Deliver `docs/LATENCY.md` budget: navigation <2s · single-file edit <30s p50 ·
  fix-loop iteration <90s p50. Every eval logs against it from now on.

### Day 7 — Wire the orphans + Weekly Report #1
- Wire EXT-027 memory recall into default solve paths (recall→inject before solving,
  kill-test-gated). Measure on dev half.
- Wire EXT-029 collaborative solve as a router-selectable STRATEGY for classes where
  the coverage tally shows two models' strengths differ.
- Report: baseline numbers, roster decisions, routed triple, latency budget, CIs.
  Push notification per policy.

---

## WEEK 2 — Raise capability where it's cheap, buy speed, harden the CLI

### Day 8-9 — Fact-injection probe → precise context v2 (decides the wrong-impl class)
- Take 10 wrong-impl failures. Deterministically extract the ONE fact each got wrong
  (real callee signature/contract/behavior — EXT-028 dependency tools). Inject it.
  Count flips.
- ≥3 flip → comprehension gap: build targeted fact-injection (signatures+docstrings
  of DIRECT deps of the target function ONLY — precision is what the failed generic
  context jig lacked). Gate on held-out.
- <3 flip → generation wall confirmed: route the class to the reasoning model (if
  admitted) or reduction; record the honest negative.

### Day 9-10 — Reduction library v1 (deterministic problem-space transformation)
Owner direction: transform hard classes into classes the roster already covers.
Reductions are roster-agnostic capital — they compound.
- R0 (formalize existing): failing-output bug → locate_from_traceback/coverage →
  single-function repair. Wire everywhere it isn't.
- R1: multi-function change → dependency-ordered sequence of single-function fills
  (EXT-028 method-dependency tool), each test-gated.
- R2: implement-algorithm-with-examples → deterministic skeleton + property-test
  generation → bounded fills.
- Each: deterministic transform + test gate + HELD-OUT proof before adoption.

### Day 10-11 — SWE-bench-Live scale-up (the external bar gets a real denominator)
- Slice 8 → 50 stratified tasks (repo diversity, patch size). Split 25 dev / 25
  frozen holdout.
- Full pipeline: solve_from_failure + routed roster + reductions + memory.
- EXPECT the rate to drop vs 5/8 — small slices flatter. The bigger denominator is
  the point; provenance into PUBLISHED.md.

### Day 11-13 — CLI daily-driver hardening (the "workable" in workable CLI)
- Dogfood sprint: agent uses `jcode` itself for ALL its own repo edits for 2 days
  (log the self-hosting ratio); owner does 2 real evening sessions.
- Log every interaction: handled / friction / failed → ranked friction list; fix the
  top 10. Known candidates: streaming output, safe Ctrl-C interrupt, session resume,
  /undo reliability across multi-file changes, progress display during long solves,
  error messages, long-test timeout UX, sticky-model routing latency.
- Crash-free rule: the REPL never dies on any input (extend EXT-010 guards);
  verify kill-tree-on-timeout under the CLI path.
- Interactive latency: prompt-cache/KV persistence across session turns.

### Day 14 — Weekly Report #2 + Holdout Run #1
- First holdout read since baseline: daily-driver holdout half + routed triple +
  latency budget. Deltas vs `baseline-w0` with CIs. Prune net-negatives. Push report.

---

## WEEK 3 — Integrate, prove it end-to-end, publish the map, go public

### Day 15-16 — Full integration pass
- Default CLI path fires EVERYTHING: router (sticky policy) → strategy pick
  (direct / think-gated / collaborative / reduction) → memory recall →
  fact-injection → solve → test gate → SEARCH/REPLACE apply → undo checkpoint.
- Wiring census: zero orphans; per-lever fire-rate telemetry.
- Kill-tests end-to-end: each lever OFF vs ON on the dev half — every lever must
  earn its place IN COMPOSITION (interaction effects differ from isolated wins).

### Day 17 — Full measurement day (the honest scoreboard)
- Daily-driver all 80 · SWE-Live all 50 · commit-replay 37+11 (untouched for weeks —
  now a pure holdout) · routed triple · latency budget · per-model coverage map.
- Everything vs baseline-w0. This is Model Map v1's data core.

### Day 18 — The Daily-Driver Challenge (the real test)
- Owner: one full real session (2-4h) doing actual work ONLY through jcode. Agent:
  same, on a foreign repo (non-eval tasks: small feature, explain subsystem, write
  tests).
- Classify every interaction: handled / handled-with-friction / failed /
  reached-for-Claude-Code-instead.
- **The handled% is the headline "distance to Claude Code" number.** The failed list
  is next month's backlog.

### Day 19 — Gap taxonomy + prune + spec truth
- Classify every Day-17/18 failure: capability(class) / routing / UX / latency /
  infra. Prune net-negatives. Update all specs to reality (stale specs are defects);
  refresh traceability.

### Day 20 — Model Map v1 (the publishable artifact + the flag)
- `docs/MODEL-MAP.md`: model × class measured scores, coverage tally,
  correlated-failure map, routed-system numbers, latency profiles, honest gaps, all
  provenance-tagged. This is the owner's public flag AND the open-sourcing trigger
  he committed to in the published post.

### Day 21 — Release
- Public-repo hygiene: Apache-2.0 LICENSE; README numbers refreshed from
  PUBLISHED.md; **scrub private details (the hardcoded Jetson LAN IP in CLAUDE.md
  and configs → env var)**; safety note (network-refusing shell + code scan); tag
  `v0.1`.
- Owner publishes Post #2 ("The Model Map: what N tiny models can and can't do") +
  repo link — release-day mechanics already written in `.launch/jaros-release-kit.md`.
- Weekly Report #3 = release notes.

---

## Honest expectations for Day 21 (so nobody grades against fantasy)

- Daily-driver: baseline (Day 3) → **≥85%**, stretch 95%. This is the only honest
  "95% of the way to Claude Code" claim.
- SWE-Live 50: an honest number with CI — likely 20-40% given the 5/8 slice and
  small-slice inflation. The gap to CC-on-Opus persists and gets MAPPED, not denied.
- Latency: navigation instant-feeling; bounded edits tens of seconds; hard tasks
  minutes. Usable daily driver ≠ frontier-snappy.
- NOT in reach in 3 weeks: long-horizon multi-file synthesis at CC level, deep
  debugging of large unfamiliar codebases, frontier-feel latency on big edits. These
  go on the map as measured gaps with named next levers.

## Risk table

| Risk | Mitigation |
|---|---|
| Jetson serial bottleneck (swap thrash) | co-residency (Day 6); sticky routing; class-batching |
| Eval time explosion | workers= parallel eval (exists); nightly full runs; 2h suite gate |
| Overfitting the dev halves | frozen holdouts, 1 read/week, commit-replay as pure holdout |
| Reasoning-model audition all-fail | abort → days flow to reductions + CLI hardening |
| Owner time for Challenge Day | schedule Day 18 on a weekend/evening block now |
| Small-slice flattery (5/8) | 50-task slice Day 10-11 before any public claim |
