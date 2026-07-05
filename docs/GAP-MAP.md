# GAP-MAP — the Claude-Code capability surface, every gap in exactly one state

> **APPENDIX to `.jarify/ROADMAP.md`** (the official Jarify Roadmap, owner directive 2026-07-04).
> The Roadmap is the organized FORWARD plan (NOW/NEXT/LATER horizons of specs/requirements) and the
> single source of truth for what's coming; THIS file is its detailed **measured-findings appendix**
> (the honest numbers + evidence behind each gap). Governed by the `jarify-manage-roadmap` skill.

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
| 2 | **Bounded single-file edits** | in-progress | **HONEST DISCRIMINATING NUMBER 2026-07-02 (n=16 widened, tighter CI): UNCURATED SWE-bench-Lite = 2/15 = 13.3% (Wilson95 [4%,38%]) on FRESH cleanly-evaluable django instances** (16 run: django-11039 + django-11133 RESOLVE; 13 miss; django-11422 EXCLUDED — its GOLD patch itself doesn't resolve, not cleanly evaluable, verify-don't-assume). The larger-n number is LOWER than the batch1-only 2/8=25% — **the CURATED easy-8 5/8 (62.5%) OVERSTATED real capability ~4.7x; ~13% is the honest external-bar number.** All 13 misses were applied-but-wrong (applicable edit, wrong logic) = genuine qwen-coder-3b generation limits, harness saturated. Reasoner-escalation (route misses→qwen3-thinking) KILLED as low-EV (2h/likely-negative). Superseded earlier: 2/8 (25%). NEXT per ladder: model-bound misses → L7/L8 (LoRA/distill). **★ 2026-07-02 UPDATE — the earlier "L7/L8 INFRA-BLOCKED" is REVERSED (training is UNBLOCKED on the Jetson):** installed `torch 2.12.1+cu130` (jetson-ai-lab `.io` jp6/cu126 index) + `peft/transformers/accelerate/datasets/bitsandbytes` (system pip `--break-system-packages`); GPU training VERIFIED (real Orin matmul). MEASURED end-to-end: a **1.5B SWE-Gym LoRA trains + GENERALIZES −11.8% held-out** (base 1.2045→adapter 1.062 on 30 unseen issues); **QLoRA-3B is FEASIBLE** (4-bit, ~4GB peak, loss descends). NEW honest boundary (not infra): (i) **bf16 3B OOMs** (≈6GB weights ≈ all 8GB) → bf16-trainable ceiling ~1.5B; (ii) **4-bit 3B is ~57s/step** on sm_87 (kernel fallback) → impractically slow for iterative runs; (iii) so the *fast-trainable* model (1.5B) is WEAKER than the served 3B baseline → training is UNLIKELY to budge the SWE-bench scoreboard near-term (a 1.5B adapter probably won't beat 5/8), and the only scoreboard-connecting path (GGUF-`--lora` serve + resolve-rate) has LOW EV given the 1.5B<3B gap. So training MECHANISM is PROVEN+GENERALIZING but scoreboard-uncertain; the real lever for THIS class stays roster-growth (a stronger fast-trainable Jetson-fit base) + accumulated verified data. **★ RESOLVED 2026-07-02 (definitive, scoreboard-tested): training gives ZERO resolve-rate lift for SWE-bench.** Trained a full 3B QLoRA SWE-Gym specialist (83min), which reduces held-out loss on SWE-bench-Lite −13% (clean, leakage-free, cross-distribution) — BUT the STAGE-2 resolve-rate test (specialist served via `--lora`, run through the real grind) = **0/11 new resolves on ALL base-misses + no regression on the control (django-11039 resolves)**: specialist ≡ base on the scoreboard (airtight). **Held-out LOSS is a MISLEADING proxy** — the "applied-but-wrong" misses are genuine REASONING limits; a LoRA lowers token-loss without instilling the reasoning to fix them. So the L7 LoRA lever is SPENT for SWE-bench (mechanism fully built end-to-end: stack/GPU/QLoRA-3B/GGUF/`--lora`-serving all ✓, capability payoff NULL). LESSON: validate a training lever on the SCOREBOARD, never the loss proxy. Revisit only with a fundamentally different distribution (reasoning-distilled data, not issue→patch) or a stronger base. (ii-legacy) the verified-solution store `solution_memory.jsonl` is EMPTY — `record_verified` is wired ONLY into the (saturating) daily-driver, so the SWE-bench solve path never captures its resolves = no accumulated fuel (the sustaining groundwork, task #62). So the SWE-bench uncurated class (~13%) is at a genuine CURRENT boundary for the roster+infra — an L9-ish bookmark (revisit on: a training GPU, a stronger Jetson-fit model, or accumulated verified data). TRACTABLE zero-cost groundwork (velocity doctrine parallel track): wire the SWE-bench solve path into `record_verified` so hard resolves accumulate for eventual distill (flywheel fuel). Also widen astropy for a full-Lite number. **ORACLE-BEST-OF-N MEASURED 2026-07-02 (decisive): oracle best-of-6 = 2/8 = first-applicable 2/8, GAP ZERO** — qwen-coder emits only ~1.75 distinct applicable candidates/instance (low diversity); for the 6 misses NOT ONE of best-of-6 resolves. So SELECTION is EXHAUSTED (a candidate-patch ranker / solve_gated / test-gate cannot recover the misses — there is no correct candidate hiding in the N). The misses are genuine GENERATION limits. CONSEQUENCE: the CPU-trainable ranker micro-model is RULED OUT for SWE-bench; the ONLY remaining lever is generation-training (L7 LoRA / L8 distill), which needs the GPU-CUDA stack (hard lift, JP7) + real data (open datasets: SWE-Gym/SWE-smith + flywheel). SWE-bench is now an evidence-complete boundary: L0-L5 harness saturated, selection exhausted, L6 reasoner low-EV, L7/L8 GPU+data-blocked. Prior: SWE-bench-Lite CURATED easy-slice **5/8 (2/8→OLD)** (django-11039 + django-11133 RESOLVE gold-free-no-leak; 10914/11001/11019/11099/11179/11283 miss) — qwen + tonight's improved harness (fence-strip). The CURATED easy-slice **5/8 (62.5%) OVERSTATED real capability ~2.5x**; 25% is the honest external-bar number the curated slice isn't. Combined uncurated so far ~2/11 (incl. the earlier 0/3). 2 genuine fresh resolves = the harness DOES generalize (not pure plumbing). NEXT: widen n for a tighter CI; escalate misses per the ladder (route to a stronger roster model / LoRA), not more harness. Prior context: SWE-bench-Lite CURATED easy-slice **5/8**, earlier UNCURATED-Lite spot-check **0/3** (django-14534/15061/14411 all resolved=False, applicable-but-wrong; 14915 incomplete). The easy-8 were selected EASY; the harness's reach on RANDOM Lite is far lower = the honest SWE-bench parity gap. HumanEval-40 code-gen gemma 33/40, qwen 36/40. (PITFALL: reading `grow_gold_*` run_ids gives gold=always-True — read the MODEL run_id.) DIAGNOSIS DONE (offline, suspect-harness-first): 14534+15061 localization VERIFIED-OK (locate matches gold-removed line) → GENUINE generation misses, not localization bugs; 14411 addition-only (unverifiable). So uncurated-Lite 0/3 is a REAL capability limit. SWE-bench axis now honestly mapped: strong on curated-easy, ~0 on random Lite, misses genuine. | axis MAPPED — steer to Foundry (#7) / shadow-mode (#6); SWE-bench levers (repair/LoRA) are lower-priority (repair already measured negative on residuals). **2026-07-02 QUIET-HOURS DEEP-DIVE on django-11964 (2 generalizable harness fixes committed, suspect-harness-first):** (1) parser now strips wrapping ```python fences from SEARCH/REPLACE blocks (`84992f9`) — qwen's CORRECT fixes were silently dropped when it fenced the block content; (2) `solve_gated` = test-gated best-of-N SELECTION (`eab457d`) — runs the real test on each distinct applicable candidate, returns the one that PASSES (first-applicable-wins was losing correct fixes). Also fixed the grind script's localization to reuse the proven production `locate_from_patch` (was naive first-substring → matched 'pass' in a comment → wrong region). VERIFIED django-11964's correct `__str__` fix RESOLVES (control: gold resolves) → it IS solvable, NOT a ceiling. Honest near-miss: the resolving `return str(self.value)` variant is a RARE qwen draw (0 resolving in ~34 gated samples across n=10 and n=24 runs; a separate 5-sample diag saw it once). Slice stays 5/8; a non-leaky lift needs flywheel-recall of the verified fix or repair fed the real str/repr failure (NOT leaking `str()` into the solve prompt). The 2 fixes are banked wins that help ANY instance with those failure modes. |
| 3 | **Multi-file edits** | in-progress | localization HARNESS BUG fixed (711a136). Multi-caller root-cause probe: gemma+multi_file_fix reaches ALL-GREEN and fixes the shared ROOT (`geometry.area`→w*h) in 38s when symptom-patching one caller is insufficient (the "strictly-reduce-failing-count" gate forces it through) — cross-file root-cause fixing WORKS on the local 2B. Quality wart: also left a redundant caller patch (CC wouldn't) — **FILLED 2026-07-02 (EXT-010 REQ-6, `7e21a88`): a test-gated delta-debugging MINIMAL-DIFF pass** (`multi_file.py::_minimize_edits`) reverts each kept edit after all-green and drops any that's redundant → minimal patch set like CC (deterministic, no model; +3 tests, suite 1125 green). hard multi-step-repo still 0 (separate wall). | diff-cleanliness (avoid redundant symptom patches); scale to real multi-file repos; then daily-driver multi-file tasks |
| 4 | **Refactors** | probed | refactor/navigation family had committed wins earlier (authored suite); no held-out CC-parity number. **QUALITY GAP FILLED 2026-07-02 (EXT-003 REQ-6, `509a7d5`): scoped tokenize-based rename** — `rename_symbol` now renames only Python NAME identifier tokens, NOT occurrences inside comments/docstrings/string-literals (was a crude `\b` regex that over-renamed non-behavioral text the test-gate couldn't catch) → CC-parity precise renames (+2 tests, suite 1127; also fixed refactor.py's untraced traceability) | daily-driver refactor slice (§9.2) |
| 5 | **Test write / run / fix loops** | in-progress | `solve_with_repair` built (best-of-N repair, test-gated); measured limited lift on hard slice; test-gate as judge is the workhorse | property-based test-gen (L2/§5C) + fix-iteration latency budget |
| 6 | **Debugging from failure** | lever-named | gold-free localization built (traceback L3 / coverage-trace); works for CRASH-class, not wrong-output (needs reasoning). **REPRO-TEST SYNTHESIS PROBED 2026-07-02 (research: Agentless selects patches gold-free via a model-synthesized reproduction test):** qwen2.5-coder-3b SYNTHESIS quality is HIGH — 8/9 plausible repro tests across 3 easy-slice issues, and the django-11964 one is ESSENTIALLY THE GOLD TEST (`MyChoice(TextChoices)` + `assert str(val)=='first'`). VERIFY-DON'T-ASSUME flipped the expected bottleneck: synthesis is NOT the 3B limit; the crux is EXECUTION-HARNESSING (running an arbitrary model test in each repo's env — django needs settings/app-registry). This is a realistic-DEPLOYMENT-path capability signal, NOT a slice-rate lift (the 5/8 slice already grades on gold tests). | (a) traceback→fix wiring on a real failing test (Docker); (b) gold-free repro-test SELECTOR = a meaty focused build (per-repo test-env harnessing to run model tests vs orig/gold) — deferred: realistic-path demo, not a convergence-number mover |
| 7 | **Long-horizon tasks (bootstrap→ship)** | probed | Foundry stood up + ship-log live (#8). `foundry_stats_cli`: **SHIP=True** — the harness produces a runnable single-file CLI that outputs correctly on 2 CLI cases. CORRECTION (Tenet 3): the earlier "SHIP=False" + "best-of-6 0/6" were BOTH **probe path bugs** (relative script path + `cwd` → script-not-found → empty stdout), NOT a model/harness capability gap — gemma's CLI code was correct all along (suspect-harness-first, 3rd bug this arc after localization + multi-file candidate_files). So the harness DOES ship runnable simple programs. MULTI-FILE (2-file lib+CLI) MEASURED: lib builds+oracle-passes, but the CLI fails cross-module COORDINATION — candidates make VARIED genuine errors (returns-string-treated-as-dict; `import stats` wrong module; str args passed as ints) even WITH the lib SOURCE in context + best-of-6 (all verified genuine, not probe bugs). So multi-file COORDINATION is a real 3B gap (ship-gated SELECTION insufficient). Ship-gated REPAIR also FAILED (0/4 iters): even fed `ModuleNotFoundError: No module named 'stats'`, gemma keeps writing `import stats` (not `from statslib import stats`) — repair-resistant on the import (partly my ambiguous "import stats from statslib" phrasing, partly genuine 3B weakness; verified real, lib imports fine). CONCLUSION: multi-file COORDINATION (imports/interfaces) is a real fragile gap for the 3B — selection AND repair insufficient. REAL LEVER (two-plane, on-doctrine, NOT more prompting): STRUCTURED multi-file build — deterministic plane writes the imports/interface wiring, model fills only logic bodies. Foundry MAPPED (single-file ships; multi-file coordination gap). | build the STRUCTURED multi-file scaffold (deterministic import/interface wiring + model fills bodies). RESEARCH (Aider, 2026-07-02): strong models coordinate multi-file via a tree-sitter REPO-MAP (concise signatures) + graph-ranked relevance + selective-edit + model planning — but I MEASURED the 3B can't coordinate even given full lib source, so DON'T rely on model-coordination; jaros-code's adaptation = deterministic wiring FROM the repo-map's concise signatures (reuse harness/repo_map.py) + model fills bodies. **MECHANISM VALIDATED 2026-07-02:** structured 2-file build (lib via build_from_intent + DETERMINISTIC CLI wiring) SHIPS — assembled tool runs correctly on both CLI cases, where free-form/repair generation failed 0/N. So the two-plane split cracks multi-file coordination. CAVEAT: wiring was TEMPLATED for this entry (not yet derived generally from repo_map); the real build = generalize wiring-synthesis from repo_map signatures. (Also: build_from_intent's lib-oracle FLAKED False while the code was correct — a separate oracle-noise item.) **PRODUCTIONIZED + VALIDATED END-TO-END 2026-07-02:** synthesize_cli committed (harness/cli_wrapper.py, EXT-035 REQ-1, 5 offline tests, f6ca3d1); the FULL structured build (build_from_intent lib bodies + committed synthesize_cli wiring → assemble → run) SHIPS the 2-file tool (both CLI cases correct, gated on the RUN). So multi-file coordination for the lib+CLI-wrapper pattern is CRACKED via the two-plane structured build. **ASSEMBLE+SHIP-GATE PRODUCTIONIZED 2026-07-02:** EXT-035 TASK-2 committed (`b89379c`, harness/foundry.py::assemble_and_ship + ShipResult, offline tests, gated on the RUN not the flaky build-oracle) — the full structured multi-file build is now a reusable, tested capability. **STEERING CORRECTION 2026-07-02 (measurement-first, Tenet-3 record-fix):** a neutral module-to-module coordination probe (mf_coord_probe.py; mathlib.mean fixture + model writes report.py; import syntax NOT dictated) measured free-form gemma SHIPS lib-to-lib coordination on the FIRST candidate at temp=0 — it DERIVES `from mathlib import mean` (imports_dep=True) and does NOT reimplement mean (verified from the captured code), and the two-plane arm also ships. So the earlier "multi-file COORDINATION is a real 3B gap" over-attributed: pure lib-to-lib IMPORT coordination is NOT the gap — the statslib+CLI botch was the CLI/argv-marshalling layer (str-vs-int, __main__ plumbing) + ambiguous phrasing, which the deterministic CLI-wrapper (REQ-1/2) correctly removes. THEREFORE a generalized import-header injector (mooted "REQ-3") is NOT built — no measured gap justifies it (would be speculative over-engineering vs Tenet-1). CAVEAT: n=1 simple single-function dep at temp=0; harder coordination (multiple deps, class interfaces, ambiguous names) unmeasured. | Foundry single-file + CLI-wrap + lib-to-lib-import classes now MAPPED (all ship). Next real Foundry lever must target a MEASURED gap: (i) a HARDER coordination case (multi-dep / class-interface / ambiguously-named dep) to find where free-form actually breaks, or (ii) a bigger bootstrap→ship project; else SWITCH axis (anti-rut) to #2 SWE-bench slice-growth (active-hours/WSL) or #6 shadow-mode (owner-gated). **HARDER-COORD PROBE 2026-07-02 (mf_coord_hard.py, INCONCLUSIVE — honest):** H1 multi-dep (import from 2 modules) — model DID coordinate (imported), failures were a downstream logic slip (doubled `%`: my fixture `pct()` already appends `%`, a fiddly-spec probe trap) not coordination. H2 class-interface — my `coordinates=True` was a FALSE POSITIVE (regex matched a LOCALLY-REDEFINED class): the model REIMPLEMENTED `Accumulator` instead of importing it, and botched the reimpl (attr/method name collision → `'int' not callable`). So NOT a clean import boundary; the real signal worth chasing = **small model REINVENTS a provided component instead of reusing it** (a reuse gap, not an import-syntax gap) — a candidate two-plane lever (inject `from accumulator import Accumulator` + instruct reuse). NEEDS a clean re-probe (fix coord-detection to check the IMPORT; drop the %-doubling spec trap) before naming a lever. **CLEAN RE-PROBE DONE 2026-07-02 (reuse_reprobe.py, task #58) — reuse is COMPETENT; earlier alarms were BOTH probe artifacts (verify-don't-assume x3):** function reuse 6/6 (imports `from statlib import mean` + uses correctly, 0 reimplements); class reuse — gemma imports+instantiates+uses Accumulator CORRECTLY (logic perfect) but occasionally GUESSES THE WRONG MODULE NAME (`from module_accumulator import` vs `accumulator`), which the strict regex miscounted as 0/6 (and the earlier "reimplements Accumulator" was a different prompt without "do NOT reimplement"). So the reuse gap is NOT reinvent-vs-reuse and NOT can't-import — it's NARROW occasional MODULE-NAME hallucination, exactly what the deterministic plane already injects for the CLI-wrapper. CONFIRMS the earlier no-speculative-REQ-3 call: model mostly gets imports right; a general import-injector is a marginal low-value build. Reuse axis CLOSED honestly. **3-FILE LONG-HORIZON PROBE 2026-07-02 (the biggest unmeasured dimension):** built mathops→calc→cli with tonight's committed machinery (build_from_intent ×2 + synthesize_cli + run-gate). SHIP=True (runs correctly on both cases) BUT verify-don't-assume caught it HOLLOW — `calc_imports_mathops=False`: calc REIMPLEMENTED the ops, mathops orphaned (not genuine coordination). ROOT CAUSE (verified, intent_loop.py:126): build_from_intent's `_run_oracle` runs each module's oracle in an ISOLATED temp dir with ONLY that module → an importing module fails its oracle (ImportError) → the loop iterates to a self-contained reimplementation. HARNESS gap, not a model limit. LEVER LANDED: EXT-008 REQ-4 (`cbaa284`) — deps threaded into the build + oracle temp dirs (`deps` param), so a module CAN import siblings + pass its oracle (offline-tested). BUT the deps-enabled 3-file re-run STILL shows calc_imports_mathops=False (byte-identical calc): REQ-4 is NECESSARY BUT NOT SUFFICIENT — at temp=0 gemma writes a SELF-CONTAINED calc that passes its oracle on iter 0, so the loop never NEEDS to import trivially-reimplementable add/sub/mul. REQ-4 removes the blocker; it doesn't FORCE coordination for trivial deps (the tool still ships correctly — just uncoordinated). Genuine coordination needs a NON-TRIVIAL dep the model can't reliably reimplement (then self-contained fails the oracle and, with deps available, the loop recovers by importing) — probing that next to validate REQ-4's actual value. **NON-TRIVIAL-DEP RESULT 2026-07-02 (codec shift-cipher + packer, deps supplied): imports_codec=False, oracle_pass=False** — packer neither imported codec nor reimplemented the cipher (referenced the symbol without emitting the import → fails). FULL PICTURE across tonight's probes: import-emission reliability DEGRADES with name-commonness — mathlib.mean imported ✓ (6/6), Accumulator imported but WRONG module name, codec.encode NOT imported (NameError). So multi-module coordination in build_from_intent is MODEL-CHOICE-LIMITED (inconsistent import-emission); REQ-4 infra is necessary but insufficient. **REVISED LEVER (measurement-backed, was earlier called 'marginal'): a DETERMINISTIC import-header injector** — generalize synthesize_cli so the deterministic plane emits the correct `from <mod> import <sym>` for known deps the model's code references (stripping any wrong model-emitted import), model fills only logic. Tonight's data (2/3 dep types fail import-emission) justifies it. **MILESTONE 2026-07-02 — genuine multi-component coordination ACHIEVED (import-resolver built + delivers):** built the import-resolver after all (EXT-035 REQ-3, commits 6e5c48c + 89d5a29): `harness/import_wiring.py::resolve_imports` injects BOTH `from <stem> import <name>` (bare-name refs) AND `import <stem>` (qualified `<stem>.attr` refs) for a supplied dep's symbols, wired into build_from_intent's `deps` path. PAYOFF MEASURED: the codec(cipher)+packer 3-file build now ships GENUINE coordination — packer.py = `import codec` (deterministic-plane-injected) + the model's own correct `codec.encode(item)` logic → `imports_codec=True, oracle_pass=True, GENUINE_COORD=True` (verified, not a probe artifact — hand-checked HI|j==HI|j). So the two-plane split DELIVERS multi-module coordination for a NON-TRIVIAL dep: the model writes the logic (it CAN coordinate — the earlier misses were the missing import line, a deterministic-plane job), the deterministic plane resolves the imports. HONEST SCOPE: proven on the codec+packer case (module-qualified usage). Breadth: the trivial-arithmetic 3-file case (mathops→calc→cli) may still self-contain (model inlines a+b rather than referencing mathops → nothing to resolve) — that's a model-choice, not an import gap. FLAG: build_from_intent oracle flakes False on correct code (reliability follow-up). **SCALE TEST 2026-07-02 (4-module, `.jaros-data/foundry/multifile4_probe.py`): coordination SCALES to 4 modules** — codec←packer←report←cli, packer_imports_codec=True + report_imports_packer=True + assembled tool runs correctly on both ship cases (`SHIP=True, GENUINE_CHAIN_COORD=True`, 100s). So the two-plane structured build holds past 2-3 modules. **BUT surfaced a real SHIP-GATE GAP (verify-don't-assume): it shipped despite codec FAILING its own oracle** — the model wrote a correct `encode` but OMITTED `decode` entirely (codec oracle=False), and the CLI ship-cases (encode-path only) never exercised the missing function, so run-gate passed on an INCOMPLETE module. LEVER (candidate fill, analog of #3/#4): the Foundry ship-gate should heed per-module `oracle_pass`. **FILLED 2026-07-02 (EXT-035 REQ-4, `2f2bf4f`): `assemble_and_ship` now takes `module_oracles` — any oracle-failed module → `ship=False` + `incomplete_modules` listed** (an incomplete build can't cleanly ship, matching CC; +3 tests, suite 1130, backward-compatible when omitted). | 4-module coord SCALES ✅; ship-gate completeness ✅ FILLED — both this session |
| 8 | **Repo-scale context** | lever-named | generic context injection measured **net-negative** (do not repeat); precise dep-signature retrieval ~parity | semantic retrieval plane (§5B, PRECISE only) + program-analysis fact-sources (§5C) |
| 9 | **git / shell tool breadth** | probed | deterministic tools exist (fs.read/list/write, shell.exec, grep, apply_patch, code.search_replace); breadth vs CC unmeasured | Gap-list vs CC's tool surface → fill by frequency |
| 10 | **Interactivity / latency** | probed | Jetson gemma p50/p95 (small-n): navigate 0.6/0.6s (target<2 ✅), edit 4.4/5.0s (target<30 ✅), fix 5.9/13.5s max16 (target<90 ✅), build-module 64/82s (full generative build, no target). Latency is NOT a bottleneck at this scale. | widen n; capture per-model (qwen/reasoner slower); track as sizes grow |
| 11 | **Robustness / recovery** | probed | test-gate + validate() gates + process-tree-kill guards; no held-out robustness number | error-recovery slice in daily-driver suite |

## Cross-cutting measured walls (dated bookmarks, never conclusions)

- **wall(2026-07-01) — hard multi-step-repo algorithm synthesis** for the 2–4B Jetson-fit roster. Evidence: pass@k 0/7 (`9856d52`), decomposition 0/8 (`ff7726f`), maximal-help 0/6 (`5006e42`), decorrelated-reasoner 0/6, collaboration 0/6, experiment-loop 0/6; cell #35 un-throttled qwen3+repair **1/2 NEUTRAL** (`baseline-pursuit`, task #35 — task2's 3-function running-median all fail). **Revisit** on: any new Jetson-fit reasoning-distilled model (L6), a LoRA specialist (L7), a reduction library (L5), or the comprehension-vs-generation probe flipping (L3). NOT yet L8 (distillation untried on this class).

## Scoreboard #3 — ROUTED-SYSTEM TRIPLE, SECOND class (2026-07-02): fix/edit/build, +0 headroom AGAIN

Extended the triple to a NON-function-gen class — the daily-driver suite's 6 fix + 2 edit + 2 build tasks (the
test_cmd/fix_loop path, which DOES call the model) (`.jaros-data/dd_triple.py` + restore-safe `dd_triple_run.sh`; runs
LOCALLY, no WSL). Result: **gemma 10/10, qwen 10/10 on the CODE tasks — PERFECTLY CORRELATED (identical per-task) →
routed = best-single = oracle, decorrelated headroom = +0.** So across BOTH measured classes the roster shows ZERO
decorrelation value: function-gen (qwen strictly dominates gemma) and fix/edit/build (gemma ≡ qwen). **HONEST
SYSTEM-LEVEL CONCLUSION: the multi-model roster does not pay via within-class decorrelation on any class jaros-code can
currently measure** — the router is correct but adds nothing over serving the single best model. Its only remaining
value hypothesis is class-COVERAGE (route a class one model wins to that model), which needs a class where models
genuinely SPLIT — neither measured class shows one. **★ RECORD CORRECTION (Tenet 3, suspect-harness-first, same tick):
the 1 navigate task (nav_callers_of_load_config) initially showed "both miss" — that was a MEASUREMENT ARTIFACT, not a
gap.** `run_daily`'s `answer_fn` defaults to an empty stub (`_default_answer_fn` returns "") — the navigate/ops
answer-oracle tasks are NEVER asked the model unless a caller injects a real answer_fn, and my dd_triple.py (like every
un-injected caller) didn't → empty answer → guaranteed fail. Diagnostic: asked gemma the navigate question DIRECTLY →
it answers `start\nreload` correctly (check_answer=True). So gemma actually solves 11/11; the daily-driver suite is
FULLY SATURATED for the roster (both small models ace every task) — even stronger evidence it can't discriminate models.
REAL harness gap surfaced: the primary parity instrument (daily-driver) has NO production answer_fn wired, so its
answer-type tasks (navigate/ops) are silently untested in any real run — a wiring gap to fix in #51. NEXT (honest
lever, NOT roster grinding — no decorrelation to harvest): (i) grow the daily-driver to HARDER tasks that actually split
the models + wire a real model answer_fn so answer-tasks are exercised (feeds #51 + #44), (ii) the model-split evidence
must come from a harder bar since every current class saturates or is single-model-dominated.

### Scoreboard #1 — DAILY-DRIVER parity headline RE-MEASURED after category fills (2026-07-03)

After filling multi-file (TASK-4) + refactor (TASK-5), the suite is 15 tasks / 6 of 8 weighted categories
(85/100 weight). Full gemma-default scorecard (`.jaros-data/dd_full_scorecard.py`): **WEIGHTED HEADLINE 0.941
(14/15 raw)** — edit 2/2, fix 6/6, multi-file 2/2, refactor 2/2, navigate 1/1 (now genuinely tested via a wired
answer_fn), build-module 1/2. The ONLY miss is one build-module task — a GENERATIVE-VARIANCE flake (build_from_intent
is from-scratch generation, higher variance; gemma solved BOTH build-module tasks in the earlier dd_triple run), NOT a
regression. HONEST CAVEATS: (1) this 94% is over EASY tasks — the suite still largely saturates for the roster (both
small models ~ace it, per scoreboard #3); a high number here reflects task easiness, not CC-parity on hard work — the
external hard bar (SWE-bench ~13%) remains the true parity gap. (2) UPDATE 2026-07-03: write-tests FILLED (TASK-6,
`b581e3a`, mutation-oracle category — model writes tests, graded by killing seeded mutants; a NEW capability, not
wiring; live gemma 1/2, oracle discriminates + degenerate assert-True→unsolved) → coverage now 95/100 (17 tasks). And
ops FILLED (TASK-7, `3e143d5`, model produces a config artifact graded by check_state; live gemma 2/2 .gitignore +
setup.cfg; wrong/empty→unsolved) → **ALL 8 declared categories now populated = 100/100 weighted coverage** (19 tasks;
4 categories filled this session: multi-file, refactor, write-tests, ops). (3) build-module variance means single-run category rates are noisy;
a multi-seed average would tighten them. This is the instrument's honest current output — useful as a REGRESSION guard
and to measure future harder-task additions, not as a parity-achieved claim.

### ROUTER VERIFIED CORRECT (2026-07-02) — closes the "should we rewire routing?" question

DIAGNOSE (read-only, live tally): the deterministic tally-argmax already routes `standalone-fn-gen → qwen2.5-coder-3b`
(matches the measured 36>32 win), `hard-multi-step-repo → qwen3-4b-thinking` (specialist), and `single-file-repair →
gemma` (a genuine TIE — both 10/10 on daily-driver fix; the tally is accuracy-only so the tie breaks to the heritage
default). So the router already sends the class qwen WINS to qwen — there is NO wasted-dominance bug, nothing to rewire.
The only uncaptured signal is qwen's ~18% latency edge on the fix tie (tally has no latency term) — a marginal,
judgment-call optimization (route fix→qwen for speed) that trades against keeping-qwen-served/swap cost, NOT a defect.
CONCLUSION: the roster-value arc is fully closed and the routing is correct as-is. This ENDS the measurement axis —
switch to a capability/instrument axis (anti-rut).

### EFFICIENCY TRIPLE MEASURED (2026-07-02, scoreboard #4) — the roster's last hypothesis FAILS too

Measured qwen per-task daily-driver latency (`dd_latency_qwen.sh`, restore-safe; gemma from `dd_latency.out`).
Both solve 11/11 (equal accuracy), so routed(gemma-default) escalates ZERO times → routed latency = gemma latency.
Result — **TOTAL wall-time over the 11 tasks: gemma 180.8s vs qwen 147.5s → qwen is ~18% FASTER**, and the direction
holds even on the low-variance non-build tasks (gemma 52.5s vs qwen 43.0s; qwen wins fix_merge_intervals 8.8 vs 16.0,
build_word_freq 14.3 vs 43.9 — qwen converges in FEWER fix_loop iterations despite being the bigger per-token 3B).
**So the roster's LAST value hypothesis (cheap-gemma-default is faster) is MEASURED-NEGATIVE: gemma is neither more
accurate NOR faster than qwen on the measured workload.** COMPLETE honest roster-value verdict across all instruments:
qwen-coder-3b weakly DOMINATES gemma on BOTH accuracy (#3, +0 decorrelation ×2 classes) AND latency (#4) on every class
jaros-code can currently measure → **"just serve qwen-coder-3b" is the honest efficient frontier for the coding
workload**; the gemma-default multi-model roster is not paying its complexity/swap cost by any measured evidence.
CAVEATS (no overclaim): single run, build-module tasks are high-variance (iterative); per-TOKEN gemma-2B is faster, qwen
wins WALL-TIME via fewer iterations. The ONE surviving roster rationale is the ORIGINAL 2026-06-28 pivot basis —
specialist COVERAGE of the HARD class (route tasks BOTH gemma AND qwen-coder fail to the qwen3-4b-THINKING reasoner):
that is coverage of a class the coder can't do, NOT the gemma-default efficiency story (now dead). Honest steer: the
multi-model layer's justified scope shrinks to "serve qwen-coder for code; escalate to the reasoner only for the
measured hard-reasoning class" — gemma-as-default earns its slot only if a future class shows it winning (none yet).
This CLOSES the roster-value axis (accuracy +0 ×2, latency negative) → SWITCH AXES per anti-rut.

### SYNTHESIS of the #3 arc (2026-07-02) — the roster's value is EFFICIENCY, not accuracy (and it's unmeasured)

Two classes now measured, both +0 decorrelated headroom, with qwen weakly dominating (function-gen) or tying (fix/edit).
The honest, fully-reasoned conclusion — carefully NOT overclaimed as "kill the roster":
- **On ACCURACY, the multi-model roster adds nothing measurable.** qwen ≥ gemma on every class tested, so best-single
  (just serve qwen) = routed = oracle. There is no accuracy-decorrelation to harvest on the coding workload to date.
- **The roster's ONLY remaining value hypothesis is EFFICIENCY** — serve the cheaper/faster 2B gemma for the many tasks
  it already handles (daily-driver: gemma solves 11/11) and escalate to the 3B qwen only where gemma fails (hard class,
  e.g. SWE-bench where gemma≈0 and qwen resolves some). That value, IF it exists, shows up on scoreboard **#4 (latency)
  and #5 (amortization)** — NOT on the #3 accuracy triple — and must be weighed against the **single-Jetson model-SWAP
  cost** (only one model served at a time → each route-switch pays a ~10s reload; routing is not free like on a
  multi-GPU host). Whether cheap-default+escalate nets POSITIVE after swap cost is **UNMEASURED**.
- So the honest steering: STOP trying to prove roster value via accuracy decorrelation (measured +0 twice — that axis is
  answered). The open, high-value question is the EFFICIENCY triple: does routing (gemma-default → qwen-on-failure) beat
  always-serve-qwen on latency/cost at EQUAL accuracy, net of swap overhead? That's the measurement that either
  justifies the multi-model architecture or honestly points to "a coding harness may only need the single best coder."
  This does NOT contradict the owner's multi-model pivot (2026-06-28), which was driven by the HARD class (route what
  gemma can't do to a specialist) — it sharpens it: the specialist-routing pays on COVERAGE of the hard class, while
  within-class decorrelation on easy classes does not. Feeds #44 (admission by marginal coverage) + #4/#5 instruments.

## Scoreboard #3 — ROUTED-SYSTEM TRIPLE, first measurement (2026-07-02, intent honest-headline metric)

The intent + external-review make the **routed vs best-single vs oracle** triple the honest headline (commitment 3):
*"routed ≤ best-single means the roster is not paying and the router is the bottleneck."* MEASURED for the first time
(`.jaros-data/routed_triple.py`, per-problem HumanEval[:40], gemma vs qwen-coder-3b): **gemma 32/40, qwen 36/40 →
best-single = ROUTED (class→qwen) = ORACLE(union) = 36/40, decorrelated headroom = +0.** qwen-coder-3b STRICTLY
DOMINATES gemma on function-gen (solves all of gemma's + 4 more; gemma solves ZERO qwen misses). **HONEST FINDING:
the multi-model ROSTER IS NOT PAYING on function-gen** — the router correctly picks the class winner, but there is no
decorrelation to harvest, so the roster adds nothing over just serving qwen-coder-3b for this class. The router is NOT
the bottleneck here; the roster is redundant on this class. OPEN QUESTION (the real lever for multi-model value): is
there ANY class where oracle > best-single (models decorrelate → routing/ensembling pays)? Until such a class is
measured, the multi-model roster's cost is UNJUSTIFIED by evidence on the classes tested — an honest gap, per the intent's
guard against the system-level no-ceiling crutch. NEXT: measure the triple on a class-DIVERSE bar (fix/edit/multi-file,
where gemma's co-adaptation might win some) to find where — if anywhere — the roster earns its cost.

## write-tests capability CHARACTERIZED (2026-07-03, offline probe) — 75%, misses are genuine model errors

Offline diagnostic (`.jaros-data/writetests_probe.py`, gemma, 8 varied functions, mutation-graded): the NEW write-tests
capability (TASK-6) is **6/8 = 75%** — passes on reference AND kills the mutant for is_even/max_of/reverse/factorial/
gcd/word_count; misses is_palindrome + clamp. DIAGNOSED both (suspect-harness-first, then VERIFIED — honest correction):
NOT a harness gap. The generated tests are complete (not truncated) and well-structured, but contain a GENUINE
model-reasoning error — e.g. gemma asserts `clamp(-5, -10, -1) == -10`, but -5 is WITHIN [-10,-1] so clamp correctly
returns -5; gemma's buggy assertion fails on the reference code, and the mutation oracle CORRECTLY scores it unsolved
(part i: tests must pass on the reference). So the oracle works exactly as intended (rejects buggy tests), and 75% is an
honest capability level; the 25% misses are real model test-assertion errors, not harness. PLAUSIBLE LEVER (queued, not
built — uncertain value): a test-gen SELF-REPAIR loop — when generated tests fail on the reference, feed the actual-vs-
expected failure back and ask the model to fix the assertion (the concrete output `-5` vs asserted `-10` is a strong
hint; might lift 75%→higher on this exact error class). Worth a focused build, not a blind 02:xx attempt.

## Research-derived lever (plateau-exit 2026-07-03) — the SLM-SWE-bench base is a 7B CODER (roster-growth candidate)

At a genuine plateau on internal levers (roster-value closed, parity categories 95% filled, hard-class reasoning
measured-blocked for the 3B), did the owner-directed external-research move. Findings (arXiv, July-2026 web):
- **Agentless (2407.01489)** — localize→repair→validate with NO agentic decisions — is EXACTLY jaros-code's
  `swebench_live.py` pipeline. Approach validated by the literature.
- **"Smaller/mid models gain MOST from localization improvements"** — matches jaros-code's #1 measured SWE-bench win
  (localization 2/8→4/8). Confirms localization is THE small-model lever. (But jaros-code's residual misses are already
  correctly-localized + applied-but-wrong-LOGIC → more localization won't move them; the residual is reasoning.)
- **SWE-Protégé (2602.22124): 42.4% Pass@1 SLM SOTA** by lightly post-training **Qwen2.5-Coder-7B** + SPARSE expert
  collaboration (+25.4% over prior SLM SOTA). KEY: the effective SLM-SWE-bench BASE is a **7B coder**, not a 3B; the
  "expert collaboration" maps to jaros-code's LOCAL reasoner-escalation (qwen3-4b-thinking already in roster).
**QUEUED LEVER (highest-value roster-growth candidate, for ACTIVE hours + careful Jetson setup):** admit
**Qwen2.5-Coder-7B** to the roster (the proven SLM-SWE-bench base; fits Jetson best-first ~5-6GB q) and test whether it
resolves hard-class misses the 3B can't. This is the SYSTEM-level no-ceiling path the intent endorses (a stronger
Jetson-fitting model, cloud still forbidden). Supersedes task #42 (Phi-4-mini) as the better roster-growth target for
the HARD class. CAVEATS (no overclaim): (i) 7B models are finicky on the Jetson (STATE: deepseek-7b "serving desyncs
manager") — needs careful serving; (ii) SWE-Protégé's gains also need light POST-TRAINING (LoRA measured-null for us at
1.5-3B, but a 7B base may respond differently — revisit trigger for GAP-1); (iii) the sparse-expert part needs the
expert to be genuinely stronger — our only local "expert" is the 4B reasoner (measured low-EV), so the collaboration
gain may not transfer without the 7B base first. Net: admit + measure the 7B coder BEFORE any collaboration/training
work. Sources: arxiv.org/abs/2407.01489, arxiv.org/html/2602.22124v1.

## 7B ADMITTED as a routed complex-build specialist — narrow, measured (2026-07-03, EXT-021)

Owner greenlit "proceed with 7B if it fits" — it fits (ctx=4096: 5.3GB used / 2.0GB free, no OOM, ~7 tok/s).
Matched head-to-head, gemma-4-e2b vs Qwen2.5-Coder-7B, on 3 complex sentence→system BUILD tasks
(`harness/system_builder.build_system`): **jobqueue — gemma ships 0/2 runs (fails the py_compile/build gate), 7B
ships 2/2 runs (reproducible positive decorrelation)**; kvstore — both ship; pipeline — both ship (gemma reaches
done=True, 7B done=False). **Totals: gemma 2/3 shipped / 1 fully done; 7B 3/3 shipped / 0 fully done.** So the 7B
gives REAL but NARROW marginal coverage (ships a complex system gemma's build gate can't) at ~3x latency + 2x RAM,
never fully-completing. Admitted to the roster catalog + registry as a ROUTED SPECIALIST for the
`complex-system-build-specialist` class ONLY (`.jaros-data/config/models/qwen2.5-coder-7b.json`,
`scripts/jetson_models.json`) — honestly NOT a default (Tenet 3: exactly one earned class, caveats recorded in the
profile). Also fixed a real bug this measurement surfaced: `scripts/jetson_model_manager.py`'s `READY_TIMEOUT_S`
default (120s) was too short for a 7B load and left `_current` desynced — raised to 300s. FOLLOW-UP (not done here,
scoped out): wire actual `build_system` routing to consult this class (needs a separate build_system-routing
analysis) — this change is admission + catalog + profile + the timeout fix only.

## ★★ HOST DEV TOOLBELT — COMPLETE + PROVEN END-TO-END (2026-07-03, EXT-037 REQ-1..5, live demo)

**EXT-037 is CLOSED — the product now turns a PROMPT into a runnable, git-committed, gitignore'd deliverable
end-to-end on the local gemma at $0 (Claude-Code-like).** REQ-5 wiring landed (`5330499`): `/buildsystem` runs a
FINALIZE step (`harness/system_finalize.py`) after a shipped build — every effect dispatched as a Decision through
`Runtime(root=root)` (two-plane: validate()→execute()→hash-chain-log), git-init+commit the source (secret-guarded),
venv-if-deps (offline, stdlib-only builds skip it), NO auto-run of generated code. **Honest live end-to-end proof
(`.jaros-data/e2e_product_demo.py`, real gemma, temp root):** a plain PROMPT → gemma builds `main.py` → runs correctly
(`python main.py <'3 4 5'` → `12`) → finalize writes `.gitignore` + git-commits → `shipped=True | runs_correctly=True |
git_committed=True` (commit `67a1c3d Initial commit: system built by /buildsystem`). **The demo caught a real
integration bug 1466 unit tests missed (Tenet-3 value of an honest e2e): the build's acceptance run creates
`__pycache__/*.pyc`, which `git add -A` staged, and the secret-guard CORRECTLY refused ignored runtime state →
whole commit blocked.** FIX (`d67f2f9`, EXT-037 REQ-5 via Jarify builder→architect): finalize writes a standard
Python `.gitignore` (covering `__pycache__/`, `.venv/`, `*.pyc`, …) BEFORE commit, so artifacts are never staged — the
product-correct behavior (a generated project ships with a sensible .gitignore, like CC). Re-ran the SAME demo → fully
green. Honest scope: `done=False` on the build's stricter internal multi-case done-ness heuristic (the system still
ships, runs correctly on the oracle, and versions cleanly); auto-run of the built system remains deferred (explicit
later opt-in, not this task). Interactive-CLI + eval-loop path-jail wiring still honestly unwired (seam ready).

### CORE (2026-07-03, EXT-037 REQ-1..4) — the pieces beneath REQ-5
The owner-prioritized toolbelt CORE is built + committed + honest (adversarially validated each piece):
- **REQ-1 root-jailed FS writes** (34af5ec mechanism + 00c7185 ENFORCEMENT): `path_jail` (realpath containment,
  rejects ../ + outside-absolute + symlink-escape) now FIRES on the 2 real write paths — the sentence→system
  product (build/modify `_jailed_write`) + the `/agent` edit loop (`Runtime(root=cwd)`). Interactive-CLI + eval loops
  honestly still unwired (seam ready).
- **REQ-2 gated CLI exec** (5ce8b49): shell_exec with timeout+process-tree-kill, destructive/egress denylist
  block-by-default, `allow_unsafe` opt-in (literal True only), cwd=root, output as inert observation.
- **REQ-3 env tools** (4f15528): env.python_detect / venv_create / venv_install / venv_pin — root-jailed venv+reqs,
  installs venv-scoped, global-scope flags gated. Hermetic.
- **REQ-4 git tools** (2f4dd82): git.init/commit/status/log/diff/branch/history_update — a SECRET-GUARD enumerates
  what would actually stage (`git status --porcelain`) and refuses .env/keys/ignored (both explicit + commit-all);
  history-rewrite gated on literal True.
Suite grew ~1385→1454, all green; two-plane throughout (Decision→validate()→execute()→log). REMAINING = **REQ-5
end-to-end wiring** (the orchestrator/`/buildsystem` product path actually WIELDS the toolbelt) — the piece that
makes it live in the product; the tools exist + are safe, the orchestration to use them is the follow-up.

## ★ HOST DEV TOOLBELT — the product must DO development on the host (owner gap, 2026-07-03)

Claude-Code parity requires the prompt→system CLI to not just EMIT code but ACTUALLY DO development on the host, safely.
Recorded as a product gap (tasks #74/#75/#76), state=lever-named (build via the execution-plane tool library, PRIME-001 T1 +
Foundry safety envelope). Sub-capabilities:
- **Safe CLI execution** — run shell/commands with deterministic gates (timeout, tree-kill, output-as-observation, NO external
  egress by default, NO destructive ops).
- **Root-jailed filesystem** — READ freely; CREATE/WRITE/UPDATE confined to the PROJECT ROOT ONLY (path-jail rejecting ../,
  outside-absolute, symlink escape). "Really good at generating CLI Python scripts that read + do limited safeguarded writes."
- **Environment setup** — detect/install Python, create/manage venvs, install+pin deps (into the root venv).
- **Git** — init, add/commit, view+update commit history, branch/status/log/diff; no force-push/history-rewrite w/o gate;
  never commit secrets.
Two-plane throughout: model emits inert Decisions; each effect is a deterministic Jaros tool (validate()+execute()),
hash-chain logged. This is what lets the product build+modify REAL projects (runnable, dependency-complete, version-controlled),
not just source files. Likely its own EXT- spec. Impact HIGH (completes the product); tractable (deterministic tools + a
path-jail; the shell/fs primitives partly exist per design.md). NEXT: scope the spec + build the path-jailed fs + gated exec first.

## ★ MULTI-FILE MODIFICATION MEASURED + a regression-gate HONESTY hole FIXED (2026-07-03, commit 20d2afe)

Single-file modification is saturated (gemma 10/10), so probed the real frontier: MULTI-FILE modify. Batch of 4 diverse
2-file (statlib.py+main.py) changes, INDEPENDENT functional oracle (run the built system, check stdout): **gemma applied
4/4, FUNCTIONALLY-CORRECT 3/4** — it localizes across interdependent modules (edits BOTH lib+CLI), preserves existing
behavior, no regressions on the 3 wins. So the create-vs-edit strength EXTENDS past single-file (gemma edits small 2-file
systems well). **The 1 miss surfaced a Tenet-3 hole:** `add-max` produced a `main.py` with a broken import
(`from statlib import max`, unexported) → main.py stopped importing entirely, YET `modify_system` returned
`applied=True, regressed=[]` (FALSE no-regression). Root cause (suspect-harness-first; first hypothesis "empty baseline"
was WRONG — verify-don't-assume): the surviving `baseline_passing` model-derived checks only `import statlib` — they never
import `main`, and the one check that did failed on the ORIGINAL (bad signature guess). The gate can't catch a break in a
module NO surviving baseline check exercises — esp. the ENTRYPOINT. FIX (EXT-036 REQ-14/TASK-21, Jarify): a DETERMINISTIC
model-independent **import smoke-gate** — `_importable_modules` (`python -c "import <stem>"`, cwd=root, timeout, rc==0) as
`baseline_importable` before the mod, re-checked after assembly; any baseline-importable module that becomes non-importable
→ SAME revert path → `applied=False`. Additive (behavioral gate intact), never-raise, no spurious revert from a
baseline-broken module. Airtight proof = the deterministic import-break UNIT TEST (fake llm); suite 1470 green. A
modification-path HONESTY floor (catches false no-regression a NO-OP/breaking edit could otherwise score as applied).
NEXT: formalize a MULTI-FILE modification suite TIER for a held-out number; difficulty lever stays SIZE (go 3+-file/real-repo).
**★ DONE + LIVE HEADLINE NUMBER (2026-07-03, commit 95c58f1 + measured): the MULTI-FILE tier is formalized (MULTIFILE_SLICE,
5 tasks: 3×2-file + 2×3-file, held-out, independent oracle, architect-verified no fixture passes a no-op). LIVE vs gemma
($0): single-file FIRST_SLICE 10/10 (100%) + multi-file MULTIFILE_SLICE 5/5 (100%) = 15/15 — new_behavior AND no_regression
perfect on every task incl. the hard 3-file mul-op. HONEST READ: the product MODIFIES small systems from a prompt at 100%
on the current suite → the modification instrument is SATURATED at this scale (2-3 file simple CLIs). Per the PRIME-001
ratchet, the next instrument must go HARDER: REAL external repos (git-cloned, django-scale localization + surrounding-code
comprehension) — that is the true CC-parity modification frontier. Modification remains gemma's STRONG half (vs greenfield
CREATION ~83% gemma / ~92% escalating); most real dev = editing, so this is the high-value realistic axis. n=15 single-run,
small simple systems — the caveat that motivates the real-repo push.**
**★ REAL-REPO (PACKAGE-STRUCTURED) MODIFICATION WORKS (2026-07-03, probe): drove modify_system on a 5-file project inside a
real git repo — a `calc/` PACKAGE (calc/__init__.py + calc/ops.py + calc/format.py), main.py entrypoint, README, git-init'd
with an initial commit. One-sentence change (add mul op) -> applied=True, new behavior CONFIRMED, changed EXACTLY calc/ops.py
(+3) + main.py (wired), left __init__/format/README untouched, all 3 runtime checks pass, and `git diff --stat` is CLEAN/minimal.
So subdir module paths, package imports, precise localization + clean diff all HOLD at package scale (_jailed_write creates
subdirs; the import-smoke-gate doesn't false-revert). NEXT rung = a LARGER real EXTERNAL repo (git-clone a PyPI-scale project),
where django-scale localization + surrounding-code comprehension is the true CC-parity frontier.**

## ★★ prompt→system PARITY LIFTED 58%→92% by a HARNESS FIX (2026-07-03, commit 20fe5db) — headline update

Suspect-harness-first on the 5 creation-suite residuals found 4/5 were ONE deterministic planner-coherence bug (gemma
plans a sole module named e.g. `calculator.py` but declares `entrypoint: main.py` → `validate_plan` rejects
"entrypoint not a listed module" → 0 modules built). FIX = `_repair_plan_entrypoint` (REQ-1): single-module case renames the
module to the entrypoint; multi-module incoherence still rejected; oracle untouched. **RE-MEASURED 12-task creation suite:
gemma shipped 4/12→11/12; gemma-alone accept 3/12 (25%)→10/12 (83%); ESCALATING SYSTEM 7/12 (58%)→11/12 (92%).** All 4
planner-bug residuals now ship+accept via gemma; only kv-store-ttl remains (genuine wrong-output). HONEST (Tenet 3):
deterministic coherence repair, oracle-verified real behavior, NOT gaming — the "58% ceiling" was ~85% a harness bug, a
5th "suspect-harness-first" vindication this session. **HEADLINE = 92% escalating / 83% gemma-alone.** CAVEAT: n=1/task.

## Sentence→system PARITY INSTRUMENT built + first honest numbers — 7B lifts it 3× (2026-07-03, EXT-036 REQ-20/21)

Owner directive: "way more CLASSES of development-systems-from-a-sentence + a set of EDIT-a-complex-system-from-a-sentence
too." Built BOTH as held-out, executable-acceptance benchmarks with an INDEPENDENT black-box CLI oracle (only the
sentence reaches the builder; acceptance runs the built `main.py` as a guarded subprocess — un-gameable, architect-verified
never-fabricates-a-pass): `harness/system_suite.py` (CREATION, REQ-20, commits 4a01cbd/9bd0eb7) + `harness/modification_suite.py`
(MODIFICATION, regression-gated, REQ-21, commit ce2a9fe). First slice = 6 creation tasks × (easy/medium/hard).
**MEASURED first numbers (n=1/task, noisy, independent oracle):** CREATION accept — **gemma-alone 1/6 (17%)** [easy .5,
med 0, hard 0] vs **Qwen2.5-Coder-7B 3/6 (50%)** [easy 2/2, med 1/2, hard 0/2]. The 7B accepts a SUPERSET of gemma here,
so the REQ-13 gemma→7B escalation delivers **≈3/6 (50%) — a 3× lift** over gemma-alone while keeping gemma's speed on the
already-shipping common case. This is the first axis where the roster/escalation is MEASURED-valuable (contrast the +0 on
the old easy classes). HONEST: the instrument itself caught + fixed a harness bug first (vague sentences → 0%/inverted →
contract-precise sentences → real numbers; a dishonest LOW rejected, Tenet 3). NEXT: grow classes to stabilize the number;
run the MODIFICATION suite live (gemma + 7B) for the first edit-from-a-sentence number. Per-task JSON in
`.jaros-data/creation_suite_{results,gemma}.json`.

**★ HEADLINE NUMBER = the ROUTED/ESCALATING SYSTEM, not gemma-alone (2026-07-03, owner steer "use the whole harness with routing"):**
Measured the ACTUAL escalating harness (`build_system_escalating`: gemma default → escalate to 7B on ship-failure → restore gemma)
live on the full **12-task** creation suite: **gemma-alone 3/12 (25%) → ESCALATING SYSTEM 7/12 (58%)** — a near-2× lift (the 7B
rescued wordcount/todo-list/reverse-lines/pubsub). This is the honest PRIME-001 scoreboard-#3 figure — REPORT 58% (system), not 25%
(gemma default). Residual 5/12 = genuine reasoning gaps (neither model). Follow-up: escalation triggers on SHIP-failure not
ACCEPT-failure (kv-store-ttl shipped-but-wrong wasn't escalated — a rescue left on the table). Runner `.jaros-data/run_creation_suite_system.py`.

**MODIFICATION suite first number → CREATE-vs-EDIT ASYMMETRY (2026-07-03):** ran the modification suite (5 tasks,
regression-gated, same oracle) live: **gemma accepts 5/5 (100%)** — every edit applied + new behavior + no regression;
VERIFIED real (a no-op modify_fn scores 0.0 — the gate genuinely requires the added behavior). So the honest picture:
the small local model is **weak at greenfield CREATION (gemma 1/6, 7B 3/6) but strong at MODIFICATION of a working
system (gemma 5/5)** — editing is easier (structure given as context, small localized change) AND is the MORE REALISTIC
dev task. No 7B modification arm needed (gemma at 5/5, no headroom). CONVERGENCE READ: gemma-alone is already
near-parity on easy-realistic EDITS; the remaining sentence→system gap is greenfield creation (where the 7B escalation
pays 3×). CAVEAT: n=1/task, 5 simple-to-moderate edits — grow to harder modifications (multi-file, behavior-change) to
find the modification ceiling. Results: `.jaros-data/modification_suite_gemma.json`.

## Steering note — SWE-bench small-model frontier (research-backed, 2026-07-02)

**External research (SWE-bench Lite leaderboards + small-model SWE papers) reframes #2 honestly:** a naive stronger
GENERAL coder does NOT help — **Qwen2.5-Coder-7B = 4.33% on SWE-bench Lite, WORSE than our 3B+harness ~13.3% uncurated.**
The small-model winners are SWE-SPECIALIZED fine-tunes (SWE-AGILE-8B 14.77%, SWE-smith-7B 11.7%, R2E-Gym 11.0%),
all 7-8B trained on SWE trajectories. So **jaros-code's ~13.3% (qwen-coder-3b + our harness, $0) is ALREADY competitive
with the specialized 7-8B SWE frontier** — we are AT the small-model frontier, not behind a tractable harness gap; the
gap to Claude (62.7%) is fundamental small-vs-large, not harness deficiency. CONSEQUENCES for steering: (1) do NOT swap
in a naive general 7B (measured-worse, would regress); (2) the ONLY lever to exceed ~13% is SWE-SPECIALIZATION — either
ADMIT a downloadable SWE-specialist (SWE-smith-7B/R2E-Gym, 7B-4bit fits the Jetson ~4.5GB; thin expected margin +0-2%
since we're already ~13%), or a trajectory-trained specialist (heavier than the 1.5B SFT probed tonight). This VALIDATES
the training axis's DIRECTION (specialization is the lever, not size) while confirming near-term budget is thin. Sources:
swebench.com, pricepertoken SWE-bench-Lite, SWE-AGILE/SWE-smith/SWE-Dev papers.

## Steering note

**Measured 2026-07-01 (daily-driver instrument, live gemma):** the **fix-single-file-to-pass-a-given-failing-test** category is a HARNESS STRENGTH — 9/9 on authored tasks up to moderate algorithmic difficulty (merge-intervals, deep-flatten, dedup-order), because `fix_loop`'s test-gated best-of-N iteration extracts the solution (same mechanism as SWE-bench 5/8). This is NOT a CC-parity claim (authored, single-file, a failing test handed in) — it is a calibration: **authoring more fix-with-test tasks no longer discriminates.**

**UPDATED 2026-07-01 (build-module added + measured):** build-from-intent ALSO passes (Stack, word_frequencies from spec, 11/11 total) — so the strength is broader than "has a failing test": across the **entire single-file daily middle** (edit/fix/build/navigate) up to moderate difficulty, the harness brute-forces correctness (fix_loop iteration + build_from_intent self-testing). **This whole region is a measured STRENGTH and does NOT discriminate vs CC** (both ~100%). Authoring more single-file moderate tasks is a confirmed rut — STOP.

**SHARPENED 2026-07-01 (multi-file measured too):** multi-file cross-file ROOT-CAUSE fixing ALSO works on moderate tasks (multi-caller probe passed, fixed the shared root). So it is not "single-file" that saturates — it is **MODERATE AUTHORED TASKS OF ANY CATEGORY**: the test-gated harness (fix_loop + multi_file_fix + build_from_intent self-testing) brute-forces correctness on anything a determined generate-and-test loop can reach. **Therefore a trustworthy DISCRIMINATING parity number cannot come from authored moderate tasks at all** — authoring more of them (any category) is the rut. Latency #4 is now measured (green). The discriminating parity signal lives ONLY in the hard/real/long-horizon instruments:
- **#2 SWE-bench** — the external hard bar we HAVE (5/8 easy-slice); GROW the slice (8→50) = the tractable discriminating capability number, no owner needed.
- **#7 Foundry** — long-horizon bootstrap→ship; the biggest unmeasured dimension benchmarks can't touch (a real fresh-focus build).
- **#6 shadow-mode** — the owner's REAL Claude Code tasks replayed; the strongest signal, PENDING owner go-ahead.

NEXT concrete step: grow the SWE-bench slice (#2) as the tractable discriminating number, and stand up the Foundry (#7) for long-horizon. Do NOT keep authoring moderate daily-driver tasks (measured non-discriminating). Bootstrap remaining: embedder/LoRA/distill probes (§9.5/6, Jetson-only per [[jaros-code-training-plane]]). Daily-driver suite stays as a fast regression/latency harness + flywheel-capture source, NOT the discriminating parity number.

## ★ NEW FRONTIER (owner directive 2026-07-03) — SENTENCE-TO-SYSTEM (build complex systems from a sentence)

Owner set the next major CC-parity gap: "really really really good at building complex systems from a sentence."
Spec EXT-036 identifies the decomposition (spec-expansion→architecture→interface→ordered-impl→test→integration→
cross-level-repair→scale). MEASURED 2026-07-03 (probes in `.jaros-data/s2s_*.py`):
- **Structural planning WORKS (surprise):** gemma produces coherence-valid plans (module DAG + signatures + entrypoint)
  from a sentence for simple/medium/complex — "a 2-3B can't architect" is FALSE at the structural level.
- **★ END-TO-END SIMPLE WORKS:** sentence "CSV column-stats CLI" → plan (csv_reader←column_stats←cli) → build each
  module → assemble → run → CORRECT per-column min/max/mean (rc=0, honestly validated). A one-sentence spec produced a
  runnable, working multi-module system.
- **2 gaps DISCOVERED + FILLED in the probe:** (i) module generation truncated at low max_tokens → SyntaxError (raise
  budget); (ii) no per-module syntax gate/repair before assembly → cryptic system error (add py_compile gate + bounded
  syntax-repair per module, analog of write-tests repair).
- **NEXT gaps (recorded, EXT-036):** REQ-2 executable acceptance (planner must EMIT a runnable acceptance matching the
  built interface — the blocker to auto-validating medium/complex); REQ-3 per-module oracle (compose write-tests to gate
  each module); then measure the medium/complex BREAK-POINT and REQ-5 cross-level repair + scale past ~4 modules.
STATUS: simple sentence→system PROVEN end-to-end; productionize the pipeline (planner + syntax-gate/repair + executable
acceptance + per-module oracle) then push complexity to find the honest break-point. This is the live convergence axis.

## Small-model MEMORY design — MEASURED (owner directive 2026-07-03, ladder L0→L1)

Owner: "memory must work differently for small models — figure it out, test it." + "maybe a memory AGENT decides
what to store/retrieve." TESTED (`.jaros-data/mem_experiment*.py`), two iterations, HONEST corrections:
- **Hypothesis (structured facts > raw transcript) — REFUTED at short context:** 4 constraint-carrying scenarios,
  RAW transcript 8/8 vs STRUCTURED 7/8. At short context the 2-3B handles the raw transcript FINE. (L0 format probe.)
- **Long-context (12 then 30 distractor facts, task needs 2): RAW-dump 2/2 == MEM-AGENT 2/2, TIE both times.** gemma is
  FAR more context-robust than the "small models can't handle context" assumption — 30 facts didn't break raw recall.
- **Memory-AGENT (L1 decompose: an agent selects relevant facts given the task) WORKS as a mechanism** — picked exactly
  the 2 relevant facts every time — but does NOT beat raw IN-SESSION (raw already works).
DESIGN (measured, not assumed): (1) **in-session short-term** = raw bounded transcript (simple, wins; TASK-1 backbone);
(2) **condensation (REQ-15)** only near the context-window budget (needed less than feared); (3) **the memory-AGENT's
value is CROSS-SESSION + LARGE-SCALE recall (REQ-16)** — where the transcript ISN'T available (persistence) or exceeds
the window — precise selection from a per-repo persistent fact store, NOT because raw is worse in-session. Escalation
ladder applied: don't build the expensive agent-recall where cheap raw works; deploy it exactly where raw structurally
can't (cross-session/scale). Guards the old retrieval-negative regression (inject the few, never a dump).

## Sentence-to-system DIFFICULTY SPECTRUM — MEASURED (2026-07-03, owner's easy/medium/hard emphasis)

Ran the productionized `build_system` (EXT-036) on easy/medium/complex specs (`.jaros-data/s2s_spectrum.py`):
- **easy** (CSV stats): 3 modules, SHIPPED, done=False (2 unmet, incl. a vague "Conceptual check"), 2 repairs, 160s.
- **medium** (URL shortener): **4 modules, SHIPPED**, done=False — unmet = ["no acceptance checklist derived"] (the
  acceptance step produced NO parseable checklist), 0 repairs, 181s.
- **complex** (task queue): 0 modules, FAILED at 13s — broke at the PLAN stage (fast-fail, no build).
HONEST BREAK-POINT: the BUILD/ASSEMBLE pipeline is STRONG — it ships runnable multi-module systems to at least 4
modules. The bottleneck is NOT the build; it's TWO things: (1) **acceptance-checklist DERIVATION is the weak link** —
the small model emits vague/non-executable ("conceptual") checks or fails to produce a parseable checklist at all, so
systems that SHIP (work) still report done=False. This is the highest-leverage next fix (robust executable-acceptance:
filter to runnable assertions, checklist-repair, or a deterministic scaffold). (2) **complex planning fast-fails** —
the plan stage breaks for a genuinely complex spec (diagnose: parse vs validation vs model-incomprehension; likely the
L1-decompose / L6-route-to-7B frontier). NEXT FILLS: robust acceptance-derivation (unblocks done across easy/medium),
then diagnose+attack the complex-plan break. The "done" gate is honest (never false-passes) — it's just pessimistic
because the derived checklist is low-quality; fixing derivation is what turns shipped→done for working systems.

## Sentence-to-system done-ness — post-TASK-6 honest picture (2026-07-03)

TASK-6 (robust executable-acceptance, `060a79a`) FIXED the vague-check bottleneck: derived checks are now filtered to
real executable `assert`s (+ stricter retry + deterministic smoke fallback that genuinely fails a broken system, no
false-pass). Live re-run of the easy CSV spec: shipped=True, done=False, unmet=["multiple entries", "handle empty data
gracefully"] — now REAL executable checks. So the done=False residual is honest + TWO-fold: (1) the built system
genuinely lacks EDGE-CASE completeness (the small model builds a basic version; repair couldn't reason the edge cases)
— the reasoning/completeness frontier (L6 route-to-7B / L7 fine-tune lever); (2) the acceptance derivation is somewhat
OVER-STRICT — it invents edge-case requirements ("handle empty data") the literal spec never asked for, so a
spec-meeting system reports not-done. NET STATE of sentence->system: build SHIPS runnable multi-module systems (to 4
modules), done-ness uses honest executable checks, and the two remaining levers are (a) acceptance-SCOPING (test the
spec's stated requirements, not invented edge cases — a refinement) and (b) model completeness on edge cases (the 7B /
fine-tune frontier). The CREATE path is functionally complete + honest; reaching done RELIABLY on the literal spec is
the acceptance-scoping refinement; reaching done on IMPLIED edge cases is the reasoning-tier (7B) frontier.

## 7B roster lever — precise requirement (2026-07-03, active hours)
The hard/highly-complex tier lever (L6) = **Qwen2.5-Coder-7B** (SWE-Protégé's proven SLM-SWE-bench base). Checked the
Jetson catalog (`.jaros-data/config/models/`): it is NOT present (only gemma-4-e2b, qwen2.5-coder-3b, qwen3-4b-thinking,
deepseek-r1-distill-qwen-1.5b/7b). The existing deepseek-7b is a REASONER (harness-format-incompatible, desyncs the
manager) — not a coder for the sentence->system task. So this lever needs: download the Qwen2.5-Coder-7B GGUF (~5GB q)
to the Jetson + a `models.json` catalog entry + serve + test build_system's complex-plan + edge-case completeness on it
+ restore gemma. Authorized roster-growth (Jetson-fit, $0, cloud-forbidden), but a substantial op with serving-desync
risk — greenlight/timing best from the owner. This is the depth lever on the TRUE parity gap (the reasoning frontier);
the overnight EXT-036 work is breadth. QUEUED for a careful active-hours execution.

## ★★ REAL-SYSTEMS FRONTIER — first honest measurement (owner directive 2026-07-03): FastAPI-from-a-prompt

Owner reframed the bar: build/modify REAL framework systems from a prompt (servers/API frameworks/libraries), AUTOMATICALLY —
not toy stdin/stdout CLIs. FIRST HONEST PROBE (`.jaros-data/real_framework_probe.py`): gave build_system a prompt for a
FastAPI service (/health -> {"status":"ok"}, /add?a,b -> {"sum":a+b}) then INDEPENDENTLY started uvicorn + hit the endpoints
over real HTTP. RESULT — mixed, honestly: (1) ✅ the local gemma GENERATED framework-correct FastAPI code (app object, typed
query params, correct JSON) and it ACTUALLY SERVES real HTTP (200 {"status":"ok"}; 200 {"sum":5}) — a REAL system working
end-to-end at $0. (2) ✗ BUT build_system reported done=True "all acceptance checks pass" as a HOLLOW PASS: the generated
service has no __main__/stdout, so the stdout oracle's model-derived checks were filtered out and it fell back to
`_smoke_checklist` = `import main; assert hasattr(main,'app')` — which passes the instant the module imports, NEVER exercising
an endpoint. So "DONE" meant "it imports", not "the API works" — the code was right by good generation, not by verification.
Tenet-3 gap: for real services the harness can't actually validate behavior. LEVER (task #84, the primary convergence lever
now): a deterministic SERVER/HTTP ACCEPTANCE ORACLE — detect a web service (FastAPI/ASGI, Flask/WSGI), start it on a free
port, poll, HTTP-request the declared endpoints, assert status+JSON, teardown (tree-kill); done=True for a service REQUIRES
the endpoints to actually respond. Frameworks are all installed (flask/fastapi/uvicorn/sqlalchemy/pandas/networkx/pydantic);
venv_install really installs. NEXT after the oracle: wire it into build_system acceptance + modify_system; then real
library systems (pandas/networkx) + larger external repos. This is the honest path to "builds REAL systems from a prompt".

## ★★★ HONEST MILESTONE (2026-07-04, commit 65610a3): a REAL system built from a prompt AND harness-HTTP-verified end-to-end, $0

The server/HTTP acceptance oracle is now WIRED into build_system (EXT-036 REQ-22/TASK-25). Re-ran the FastAPI probe
(`.jaros-data/real_framework_probe.py`) — build_system now reports **done=True note='DONE (web service HTTP-verified:
GET /health, GET /add?a=5&b=3, GET /add?a=100&b=-50)'**: it detected the web service, DERIVED HTTP checks from the prompt,
STARTED the server, HIT the endpoints, and gated done on their real responses. Independent oracle confirms
ACTUALLY_WORKS_over_HTTP=True (/health 200 {status:ok}; /add 200 {sum:5}). So the earlier HOLLOW import-smoke pass is
CLOSED — for a detected web service, done=True now REQUIRES real endpoints responding, and a service that can't be
HTTP-verified reports done=False (never a hollow pass; the broken-app unit-test control proves the gate is real). This is
the first REAL framework system built from a prompt on the local gemma at $0 AND honestly verified by the harness itself —
the exact bar the owner set. Non-web CLI builds are byte-identical (zero regression; creation suite unaffected). NEXT on the
real-systems roadmap: #86 external-dep/DB setup (Qdrant/Cassandra + a datastore acceptance oracle), #85 web-research plane,
#87 repo-comprehension+planning, #89 scratch-script plane, #90 episodic memory, #91 long-horizon coherence (capstone).

## ⚠️ EXTERNAL-AGENT FEEDBACK — encoded as steering discipline (2026-07-04)

A reviewing agent flagged three things; all correct, all now binding:
1. **RESEARCH PLANE = biggest honesty attack surface.** SWE-bench-Live fixes are PUBLIC on GitHub. The eval-leak
   guard must HARD-DISABLE research during any scored run (global switch forced by the eval harness) AND the
   allow-list must categorically EXCLUDE every eval target (repos/issues/PRs + held-out sources) via a deterministic
   denylist checked before each fetch — provable, not trust-based; one leaked fetch voids the number + credibility.
   ALSO: fetched docs are UNTRUSTED INPUT — quarantine page content as data, fence/label it, strip imperative
   authority; the planner NEVER obeys instructions embedded in a fetched page (doc-page prompt-injection is live now
   that research feeds the planner). Both are HARD acceptance criteria on the web-research spec (task #92 gates #85).
2. **DON'T let the headline migrate to the friendliest instrument.** The self-authored creation/modification suites
   (creation ~83/92%, modification 15/15) SATURATE fast and are what the agent tunes against — they are the
   FLOOR/regression-guard, NOT the headline. The credible, UN-GAMEABLE headline is the **shadow-mode parity log**
   (the owner's real Claude Code tasks replayed against jcode — nobody can game it) + the **amortization ratio**
   (intent instruments 5 & 6). These did NOT land in this batch — landing/refreshing them is HIGH priority (task
   #93); until they do, report the authored-suite numbers as FLOOR, never as parity proof.
3. **BREADTH BRAKE.** Planes (a)-(g) opened a large surface fast. The commits show COMPLETED verified slices per
   plane (not seven half-built things), so this is a caution, not a defect — but impact×tractability ranking here is
   the brake, and the **long-horizon coherence instrument (#91, the north-star) PULLS the roadmap**: build the
   minimal coherence instrument SOON so it ranks which planes matter, rather than adding planes speculatively.

## ★ NORTH-STAR: first LIVE coherence number (2026-07-04) — SATURATED at minute-scale (a FLOOR, not parity)

Ran the coherence instrument (690b6a6) LIVE against build_system(gemma): 3 multi-requirement tasks, each requirement
independently oracle-verified. RESULT: **mean_coherence=1.00, fully_coherent_rate=1.00** — stats-cli 4/4, text-tools-cli
5/5, ledger-cli 5/5 (builds 94-203s). HONEST READ (no spin — this is the north-star): at 4-5 requirements / single-file
CLI / minute-scale, the SINGLE-PASS build_system already stays FULLY coherent — it does NOT drop requirements. So the
instrument is SATURATED here = a FLOOR, not parity, and it does NOT yet justify the governed decompose->task->alignment-gate
CAPSTONE (no MEASURED coherence failure to fix — building it now would be speculative, against the breadth brake). DISCIPLINE
(measure-first): RATCHET the instrument until it BREAKS — many more requirements (8-12+), INTERDEPENDENT requirements,
MULTI-FILE systems, longer horizon — the break is what justifies + directs the capstone. Probing a harder task next.

## ★ NORTH-STAR BREAK DIAGNOSED (2026-07-04) → the governed CAPSTONE is now justified + directed

Ratcheted the coherence instrument: an 11-requirement INTERDEPENDENT kvdb-cli broke build_system at **10/11=0.91**.
DIAGNOSED (suspect-harness-first, verify-don't-assume): the dropped requirement is **`incr`** — the single-pass build
implements 10 of 11 commands and OMITS the incr branch entirely (`incr n` -> falls through to `usage`). It is a DROPPED
requirement, NOT a wrong impl → decomposition/re-grounding is the correct lever. SECOND finding (Tenet-3): build_system
reported **done=True "all acceptance checks pass" DESPITE the drop**, because its SELF-DERIVED acceptance checklist shares
the code's blind spot (both generated from the same prompt by the same model, so the dropped requirement is absent from
BOTH). Only the INDEPENDENT coherence oracle (enumerating all 11 requirements) caught it — mechanism-level proof of the
reviewer's "don't trust self-graded instruments." LEVER (capstone #91): a GOVERNED build path that (1) decomposes the
prompt into an EXPLICIT enumerated requirement list, (2) builds, (3) verifies EACH requirement independently, (4) repairs
any UNMET requirement (feed the full list + the unmet one, regenerate, re-verify ALL so none is re-dropped), done=ALL-met.
Target: lift the kvdb-cli coherence 10/11 -> 11/11. Directed by a real, diagnosed failure — not speculative.

## ★ NORTH-STAR CAPSTONE — honest NEGATIVE after 2 live attempts (2026-07-04): governed path REGRESSES, no lift yet

Attempt 1: build_system_governed live-broke (0 reqs decomposed -> 0/11). Fixed parse (one-array-per-line) + black-box CLI
verify + floor (498209a). Attempt 2 (live, kvdb-cli 11 reqs): parse now works (14 reqs decomposed) BUT the governed final
system scores **8/11 on the independent check — a REGRESSION from single-pass 10/11** (done=False; failed incr/clear/usage).
TWO real defects: (1) the REPAIR LOOP DAMAGES working behavior — chasing incr/keys it broke clear+usage that single-pass had
right; its internal 14-requirement check set (incl. non-behavioral "program_structure"/"data_structure" reqs) is a NOISY
proxy for real coherence, so repair optimizes a wrong target and degrades true behavior. (2) the NO-REGRESS FLOOR FAILED —
8/11 < 10/11 was returned; the floor only handles empty-decompose, it does NOT compare final quality. HONEST VERDICT: the
governed decompose->verify->repair capstone, as built, is NET-NEGATIVE on this task — NOT a lift. SAFETY-CRITICAL FIX: the
floor must return the BETTER of {build_system output, governed-repaired output} on a consistent check set, so governed can
NEVER be worse than single-pass. After that, if governed only ever EQUALS single-pass (no lift), bank it honestly as
floor-safe-but-no-measured-lift (a bookmark, like the training-scoreboard-null finding) — do NOT force/claim a lift that
isn't in the live number. Possible deeper truth: single-pass 10/11 may be near the model's ceiling for this task and the
repair can't reliably improve it (damages ~ as much as it fixes) — an honest negative to accept if it holds.

## ★ NORTH-STAR CAPSTONE — BANKED as an HONEST NEGATIVE (2026-07-04, after 3 live attempts)

build_system_governed (governed decompose->verify->repair for long-horizon coherence) across THREE live attempts on the
11-req kvdb-cli: attempt 1 = 0/11 (decompose parse broken); attempt 2 = 8/11 (parse fixed, but repair DAMAGED working
behavior, regressed below single-pass); attempt 3 (floor active) = 0/11 (broken build, 0 repair rounds, floor did not
reliably hold live). Single-pass build_system = 10/11 throughout. VERDICT: the governed approach as built is NET-NEGATIVE
and UNRELIABLE on the hard multi-requirement class — NEVER a measured lift, and it can produce systems WORSE than
single-pass. Root issues found + fixed along the way (all committed, real): decompose parse for gemma's one-array-per-line
output (498209a); black-box CLI verification vs the model's imagined class-API checks; a no-regress floor that re-verifies
final on-disk state (4706aa3). The instrument + parser + black-box verify + floor are REUSABLE. But the CORE lever
(decompose->repair lifts coherence) is UNPROVEN/negative: gemma's repair damages ~ as much as it fixes, its 14 self-
decomposed requirements are a noisy proxy that doesn't align with true behavior, and single-pass ~10/11 may be near the
model's ceiling for this task. HONEST BOOKMARK (like training-scoreboard-null): revisit with a stronger base, a
deterministic (not model-authored) requirement-check derivation, or a fundamentally different anti-drift mechanism.
DO NOT wire build_system_governed into /buildsystem (it can regress) — single-pass build_system stays the product default.
KEY LESSON REINFORCED: the coherence INSTRUMENT + live re-measure caught a unit-green, architect-approved capstone
regressing 3x — the number is the truth, not the tests. The night's real WIN is the FastAPI real-system HTTP-verification,
NOT this capstone.

## ★ HARDENED coherence instrument — DISCRIMINATES + reveals build-reliability variance (2026-07-04)

Ran the hardened coherence HARD_SLICE (kvdb-cli, taskmgr-cli; 11 interdependent reqs each) live vs single-pass
build_system(gemma): kvdb-cli 0/11 (49s), taskmgr-cli 11/11 (152s). HONEST READ: (1) the instrument now DISCRIMINATES —
it does NOT saturate at 1.0 like the minute-scale FIRST_SLICE (which read 1.00); that was the point of hardening it.
(2) The real signal is BUILD-RELIABILITY VARIANCE: kvdb's 0/11 was a FAST BROKEN build (49s vs 152s), and across runs it
swung 0/11 -> 10/11 -> 8/11; taskmgr hit a clean 11/11. So on hard 11-req interdependent tasks, single-pass build_system is
HIGH-VARIANCE at n=1 — it either mostly-nails it (10-11/11) or fails hard (0/11 broken build), draw-dependent. A single run
is NOT a stable coherence number. NEXT (real instrument improvement the data demands): add an n>1 (median-of-k) option to
run_coherence_suite so the coherence number is STABLE, and separate "build failed entirely" from "dropped a requirement"
in the report. Honest — do NOT headline a single noisy 0/11 or 11/11.

## ★★ COHERENCE FAILURE MODE CORRECTED (2026-07-04, median-of-3) — it's BUILD-RELIABILITY, not dropped-requirements

The n>1 median-of-k measurement (repeats=3) on HARD_SLICE clarifies the earlier noisy n=1 signal: kvdb-cli median=1.0
runs=[11,11,0] build_failed=1 dropped_req=0; taskmgr-cli median=1.0 runs=[11,11,11]. **Median coherence = 1.0 on BOTH hard
11-req tasks — when single-pass build_system SUCCEEDS it nails ALL 11 interdependent requirements.** The variance is NOT
gemma dropping individual requirements (dropped_req=0 across this sample); it's an occasional TOTAL BUILD FAILURE
(build_failure_rate ~17% = 1/6 builds produced nothing runnable -> a 0). **This CORRECTS the capstone premise:** the
governed decompose->repair lever chases DROPPED requirements that mostly don't exist at this scale — which is exactly WHY
it was net-negative (nothing to repair; the repair only damaged working builds). The RIGHT lever the data points to is
BUILD-RELIABILITY: best-of-k builds (build k times, keep the one that passes acceptance) masks the ~17% total-failure rate,
is deterministic (test-gated selection, no model-drift), and directly raises effective coherence — unlike the capstone.
(Caveat: earlier runs DID show occasional partials e.g. 10/11, so both failure modes exist; best-of-k helps BOTH.) This is
the honest convergence: the instrument + median-of-k didn't just measure — they RE-DIAGNOSED the problem and pointed to the
correct, cheaper lever. Next: a best-of-k build wrapper (test-gated selection over k build_system draws).

## ★ BEST-OF-K live: masks TOTAL failures, but SELECTION inherits the sparse self-checklist (2026-07-04, honest nuance)

Live verify build_system_best_of_k(kvdb-cli, k=2, gemma): done=True, attempts_run=1 (EARLY-EXIT), the build passed its OWN
derived acceptance (4/4 checks) — but the INDEPENDENT 11-req check scored 10/11 (missed `usage`). HONEST FINDING: best-of-k
correctly MASKS total build failures (retries a 0-check build), BUT it selects/early-exits on the BUILD'S SELF-DERIVED
acceptance checklist (only 4 checks here), which does NOT cover all 11 independent requirements — so it early-exited on a
build that independently drops `usage`. This is the SAME blind-spot that runs through the whole session: the model's
SELF-derived acceptance is incomplete, so build.done AND best-of-k selection are both blind to requirements the model
never wrote a check for (exactly what the hollow-FastAPI-done and the independent coherence oracle exposed). REFINEMENT
(the honest next lever): score best-of-k attempts against a FULLER / INDEPENDENT requirement set (enumerate requirements +
derive an independent check per requirement — like the coherence instrument), not the model's sparse self-checklist. Then
best-of-k selects the attempt that satisfies the MOST real requirements, not the one that passes its own thin self-test.
best-of-k is UNIT-proven (masks total failures); this live run is the honest caveat that selection quality = acceptance
completeness. THE THROUGH-LINE OF THE NIGHT: independent verification beats self-report, everywhere.

## ★★ SECURITY: generated-code execution is now SCANNED + SANDBOXED in build_system (2026-07-04, owner-directed)

Owner asked: are we checking generated code for quality + gating it to be SECURE to run on this system? Answer was "no/partial" — build_system ran model-generated code as a plain subprocess (full host env incl. secrets, full perms, no scan, no egress control). NOW CLOSED for build_system's acceptance path (fae847c foundation + 39f62d3 wiring, adversarially validated — the architect caught + made us fix a real blanket-egress hole first, Tenet-3 working on the security layer itself):
- **SCAN GATE** (harness/secure_exec.py::scan_code): build_system scans every generated module (DENY_ALL egress) AFTER assemble, BEFORE either acceptance path (CLI or uvicorn) — a build with un-permitted dangerous ops (subprocess/shell, eval/exec, destructive/fs-outside-root, un-allow-listed network egress) is REFUSED (done=False, security field, honest note); the dangerous code is written to disk for inspection but NEVER executed.
- **SANDBOXED execution** (run_sandboxed): acceptance runs generated code with a SCRUBBED env (secrets NOT visible to it — proven by test), POSIX resource caps, timeout+tree-kill, DENY_ALL egress.
- **PER-HOST GATED EGRESS** (EgressPolicy): default-deny + allow-list, FAIL-CLOSED, exact-host match (no substring bypass: evil-pypi.org.attacker.com blocked under allow('pypi.org')) — research/deps get controlled egress, nothing else.
- governed/escalating/best_of_k/modify_system inherit the gate (all call build_system / _run_check).
- **★ 2026-07-04 FOLLOW-UP LANDED (1bb35da, TASK-11, architect-validated):** the two remaining exec sites are now sandboxed too — `server_oracle`'s uvicorn/flask launch and `system_suite._run_cli` both build their subprocess via `secure_exec._scrubbed_env` + POSIX RLIMIT caps (`_run_cli` gets full `run_sandboxed` w/ DENY_ALL egress; the long-running server reuses run_sandboxed's building blocks since the blocking helper can't host a server the caller must poll/kill). `run_sandboxed` gained an optional `stdin` param (sentinel-guarded → byte-identical prior behavior when omitted). Env-scrub proven LIVE at both new sites (host secret invisible to the built CLI AND to a real FastAPI `/secret` endpoint); real FastAPI+Flask server fixtures still bind+serve clean, no orphans. Suite 1627 green. So EVERY site that runs model-generated code now runs scrubbed+capped, on top of the scan-gate refusal.
HONEST REMAINING (named, not dropped): (1) **real runtime network-egress ENFORCEMENT** (a Linux network-namespace / firewall rule on the Jetson) is still NOT implemented — every egress gate (incl. the new documentation-only `SERVER_EGRESS_POLICY`) is a static/scan-time construct; a compromised-but-scan-clean process could still reach the network at runtime. This is the ONE substantive open security gap; REQ-7 correctly stays `partial`.

## ★ CODE-QUALITY signal LANDED + gate-vs-advisory DECIDED FROM DATA (2026-07-04, commits 4b319aa + this)

Owner's second question ("are we checking the actual code it's writing for quality?") is now YES. `harness/code_quality.py::assess_quality` (EXT-037 REQ-8/TASK-12, commit `4b319aa`, architect-validated) computes — PURE stdlib `ast`, no ruff/radon/pyflakes — McCabe cyclomatic complexity + 7 structural smells (bare_except, swallowed_exception, mutable_default_arg, star_import, long_function >80L, high_complexity CC>15, deep_nesting >5) over every generated module, surfaced as an **advisory** `quality=` field on all 4 `build_system` return paths. ADVISORY-not-gating is load-bearing + proven: a smelly-but-working build still returns done=True; existing callers ignoring the field are byte-unaffected; the security-scan REFUSAL path is untouched. Suite 1640 green.
- **DECIDE-BY-DATA (owner directive) — MEASURED, stay ADVISORY:** ran `build_system` live (gemma) over a spread of real creation tasks (scratch probe, config-driven backend). Of the builds that completed (2/4; the other 2 = the known ~17% total-build-failure, NOT a quality issue), gemma's generated code is **structurally SIMPLE — max cyclomatic complexity 5–8, far below the CC>15 threshold**, single-module. The ONLY recurring smell is **`swallowed_exception` (2/2 built systems)** — a `try/except` that silently passes. That is a real robustness nit but NOT a correctness/security defect (security is separately gated + enforced; both builds passed acceptance). **VERDICT: keep the signal ADVISORY, do NOT gate.** Gating on `swallowed_exception` would fail *working* builds on a style/robustness issue — precisely the owner's "never fail a working build on style." Complexity gating is moot (generated code is nowhere near the threshold). The actionable lever the data reveals is GENERATIVE, not a gate: feed "don't swallow exceptions" back into the build prompt to raise robustness at the source (a future task), measured on the same advisory signal. (Honest caveat: n=2 built is a small sample; the advisory field now runs on every build, so the signal will accumulate and the gate decision can be revisited if a smellier pattern emerges at scale.)

HONEST REMAINING on quality: no per-build gate (advisory by measured decision, above); the swallowed_exception prompt-feedback lever is unbuilt (future). The runtime-egress security gap (1, above) is the one substantive open security item.

## ★ WEB-RESEARCH PLANE LANDED — live at $0, gated + guarded (2026-07-04, commits c845242 + 71f829d)

The product can now research the live web (PRIME-001 intent §(a); tasks #92 then #85). Built in the honest order — safety FIRST: `harness/research_guard.py` (REQ-1, `c845242`) provides the eval-leak HARD-DISABLE (fail-closed: research categorically OFF inside `eval_lock()` or when `JCODE_EVAL_ACTIVE=1`, so one leaked fetch of a public held-out benchmark fix can NEVER invalidate a measurement — Tenet 3 enforced, not trust-based), the untrusted-content wrapper (fetched text fenced/labeled DATA-not-instructions), and `research_egress_policy()` (reuses `secure_exec.EgressPolicy`, fail-closed allow-list, exact-host, no substring bypass). Then `harness/web_research.py::fetch` (REQ-2, `71f829d`) rides on top with a traced-real 5-point contract: (1) `assert_research_allowed()` first — before any URL parse/DNS/transport; (2) egress-gated with hop-by-hop redirect revalidation (a redirect off the allow-list is refused, not followed); (3) read-only GET, size/timeout/redirect capped, no disk-write path; (4) SSRF block on RESOLVED IPs (127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7) even for an allow-listed host; (5) EVERY return path (success/truncated/failure) wraps text via `wrap_untrusted` — no raw-text path exists. Pure stdlib (urllib), no new dep. Suite 1695 green; 55 guard+fetch tests fully offline (mocked transport).
- **LIVE-VERIFIED ($0, scratch smoke, not pytest):** a real GET to `https://docs.python.org/3/` → ok=True, status 200, output carries the `UNTRUSTED WEB CONTENT` header; a non-allow-listed host (`example.com`) → `EgressRefused` live; a fetch inside `eval_lock()` → `ResearchDisabledError` live. The gating + eval-leak-hard-off hold in practice, not just in tests.
- HONEST REMAINING: the fetch plane is NOT yet wired into the orchestrator/planner (a built system's research-informed planning is the next task); the eval runners don't yet auto-assert `eval_lock()` around measurement (the mechanism exists + is proven; wiring it into every eval entrypoint is a follow-up so the hard-off is automatic, not caller-remembered).

## ★ ACCEPTANCE-COMPLETENESS PROBED — done-signal is HONEST (no overclaim); a recoverable UNDER-claim exists (2026-07-04)

Tenet-3 check after landing 3 build_system-gated capabilities: does build_system's SELF-derived `done` match the INDEPENDENT black-box oracle (`system_suite` `task.checks`, never shown to the build)? Ran a streaming probe over a 4-task creation slice (live gemma). Result: **ZERO false-done (done=True but oracle-rejected) — build_system does NOT overclaim success; the green results are honest in the Tenet-3-critical direction.** 2 tasks fully sound (done=True/accepted=True), 1 genuine honest build failure (todo-list, done=False/accepted=False). The one anomaly is a **false-NOT-done**: temp-converter-cli built a system that passes all 3 independent checks yet build_system self-reported `done=False` — an UNDER-claim (self-derived acceptance misaligned/stricter than the true contract), which COSTS done-rate but is the honest-safe direction (never the reverse). VERDICT: the done-signal is honest (no dishonest overclaim); the recoverable lever is aligning build_system's self-derived acceptance with the real contract to stop discarding its own working output (a capability lift, not an honesty fix). Honest caveat: n=4 is a small slice — widen n + diagnose WHY temp-converter self-reported not-done (stochastic build variance vs a systematic checklist-vs-contract mismatch) before building the alignment fix.

## ★ DATASTORE ACCEPTANCE ORACLE LANDED — catches hollow-persistence (2026-07-04, commit 1298fab, EXT-039 REQ-1)

First offline-testable rung of the real-systems datastore capability (task #86). `harness/datastore_oracle.py::verify_persistence` drives a built system's CLI (sandboxed, via `system_suite._run_cli`) to perform writes, then derives its verdict from an INDEPENDENT `sqlite3` query of the resulting db file — NEVER from the CLI's stdout — and proves CROSS-INVOCATION persistence via a genuinely fresh second subprocess. This closes a hollow-done class analogous to the hollow-FastAPI-done the server oracle fixed (#88): a system that prints "Saved!" but never persists is caught (`ok=False`), as is one that writes rows but resets its table every run. Architect-traced: the verdict genuinely comes from the sqlite query across a real process boundary, not stdout-sniffing (the load-bearing property). Stdlib `sqlite3` only, never-raises (6 failure-mode tests), 14 offline tests (hand-written CLI fixtures, no gemma in-suite). A `notes-sqlite-cli` task lives in a new `DATASTORE_SLICE` (kept separate from `ALL_CREATION_TASKS` to preserve the EXT-036 invariant). Suite 1709 green.
- **HONEST SCOPE of #86:** only the ACCEPTANCE-ORACLE half landed, and only for the EMBEDDED (sqlite) datastore. The heart of #86 — actually PROVISIONING real external services (Postgres/Redis/Qdrant/Cassandra: bring up on localhost, caps, teardown) — is NOT built; it is EXT-039 REQ-2 (a documented `ServiceProvisioner` seam, no fabricated criteria). #86 stays open on that half. The oracle is written so a real-service backend plugs into the same `verify_persistence` interface. Caveat: the 14 tests use hand-written CLI fixtures — a live build_system+gemma run of the notes-sqlite-cli task (proving the oracle works on REAL generated output, not just fixtures) is the next honest confirmation.

## ★ HARNESS BUG FIXED + TWO HONEST FINDINGS from the live datastore smoke (2026-07-04, fix commit 27120d8, #96)

Chasing the datastore oracle's live confirmation (suspect-harness-first) surfaced a real harness bug and two honest measurements:
- **FIXED (harness) — commit 27120d8, EXT-036 TASK-34:** `validate_plan` was flagging STDLIB imports (`sqlite3`, and by extension `os`/`json`/`datetime`...) listed in a plan module's `imports` as "imports unknown", rejecting the ENTIRE plan → 0 modules built. This silently blocked the whole datastore class (and any stdlib-cross-file-import system). Fix exempts `sys.stdlib_module_names` (top-level split, dotted-safe) while STILL flagging genuinely-dangling LOCAL references. LIVE-CONFIRMED: after the fix the notes-sqlite-cli plan is no longer rejected — it now consistently SHIPS (done_rate 1.0, was 0 before, plan-rejected on 'imports unknown sqlite3'). The model was doing the right thing; the harness was suppressing it — a harness failure, not a model limit (founding assumption vindicated once more).
- **FINDING 1 (honesty gap — build_system false-done, now a CONCRETE case):** with the plan unblocked, the build reports `done=True` / note "DONE (all acceptance checks pass)" — yet `python main.py add buy milk` CRASHES on a fresh dir with `sqlite3.OperationalError: no such table: notes` (this particular stochastic draw's `add` branch inserts without first calling `initialize_db`; a plain-subprocess control reproduces the crash, so it is NOT the sandbox / not my security work). So build_system's SELF-derived acceptance passed a system that crashes on its PRIMARY command from the declared clean state — a real FALSE-DONE. This upgrades the earlier n=4 statistical "under-claim only" reading: the datastore class DOES produce over-claims. Root cause hypothesis (to confirm): the self-acceptance doesn't exercise the primary CLI command from a fresh state / doesn't treat a non-zero exit as a fail. THE acceptance-completeness lever is now concretely motivated (make build_system's self-acceptance run the declared contract from clean state, non-zero-exit = fail) — a Tenet-3 honesty fix that would also let best-of-N/repair reject the broken draws.
- **FINDING 2 (capability — gemma datastore reliability, honest):** gemma's datastore-CLI code is unreliable across draws — some correctly `initialize_db` before insert (a clean earlier diag build ran add/list/count perfectly and persisted), others forget it and crash on `add`. The INDEPENDENT datastore oracle CORRECTLY rejects the broken draws (accepted=False) — proving on REAL generated output that the oracle is not fooled (it does its job in the negative direction). Honest end-to-end status of the sqlite datastore capability: plan-unblocked + oracle-real, but low accept-rate driven by (a) gemma reliability on this class and (b) the false-done above; NOT a green "capability works" claim.

---

## Product-surface parity — the CLI as a PRODUCT (added 2026-07-04, researched from the official Claude Code docs)

**Why this section exists (owner directive):** the bar is parity with **the Claude Code CLI
product running Opus 4.8 — the ENTIRE product experience — not just what the model does.**
The 11 capability rows above measure solving; these rows measure the PRODUCT SURFACE,
researched from the official docs (code.claude.com/docs: overview, cli-reference,
commands/skills, hooks, memory, MCP, sub-agents, checkpointing, settings). Claude Code is a
moving target: **re-audit the official docs monthly** and add rows for anything new.
Placement discipline: every row lands Jaros-native (judgments = agents; effects = gated
deterministic tools; hooks/permissions = clerk-side config; sessions = durable state).

| # | Gap (CC feature surface) | State | Current honest state in jcode | Next lever |
|---|--------------------------|-------|-------------------------------|------------|
| 12 | **Sessions: continue / resume / fork / name** (`-c`, `-r <id\|name>`, `--fork-session`, durable transcripts) | closed(EXT-044) | the EXT-036 REQ-12 session store now carries an optional `name` + `created`/`last_active` timestamps + a `.jaros-data/sessions/index.json` (name lookup + most-recent, never raises on a missing/corrupt index); `jcode -c`/`--continue` resumes the most-recently-active session, `-r <id\|name>` resumes a specific one by id OR name (honest non-zero-exit error, `JcodeCli` never constructed, on an unknown ref), `--fork [<id\|name>]` copies a transcript into a brand-new id leaving the source untouched, `/name`+`/fork` mirror both in the REPL; resumed prior turns reach the orchestrator context via the existing `condense()`/`recent()` path (no new mechanism); fresh runs with no flags are byte-identical | a `--fork-session` alias spelled 1:1 like CC's flag (cosmetic); enforce globally-unique session names (today a name collision resolves to the most-recently-active match) |
| 13 | **Headless + piping + structured output** (`-p`, stdin pipe, `--output-format json/stream-json`, `--json-schema`, `--max-turns`, exit codes — the Unix/CI surface) | closed(EXT-043) | stdin piping (`echo req \| jcode`, `jcode -`), `--output-format text\|json` (single parseable `{request,response,ok,model}` object), `--max-turns` cap (N<1 genuinely refuses; N>=1 documented no-op above the existing single-turn path), and deterministic exit codes (0/1) all wired + test-covered, additive over the unchanged one-shot/REPL paths | `stream-json` line-delimited output (needs a per-tool event stream at the `handle()` seam); `--json-schema`; explicit `-p` alias |
| 14 | **Project-instruction memory hierarchy** (CLAUDE.md-equivalent: project + user levels, auto-loaded every session, imports, `/init` generator, auto-memory) | closed(EXT-042) | `JCODE.md` auto-loaded at project root AND user level (`~/.jcode/JCODE.md`), injected as a labeled preamble into the orchestrator/planner context every turn; `/init` writes a starter file from repo comprehension (root-jailed, never clobbers); coexists with `.jcode/memory.md` + `/remember` + episodic store | `@path` import expansion inside JCODE.md (deferred, minor) |
| 15 | **Custom commands / skills** (user-drops-a-markdown-file → new `/command`; args; model-invocable when relevant) | closed(EXT-046) | `.jcode/skills/<name>.md` (project) + `~/.jcode/skills/<name>.md` (user, project wins on a name collision) register a real `/name` command; `harness/skills.py` parses optional frontmatter (`description`/`argument-hint`) + the markdown body (the plan template), never raising on a missing dir or a malformed file; `JcodeCli.dispatch` only falls to a matching skill AFTER the built-in `cmd_*` lookup misses (a skill can never shadow a built-in), substitutes typed args (`$ARGUMENTS`/`$1`/`$2`...) into the template, and routes the rendered text through the SAME plain-language chain (`_route_plain`) a typed non-slash request already uses; `/skills` lists discovered skills, `/help` documents the convention; a repo with no `.jcode/skills/` anywhere is byte-identical to before | argument-hint validation/tab-completion; a "model-invocable when relevant" auto-suggestion mode (the orchestrator reaching for a skill without `/name`); skill-authoring/scaffolding tooling |
| 16 | **User-configurable hooks** (shell hooks on PreToolUse/PostToolUse/SessionStart/Stop — deterministic user extensions) | closed(EXT-047) | `.jcode/hooks.json` (project) + `~/.jcode/hooks.json` (user, both tiers additive) map PreToolUse/PostToolUse/SessionStart/Stop to shell commands, optionally `matcher`-scoped by tool/Decision type; `harness.coding_loop.Runtime.apply` — the ONE gate→executor→decision-log choke point every tool call already passes through — fires PreToolUse hooks before `validate()` and PostToolUse after a successful `execute()`; a PreToolUse hook exiting non-zero BLOCKS the call (refused like a gate rejection); SessionStart fires once at `JcodeCli` construction, Stop once at session end (REPL quit/EOF/interrupt or after a one-shot turn); every hook's shell command runs through the SAME gated `shell.exec` path (denylist+timeout+tree-kill) via a fresh hooks-disabled `Runtime` so firing a hook can never recurse; no config anywhere is a byte-identical no-op; `/hooks` lists what's configured | surface fired-hook activity in the EXT-045 stream beyond a blocking PreToolUse's `error` event; an ask/allow/deny permission UX around hooks (overlaps row #17) |
| 17 | **Permission rules + modes UX** (allow/ask/deny per tool-pattern, settings hierarchy, `plan`/`acceptEdits`/`bypass` modes, interactive approval prompts) | closed(EXT-048) | `.jcode/permissions.json` (project) + `~/.jcode/permissions.json` (user, project first) hold `{tool, arg, action}` rules (allow/ask/deny, first-match-wins glob); `harness.coding_loop.Runtime.apply` — the same gate→executor→decision-log choke point EXT-047's hooks use — consults a matching rule ONLY AFTER the hard gate (egress/destructive-ops denylist, secrets, path-jail) already accepted the Decision, so a user `allow` rule can NEVER un-block a hard-gate refusal (proven by an explicit test); an `ask` result prompts interactively in the REPL only, and safely DENIES by default headless (never hangs); `/mode [plan|default|acceptEdits]` cycles a REPL mode wired at the same seam — `plan` withholds every write/shell Decision before the gate/hooks ever see it (description only), `acceptEdits` narrowly auto-approves an `ask`-resolving WRITE Decision (never `shell.exec`); `/permissions` lists configured rules; no config anywhere + `mode="default"` are byte-identical no-ops | a `bypassPermissions`/"YOLO" mode (deliberately not built — it would let a rule/mode skip the hard gate); a richer settings-hierarchy precedence UI beyond `/permissions`'s flat listing |
| 18 | **External-tool extensibility protocol (MCP client)** (connect stdio/HTTP tool servers; tools join the toolbelt; the ecosystem standard) | unmeasured | none | implement an MCP CLIENT as execution-plane adapters: each server tool wrapped as a gated Jaros tool (two-plane preserved; instant ecosystem access) |
| 19 | **Subagent authoring surface** (user-defined agents: prompt/tools/model in a markdown file; delegate-with-own-context) | probed | agents exist as Python in `.jaros-data/agents/` (builder-authored, not user-friendly); no user-authoring format | markdown agent spec → loader compiles to a Jaros agent; router can delegate |
| 20 | **Fine-grained checkpoint / rewind** (auto-checkpoint before EACH edit; `/rewind` code, conversation, or both) | probed | whole-run checkpoint + `/undo` exist (EXT-009) | per-edit checkpoint ring on the existing snapshot tool; `/rewind <n>` |
| 21 | **Interrupt + steer mid-run** (Esc to stop safely mid-task, queue a correction, agent adjusts) | unmeasured | Ctrl-C guards exist for crash-safety; no graceful interrupt-and-steer loop | cooperative cancel points between plan steps (clerk checks an interrupt flag; partial state preserved via checkpoints) |
| 22 | **Context management for long sessions** (auto-compact, context meter, `@file` references, `/compact`) | lever-named | compaction deferred earlier (bounded flows didn't need it); long-horizon runs now DO; no @-refs | deterministic compactor (summarize decided/verified state into the spec — jarify IS the compaction target); `@path` expansion in the REPL |
| 23 | **Background runs surface** (`--bg`, attach/logs/stop, agent view — kick off a long build, keep working) | probed | runner/daemon infra exists internally (run_forever, experiment chain); not exposed as a product surface | `jcode --bg` submits through the existing inbox; `jcode logs/attach/stop <id>` read the Jaros log |
| 24 | **Terminal UX polish** (streaming output, progress display, statusline, `/help` discoverability, `/export`, tab-completion, themes) | closed(EXT-045) | tool calls now stream a concise `→ call` / `✓ result` line to stdout as they happen (from the same seam that logs each accepted Decision to the hash-chain), on by default on a live terminal, suppressed under `--output-format json` or a non-TTY stdout unless `JCODE_STREAM_EVENTS=1` forces it, byte-identical when off; `statusline()` renders `model · class · $0 · latency` from current state, `/statusline [on|off]` toggles a persistent status line above every prompt; `/help` documents both | a live in-flight spinner/elapsed counter for a single long tool call (today's line only appears at call-start/completion); `/export`; tab-completion; themes |
| 25 | **Install + health story** (one-command install macOS/Linux/Windows, auto-update, `/doctor` diagnostics) | lever-named | serve.sh/ps1 + jcode.sh/ps1 exist (repo-local); no packaging, no `/doctor` | `pipx install jaros-code` packaging; `/doctor` = deterministic checks (Jetson reachable, model served, Docker, git) |
| 26 | **Multimodal input (images)** (paste a screenshot/mockup → build/debug UI) | unmeasured | none; NOTE Gemma e2b/e4b are vision-capable on the Jetson (VLA demos) — genuinely reachable | probe: image → e4b vision → structured UI description → existing build pipeline |
| 27 | **Deliberately deferred surfaces (honest scope)** — IDE extensions, desktop app, web/cloud sessions, Slack/GitHub-Actions integrations, remote control | probed | out of scope for the CLI-parity pursuit FOR NOW; recorded so the scope is stated, not silent | revisit after CLI-product parity; none block the terminal product |

**Instrument for this section (new):** the **Product-Parity Checklist** — feature-by-feature
scoring vs the official docs (works / partial / missing), re-synced from the docs monthly.
It joins the scoreboard beside the daily-driver suite: the suite measures how WELL the
product solves; the checklist measures whether the PRODUCT is actually there.
