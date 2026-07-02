# GAP-MAP — the Claude-Code capability surface, every gap in exactly one state

**The steering wheel of THE PURSUIT** (`docs/PURSUIT.md` §2.7 / §9.3). Work always flows to the
highest **(impact × tractability)** gap here. Living document — updated every cycle; never "done."

**States (exactly one per row):**
`unmeasured → probed → lever-named → in-progress → closed(number) → wall(dated, evidence)`

- **unmeasured** — no honest number yet.
- **probed** — a cheapest-falsifier probe has run; we know roughly where it stands.
- **lever-named** — the next mechanism to try is identified (with its escalation-ladder rung).
- **in-progress** — that lever is being built/measured now.
- **closed(number)** — parity-or-better vs Claude-Code-on-Opus-4.8 on a held-out instrument, with the number.
- **wall(date, evidence)** — no Jetson-fit path found across the FULL escalation ladder (L0–L8); DATED, revisited on every new model/method. A bookmark, never a conclusion.

Escalation ladder rungs referenced below: L0 prompt/format · L1 decompose/control-flow · L2 plane-shift · L3 precise-retrieval/fact-injection · L4 experience-recall · L5 reduction · L6 routing/new-model · L7 LoRA · L8 micro-model/distill · L9 dated wall.

> **v0 (2026-07-01)** — seeded from the session's measured results at tag `baseline-pursuit` (pending). Numbers are honest current state, NOT parity claims; NO row is `closed` (nothing yet matches Claude Code end-to-end). The daily-driver suite (§9.2) will replace these ad-hoc numbers with the frequency-weighted parity instrument.

---

## Capability surface

| # | Gap | State | Current honest number / evidence | Next lever (rung) |
|---|-----|-------|----------------------------------|-------------------|
| 1 | **Repo navigation / understanding** | probed | `/map` repo-map built (Aider-derived, `harness/repo_map.py`); no held-out parity number vs CC | daily-driver nav slice (§9.2) → measure (impact HIGH, tractable) |
| 2 | **Bounded single-file edits** | in-progress | SWE-bench-Lite CURATED easy-slice **5/8**, but UNCURATED-Lite (qwen best-of-N) measured **0/3** (django-14534/15061/14411 all resolved=False, applicable-but-wrong; 14915 incomplete). The easy-8 were selected EASY; the harness's reach on RANDOM Lite is far lower = the honest SWE-bench parity gap. HumanEval-40 code-gen gemma 33/40, qwen 36/40. (PITFALL: reading `grow_gold_*` run_ids gives gold=always-True — read the MODEL run_id.) DIAGNOSIS DONE (offline, suspect-harness-first): 14534+15061 localization VERIFIED-OK (locate matches gold-removed line) → GENUINE generation misses, not localization bugs; 14411 addition-only (unverifiable). So uncurated-Lite 0/3 is a REAL capability limit. SWE-bench axis now honestly mapped: strong on curated-easy, ~0 on random Lite, misses genuine. | axis MAPPED — steer to Foundry (#7) / shadow-mode (#6); SWE-bench levers (repair/LoRA) are lower-priority (repair already measured negative on residuals) |
| 3 | **Multi-file edits** | in-progress | localization HARNESS BUG fixed (711a136). Multi-caller root-cause probe: gemma+multi_file_fix reaches ALL-GREEN and fixes the shared ROOT (`geometry.area`→w*h) in 38s when symptom-patching one caller is insufficient (the "strictly-reduce-failing-count" gate forces it through) — cross-file root-cause fixing WORKS on the local 2B. Quality wart: also left a redundant caller patch (CC wouldn't). hard multi-step-repo still 0 (separate wall). | diff-cleanliness (avoid redundant symptom patches); scale to real multi-file repos; then daily-driver multi-file tasks |
| 4 | **Refactors** | probed | refactor/navigation family had committed wins earlier (authored suite); no held-out CC-parity number | daily-driver refactor slice (§9.2) |
| 5 | **Test write / run / fix loops** | in-progress | `solve_with_repair` built (best-of-N repair, test-gated); measured limited lift on hard slice; test-gate as judge is the workhorse | property-based test-gen (L2/§5C) + fix-iteration latency budget |
| 6 | **Debugging from failure** | lever-named | gold-free localization built (traceback L3 / coverage-trace); works for CRASH-class, not wrong-output (needs reasoning) | traceback→fix wiring on a real failing test (Docker) |
| 7 | **Long-horizon tasks (bootstrap→ship)** | probed | Foundry stood up + ship-log live (#8). `foundry_stats_cli`: **SHIP=True** — the harness produces a runnable single-file CLI that outputs correctly on 2 CLI cases. CORRECTION (Tenet 3): the earlier "SHIP=False" + "best-of-6 0/6" were BOTH **probe path bugs** (relative script path + `cwd` → script-not-found → empty stdout), NOT a model/harness capability gap — gemma's CLI code was correct all along (suspect-harness-first, 3rd bug this arc after localization + multi-file candidate_files). So the harness DOES ship runnable simple programs. | scale to MULTI-FILE / real projects (where long-horizon coherence is the real test); wire the ship-gated build loop into the harness proper |
| 8 | **Repo-scale context** | lever-named | generic context injection measured **net-negative** (do not repeat); precise dep-signature retrieval ~parity | semantic retrieval plane (§5B, PRECISE only) + program-analysis fact-sources (§5C) |
| 9 | **git / shell tool breadth** | probed | deterministic tools exist (fs.read/list/write, shell.exec, grep, apply_patch, code.search_replace); breadth vs CC unmeasured | Gap-list vs CC's tool surface → fill by frequency |
| 10 | **Interactivity / latency** | probed | Jetson gemma p50/p95 (small-n): navigate 0.6/0.6s (target<2 ✅), edit 4.4/5.0s (target<30 ✅), fix 5.9/13.5s max16 (target<90 ✅), build-module 64/82s (full generative build, no target). Latency is NOT a bottleneck at this scale. | widen n; capture per-model (qwen/reasoner slower); track as sizes grow |
| 11 | **Robustness / recovery** | probed | test-gate + validate() gates + process-tree-kill guards; no held-out robustness number | error-recovery slice in daily-driver suite |

## Cross-cutting measured walls (dated bookmarks, never conclusions)

- **wall(2026-07-01) — hard multi-step-repo algorithm synthesis** for the 2–4B Jetson-fit roster. Evidence: pass@k 0/7 (`9856d52`), decomposition 0/8 (`ff7726f`), maximal-help 0/6 (`5006e42`), decorrelated-reasoner 0/6, collaboration 0/6, experiment-loop 0/6; cell #35 un-throttled qwen3+repair **1/2 NEUTRAL** (`baseline-pursuit`, task #35 — task2's 3-function running-median all fail). **Revisit** on: any new Jetson-fit reasoning-distilled model (L6), a LoRA specialist (L7), a reduction library (L5), or the comprehension-vs-generation probe flipping (L3). NOT yet L8 (distillation untried on this class).

## Steering note

**Measured 2026-07-01 (daily-driver instrument, live gemma):** the **fix-single-file-to-pass-a-given-failing-test** category is a HARNESS STRENGTH — 9/9 on authored tasks up to moderate algorithmic difficulty (merge-intervals, deep-flatten, dedup-order), because `fix_loop`'s test-gated best-of-N iteration extracts the solution (same mechanism as SWE-bench 5/8). This is NOT a CC-parity claim (authored, single-file, a failing test handed in) — it is a calibration: **authoring more fix-with-test tasks no longer discriminates.**

**UPDATED 2026-07-01 (build-module added + measured):** build-from-intent ALSO passes (Stack, word_frequencies from spec, 11/11 total) — so the strength is broader than "has a failing test": across the **entire single-file daily middle** (edit/fix/build/navigate) up to moderate difficulty, the harness brute-forces correctness (fix_loop iteration + build_from_intent self-testing). **This whole region is a measured STRENGTH and does NOT discriminate vs CC** (both ~100%). Authoring more single-file moderate tasks is a confirmed rut — STOP.

**SHARPENED 2026-07-01 (multi-file measured too):** multi-file cross-file ROOT-CAUSE fixing ALSO works on moderate tasks (multi-caller probe passed, fixed the shared root). So it is not "single-file" that saturates — it is **MODERATE AUTHORED TASKS OF ANY CATEGORY**: the test-gated harness (fix_loop + multi_file_fix + build_from_intent self-testing) brute-forces correctness on anything a determined generate-and-test loop can reach. **Therefore a trustworthy DISCRIMINATING parity number cannot come from authored moderate tasks at all** — authoring more of them (any category) is the rut. Latency #4 is now measured (green). The discriminating parity signal lives ONLY in the hard/real/long-horizon instruments:
- **#2 SWE-bench** — the external hard bar we HAVE (5/8 easy-slice); GROW the slice (8→50) = the tractable discriminating capability number, no owner needed.
- **#7 Foundry** — long-horizon bootstrap→ship; the biggest unmeasured dimension benchmarks can't touch (a real fresh-focus build).
- **#6 shadow-mode** — the owner's REAL Claude Code tasks replayed; the strongest signal, PENDING owner go-ahead.

NEXT concrete step: grow the SWE-bench slice (#2) as the tractable discriminating number, and stand up the Foundry (#7) for long-horizon. Do NOT keep authoring moderate daily-driver tasks (measured non-discriminating). Bootstrap remaining: embedder/LoRA/distill probes (§9.5/6, Jetson-only per [[jaros-code-training-plane]]). Daily-driver suite stays as a fast regression/latency harness + flywheel-capture source, NOT the discriminating parity number.
