# THE PURSUIT — indefinite, maximum-velocity directive (owner, 2026-07-01)

Supersedes and replaces the 3-week roadmap (deleted). This is the standing strategy for
reaching a **real, Claude-Code-comparable CLI whose inference runs entirely on a Jetson
Orin Nano** — pursued as fast as honest measurement allows, for as long as it takes.
The supervisor agent should reconcile PRIME-001 and the specs with this directive
through the normal jarify flow (spec-first; this document is direction, specs are law).

---

## 1. The question, stated honestly

**"Can a Jetson-fit system reach Claude-Code-comparable capability?" is an OPEN
EMPIRICAL QUESTION.** Predictions in either direction are not data. The pursuit answers
it by construction (close the gaps) or by evidence (map the walls) — never by
assumption. Three consequences:

- **The bar never lowers.** Comparable means comparable: measured against what Claude
  Code actually does for a working engineer, on a frequency-weighted instrument.
- **Wall claims are the hardest claims to make.** "This gap cannot be closed on
  Jetson-fit inference" is only utterable with evidence across the FULL escalation
  ladder (§6) — including trained models — and it is always dated: *"a wall as of
  <date>, with <roster + methods>"*, never permanent. New models and new methods
  reopen every wall.
- **Optimism is also not data.** Every capability claim carries its held-out number
  and CI. A dishonest 95% is worse than an honest 40% (Tenet 3, unchanged, supreme).

## 2. The scoreboard (the instrument comes first)

Progress is these numbers and nothing else. Build/maintain them before and during
everything:

1. **Daily-driver suite %** — 80+ tasks through the CLI end-to-end, frequency-weighted
   by real usage (navigate/explain 20 · bounded edit 20 · fix-failing-test 15 ·
   write tests 10 · refactor 10 · build module 10 · multi-file feature 10 · ops 5).
   Deterministic oracles; dev/holdout split; holdout read ≤1×/week. **This is the
   parity number.**
2. **External hard bar %** — SWE-bench-Live, growing slice (8 → 50 → 200+), stratified,
   dev/holdout. The number that keeps us honest against the field.
3. **Routed-system triple** — routed vs best-single vs oracle-per-task. Proves the
   multi-model system pays; localizes whether gaps are routing or coverage.
4. **Latency budget** — p50/p95 per command class, measured ON THE JETSON (nav <2s,
   bounded edit <30s, fix-iteration <90s as current targets; tighten over time).
5. **The Gap Map** (`docs/GAP-MAP.md`, living) — the full Claude-Code capability
   surface, each gap in exactly one state:
   `unmeasured → probed → lever-named → in-progress → closed(number) → wall(dated, evidence)`.
   Surface skeleton: repo navigation/understanding · bounded edits · multi-file edits ·
   refactors · test write/run/fix loops · debugging-from-failure · long-horizon tasks ·
   repo-scale context · git/shell tool breadth · interactivity/latency ·
   robustness/recovery. The Gap Map is the pursuit's steering wheel: work always flows
   to the highest (impact × tractability) gap.

## 3. Velocity doctrine (what "as fast as possible" means mechanically)

The Jetson is serial; the loop's true budget is **information gained per Jetson-hour**.

- **Probe before build.** Every hypothesis gets its cheapest falsifier first (the
  proven pattern: raw single-call probes, the fact-injection probe). A day of building
  is never spent on a direction a 30-minute probe could kill.
- **Pre-registered kill criteria.** Every experiment declares success/kill thresholds
  BEFORE running. No post-hoc rationalization of weak results.
- **Kill fast, log the negative, move.** Negative results are map data (they are half
  our best findings). Two consecutive held-out failures on an axis → switch axes
  (existing ADAPT rule).
- **Parallel non-inference tracks.** While the Jetson crunches: corpus building, spec
  work, deterministic-plane tools, training-data curation, research reading, Gap-Map
  upkeep. The GPU being busy is never an excuse for the loop idling.
- **Batch by model** — order eval work to minimize swaps; sticky-model routing in
  interactive use.
- **Dev-time parallelism (owner option):** additional OWNED hardware (a PC GPU, a
  second Jetson) may run extra copies of the same Jetson-fit models to parallelize
  EVALS and to TRAIN. This violates nothing — the product's inference target stays
  Jetson-fit; latency truth stays Jetson-measured. If available, this is the single
  biggest velocity multiplier; ask the owner.
- **The chain never idles** (existing rule, unchanged).

## 4. The sovereignty boundary (what Tenet 2 means now)

- **Inference:** Jetson-fit, local, forever. No cloud, no paid API, not as fallback.
- **Training:** allowed and encouraged on ANY owned hardware (Jetson, owner's PC).
  Training our own weights is MORE sovereignty, not less.
- **Data:** open datasets, our own verified-solution store, synthetic data generated
  and test-verified by our own system. No data leaves the machines.
- **Dev-time acceleration** on owned hardware: allowed (§3). Published latency numbers:
  Jetson only.

## 5. The arsenal (constraints on METHODS are hereby removed)

Everything below is authorized. Existing proven levers stay; new families are opened.
Every adoption still passes the held-out gate — the arsenal is unconstrained, the
acceptance criteria are not.

**A. Existing, proven (keep sharpening):** deterministic control flow · test-gate as
judge · plane-placement + generate-and-test · multi-model routing by measured class
coverage (admission = marginal coverage on the roster's shared failures) · reductions ·
gold-free localization (traceback/coverage) · SEARCH/REPLACE editing · verified-solution
memory · gated reasoning · collaborative draft→critique→revise.

**B. Semantic retrieval plane (new, build early).** Tiny embedding models (bge-small /
nomic-embed class, ~100-500MB) run alongside the roster. Build: semantic code search
over the working repo; semantic recall over the verified-solution store (upgrade
EXT-027 from structural to semantic match); API/doc retrieval. LESSON CARRIED FORWARD:
generic context injection measured net-negative — retrieval must be PRECISE (direct
dependencies, single missing facts, nearest solved analogue), and every retrieval
mechanism gates on held-out like any jig.

**C. Program-analysis plane deepening (new).** The deterministic plane can grow
without limit and costs no inference: type inference, dataflow/def-use analysis,
coverage-guided fault localization (extend), property-based test generation, mutation
testing, AST-diff pattern mining from repo history, contract extraction. Each analysis
is a fact-source for precise injection (B) and a new reduction ingredient.

**D. TRAIN OUR OWN MODELS (new — the big unlock).** Three tiers, all owned-hardware:
1. **LoRA/QLoRA specialists** on roster models: fine-tune for our exact formats and
   grains — a SEARCH/REPLACE-emission specialist, a localization specialist, a
   test-writer, a commit-intent parser. Small data, hours of training, immediately
   Jetson-servable (adapter on the same base).
2. **Micro-models for narrow judgments:** train tiny classifiers/rankers (1-100M
   params) on data our own evals generate for free — the router's class judgment, a
   candidate-patch ranker, a retrieval re-ranker. Deterministic-plane speed with
   learned judgment; every eval run is a labeled dataset.
3. **Self-distillation (the flywheel, §7):** train roster models on our own
   test-verified solutions so tomorrow's bare model does what today's model+harness
   needed scaffolding for.

**E. Novel orchestration (new, judged like everything else).** Experiment-to-understand
loops (EXT-030), speculative parallel solves where batching permits, tournament
selection under the test gate, agent-authored deterministic tools (the model writes a
tool once, the tool runs forever — test-gated before adoption). Invent freely; gate
ruthlessly.

**F. External knowledge (standing).** At any plateau: papers, competing harnesses,
model releases. Every new small-model release is a potential roster candidate —
audition by marginal coverage within days of release.

## 6. The escalation ladder (the "find the limit, then fill it" doctrine)

For ANY gap or failing class, escalate in cost order. A wall claim requires evidence
at every rung below it:

- **L0** prompt/format jig
- **L1** decomposition / deterministic control flow
- **L2** plane-shift: deterministic tool replaces the judgment (generate-and-test)
- **L3** precise retrieval / single-fact injection (B + C)
- **L4** experience recall: nearest verified solved analogue (memory, semantic)
- **L5** reduction: transform the instance into classes already covered
- **L6** routing: different roster model / audition a new model (marginal coverage)
- **L7** LoRA specialist: fine-tune a roster member for the grain
- **L8** train a micro-model or distill (D2/D3)
- **L9** dated wall: record the evidence trail L0-L8, name the missing capability
  class, add to the Gap Map as `wall(date, evidence)`. Revisit on every new model
  release or method discovery. L9 is a bookmark, never a conclusion.

## 7. The self-distillation flywheel (how the system climbs indefinitely)

The test gate turns compute into **free verified training data**: every solved task —
from evals, dogfooding, commit-replay, SWE-Live — yields a (problem, verified
solution) pair; every heavily-scaffolded win yields (bare problem → final verified
output) pairs that teach the model to skip the scaffold.

The loop: **harness discovers → test gate verifies → store accumulates → training
distills into weights → the bare model absorbs the jig → harness budget moves to the
next gap.** Compile the jigs into the weights, then build new jigs at the new
frontier. This is the only known mechanism by which the SAME hardware gets
indefinitely more capable, and it is fully sovereign. Standing orders:
- Nothing verified is ever thrown away: persist every (problem, attempts, outcomes,
  winning solution, model, scaffold-config) tuple from every run, starting NOW —
  retroactively harvest what logs allow.
- First distillation experiment: pick the highest-volume solved class, LoRA the
  weakest roster member on it, measure bare-model lift held-out. Even a small win
  validates the flywheel; a null result is map data.

## 8. Cadence, reporting, honesty plumbing

- Continuous operation (existing runner + governance loop). Weekly full scoreboard:
  all five instruments, deltas, CIs, Gap-Map state changes, kills and their evidence.
- `PUBLISHED.md` provenance for every public figure (existing, keep).
- Dogfooding is a standing instrument: the agent uses `jcode` for its own edits where
  it can; friction items feed the Gap Map's UX rows.
- Milestones are emergent, not scheduled: when the Gap Map's first full pass is done
  (every row at least `probed`), that is **Model Map v1** → triggers the public
  release the owner committed to. Subsequent map editions ship when the map
  materially changes.

## 9. Bootstrap sequence (first moves under this directive)

Order matters only here; after this, the Gap Map steers.
1. **State census + `baseline-pursuit` tag** — roster, wiring (no silent orphans),
   all current numbers. One day.
2. **Daily-driver suite** (§2.1) — the parity instrument. Two days. Baseline both
   halves.
3. **Gap Map v0** — every row seeded with its current state and number (or
   `unmeasured`). One day, updated forever after.
4. **Solution-store persistence** (§7) — start capturing every verified solve
   immediately; it is the training corpus and it only grows if it exists.
5. **Embedding model onboarding** (§5B) — smallest useful embedder on the Jetson;
   semantic memory recall as first application, held-out gated.
6. **Reasoning-model auditions** by marginal coverage (already specced) + first
   **LoRA specialist experiment** (§5D1, pick the S/R-format emitter or localizer)
   + first **distillation probe** (§7) — these three run as the experiment chain's
   next links, probes first.
7. From then on: highest (impact × tractability) gap on the map, escalation ladder,
   probe-before-build, forever.
