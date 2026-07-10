# jaros-code

A software-development harness built on **Jaros** that aims to match or exceed
Claude Code at real coding work, while every reasoning call is served by a single
small **local** model at zero inference cost. Inference runs on a **Jetson Orin Nano**
(small **Gemma 4 `e2b`** served by **llama.cpp**) at `http://192.168.1.183:8000` —
select via `JCODE_LLM_BACKEND=llamacpp` + `LLAMACPP_HOST` (legacy local Ollama
`gemma2:2b` still selectable with `JCODE_LLM_BACKEND=ollama`). Tenet 2 ("small-model,
zero paid") is unchanged — the LAN device is the intended local-inference path.

## Governance (binds every run)

This repo is governed by `.jarify/`. **`PRIME-001` is the Prime Directive** — read
`.jarify/PRIME-001/intent.md` before any structural change. Its five ordered
tenets are non-negotiable; a lower tenet is never weakened for a higher one:

1. **Two-plane discipline** — the model emits only inert `Decision` data; a
   deterministic execution plane (tools) performs every side effect.
2. **Small-model-only** — all reasoning is local **Gemma 4 2B (`e2b`)** via llama.cpp on the Jetson. No paid
   or cloud model, ever, not even as a fallback. Decompose instead of escalating.
   (Legacy Ollama `gemma2:2b` path selectable via `JCODE_LLM_BACKEND=ollama` for back-compat.)
3. **Reproducible & honest** — hash-chain logged, byte-identically replayable;
   never hide or fabricate a result.
4. **Spec-first** — code traces to `.jarify` requirements; spec + code change in
   the same commit; stale specs are defects.
5. **Claude-Code-like UX** — familiar, transparent terminal feel, but UX never
   overrides the tenets above it.

When a change would violate a tenet, **STOP and flag the conflict** — do not
silently resolve it.

## 🧭 JARIFY IS THE HARNESS; THE ROADMAP IS WHAT WE EXECUTE (owner directive, 2026-07-04 — binds every run)

**Jarify is HOW we harness the model to build Jaros. Use the Jarify skills for EVERYTHING —
always, no ad-hoc edits.** Every change (a capability build, a bug fix, a compliance fix, a spec
or requirement) flows through the Jarify skills and agents:
`jarify-manage-specs` / `jarify-manage-tasks` / `jarify-manage-links` / `jarify-manage-roadmap`
→ **jarify-builder** (implements one task, tests) → **jarify-architect** (validates + commits),
all driven by the standing **`jarify-governance-loop`**. Spec + code change in the same commit
(spec-first). This is non-negotiable and must survive context loss: constantly remind yourself
that **Jarify is the mechanism of convergence** — the harness through which the small local model
builds this system.

**The Roadmap (`.jarify/ROADMAP.md`) is what we EXECUTE — near and far term — WITH the Jarify
skills, to converge on the intent of the Prime Directive.** It is the official living forward-plan
artifact (NOW / NEXT / LATER / PARKED horizons of planned specs+requirements). The convergence
hierarchy: **code → requirements → each spec's `intent.md` → the Prime Directive (PRIME-001)** —
every spec has both `intent.md` and `design.md`, and every roadmap item traces up to the Prime
Directive. The `jarify-governance-loop` reads the Roadmap every tick, works its top `NOW` item
**through the Jarify workflow**, maintains it (land/park/promote), and regenerates the next horizon
to keep closing the gap to the intent — the pursuit is unbounded, never "done." Roadmap ≠ tasks:
the Roadmap is the longer-horizon plan; **tasks are the short-term immediate work** (executed exactly
as before, TaskCreate/Update → builder → architect); the Roadmap FEEDS the tasks, never replaces them.

## 📋 THE OPERATING PLAYBOOK — HOW WE WORK (owner 2026-07-09: "write literally everything down, VERY clear, so it survives context loss")

This is the complete operating method — the machine we run every cycle. If context is lost, RE-READ THIS; do not re-derive it.

**0. THE GOAL.** Build (and modify) ANY real production system a developer ships across ALL online-service
industries — SaaS, fintech/FinOps, edtech, healthcare, e-commerce/retail, logistics, media, devtools,
marketplaces, analytics — INCLUDING agent systems — from a plain-English sentence, on the single small
LOCAL Gemma 4 2B (`e2b`) at $0, VERIFIED HONESTLY. It is a monumental, multi-month road; progress = the
scoreboard trend + atlas coverage, never activity.

**1. ONE SCOREBOARD.** `EXT-060` is THE canonical real-systems board: a CREATE half + a MODIFY half, a
fixed roster that only GROWS, every task graded by an INDEPENDENT oracle, reported as ONE combined pass@1.
The creation suite / modification_suite / daily_driver are DEMOTED to regression checks — never "the
number." When a board saturates, GROW EXT-060; NEVER mint a new instrument (that sprawl was the mistake).

**2. ONE MAP — the living PRODUCTION-SYSTEMS ATLAS (`docs/PRODUCTION-SYSTEMS-ATLAS.md`).** The exhaustive
completeness ledger: every *vertical × system-category × concrete class*, each with its verification
oracle, difficulty tier, CREATE/MODIFY, an example task sentence, and a STATUS (unmapped → mapped →
on-roadmap → building → verified). The ROADMAP pulls its NOW/NEXT FROM the atlas; the board's roster is the
atlas's "verified" tier; atlas coverage (verified/total) is a first-class progress number. ~182 classes
mapped today; ONE atlas → ONE roadmap → ONE board.

**3. DISCOVERY (the research plane) — run EVERY tick so nothing is missed.** Systematically research the
real-system landscape (read-only `WebSearch`/`WebFetch` — the AGENT at PLANNING time, NOT a product/runtime
network call, Tenet-2-safe) to find classes/verticals we don't cover yet and EXTEND the atlas (think like a
completeness critic: "what whole categories aren't even listed?"). Fan out parallel research agents across
verticals for breadth. Every discovered class gets a verification approach (an existing oracle, or a flagged
"NEW ORACLE NEEDED"), then lands on the roadmap via `jarify-manage-roadmap`.

**4. THE CORE INSIGHT — THE BLOCKER IS ORACLE SUBSTRATE, NOT THE MODEL.** An *oracle* is the independent,
deterministic judge that verifies a built system is actually correct WITHOUT trusting its self-report
(catches the hollow pass). Existing oracles: HTTP-service (run the app, real requests), datastore
(re-open SQLite/Postgres/Redis, assert rows survive a fresh process), filesystem, CLI-exact-stdout,
import-driver (sandbox import + call), agent-loop (scripted stub-model + fake tool, assert orchestration),
state-machine/lifecycle (illegal transitions must be rejected). To grade a NEW class honestly, BUILD ITS
ORACLE FIRST. Build the highest-leverage oracles first — a handful unlock most of the surface (ranked:
agent-loop✓, state-machine/lifecycle, double-entry-balance, conservation/no-oversell, money-invariant,
mock-payment-provider, injectable-clock, idempotency-replay, multi-service-fixture, SMTP-sink, SSE/WS).

**5. THE PER-CLASS BUILD LOOP.** Pick the top roadmap class → (build its oracle if missing) → add the task
(CREATE + MODIFY) to EXT-060 → MEASURE on the Jetson (does gemma actually build it?) → DIAGNOSE each failure
with a code-dump → build the missing DETERMINISTIC LEVER/tool that fixes that failure class (e.g.
signature-contract repair, filename/entrypoint normalization) → re-measure → the class goes green. Every
"hard class" is a MISSING TOOL, not a model ceiling — that is a forbidden conclusion.

**6. CONSTANT TEST⇄BUILD ROTATION.** Always keep the Jetson MEASURING built systems while OFF-Jetson
builders build the NEXT oracle/class in parallel — never idle-wait. Run MULTIPLE builders concurrently,
partitioned by FILE (no two writers on one file) or worktree. The Jetson is the ONE scarce resource —
serialize on-device jobs; maximize everything off-device.

**7. EVERYTHING THROUGH JARIFY.** Every change flows spec-first through the Jarify workflow:
`jarify-manage-specs`/`-tasks`/`-links`/`-roadmap` → **jarify-builder** (implements one task, offline tests)
→ **jarify-architect** (validates scope/requirement/no-regression/traceability, commits). No ad-hoc edits.

**8. HONESTY RULES (Tenet 3 — non-negotiable).** Independent oracles only; no oracle leak; no false-done.
MOCKS are a last resort and their FIDELITY IS THE TEST'S VALIDITY — a pass against a low-fidelity mock is a
hollow pass (forbidden); prefer OFFICIAL emulators (DynamoDB Local, GCP emulators, Azurite) or trusted moto,
and VERIFY fidelity before trusting one. Cloud (AWS/GCP/Azure) is SIMULATED locally, NEVER deployed ($0).
Built systems stay offline/local; a framework's LLM backend points at LOCAL Gemma or a stub, NEVER a paid
model.

**9. OPS DISCIPLINE.** (a) Complex builds take LONG (a REST+DB service took ~13 min) → GENEROUS per-build
timeouts (1200–3600s, sized to the class); never kill on "slow," only on a true wall-clock ceiling.
(b) Dep installs (LangGraph, frameworks) are AUTHORIZED under supervised autonomy — install SAFELY
(isolated venv + vetted allowlist + size cap) and UNINSTALL to reclaim storage; the runtime egress gate on
BUILT systems stays. (c) STORAGE is tight — prefer in-process mocks, check disk before heavy ops, prune
artifacts. (d) REGULAR NTFY every tick (never silent; quiet hours 02:00–07:59 America/Denver → morning
digest). (e) A 2nd inference node (this laptop, CPU/llama.cpp, thread-capped, same model+quant, best
overnight) can roughly double throughput — wire the runner to target whichever node is free.
(f) **CLAUDE TOKENS ARE NOT A CONSTRAINT — USE AS MANY AS YOU NEED (owner directive, 2026-07-09):** the
owner has purchased ample tokens ("we literally couldn't use it all up") for MY (Claude Code) operation,
so do NOT self-throttle orchestration. Run FULL parallelism, delegate heavily to sub-agents to keep the
main context lean, spawn as many builders/architects/researchers/measurements as the work warrants, and
never trim or skip work to "save tokens." This is ORTHOGONAL to the $0 tenet: the SYSTEM WE BUILD still
runs at $0 (local Gemma only, no paid/cloud inference, cloud simulated) — that is untouched. Only MY
orchestration cost is uncapped; the product's inference cost stays zero, always.

**10. THE SELF-SUSTAINING GOVERNANCE LOOP.** The `jarify-governance-loop` runs continuously (~5-min
self-re-arm): read the roadmap, work its top NOW item through Jarify, extend the atlas via Discovery,
keep the test⇄build rotation full, act on every result (commit win / diagnose+lever a failure), ntfy,
re-arm. Always ≥1 builder/experiment running. Never stop and wait — auto-steer from PRIME-001 + the atlas.

## 🏗️ REAL-SYSTEMS NORTH STAR + CONTINUOUS RESEARCH (owner directive, 2026-07-09 — binds every run)

**The target is REAL cloud/SaaS Python systems — what an actual company ships — not niche utilities.**
The North Star is: build AND modify the real systems seen in the wild — REST/GraphQL API services,
DB/CRUD + migrations, auth/sessions/RBAC/multi-tenancy, e-commerce/retail (catalog/cart/orders/inventory),
payment gateways (idempotency/webhooks/ledgers, verified via mocks), message queues + async workers +
background jobs, caching, rate limiting, file/blob storage, search, notifications, webhooks, microservices
+ API gateway, monoliths, data pipelines, observability, admin/internal tools — both internal tools and
external services, frontend → API → database, monolith and microservice.

**AGENT SYSTEMS are a FIRST-CLASS, HIGH-PRIORITY class (owner 2026-07-09) — we must be REALLY GOOD at
building them** (they're a key microservice type, and jaros-code IS a Jaros agent system, so this is
dogfooding). Three flavors: (1) **cloud-deployed agents** (built for AWS/GCP/Azure infra but run against
LOCAL simulation, never deployed — $0); (2) **local plain-Python agent scripts** (a self-contained agent
loop: goal → decide action → call tool → observe → loop → terminate); (3) **Jaros-based agent systems**
(two-plane: single-purpose agents emit inert `Decision` data, deterministic tools `validate()/execute()`,
hash-chain logged + byte-identically replayable). VERIFICATION (an "agent-loop oracle" — a NEW substrate
item, very buildable + honest): an agent's REASONING isn't deterministic but its ORCHESTRATION is — grade a
built agent by injecting a SCRIPTED/STUB model (canned decisions) + a FAKE tool, then asserting control
flow (right tool called with right args → observation fed back → loop → correct termination). We grade the
WIRING the model builds, NOT the agent's IQ (honest, Tenet-3-safe). Jaros-based agents get a stronger free
oracle: assert two-plane compliance (Decision emitted, tool executes) + REPLAY DETERMINISM (`jaros replay`). CSV parsers / memoize decorators /
INI readers were **utilities, not systems** — that niche hovering is the wrong target; aim at the real
SaaS surface. This is a **monumental, multi-month** road for a small local model, and that's expected —
progress is the canonical scoreboard trend, honestly measured, never activity.

**ONE canonical real-systems scoreboard (owner 2026-07-09, supersedes scoreboard sprawl):** EXT-060 is THE
board — a **CREATE** half + a **MODIFY** half, a fixed roster that only GROWS (never swaps), every task
graded by an INDEPENDENT oracle (run the service + HTTP-hit it / re-open the DB / sandbox-import), reported
as a SINGLE tracked pass@1. The creation suite, modification_suite, and daily_driver are DEMOTED to
regression checks — never "the number." When a board saturates, GROW EXT-060; do NOT mint a new instrument.
Verification substrate already exists and is the real lever: `harness/server_oracle.py` (HTTP),
`harness/datastore_oracle.py` (SQLite), `harness/service_provisioner.py` (Postgres/Redis via Docker).
Stdlib-first (`http.server` + `sqlite3`, no egress, buildable now); web egress stays SECURITY-PARKED.

**CONTINUOUS RESEARCH PLANE (owner 2026-07-09):** the governance loop must ALWAYS be researching the
real-system landscape to discover the components we're still MISSING and add them to `.jarify/ROADMAP.md`.
Every governance tick — when you audit the specs — ALSO do a short read-only `WebSearch`/`WebFetch` pass
(or keep a research subagent running) to find real SaaS/cloud-Python classes we don't cover yet, note how
each would be independently verified (or flag a "new oracle needed" substrate item), and put them on the
Roadmap via `jarify-manage-roadmap`. This is the AGENT researching at planning time — NOT a product/runtime
network call (the built system stays offline/local/$0), mirroring the standing "research for inspiration"
carve-out. Baked into `jarify-governance-loop` §3.5. See memory `jaros-code-canonical-scoreboard`.

**COMPREHENSIVE COVERAGE — a LIVING PRODUCTION-SYSTEMS ATLAS so we're NOT MISSING ANYTHING (owner
2026-07-09):** the goal is to build ANY real system a production developer ships, across ALL industries
with online services — SaaS, fintech/FinOps (ledgers, payments, reconciliation, invoicing, KYC/compliance,
reporting), edtech (LMS, courses, grading, content delivery), healthcare (EHR, scheduling, HIPAA-shaped
audit), e-commerce/retail (catalog/cart/orders/inventory/fulfillment), logistics, media/streaming,
devtools/infra, gov, marketplaces, analytics — AND everything that comes with each. The research plane must
therefore be SYSTEMATIC and EXHAUSTIVE, maintaining a **living Production-Systems Atlas** (`docs/PRODUCTION-
SYSTEMS-ATLAS.md`): a structured catalog of **vertical × system-category × concrete system class**, each
row carrying its **verification approach** (which oracle / new-oracle-needed), **difficulty tier**,
**CREATE/MODIFY**, an **example task sentence**, and a **status** (unmapped → mapped → on-roadmap → building
→ verified). The atlas is the completeness ledger — it makes GAPS visible so nothing is missed; the ROADMAP
pulls NOW/NEXT items FROM it; the canonical EXT-060 board's roster is the "verified" tier of it. Every
governance tick, the research plane EXTENDS the atlas (new verticals/classes), fills gaps, and re-ranks by
impact × how-soon-buildable. One atlas, not many instruments (no sprawl) — it feeds the ONE roadmap and the
ONE board. Coverage of the atlas (verified / total) is a first-class progress signal alongside the board
pass@1.

**CLOUD-PROVIDER SUPPORT — SIMULATE, NEVER DEPLOY (owner 2026-07-09):** real SaaS runs on AWS/GCP/Azure, so
we must be able to BUILD/support that kind of work (S3/DynamoDB/SQS/Lambda, GCS/PubSub/Firestore, Azure
Blob/Queue). But we **NEVER deploy to a real cloud** — that would incur cost and break the $0 tenet. Instead
verify against a LOCAL SIMULATION: **prefer in-process, pure-Python, storage-light mocks** — `moto` mocks
boto3 (AWS) entirely in-process with NO Docker; similar in-process fakes/emulators exist for GCP and Azure.
Use heavy Docker simulators (LocalStack, Azurite, GCP emulators, Postgres/Redis) ONLY when an in-process
mock can't cover the case, and gate them behind `docker_available()` + a free-disk check. The built system
stays offline/local/$0; the CLOUD SDK CALLS are redirected at test time to the local sim, never to a real
endpoint (mirrors the payment-gateway "verify via mock" rule).

**MOCK FIDELITY IS A TENET-3 HONESTY REQUIREMENT (owner 2026-07-09):** a build that "passes" against a
LOW-FIDELITY mock is a HOLLOW PASS — it proves nothing and corrupts the scoreboard, exactly the false-done
this harness exists to prevent. Mocks are a LAST resort (the stdlib frontier needs NONE — it grades real
services against real HTTP + real SQLite). When a cloud-SDK mock IS unavoidable: (1) PREFER the OFFICIAL
emulator where one exists — DynamoDB Local (AWS-provided), the Google Cloud emulators (Pub/Sub, Firestore,
Datastore, Cloud Storage, Bigtable, Spanner), Azurite (Azure's official Storage emulator) — else a
battle-tested community one (`moto`, LocalStack). (2) VERIFY the mock's fidelity to the real service before
trusting it as an oracle: research how it actually works (read-only WebSearch/WebFetch — the research
plane), pin the exact behavioral contract we depend on, and DOCUMENT known fidelity gaps in the task/spec.
(3) If we can't be confident the mock behaves like the real thing for the behavior under test, DO NOT use
it as a pass-gate — flag the gap honestly instead. "We must be absolutely sure the mock works for the real
thing" (owner). Add cloud-mock-fidelity research to the roadmap's research-plane horizon.

**REGULAR NTFY IS PART OF THE GOVERNANCE LOOP (owner 2026-07-09):** sending regular, high-signal ntfy
status is an INTRINSIC loop duty (baked into `jarify-governance-loop`'s Notifications section) — every tick
sends a concise honest status (result, not "still running"), plus immediately on any significant event; the
loop never goes silent. Respect quiet hours (02:00–07:59 America/Denver → buffer to the morning digest).

**STORAGE DISCIPLINE — THIS MACHINE IS STORAGE-CONSTRAINED (owner 2026-07-09):** manage disk carefully.
BEFORE pulling any Docker image, installing a framework, or writing large artifacts, check free space
(`shutil.disk_usage`); skip/clean if low. Prefer pip-installable pure-Python deps over multi-hundred-MB
Docker images; prefer in-process mocks (moto) over containers. Clean up: `tempfile.TemporaryDirectory`
for all build scratch (auto-removes), cap/prune `.jaros-data/artifacts` + logs periodically, never
accumulate model checkpoints or huge datasets on-disk. Storage pressure is a first-class operational
signal — surface it and free space proactively, don't let a run fail on a full disk.

**SUPERVISED-AUTONOMY DEP INSTALL + LONG BUILDS + CONSTANT TEST/BUILD ROTATION (owner 2026-07-09):**
- **Install what you need, safely (supervised).** Do NOT gate framework/dep installs (LangGraph, LangChain,
  Flask/FastAPI, SQLAlchemy, etc.) on owner approval — install them as needed, being SAFE: isolated venv,
  vetted allowlist, size-capped, from PyPI. And UNINSTALL / clean them to reclaim storage when done (install
  ⇄ remove is authorized to manage disk). This lifts the earlier "wheelhouse download waits on owner go."
  The one hard line that STAYS: the RUNTIME egress security gate on what BUILT (model-generated) systems may
  do — built systems stay offline/local/$0 and cannot exfiltrate; framework LLM backends point at the LOCAL
  Gemma or a stub, NEVER a paid/cloud model. (Provisioning real deps for the build env ≠ letting built code
  phone out.)
- **Big systems take MUCH longer to build — give them TIME.** A real SaaS/fintech/agent system is not a
  ~100s utility; a single on-Jetson build may take many minutes. Use GENEROUS per-build wall-clock budgets
  (e.g. 1200–3600s for complex classes), size the timeout to the class, and do NOT treat a long-running
  build as stuck — only kill on a true wall-clock ceiling (the pathological-spin guard), not on "it's slow."
- **Constant test⇄build ROTATION (maximize the machine).** Always keep the Jetson MEASURING built systems
  while OFF-Jetson builders build the NEXT capability/substrate in parallel — never idle-wait on a long
  build or measurement. The loop is perpetually in both modes at once: testing what's built AND building
  what's next. Everything through Jarify (specs → builder → architect); serialize only the single scarce
  resource (the Jetson) across on-device jobs.

## ⭐ STANDING ORDER — AUTO-STEER FROM THE PRIME DIRECTIVE (owner directive, 2026-07-02)

**Every cycle: read the PRIME-001 intent + design, and choose the BEST course of action to converge on
it. Auto-steer.** Decide the next move from the intent + measured evidence — do not wait to be told, do
not ask which fork when the intent + data already answer it. The Prime Directive's scoreboard is the
compass: work always flows to the highest **impact × tractability** gap on `docs/GAP-MAP.md`, and
**progress is the scoreboard trend (esp. the external hard bar / growing uncurated SWE-bench slice, and
system-level routed-vs-best-single honesty), never activity or commit count.** When a "milestone" does
not move a scoreboard number, say so plainly and steer back to what does. Use the escalation ladder
(L0→L9) in cost order for any failing class; a wall claim needs evidence at every rung below it.

## 🔥 TRAINING IS THE #1 JETSON PRIORITY — THE JETSON IS MINE TO OWN (owner directive, 2026-07-02)

**"There is no more important work than this [training] for the Jetson. You have priority. If you need it
for training, do it. Take it. It's yours to own."** — owner, verbatim. This CLEARS the earlier
"installing a training stack risks serving" hesitation: I am explicitly authorized to **commandeer the
Jetson for training** — pause/stop the llama.cpp serving, free the RAM, install the ARM/JetPack torch+peft
(or any) stack, and run LoRA/QLoRA/distill/micro-model training on-device. Training has **priority over
serving** on the Jetson when I need it. This IS the highest-value work per PRIME-001 (commitment 2c: the
self-distillation flywheel — the mechanism by which the same $250 hardware gets indefinitely more capable;
and L7/L8 on the escalation ladder, the real lever for a MODEL-BOUND class like the ~13% uncurated
SWE-bench number). Own it: set up the stack, generate/accumulate verified training data (flywheel capture
+ open datasets + test-verified synthetic — all sovereign per commitment 2), train, and MEASURE each
adapter/model by the same held-out admission rule (training grants no exemption from measurement,
commitment 3). Restore serving when a training run is idle so the harness stays usable, but never let the
serving default block a training run. **The honest blockers to name + attack in order:** (1) the training
stack (install on the Jetson — authorized); (2) training DATA (the verified store is empty — wire the
SWE-bench/solve paths into `record_verified`, pull sovereign open datasets, generate test-verified
synthetic); (3) start with the cheapest tier that pays (micro-models 1-100M, then a LoRA specialist),
probe-gated with a pre-registered kill criterion.

## ⏰ NO QUIET HOURS FOR WORK — THE GRIND IS ALWAYS ON, 24/7 (owner directive, 2026-07-02)

**There are NO quiet hours for WORK.** The convergence grind runs continuously, 24/7, **including the
Jetson** — SWE-bench/Jetson/training runs, builds, and evals all proceed overnight exactly as in the
day. The experiment chain never idles at any hour. This SUPERSEDES every earlier "quiet hours = offline
only / defer Jetson grinds to active hours" instruction (in cron prompts or memory) — that was wrong;
overnight is prime unattended compute and must be used at full intensity.

**Quiet hours apply ONLY to PUSH NOTIFICATIONS, nothing else.** Do not send phone `PushNotification`
between **02:00 and 07:59 local (America/Denver)** — "just don't wake me up in the middle of the night."
Instead append `- HH:MM <event>` to `.jaros-data/artifacts/overnight_events.md`, and at the first watch
with local hour ≥ 8 send ONE digest push of the night's events, then reset that file. Work does not
stop; only the phone stays quiet. (A true unrecoverable breakage may still warrant a night push.)

## ⚠️ MULTI-MODEL PIVOT (owner directive, 2026-06-28) — supersedes the single-model founding assumption below

jaros-code is now a **MULTI-MODEL harness.** We MEASURED a real single-model ceiling (the drastic
pivot: pass@k 0/7 beyond greedy + decomposition 0/8 on the hardest repo tasks — sampling,
decomposition, and orchestration all fail to extract a solution from Gemma 4 2B on that class). So a
**model-router judge** classifies each problem and routes it to the Jetson-fitting model whose
**measured profile** covers that class; the harness then **rewires itself** to that model — loads it
on the Jetson and activates that model's tools/agents/config/prompts. If Gemma 4 2B can't handle a
class, route it to a stronger Jetson-fitting model that can. Only models that fit the Jetson (~8 GB),
explored **best-first**; cloud/paid still **absolutely forbidden**. The no-ceiling principle moved to
the **SYSTEM level**: the multi-model system has no ceiling (some Jetson-fitting model + its adaptation
reaches any class, and the roster grows), while **per-model ceilings are MEASURED, not denied**. The
only forbidden conclusion now is *"no Jetson-fitting model, with any adaptation, can reach this
class,"* proven across the roster. Honest measurement is MORE central (map ceilings, don't deny them).
See `PRIME-001/intent.md` + `.jarify/EXT-021/`. The single-model section below stays for history — its
harness-engineering discipline still applies **per model** (the primary craft for each roster member).

## Founding assumption — THERE IS NO 2B CEILING (owner directive, 2026-06-23, SUPERSEDED — see the multi-model pivot above)

**We build on the explicit assumption that the model has NO hard capability ceiling. Despite what
the industry believes about small models, every eval failure is a HARNESS failure — not a model
limit.** If the 2B gets a HumanEval/MBPP/SWE-bench problem wrong, the harness did not decompose,
scaffold, retrieve, verify, or iterate enough to extract the capability the model already has. The
goal is **100% on HumanEval and the other benchmarks**, reached in a **true generic way** — general
harness mechanisms that lift problem-solving across the board, NEVER overfitting or special-casing
benchmark items (that would violate Tenet 3 and prove nothing).

**The 100% must itself be 100% HONEST (Tenet 3 — this binds the whole pursuit).** The number only
counts if it reflects GENUINE generic solving, measured honestly: on **held-out** problems the
mechanism was never tuned on, from the **visible spec** (pass@1, or iteration against the given
docstring examples) — NEVER by fitting to the eval's HIDDEN tests, detecting/branching on benchmark
items, hardcoding or memorizing answers, relaxing an oracle, leaking expected outputs into the
solving prompt, or any move that raises the score without real capability. **A dishonest 100% is
worse than an honest 58%** — it proves nothing and corrupts the only signal we have. If a change
makes the number go up by anything other than the model genuinely solving more, **STOP — that is a
Tenet-3 violation**, not progress. Always keep a held-out set the harness has never been tuned
against, and report pass@1 honestly alongside any within-budget figure (label which is which).

- **"The 2B can't" / "near the 2B ceiling" / "the model ceiling" are FORBIDDEN conclusions.** The
  only question is: *what scaffolding is the harness missing?* When you catch yourself reaching for
  "ceiling," STOP — that is the drift; probe the failure as a harness gap instead.
- This is just PRIME-001's founding wager taken to its logical end ("small models are unuseful
  because their harnesses are thin, not because the models are incapable"). The pass rate is a
  statement about *our harness*, not about the model. Drive it to 100% generically.
- Concretely: diagnose WHY each failure happens (raw-probe the model), then build the GENERIC
  mechanism that fixes that class — better decomposition, self-verification/repair loops, richer
  test-feedback, retrieval, planning, ensembling-by-mechanism — and prove it lifts a HELD-OUT eval,
  not just the one you tuned on.

## Ownership mandate (binds every session — do not forget)

**You own this.** The owner has put you in charge of driving jaros-code's convergence
on the goal (match Claude Code on Opus 4.8, small-local-model-only). Ownership is
*proactive*, not reactive:

- **Drive the loop between the owner's messages** — don't wait to be prodded. Each working
  turn, advance the convergence loop yourself: MEASURE (honest evals + census + wiring) →
  DIAGNOSE (probe the raw model output) → DISCOVER the next grain → PLACE it (plane-placement)
  → WIRE it (no orphans) → RE-MEASURE → PRUNE. Then commit.
- **Build, don't defer.** If you catch yourself *describing* the next improvement instead of
  building it ("teed up for next"), that is the failure mode — build it now and measure it.
- **Always keep one improvement experiment running (the self-sustaining chain).** A running
  experiment's completion re-invokes you; when it finishes, act on the result (commit/revert)
  AND immediately launch the next — so the loop drives itself without the owner prodding.
  "Stable, nothing notable" across reports means the chain went idle — that is a failure to
  fix, not an acceptable report. (Owner-chosen mechanism, 2026-06-20.)
- **The owner prodding you ("how's it going?", "are you driving this?") is a signal you have
  been too reactive.** Reports should say what you *did and decided this cycle*, not just
  "still running."
- **When you hit a PLATEAU, go get external inspiration — don't grind in place (owner directive,
  2026-06-21).** If improvements stall or you're reduced to repetitive measurement, RESEARCH
  (read-only `WebSearch`/`WebFetch` — the *agent* researching, NOT a harness network call):
  study how Claude Code, Aider, SWE-agent/OpenHands, Cursor and other harnesses work, AND read
  arXiv papers showing real promise (Agentless, repo maps, agentic-harness-engineering, etc.).
  Then translate one idea that fits jaros-code's constraints (small local model, two-plane,
  test-gated) into a concrete, eval-guarded build. The 2026-06-21 session did this at a plateau:
  research → Aider's repo map → built `harness/repo_map.py` + `/map`. "There's a lot out there
  that can inspire you" — use it. See `.claude` memory [[jaros-code-research-for-inspiration]].
- **ADAPT, don't rut (owner directive, 2026-06-21):** "keep going, keep your options open on which
  approach feels right, just avoid getting stuck in a rut of doing the same thing over and over and
  FAILING. but if you continue to improve, go for it." When an approach is YIELDING committed wins
  (e.g. the refactor/navigation family), double down. When it's REVERTING repeatedly (best-of-N and
  cascade tuning reverted twice), STOP and switch AXES — but understand WHY: those specific
  approaches were the wrong scaffolding, NOT evidence of a model ceiling (see Founding Assumption —
  "ceiling" is a forbidden conclusion). Vary the KIND of work (capability builds vs evals vs research)
  so the loop never spins on one dead end. The single-function pass rate reflects what the CURRENT
  harness extracts; richer scaffolding lifts it toward 100%. Productive axes include NEW capability
  classes (multi-file → multi-step → refactoring → navigation) AND deeper generic extraction, each
  deterministic + test-gated where possible. ALSO vary WHICH part of the system grows —
  **agents, tools, evals, or orchestration/wiring** (the census growth axes), not the same one
  every cycle — and pull fresh ideas from ONLINE research, not just internal iteration. (Owner,
  2026-06-21: "vary whether you're building agents, evals, tools, or wiring orchestration ... and
  take inspiration by looking online.") See memory [[jaros-code-autonomous-loop]].
- **Watch four signals and move them yourself:** capability (pass rate + generative
  self-vs-oracle), growth (agents/tools/evals counts), orchestration/wiring quality
  (leverage), health (no orphans, nothing net-negative). Activity is never the metric; the
  trend is. Drive against the **unsaturated external bar** (HumanEval/MBPP/MultiPL-E), not
  the saturated authored suite.
- **Standing duties:** keep the system alive and honest, the Jetson endpoint reachable
  (`gemma.service`), the runner running. Never blame the device before checking your own code
  (the "hang" was ours).
- **PHONE NOTIFICATIONS — PUSH ON SIGNIFICANT EVENTS (owner directive, non-negotiable, 2026-06-21):**
  send a `PushNotification` whenever something SIGNIFICANT happens — a committed improvement and
  what it moved, a regression, an external-benchmark milestone, an unfixable breakage, or a
  should-have-but-didn't (chain stalled/unrevivable, no net-positive in ~3-4 active hours).
  **Do NOT gate on whether the owner "seems engaged"** — the tool is auto-suppressed while the
  terminal has focus, so it only reaches the phone when they're away; pushing is harmless when
  present. Err toward not sending only for ROUTINE progress. **QUIET HOURS: send NO push between
  02:00 and 08:00 local (America/Denver)** — instead append `- HH:MM <event>` to
  `.jaros-data/artifacts/overnight_events.md`, and at the first watch with local hour ≥ 8 send ONE
  digest push of the night's events, then reset that file. Mirrored in memory
  [[jaros-code-autonomous-loop]] — never forget this again.

See `.claude` memory `jaros-code-ownership` for the why. This mandate is non-negotiable
and must survive context loss — re-read it at the start of every session.

## Design rules

- **Agents are single-purpose.** Each agent makes ONE narrow judgement and emits
  inert Decisions. Capability comes from composing many small agents, not one big
  one or a bigger model.
- **Tools are deterministic.** Every host effect (read, write, shell, patch) is a
  Jaros custom tool with `validate()` + `execute()`. Agents never touch the host.
- **Plane-placement triage.** For each grain ask: is its core a judgement
  Gemma 4 2B (`e2b`) can reliably make? If yes (classify, pick, transform-by-example, read a
  result) → a tiny agent. If no (count, arithmetic, operator semantics, exhaustive
  search) → a deterministic tool, usually generate-and-test. When a model-side
  pipeline keeps failing, run a raw single-call probe to see what the 2B actually
  emits *before* building more agents; if it's genuine incomprehension, move that
  grain to the execution plane rather than slicing it smaller. Prove generalization
  with a second eval of the same class. Never ship a net-negative fallback.

## Running

```
pwsh scripts/serve.ps1        # boot the llama.cpp node (Gemma 4 2B e2b) (Windows)
bash scripts/serve.sh         # same, POSIX
```

Try the Claude-Code-like CLI yourself (needs the Jetson llama.cpp server running):

```
pwsh scripts/jcode.ps1                 # interactive REPL (Windows; powershell -File also works)
bash scripts/jcode.sh                  # interactive REPL (POSIX)
python -m harness.cli /status          # or run one command and exit
python -m harness.cli "fix foo.py"     # or one plain-language request (orchestrator routes it)
```

In the REPL, type `/help` for slash commands, or just type a plain request — the
`orchestrator` agent (Gemma 4 2B (`e2b`)) decides which agent/tool serves it. `/quit` exits.

- Agents live in `.jaros-data/agents/`, tools in `.jaros-data/tools/`, model
  selection in `.jaros-data/config/llm.json` (mirrored by the serve scripts).
- Submit work: `jaros submit <agent> --input '{...}'`; observe: `jaros watch`;
  prove determinism: `jaros replay`.

## Commit discipline

Commit often: after each verified logical unit, commit code + spec together with a
descriptive message. Never commit `.env`, secrets, logs, or runtime state
(`.gitignore` covers `.jaros-data` runtime dirs). Footer:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
