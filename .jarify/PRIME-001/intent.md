# Intent

**jaros-code** is a software-development harness built on Jaros whose purpose is to
match or exceed Claude Code at real coding work **while every reasoning call is
served by a local open-weight model that runs entirely on-device on the Jetson Orin Nano
via llama.cpp — at zero inference cost.** As of 2026-06-28 the system is a **multi-model
harness** (owner directive): rather than one fixed model, a **model-router judge** classifies
each problem and routes it to the on-device model best able to handle that *class* of problem,
and the harness then **rewires itself** — loading that model on the Jetson and activating the
tools, agents, configuration, and prompts proven to adapt the harness *to that model*. Every
model still runs on the Jetson at zero cost (commitment 2); the system began on **Gemma 4 2B
(`e2b`)**, which remains one member of the model roster and the honest baseline anchor.

**What the product concretely IS — the END GOAL (owner clarification, 2026-07-03):** a **CLI that
BUILDS and MODIFIES complete software systems from a PROMPT.** That is the operational meaning of
"be just like Claude Code": a developer describes a system — or a change to an existing one — in a
natural-language prompt at the terminal (a sentence, a paragraph, or an iterative back-and-forth,
with whatever context they give), and jaros-code plans → builds → tests → ships it (or evolves it)
end-to-end, locally, at $0. Every other element of this directive — the model roster, the
deterministic router, the agent swarm, the tool library, the evals, the flywheel — exists to make
THAT product as good as or better than Claude Code on Opus 4.8. The prompt→system
build-and-modify CLI is **not one feature among many; it is the point** — and the parity instruments
that measure it (the held-out creation + modification suites, graded end-to-end through the CLI by
independent oracles) are therefore the headline scoreboard for the whole pursuit.

**REAL systems, increasingly complex — the ratchet (owner clarification, 2026-07-03).** "Complete
software systems" means **REAL** ones, not toy stdin/stdout scripts: real web servers and API
frameworks (Flask/FastAPI/Django), real data/graph/ML libraries (pandas, networkx, SQLAlchemy…),
real external services and **databases** (Qdrant, Cassandra, Postgres, Redis…). The product both
**builds** such systems from a prompt and **modifies** existing ones, and the bar **continuously
ratchets** — from small easy changes to large complex ones, from one file to whole repositories —
so the instruments get harder over time and the system must keep improving to stay at parity. A
capability only counts when the real system is **honestly verified working** (a server answers real
HTTP, a DB query returns real rows, a library computes the real result), never a hollow
import-smoke pass. To do this, the product must be able to, autonomously from a prompt:
(a) **research the web for current, correct information — and KNOW when it must** — read the latest
official documentation, framework/library APIs, and evolving protocols (e.g. the A2A agent
protocol, vector-DB and datastore docs) before implementing against them, rather than guessing from
stale training memory. **Two HARD guards bind this plane (non-negotiable — the research plane is the
single biggest honesty attack surface):** (i) **eval-leak is HARD-DISABLED, not merely discouraged** —
research is categorically OFF during any eval/measurement run (a global switch the eval harness forces),
AND the allow-list categorically EXCLUDES every eval target (SWE-bench/-Live repos, issues, PRs, and any
held-out suite's source), because those fixes are public on GitHub and ONE leaked fetch invalidates the
number and our credibility — a skeptic will ask exactly this, so the guard must be provably airtight,
not trust-based (Tenet 3). (ii) **fetched content is UNTRUSTED DATA, never instructions** — a doc/web
page is quarantined as reference data and can inform the plan's facts, but the planner/agents must NEVER
execute or obey instructions embedded in fetched text (prompt-injection via a doc page is a real vector
now that research feeds the planner); fetched text is fenced/labeled as untrusted and stripped of any
imperative authority before it reaches a reasoning prompt;
(b) **set up and depend on external components** — install packages, stand up and configure the
databases/services a system needs (from the researched docs), and wire the system to them;
(c) **research and comprehend large, complex repositories** it is changing — build an accurate
mental model of an unfamiliar codebase before editing it;
(d) **form complex, correct plans** for changes of any size — decompose a large multi-file, multi-
component change (or a small surgical one) into a correct ordered plan, execute it, and verify;
(e) **investigate by writing throwaway research scripts** — exactly as Claude Code does: author a
small script into a **temporary/scratch location** (outside the target repo) to probe a system
locally *or* externally (inspect a DB, hit an API, measure a dependency, explore a repo), **run it,
and stream its output to stdout — or to a file that it then parses when the output is too large** —
then act on what it learned. This is a first-class investigation loop, not a side trick;
(f) **remember what it did and WHY, and plan from experience** — keep a durable, referenceable record
of its actions and the *rationale* behind them (an episodic/provenance memory), so that when the user
says "do that again" or refers to something done earlier, it can recall the exact prior work; and
**while forming a new plan it first retrieves any similar past work and reconciles the new plan
against it** — past experience is part of the upcoming plan's context, not forgotten each run. (Guard:
this is PLAN + provenance recall, distinct from behavior-keyed few-shot code examples, which measured
*negative* for solving on the 2B — recall informs the plan, it does not paste stale code.)

**(g) stay aligned across LONG-HORIZON builds — minutes → hours → days (owner directive, 2026-07-03).**
The hardest, highest goal: build a LARGE system over a long autonomous run **without drifting from what
was asked.** The product decomposes the prompt into a **governed spec** (requirements + an ordered task
list), builds it **task-by-task**, and after each unit runs an **alignment + verification pass** (a
jarify-architect-style check: does this still serve the spec? is it correct? no scope drift?) before
advancing — **continuously re-grounding on the spec** so an hours-long (eventually days-long) run stays
coherent instead of wandering. The mechanism for this alignment **IS jarify** — its skills (manage-specs →
builder → architect) and agents, or a **jaros-code-native equivalent we must still fully implement inside
the product** (today jarify governs how *we build jaros-code*; the product must run the same governed loop
*internally* to build the user's system). **jarify is key** — its spec-first discipline (Tenet 4) is the
anti-drift engine of a long run. The difficulty **ratchet applies to DURATION too**: start with builds that
finish in **minutes**, and expand to systems so large they take **hours or days** — a run only counts when,
at the end, every requirement is traced to work that is honestly verified. This is the north-star form of
"just like Claude Code": hand it something big, walk away, and it stays on-task and delivers.

**(h) BUILD LARGE SYSTEMS BY COMPOSITION OF VERIFIED CLASSES — the compositional convergence mechanism
(owner directive, 2026-07-07).** The system reaches arbitrarily complex systems by growing a **library of
small, atomic problem-CLASSES** it can each build and verify in isolation — an LRU cache, a rate limiter, a
TTL store, a parser, a state machine, a datastore — **each backed by its own reference oracle**, and then
**COMPOSING them — as a DAG, not a flat list — into larger systems**: a big prompt is decomposed into a DAG
of known leaf-classes plus the novel glue between them, each leaf built or retrieved and **independently
verified**, and the whole wired together and verified bottom-up. Two things are first-class. **(1) The
verified leaf-library:** every class the per-class scoreboard shows *solidly* passing is promoted into a
reusable, oracle-backed building block (the **ADT differential oracle is the seed** — five canonical
data-structure leaves already exist with reference implementations), so a large project *reuses verified
pieces instead of re-deriving them* — a flywheel of capability, not only of training data. **(2) The
deterministic composer + connectors:** the wiring and the **CONTRACTS between leaves are where composition
bugs live** — MEASURED 2026-07-07: the creation failures were *compositional* (a missing entrypoint that
ties modules together; the model can write the pieces but stumbles on the wiring), while *modifying* an
already-composed system is markedly more robust — so the connectors are **deterministic, checkable grains,
not left to the model**. The leaf taxonomy is **GROWN EMPIRICALLY from measurement** (the scoreboard names
which classes recur as independently-verifiable units), never designed top-down; not every problem divides
cleanly, so a leaf may be a novel sub-problem the model must still solve fresh — the DAG *organizes* the
work, it does not eliminate irreducible reasoning. This is the concrete shape of the difficulty ratchet:
**master the atomic classes, then ratchet to COMPOSITIONS of them** (two solid leaves wired into one
system), then to larger DAGs — the path to the large, real, multi-component systems this directive demands.
It is the build-level twin of the agent-swarm's "capability comes from composition" (below): the swarm
composes tiny *agent judgments*; this composes verified *system classes*.

**(h.1) The GRAPH DSL — the explicit interface between JUDGMENT and CONSTRUCTION (owner idea, MEASURED
go/no-go 2026-07-07).** The DAG of (h) is made an explicit **graph DSL**: nodes are verified leaf-classes,
edges are typed connectors, and the pipeline splits at a clean seam — **NL→DSL is the reasoning (judgment);
DSL→system is deterministic construction**; modification is a **declarative graph-diff** (declare the desired
graph, diff it, apply only the delta). The DSL is a *reduction* (a first-class grain type, below): it moves
the reasoning onto a compact, grammar-checkable representation so a small model's **judgment** — not its
from-scratch code-generation — is what's required. This was MEASURED on gemma-4-e2b before adoption (the
owner's two-gate rule, honest, no oracle leak): **Gate 1** — the small LOCAL model converts NL↔DSL reliably
(valid 7/7, right-core-block 7/7, stable round-trip 7/7); **Gate 2** — routing a known class to its verified
leaf (DSL→emit-reference) produces a working system on the exact HARD class (TTL store) where from-scratch
generation fails, **DSL-path 3/3 vs free-form 0/3**. Direct evidence that **for the compositional class,
development is more JUDGMENT + PATTERN-MATCHING than reasoning** — precisely the small model's strength.
**Tenet-2 bound (non-negotiable):** the DSL is emitted by the **SMALL LOCAL model** (Gate 1 proves it can;
the constrained DSL is what makes it tractable) — a frontier/cloud model is FORBIDDEN in the product,
permitted only as a temporary, labeled validation scaffold, never shipped. **Honestly scoped:** proven for
single verified leaves + NL↔DSL fidelity; multi-leaf compositions and broad node-vocabulary coverage are the
next MEASURED work, and a leaf with irreducible novel logic still needs reasoning (the custom-node escape
hatch). As it proves out, the DSL becomes a **spec-language alongside Gherkin**, semi-deterministically
guiding both the model and the harness (spec EXT-058).

**HOW it solves all of the above — the prime-directive method, applied REFLEXIVELY (owner directive,
2026-07-04).** The product tackles a problem with the SAME disciplined method by which this directive itself is
pursued — there is ONE method, used both to *build jaros-code* and *by jaros-code to build/modify/solve*:
**decompose** the problem into the smallest verifiable steps; climb the **FULL escalation ladder cheapest-rung-first**
(L0 prompt → L1 decompose → L2 plane-shift → L3 retrieve → L4 experience-recall → L5 reduce → L6 route to a fitting
model → **L7 train a LoRA specialist → L8 train a micro-model / self-distill**, powered by the self-distillation
flywheel — the test gate turns verified solves into free training data), never reaching for a heavier lever than the
failure needs. **Yes — the ladder includes model FINE-TUNING (L7/L8): it is the TOP, most expensive rung, reached
only after the cheaper rungs are honestly exhausted for a genuinely model-bound class, and it grants NO exemption
from measurement — a trained adapter is scored on the same held-out scoreboard as everything else (Tenet 3; we have
already measured a case where training cut held-out loss yet moved the scoreboard zero, and banked the built stack
rather than overclaim).** At the PRODUCT level the cheap rungs (L0–L6) run inline within a build; the training rungs
(L7/L8) are the long-horizon FLYWHEEL lever — accumulate verified data across many runs, train a specialist, the whole
roster gets more capable over time — the mechanism by which the same $250 device grows indefinitely (design §training
plane / flywheel). The reflexive method spans the WHOLE ladder for both levels; **VERIFY, don't assume — and suspect your own harness/plan before blaming the model
or the environment** (raw-probe what actually happened first; a zero/absurd result is a bug in the approach until
proven otherwise); accept only **HONEST completion** — real acceptance that exercises the real behavior, **never a
hollow pass**, a failure reported as a failure (Tenet 3); when a grain is a judgement the model can't reliably
make, **move it to the deterministic plane** rather than slicing it thinner; and **govern the whole run spec-first
with an alignment gate (jarify)** — decompose → build → an architect-style check that the work serves the spec
before advancing → record what was done and why (which feeds (f)'s experience memory). This method is the
`MEASURE → DIAGNOSE → DISCOVER → PLACE → WIRE → RE-MEASURE → PRUNE` convergence loop (design §"The convergence
loop") turned inward: the product runs it to converge on the user's prompt exactly as the supervisor runs it to
converge on this directive. Reconciled here so the two are explicitly the same discipline, never divergent.
**Tenet reconciliation (this does NOT weaken Tenet 2):** web research and package/service setup are
**read-only information retrieval and build-time actions**, not inference — *every reasoning call
still runs on the local Jetson model at $0; no cloud/paid model is ever used for thinking.* Fetching
public documentation is the system reading the manual, exactly as a developer does; it is explicitly
sanctioned here and **supersedes the earlier "the harness makes no network calls" stance for the
product's research + dependency-setup capability** (network egress stays gated/observed for safety —
research reads are allowed; arbitrary egress from *built* code remains off by default). The honesty
guard is unchanged and absolute: web access must **never** be used to leak or look up held-out eval
answers (Tenet 3).

**The bar is explicit and high — it is the very North Star: the system must become so
good that it overcomes the model limitations of Gemma 4 2B (`e2b`) and is AS GOOD OR BETTER,
in ALL ways, than the Claude Code CLI running on Claude Opus 4.8 at its max.** Matching
is the floor; exceeding it — on capability, reliability, transparency, and developer
experience alike — is the aim. The harness — not the model — closes that gap. We do not get
to claim we are near the bar; we have to *prove* it. So this system is built
together with a growing suite of **tests and evaluations** that measure, run over
run, whether we are getting closer to Claude-Code-on-Opus-4.8 parity on real coding
tasks. We both author our own task evals *and* run existing public coding
benchmarks where they exist (e.g. SWE-bench / SWE-bench-Verified, HumanEval/MBPP,
Aider's edit benchmark) so the bar is an external, recognized one — not a yardstick
we drew ourselves. Progress is the benchmark trend, not a feeling.

**"In ALL ways" means the WHOLE PRODUCT, not just the model's task-solving (owner
clarification, 2026-07-04).** The bar is the **Claude Code CLI as a product** — everything
a developer actually experiences at the terminal — researched from the OFFICIAL Claude Code
documentation and tracked as its own instrument. Concretely, parity spans, beyond solving
capability: **sessions** (continue / resume / fork / named, durable transcripts);
**headless + Unix composability** (print mode, stdin piping, JSON/stream output,
scriptable in CI); **instruction memory** (an auto-loaded per-project instruction file +
user level + `/init`, alongside the episodic store); **user extensibility** (custom
commands/skills as drop-in files, user-configurable lifecycle hooks at the clerk's gate,
user-authored subagents); **an external-tool protocol client** (MCP — each server tool
wrapped as a gated deterministic tool, two-plane preserved); **permission rules + modes
UX** (allow/ask/deny per tool-pattern, plan / accept-edits modes, interactive approvals);
**fine-grained checkpoint/rewind**; **interrupt-and-steer mid-run**; **long-session
context management**; **a background-runs surface** (start, attach, logs, stop);
**terminal UX** (streaming output, progress, statusline, discoverability); **an install +
health story** (one-command install on macOS/Linux/Windows, `/doctor`); and eventually
**multimodal input** (the Jetson roster's vision-capable members make this reachable).
These live as the **Product-surface parity rows (#12–27) of `docs/GAP-MAP.md`**, and their
instrument is the **Product-Parity Checklist**: feature-by-feature scoring (works /
partial / missing) against the official docs, **re-synced from those docs monthly**
because Claude Code is a moving target — parity with a moving target requires tracking
the target. The capability scoreboard measures how WELL it solves; this checklist
measures whether the PRODUCT is actually there. Both must converge; neither substitutes
for the other. Deliberately deferred surfaces (IDE/desktop/web integrations) are RECORDED
as deferred (GAP-MAP #27) so scope is stated, never silent.

**Scope: PYTHON-FIRST (owner directive, 2026-06-28).** The system focuses on a SINGLE language —
**Python** — for now. The evals, the problem **classes** + their taxonomy, the deterministic
classifier's signals (Python AST + traceback/error parsing), and each model's measured profile are
all Python-scoped. Other languages are a deliberate LATER expansion, not a current dilution: one
language done excellently first, then broaden. Until then the roster, the coverage tally, and the
class ontology are Python-specific, and that focus is a feature — it lets the classifier exploit
Python-specific structure (typed signatures, tracebacks, imports) rather than staying language-generic
and shallow.

**The evaluations must get harder and harder.** An eval suite the harness can ace is
too easy to be informative and MUST be made harder — this is a non-negotiable
ratchet. As the pass rate on a tier climbs, the system escalates: harder authored
tasks, then progressively harder *real public benchmarks*, raising the bar until
parity is proven on genuinely hard, external problems and not before. We never lower
the bar to flatter the system; when it masters a level, the level gets harder. If our
home-grown evals are not good enough, hardening them — and pulling in tougher real
benchmarks — is itself required work, not optional.

The wager behind this system — refined by measurement as of 2026-06-28: *small models have
not been useful for development because their harnesses are thin — but each individual small
model still has a real, measurable class-ceiling, and the honest move is to MAP that ceiling and
**BUILD THE DETERMINISTIC PROSTHETICS that let the model work PAST it** — routing to a stronger
roster model only as the SECONDARY lever, once the prosthetic plane is exhausted — not to deny it.*
We no longer assume a single model has no capability ceiling;
we **measured** one and recorded it honestly: on the hardest repo-level tasks, sampling at scale
(pass@k, k=20 at a fair temperature), explicit decomposition, and non-deterministic orchestration
**all** failed to extract a solution from Gemma 4 2B. But that is **one FAMILY of levers**
(sampling / prompting / orchestration around an *unchanged* problem representation) exhausted on
that instance — it points NOT at a bigger model but at a **deterministic prosthetic not yet built**
for that class: a tool that makes the specific failure VISIBLE, LOCALIZES it, and FEEDS the concrete
failure back so the model can reason on it (the plane those levers never touched — the 2B reliably
fixes a bug the instant it can SEE it). Reporting the negative honestly is required (commitment 3);
concluding *"the model just can't — wait for a bigger one"* from it is the forbidden drift (owner
directive 2026-07-07). The measured wall names the **missing prosthetic to build**, never a ceiling
to accept.

**The no-ceiling principle now lives at the SYSTEM level.** The *multi-model harness* has no
ceiling, because for any class of problem some Jetson-fitting model — paired with the harness
adaptation built for it — can reach it, and both the model roster and the per-model adaptations
grow without bound. So a model failing a class is, in order: **(a)** still a **harness gap for
THAT model** — did its adaptation decompose, scaffold, retrieve, verify, and iterate enough, and
**above all, has the missing deterministic PROSTHETIC been built** — the tool that makes the
specific failure VISIBLE, localizes it, verifies/counts/searches, and hands the model a
now-tractable judgment (this is the PRIMARY lever for a per-model cap)? this remains the primary
craft and is exhausted honestly first; and only then **(b)** — as the COMPLEMENTARY, secondary
lever — a signal to **route that class to a stronger Jetson-fitting model** whose measured profile
covers it. *"No
Jetson-fitting model, with any harness adaptation, can reach this class"* is the only forbidden
conclusion now — and it may be asserted **only when proven by measurement across the roster**,
never assumed from one model's limit. Escalating to a cloud or paid model stays absolutely
forbidden (commitment 2). The craft is now three-layered — per-model harness engineering, the
router that picks the right model per class, and growing the Jetson-fitting roster + each model's
reachable-class map — and every layer's claims stay **generic** (general mechanisms, held-out
proof, never benchmark-fitting) and **honest** (commitment 3): a dishonest score is worse than an
honest one, and a denied ceiling is worse than a mapped one.

**The system-level no-ceiling is a *reachability* principle, not a performance claim (external
review, 2026-07-01).** That some Jetson-fitting model *can* reach a class NEVER means the
*current routed system* beats the best single model — that is a separate fact and must be
**measured end-to-end**, not assumed (commitment 3). Left unmeasured, "the system has no ceiling"
becomes the very unmeasured crutch that "no 2B ceiling" was before it was probed. So the roster
only earns its cost when routed performance is measured against **(a) the best single model** and
**(b) the oracle best-model-per-problem** on the same bar: when routed ≤ best-single the roster is
**not paying yet** and the router is the bottleneck — a gap to close, never a win to claim.

**THE PURSUIT (owner directive, 2026-07-01 — the standing operational doctrine; also
mirrored in `docs/PURSUIT.md`, `docs/IDEA-BANK.md`, `docs/IDEA-PLAYBOOK.md`).**
The deadline framing is retired. The pursuit is **indefinite and maximum-velocity**:
*"Can a Jetson-tier system reach Claude-Code-comparable capability?" is an OPEN EMPIRICAL
QUESTION* — answered by construction (close the gaps) or by evidence (map the walls),
never by assumption in either direction. The bar never lowers. Its standing elements:

- **The scoreboard — progress is these instruments and nothing else:** (1) the
  **daily-driver suite** — 80+ tasks through the CLI end-to-end, frequency-weighted by
  real usage, deterministic oracles, dev/holdout split — the parity number; (2) the
  **external hard bar** (SWE-bench-Live, growing stratified slice); (3) the
  **routed-system triple** (routed vs best-single vs oracle-per-task); (4) the **latency
  budget** (p50/p95 per command class, Jetson-measured); (5) the **amortization ratio** —
  % of tasks served from memory/deterministic paths/precomputation WITHOUT a full model
  solve (the measured signature that jigs compound); (6) the **shadow-mode parity log** —
  the owner's REAL Claude Code tasks logged locally and replayed against jcode, which as
  it accumulates becomes the headline parity instrument; (7) the living **Gap Map**
  (`docs/GAP-MAP.md`) — the full Claude-Code capability surface, every gap in exactly one
  state (`unmeasured → probed → lever-named → in-progress → closed(number) →
  wall(dated, evidence)`), steering all work by impact × tractability; (8) the **Foundry
  ship-log** (below).

- **The Roadmap — the official LIVING forward-plan artifact (`.jarify/ROADMAP.md`), bound here as a
  first-class Jarify governance layer (owner directive, 2026-07-04).** It fills the gap between this
  Prime Directive (fixed north-star intent) and per-spec tasks: it holds the FORWARD plan across
  specs — *which specs/requirements we intend to CREATE and IMPLEMENT next* — organized by horizon
  (NOW / NEXT / LATER / PARKED), each item tied to a scoreboard number or measured gap by impact ×
  tractability. It uses the Gap Map paradigm (item 7 is its measured-findings appendix). It is
  **LIVING and UNBOUNDED**: the convergence loop reads it every tick, works the top NOW item through
  the Jarify workflow, marks landed/parks blocked, and when a horizon empties **regenerates the next
  horizon from this intent + the measured gaps** — the roadmap is NEVER "done" (an empty roadmap is a
  signal to look harder, never to stop). Governed by the **`jarify-manage-roadmap`** skill; created,
  maintained, and regenerated by the **`jarify-governance-loop`**. This is how the owner and the loop
  stay aligned on what is coming.

- **The velocity doctrine — "as fast as possible" means mechanically:** the budget is
  *information gained per Jetson-hour*. Probe before build (every hypothesis gets its
  cheapest falsifier first); **pre-registered kill criteria** (success/kill thresholds
  written BEFORE an experiment runs — no post-hoc rationalization); kill fast and log the
  negative (negatives are map data); parallel non-inference tracks while the device
  crunches (corpus building, spec work, tools, training-data curation, research); batch
  by model to avoid swap thrash; the experiment chain never idles.

- **The escalation ladder — for ANY failing class, escalate in cost order; a wall claim
  requires evidence at EVERY rung below it:** L0 prompt/format jig → L1 decomposition /
  deterministic control flow → L2 plane-shift (deterministic tool replaces the judgment)
  → L3 precise retrieval / single-fact injection → L4 experience recall (nearest verified
  solved analogue) → L5 reduction to a covered class → L6 routing / admit a new model
  (marginal coverage) → L7 LoRA specialist → L8 train a micro-model or distill → **L9 a
  DATED wall**: the evidence trail recorded, the missing capability class named, revisited
  on every new model release or method — **L9 is a bookmark, never a conclusion.**

- **The expanded arsenal (methods are unconstrained; acceptance criteria are not — every
  adoption passes the held-out gate):** the proven levers (deterministic control flow,
  test-gate as judge, plane-placement, generate-and-test, reductions, gold-free
  localization, SEARCH/REPLACE editing, verified-solution memory, gated reasoning,
  collaborative draft→critique→revise); a **semantic retrieval plane** (tiny embedders
  beside the roster — semantic code search, semantic recall over the solution store,
  API/doc retrieval — PRECISE injection only; generic context measured net-negative);
  **program-analysis deepening** (type inference, dataflow, coverage localization,
  property-test generation, mutation testing, AST-diff mining — inference-free
  fact-sources); **training our own models** (commitment 2, above); **decode control**
  (grammar-constrained generation — format-failure classes made unemittable);
  **always-on levers** no metered cloud tool can copy (overnight precomputation, a
  speculative drawer of pre-verified patches, per-repo adapters trained on the working
  repo's own history); and **novel orchestration**, invented freely and gated ruthlessly.

- **The self-distillation flywheel — how the same hardware gets indefinitely more
  capable:** the test gate turns compute into free VERIFIED training data (every solved
  task, every verified reasoning trace). Harness discovers → tests verify → the store
  accumulates → training distills into weights → the bare model absorbs the jig → the
  harness budget moves to the next gap. Nothing verified is ever thrown away: every
  (problem, attempts, outcomes, winning solution, model, scaffold-config) tuple persists.

- **The Foundry — build real systems, not just benchmark scores:** a standing portfolio
  of diverse real software (CLI tools, localhost services, data pipelines, a telemetry
  dashboard for jaros-code itself) built end-to-end BY jaros-code, the jarify way, on the
  owner's laptop and the Jetson. It measures what benchmarks cannot (bootstrap, config,
  long-horizon coherence, "did it ship"), yields verified solutions in new domains
  (flywheel fuel) and the true task distribution. Grading is binary and honest: it ships
  and runs, or it doesn't, plus a logged gap-list. **Safety envelope, non-negotiable:**
  dedicated sandbox workspace, localhost-only binding, containerized/resource-capped where
  possible, the existing shell gates stay (no external egress, no destructive ops, no
  secrets); any exception is a per-project owner-approved manifest, never a default.

- **The idea machinery — the pursuit never runs out of levers:** `docs/IDEA-BANK.md`
  holds the queued novel levers, each with its cheapest probe and pre-registered kill
  criterion; when the bank runs low (<5 live ideas), a wall stands, or monthly, the
  supervisor runs `docs/IDEA-PLAYBOOK.md` — nine MECHANICAL generation operators
  (asymmetry mining, failure-class inversion, boundary shifting, exhaust mining, analogy
  transplant, recombination, extremization, constraint tightening, research-raid
  translation) applied to artifacts the loop already maintains. Every generated card
  passes the filter: Jaros-native placement, sovereignty, cheapest probe named, kill
  criterion pre-registered, honesty check. Per-operator yield is tracked; the playbook
  itself is self-improving under the same rules.

- **Jaros-native, always:** every lever above lands AS Jaros — judgments as
  single-purpose agents emitting inert Decisions; every side effect (watchers,
  schedulers, training runs, index builds, Foundry deployments) as a deterministic tool
  with validate()/execute(), hash-chain logged and replayable. If a lever seems to need
  to escape Jaros, that is a signal to EXTEND Jaros, never to bypass it.

- **Reflexivity — jarify itself is an improvement target:** jaros-code is jarify's
  proving ground. When the loop exposes weakness in jarify's own mechanisms (spec
  formats, traceability, the skills, the governance heartbeat, Jaros primitives), fixing
  THAT is in-scope pursuit work under the same convergence discipline. The tool that
  converges the system is converged BY the system.

**And the 100% must itself be 100% honest** (commitment 3 binds the whole pursuit). The
number counts only if it is GENUINE generic solving, measured on **held-out** problems
the harness was never tuned on, from the **visible spec** (pass@1, or iteration against
the given examples) — never by fitting to the eval's hidden tests, detecting benchmark
items, hardcoding/memorizing answers, relaxing an oracle, or leaking expected outputs
into the solving prompt. **A dishonest 100% is worse than an honest 58%**: it proves
nothing and corrupts the only signal we have. If the number rises by anything other than
the model genuinely solving more, that is a defect to STOP and flag, not progress.

A deterministic, reproducible, capability-safe harness that decomposes development
into many small, single-purpose, well-scoped agent decisions — each backed by a
deterministic tool — can close the gap that a single large prompt to a single
large model cannot.

These commitments are ordered. A lower-numbered commitment is never weakened to
satisfy a higher-numbered one. When any specification, agent, tool, or change
would violate one, **STOP and flag the conflict** rather than silently resolving it.

1. **Two-plane discipline (inherited from the Jaros prime directive).**
   The model only ever writes recommendations on slips of paper: inert,
   JSON-serializable `Decision` data. A deterministic execution plane (the
   "clerk") decides whether and how each decision actually runs. The reasoning
   plane never performs a side effect directly — no file write, no shell command,
   no network call originates from a model output. Everything the harness *does*
   is a deterministic tool the clerk runs.

2. **Local-on-device-only, MULTI-MODEL, zero paid inference.**
   Every reasoning call goes to a local open-weight model served by **llama.cpp** on the
   **Jetson Orin Nano**, at **zero inference cost**. The binding constraint is **local + fully
   on-device + free** — *any* open-weight model is permitted **so long as it actually fits and
   runs on the Jetson** (within its ~8 GB budget). The constraint was never a specific parameter
   count; it is the device and the zero-cost, no-cloud rule. **No cloud model, no paid API,
   ever** — not as a fallback, not "just for the hard parts."

   **The constraint is the Jetson TIER, not this specific board (owner directive,
   2026-07-01).** "Jetson-fitting" means *inference on a ~$250-class owned edge device* —
   today the Orin Nano 8 GB. Sovereignty (local, owned, free, private) is the invariant;
   the silicon in that price class improves over time, and when the tier's hardware
   refreshes, the system re-baselines **honestly and labeled** (commitment 3) — never
   silently mixing numbers across devices. Published latency figures come from the
   Jetson-tier device only.

   **TRAINING OUR OWN MODELS is authorized and encouraged (owner directive, 2026-07-01) —
   it is MORE sovereignty, not less.** The zero-cost/no-cloud rule binds *inference*;
   *training* may use ANY owned hardware (the Jetson, the owner's PC/laptop). Three tiers,
   all first-class methods: **(a) LoRA/QLoRA specialists** fine-tuned on roster models for
   our exact grains and formats (a SEARCH/REPLACE emitter, a localizer, a test-writer — the
   adapter serves on the same Jetson base model); **(b) micro-models** (1–100M params:
   classifiers, rankers, calibrators) trained on the labeled data our own evals already
   produce for free; **(c) self-distillation** — training roster models on our own
   test-VERIFIED solutions and verified reasoning traces, so the bare model absorbs what
   yesterday needed scaffolding (the flywheel, below). Data sovereignty binds throughout:
   open datasets, our own verified-solution store, and synthetic data our system generates
   and test-verifies — nothing leaves the machines. A trained adapter/model enters the
   roster by the SAME admission rule as any candidate (marginal coverage, held-out proof) —
   training grants no exemption from measurement. **Dev-time parallelism** on owned
   hardware (extra copies of Jetson-fit models on the owner's PC to parallelize evals and
   training) is allowed and encouraged — the product's inference target stays the Jetson
   tier; latency truth stays Jetson-measured.

   **The system is a MULTI-MODEL harness (owner directive, 2026-06-28).** It maintains a
   **registry of Jetson-fitting models**, explored best-first (strongest-that-fits first). Each
   model carries a **profile**: the problem *classes* it is measured to handle, plus the **tools,
   agents, configuration, and prompts** that adapt the harness *to that model* — because a model
   is only as good as its adaptation (a naive model swap regressed, confirming the harness is
   co-adapted per model; the adaptation, not just the weights, is what performs). At solve-time a
   **model-router judge** classifies the problem and selects the model whose profile best covers
   that class (the routing choice is itself an inert `Decision`, commitment 1). The harness then
   **rewires itself** to the chosen model: it ensures that model is the one served on the Jetson
   (swapping the llama.cpp model if needed) and activates that model's tools / agents / config /
   prompts. When no current model's profile covers a class, the levers are (a) **deepen that
   model's adaptation** — decompose into smaller agent steps and stronger deterministic tools —
   and (b) **bring a stronger Jetson-fitting model into the roster and adapt it**; escalating to a
   cloud or paid model remains absolutely forbidden. **Gemma 4 2B (`e2b`)** is the founding
   roster member and the honest baseline anchor; it is kept, profiled, and routed to for the
   classes it is measured to handle well — not discarded.

   **Decomposition has two directions, not one.** "Decompose" does *not* only mean
   "more, tinier agents." Some judgements are boulders no model-side slice can shrink:
   when a grain's *core* is something a 2B genuinely cannot do — count lines, do
   arithmetic, comprehend that `<` should be `<=` — slicing it thinner just reproduces
   the same failure at smaller scale. The correct move there is to push the work across
   to the **execution plane**: replace the impossible judgement with a deterministic
   tool, often generate-and-test (try each candidate edit, keep the one the suite
   accepts). This shrinks the model's role to something it *can* do — or to nothing —
   and it is a *deepening* of Tenet 1, not an escape from the swarm. This was proven,
   not theorized: a single-operator off-by-one fix defeated every model-side
   decomposition (a line-locator hallucinated line 6 of a 3-line file; an OLD/NEW
   prompt reproduced the bug unchanged across 5 seeds), and a model-free boundary
   mutation-repair cracked it on the first candidate, byte-identically reproducibly.

   A third form of this same move is a **reduction**: a deterministic transform that maps a
   hard-class instance into a class the roster already covers — the covered model solves the
   reduced form and the clerk maps the answer back. Reductions are a **first-class grain
   type** (external review, 2026-07-01): building a library of them is a distinct lever for a
   class no current model reaches, alongside deepening a model's adaptation and growing the
   roster. Before reaching for a reduction or a bigger model, one cheap diagnostic settles
   which is needed: hand a failing instance the single missing fact it got wrong (the real
   contract/type/behavior) and see if it flips — if it flips, the wall is *comprehension* and
   a deterministic fact-injection grain fixes the class; if not, the FIRST lever is still a
   deterministic prosthetic — a reduction, or a tool that makes the concrete failure visible,
   localizes it, and feeds it back — and only once that plane is exhausted does a
   different-distribution model become the secondary lever.

3. **Reproducible & honest.**
   Every run is hash-chain logged and replayable to byte-identical state with zero
   model calls. The harness never hides, rounds away, or fabricates a result. A
   failing test is reported as failing; a skipped step is reported as skipped. The
   decision log is the auditable truth of what the system did and why.

   **Honesty is measured at the SYSTEM level, not just per model (external review,
   2026-07-01).** In a multi-model system every per-model profile can improve while the
   system does not, so the honest headline metric is **end-to-end routed performance**,
   reported against **(a) the best single model on the same bar** and **(b) the oracle
   best-model-per-problem**. Routed ≤ best-single means the roster is not paying and the
   router is the bottleneck; the routed-vs-oracle gap says whether the deficit is routing
   *accuracy* or genuine *coverage*. This is the honest guard on the system-level
   no-ceiling (commitment 2): reachability is not a performance claim.

   **Held-out sets wear out; expand the denominator and keep a never-read tier.** A scored
   corpus read on every decision is quietly tuned to, even under discipline, and a small n
   cannot carry the next claim. So the held-out discipline is two-tiered: a working
   held-out set AND a **never-read final-gate tier** — a repo or commit range left wholly
   untouched until a claim is final, then read once. As the corpus is exhausted it is
   **expanded** (more repos through the same red→green pipeline); too small an n is itself a
   defect to fix before publishing a number.

   **Published claims are part of this surface.** Once a figure is stated publicly it must
   stay reproducible: every published number records the exact commit/run behind it
   (`.launch/PUBLISHED.md`), added in the same commit that states it, and a figure that
   later fails to reproduce is a defect to fix or disclose — never to ignore.

4. **Spec-first, the jarify way — all the way down.**
   Behavior is governed by `.jarify` specifications. Code traces back to
   requirements through `index.json`. When specified behavior changes, the spec
   and the code change in the same commit. Stale specs are defects. This Prime
   Directive is the north star every other spec must serve and must never contradict.

   This is reflexive, and it is the product itself: **`jaros-code` is a code-building
   tool, and the way it builds a user's system IS the way jarify is used.** When it
   takes on a user's project it first captures *the user's* intent as a prime
   directive for that project, decomposes that intent into requirements / design /
   tasks, implements one scoped task at a time with single-purpose agents, validates
   each task against its requirement, and traces the resulting code back to the spec —
   the identical loop that produced `jaros-code` itself.

   **Jarify is the mechanism of convergence on the user's intent.** Because a 2B
   model left to free-form prompting drifts, jarify pins every actor — the operator,
   each single-purpose agent, every deterministic tool — to one explicit, written
   statement of what the *user* asked for. The spec is the shared north star that
   keeps the whole fleet pulling toward the user's actual goal instead of wandering.
   We build the harness the way we want the harness to build; the harness builds the
   user's software the jarify way so the result converges on what the user meant.

5. **Claude-Code-like experience.**
   The operator-facing experience should feel familiar and transparent: a terminal
   harness that shows what it is doing, what each agent decided, and what each tool
   ran — with the same kind of look and feel as Claude Code. But UX is the last
   tier: it never overrides correctness, reproducibility, or the model-only
   constraint above it.

**The method, stated once:** capability comes from *composition* — many small,
single-purpose agents each making one narrow judgement, wired together by
deterministic tools and a durable state machine — not from one big agent, one big
prompt, or a bigger model. Build the fleet wide and the tools sharp.

**Plane-placement is the core craft.** Composition alone is not enough; each grain
must be routed to the plane that can actually do it. For every grain ask: *is its core
a judgement Gemma 4 2B (`e2b`) can reliably make?* If yes (classify a bug class, pick a file,
transform-by-example, read a test result) → a tiny **agent**. If no (counting,
arithmetic, operator semantics, exhaustive search) → a deterministic **tool**, usually
generate-and-test. Agents and tools therefore grow *together*; the skill that closes
the Opus-4.8 gap is this triage, not a preference for either plane. When a model-side
pipeline keeps failing, the discipline is to run a raw single-call probe to see exactly
what the 2B emits, and — if the failure is genuine incomprehension rather than
formatting — move that grain to the execution plane rather than slicing it smaller. A
fallback that is net-negative (e.g. one that corrupts the file) is never shipped.

**The scale is the strategy.** We are explicitly aiming for a *swarm* — hundreds,
then thousands, then tens of thousands of agents — to reach Claude-Code-on-Opus-4.8
quality. Every agent is expected to be **single-purpose and tiny**: one narrow
judgement, a minimal prompt, a minimal output contract — never a generalist. The
intelligence is in the multitude and the wiring, not in any one agent. This swarm is
matched by an equally **extensive library of deterministic tools** (the verbs the
agents compose) and an **extensive suite of evaluations** (the proof we are
converging on the bar). More capability is always answered by *more, smaller* agents,
*sharper* tools, and *more* evals — never by a bigger model.

**The router OUTSIDE is DETERMINISTIC; the model judges only INSIDE.** The multi-model harness adds an
OUTER routing layer before any solving begins — and that layer is **deterministic, not a model
judgement** (external review + owner, 2026-06-28). The **router** classifies the problem's *class* from
deterministic features (standalone-vs-repo, has-examples, multi-file, size, language), consults the
deterministic **coverage tally** (which roster model is measured-best for that class), and — when more
than one model qualifies — lets the **deterministic test gate** pick the winner: try the candidates
best-measured-first and keep the first whose output passes the given/visible test. A model is **never**
used to route or to choose between models — model-as-judge was *measured* net-negative, and letting a
model pick models would re-introduce the very randomness multi-model exists to tame; the decorrelated
errors of diverse small models are harvested by the *test*, not by a meta-model. Escalation always goes
to the next-best **local, Jetson-fitting, free** model — **never** a cloud or paid model (commitment 2).
The reasoning plane's judgement is reserved for INSIDE the chosen model — its **orchestrator** (below)
composes *that model's* agents and tools to solve the task. Routing, the tally lookup, the test-gated
selection, and the rewire are all deterministic clerk operations (commitment 1) — hash-chain logged and
replayable — and a model's coverage is **earned by measurement** (a class is credited only on held-out
evidence); an unmapped or mis-routed class is a harness gap to close (better features, deeper per-model
adaptation, or a stronger roster model), never a model limit to accept.

**The composition is EMERGENT and NON-DETERMINISTIC — orchestrated by the model itself.** The swarm is
not one fixed pipeline. At solve-time the 2B acts as an **orchestrator** that judges which agents and
tools to apply next, in what order, and when the work is done — composing the proven grains emergently,
revisiting any of them as needed, and exploring **non-deterministically** rather than following one
hard-coded path. That choice is itself a `Decision` on the reasoning plane (commitment 1): the model
only *recommends* the next grain; the deterministic clerk runs it; and the run remains hash-chain logged
and byte-replayable (commitment 3) — non-deterministic *exploration*, fully *reproducible* once logged.
**The ultimate aim — and this is a most-important piece — is that this orchestrator makes the RIGHT
decision every single time.** Perfect next-step judgement is the asymptote we march toward and never
stop short of: every wrong orchestration choice is a harness gap to close, never a model limit to accept
(the founding assumption), until the system chooses correctly on every step of every real task — a bar
we approach forever and are never satisfied to have merely neared. **And all of it MUST run native on
Jaros** — every orchestration decision and every tool effect flows through the Jaros runtime (gate →
execute → hash-chain log → replay). Running on Jaros is non-negotiable: it is how the two-plane
discipline is *enforced* rather than merely intended, not an implementation detail.

**The deterministic plane is a PROSTHETIC for the model's reasoning (owner directive, 2026-07-07 — the
sharpest form of Tenet 1).** A small model has a real, per-model reasoning limit — but a deterministic
tool does the specific work the model cannot (make a failure VISIBLE, LOCALIZE it, verify, count,
search, generate tests, check invariants, feed the concrete failure back) and hands the model a narrow,
now-tractable judgment, so the model's genuine-but-bounded reasoning becomes *sufficient to work PAST
the cap.* The per-model cap is real; the SYSTEM (model + deterministic prosthetics) has none, because
for any hard class there is a missing prosthetic to build. Therefore the PRIMARY lever for any
hard-class failure is **build the missing deterministic prosthetic** — never "the model can't, wait for
a bigger one" (the forbidden drift), and only secondarily route to a stronger roster model. The mission
is to find the COMPLETE SET of prosthetics.

**The judge-orchestrator is a key piece of the system's success — and it is only ever as strong as the
deterministic plane that empowers it.** A 2B has far less reasoning than Opus, so the
right-decision-every-time bar is reached NOT by trusting the model more, but by **building out an
extensive library of deterministic Jaros tools — and the deterministic CHECKS that fire WHEN each tool
is called — for the orchestrator to wield.** Validation here means exactly that: every tool's
`validate()` gate runs a **deterministic check** before its `execute()`, verifying inputs,
preconditions, and whether the candidate is actually correct, so a wrong or unsafe model decision is
CAUGHT deterministically before it ever takes effect — this gate IS the clerk of commitment 1. Each tool
carries load the small model cannot bear (computing, searching, generate-and-test, constraining the next
choice to only safe/valid moves); each per-call check is the deterministic safety net under the model's
fallible judgement; the **evals** are the standing proof the net holds. The deterministic plane is what
turns a narrow model judgement into a correct decision. Relentlessly growing this library — the tools
AND the per-call deterministic checks that catch the orchestrator's mistakes, narrow its options, and
verify its work — is first-class, required work, the primary lever by which a small model reaches and
exceeds the Opus-4.8 bar.

**The convergence loop is a standing, supervised discipline — never finished.**
Reaching the bar is not a one-time build; it is a loop run continuously and owned by a
named supervisor whose job is to *keep the system converging on the ultimate intent:
replacing Claude Code on Opus 4.8.* The loop, run forever:

1. **Measure honestly** — run the evals (repair pass-rate AND generative self-vs-oracle
   fidelity), the growth census, and the wiring/orphan health. No flattering numbers.
2. **Diagnose, don't guess** — when something fails, probe the raw model output to find
   *which grain* failed and *why* before changing anything.
3. **Discover the next type of sand** — name the missing grain the failure demands.
   The mountain needs *many distinct grain types*, not many copies of one; a new failure
   class is a new grain to invent. Pull first from the IDEA-BANK's queued levers; when
   the bank is dry or the class resists its named levers, run the IDEA-PLAYBOOK's
   generation operators — discovery is mechanical, never blocked on inspiration.
4. **Place it on the right plane** — apply plane-placement triage: a judgement the 2B
   can make → a tiny agent; computation/search/arithmetic it cannot → a deterministic
   tool (often generate-and-test). Wire it so it actually fires (no orphans).
5. **Re-measure and prune** — keep only what raises a real metric; remove agents, tools,
   and evals that do not help. Net-negative changes are reverted, never shipped.

The supervisor **watches the system closely and corrects it** — the wiring, the agents,
the deterministic tools, the evals, **the model-router's class profiles, each model's
harness adaptation, the Jetson-fitting model roster, the trained adapters and
micro-models, the verified-solution store and its distillation pipeline, the Gap Map,
the Foundry portfolio, and the idea bank's health** — and treats the convergence
trend on THE PURSUIT's scoreboard (not activity) as the sole proof of progress. When a class is failing, the loop now
also asks: is this a gap in *this model's* adaptation, in the *router's* profile for it, or
does it need a *stronger roster model* — and measures the answer rather than guessing. This loop, and the supervisor's ownership of it, is itself
part of the intent: the system is never "done" until parity is proven on genuinely hard,
external problems.
