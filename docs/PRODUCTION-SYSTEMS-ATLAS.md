# Production-Systems Atlas — jaros-code Completeness Ledger

**Status:** living planning artifact (a coverage ledger, like `docs/GAP-MAP.md`) — **NOT product code.**
**Last assembled:** 2026-07-09 · **Wave-1 OSS-decomposition expansion:** 2026-07-10 (§3.4, +73 classes) · **Wave-2 selfhosted-ecosystem expansion:** 2026-07-10 (§3.5, +50) · **Wave-3 industry-vertical expansion:** 2026-07-10 (§3.6, +60 — six NEW verticals) · **Wave-4 infra/integration pattern layer:** 2026-07-10 (§3.7, +33) · **Wave-5 agent-cluster expansion:** 2026-07-10 (§3.1 A11–A40, +30) · **Wave-6 not-covered-backlog sweep:** 2026-07-10 (§3.8, +57) · **Wave-7 engineering-blog mining:** 2026-07-10 (§3.9, +21) · **Wave-8 Python-library/tooling ecosystem:** 2026-07-10 (§3.10, +41 — the reusable import-time leaf-component layer) · **Sources:** `.jaros-data/artifacts/atlas/{saas_devtools,fintech_finops,verticals}.md` + `.jaros-data/artifacts/saas_taxonomy_research.md` (folded in / reconciled below) + read-only GitHub/OSS product research (§3.4 provenance note).

---

## 1. Intent — what this atlas is and how it steers the loop

This is **THE catalog of every real production system** a developer ships, across every vertical we
target. It exists so the roadmap **misses nothing** and so "how much of the real world can jaros-code
build?" becomes a **measured coverage number** instead of a vibe.

**One atlas → one roadmap → one board (no sprawl):**

- **The atlas** (this file) is the completeness universe: every class, tagged with an oracle, a
  difficulty tier, create/modify, stdlib-buildability, and a **status**.
- **The ROADMAP** (`.jarify/ROADMAP.md`) pulls its **NOW / NEXT** horizons *from* this atlas — the
  atlas is the backlog the roadmap prioritizes against; the roadmap never invents classes the atlas
  doesn't hold.
- **The EXT-060 board** is the execution surface; its **roster of built+verified systems is this
  atlas's "verified" tier.** A class is `verified` here only once the board has it green under a real
  oracle.

**Coverage (verified / total) is a first-class progress signal** — it belongs on the scoreboard
next to the SWE-bench slice. Activity (commits, "mapped" rows) is not progress; a rising
**verified** count under honest oracles is. **The substrate (the oracles) is the lever**, not the
individual builds: each new oracle flips a whole sub-cluster from `mapped` to buildable (see §4).

Everything here stays **offline / local / $0** at solve time. Payment providers, carriers, IdPs,
SMTP, CDNs, cloud queues are **simulated in-process** (high-fidelity mocks / fixtures), never
deployed — Tenet 2/3 clean.

> **🛰️ RESEARCH PLANE — CONVERGED (2026-07-10).** Eight independent research waves have now mapped
> **~547 classes** across every targeted vertical *plus* the reusable import-time leaf-component layer
> (parsers/validators/codecs/ADTs/algorithms), with **zero new oracle KINDS** required beyond the §4
> table (waves 5–8 each confirmed the vocabulary is complete-in-kind). **The mapping frontier is no
> longer the bottleneck** — the bottleneck is now **BUILDING mapped classes onto the EXT-060 board**
> (moving the `verified` tier, still ≈ 5+1 / 547). Future discovery research is therefore a
> **low-priority top-up**, not the active frontier: a possible **Wave-9** would sweep the remaining
> awesome-python component pockets (`pyparsing` grammars, `python-stdnum` national-ID formats,
> `phonenumbers`-style locale tables, `shapely`-lite geometry predicates) and should expect the same
> **import-driver-only, diminishing-but-nonzero** pattern — no new substrate. Spend effort on the
> board, not on more mapping.

---

## 2. Coverage summary

### 2.1 Totals

| Metric | Count |
|---|---|
| Raw class rows across the 3 slices | **199** (SaaS/devtools 80 · fintech/finops 59 · verticals 60) |
| Cross-slice duplicates reconciled | **~17** (see §2.4) |
| Wave-1 OSS-decomposition additions (§3.4, 2026-07-10) | **+73** (G1–G73, deduped against all prior rows) |
| Wave-2 selfhosted-ecosystem additions (§3.5, 2026-07-10) | **+50** (81 staged − 31 final-dedupe drops — wave 1 mined the same OSS space; see §3.5 dedupe record) |
| Wave-3 industry-vertical additions (§3.6, 2026-07-10) | **+60** (62 staged − 2 drops; **six entirely NEW verticals**: Gov/Civic, Legal, Proptech, Agriculture, Energy/Utilities, Insurance) |
| Wave-4 infra/integration pattern additions (§3.7, 2026-07-10) | **+33** (44 staged − 11 drops vs wave-1 G-rows + S-rows; see §3.7 dedupe record) |
| Wave-5 agent-cluster additions (§3.1 A11–A40, 2026-07-10) | **+30** (all 30 staged survived final dedupe; stager pre-dropped 18 near-dups) |
| Wave-6 not-covered-backlog additions (§3.8, 2026-07-10) | **+57** (63 staged − 6 cross-wave drops; stager pre-dropped 16 vs G-rows) |
| Wave-7 engineering-blog additions (§3.9, 2026-07-10) | **+21** (EB1–EB21; all 21 staged survived final dedupe — the stager pre-dropped ~35 vs the full atlas, the heaviest overlap of any wave, as predicted) |
| Wave-8 Python-library/tooling additions (§3.10, 2026-07-10) | **+41** (PL1–PL41; ~34 pre-dropped by the stager against the ADT/parser/calculator leaf rows + trivial-stdlib leaves; all 41 survivors carry an explicit ≠ distinction from their nearest atlas neighbor — final-dedupe added 0 further drops. The **first wave aimed at the reusable import-time COMPONENT layer** — parsers/validators/codecs/ADTs/algorithms/calculators; the most import-driver-PURE slice in the atlas) |
| **Distinct production-system classes** | **≈ 547** |
| Stdlib-buildable-now (zero deps, offline) | **≈ 540 / 547 (~99%)** (all 41 wave-8 leaf components are pure-stdlib) |
| Needs a 3rd-party dep (all have a stdlib/simulated path) | **~7** (CAMT/OFX/MT940 parse, NACHA validator, real broker, Postgres/Redis wire, DKIM full RSA sign (X40 — canonicalization itself is stdlib) — Docker-backed oracles exist) |

### 2.2 Per-vertical / cluster counts

| Vertical / cluster | Classes | Slice source |
|---|---|---|
| SaaS-core (API, auth, rate-limit, jobs, webhooks, billing, observability, storage, search) | 60 | `saas_devtools.md` #1–#70 (non-agent) |
| DevTools / Infra / CI-CD / dev-platform | 10 | `saas_devtools.md` (devtools rows) |
| **Agent / LLM-orchestration cluster** | **10** | `saas_devtools.md` A1–A10 |
| Fintech / payments / ledger / markets | 41 | `fintech_finops.md` #1–#41, #53–#59 |
| FinOps / cloud-cost | 10 | `fintech_finops.md` #42–#52 |
| EdTech | 11 | `verticals.md` (EdTech) |
| Healthcare | 9 | `verticals.md` (Healthcare) |
| E-commerce / Retail | ~19 | `verticals.md` (E-comm) |
| Logistics | 7 | `verticals.md` (Logistics) |
| Media / Streaming | 7 | `verticals.md` (Media) |
| Marketplaces | 6 | `verticals.md` (Marketplaces) |
| Cross-cutting infra (shared, build-once) | ~4 | `verticals.md` (cross) |
| **Wave-1 OSS decompositions** — observability/error-tracking 9 · product analytics 7 · collaboration+community 9 · scheduling 6 · workflow/automation 6 · ERP/HR/internal-ops 5 · support desk 4 · marketing/email 3 · monitoring/status 3 · files/sync 4 · CMS/publishing 5 · IAM 3 · commerce/finance 2 · BI 3 · PM 2 · web/forms 2 | **73** | §3.4 (GitHub-mined) |
| **Wave-2 selfhosted/prosumer tier** — bookmarks 5 · feeds 6 · media organizers 5 · inventory/asset 4 · wikis 3 · notes 2 · passwords 2 · paste/share 3 · dashboards 2 · polls/forms 2 · recipes 3 · time-tracking 3 · helpdesk 2 · budgeting 2 · community/federation 2 · monitoring 1 · archiving 1 · tasks 1 · doc-mgmt 1 | **50** | §3.5 (awesome-selfhosted sweep) |
| **Gov/Civic (NEW vertical)** 12 · **Legal (NEW)** 7 · **Proptech (NEW)** 5 · **Agriculture (NEW)** 4 · **Energy/Utilities (NEW)** 4 · **Insurance non-health (NEW)** 3 | **35** | §3.6 (wave 3) |
| Wave-3 vertical depth — Healthcare +7 · Logistics +7 · EdTech +6 · Media +5 | **25** | §3.6 (wave 3) |
| **Wave-4 pattern layer** — identity/authz 6 · API surface 7 · webhooks/eventing 2 · jobs/incidents 2 · data movement 5 · billing/compliance-ops 4 · config/secrets/runtime 7 | **33** | §3.7 (wave 4) |
| **Wave-5 agent-cluster extension** — orchestration shapes 9 · model-I/O 5 · memory/context 2 · RAG decomposed 3 · guardrails/economics 5 · agent ops/platform 6 | **30** | §3.1 A11–A40 (wave 5) |
| **Wave-6 backlog sweep** — chat/NLU 3 · object-storage internals 2 · deep billing 2 · CI/CD+registries 5 · ATS 1 · genealogy 2 · maps/GPS 3 · IoT 2 · NVR 2 · DNS/VPN 3 · groupware/CalDAV 3 · CRM 4 · mail stack 3 · e-books/ILS 3 · backup 3 · GTFS transit 2 · payroll 3 · construction 3 · hospitality 2 · telecom BSS 2 · manufacturing MES 2 · emergency CAD 2 | **57** | §3.8 (wave 6) |
| **Wave-7 engineering-blog mining** — collab/sync-engine 6 (Figma/Linear/Notion/Slack/Discord) · traffic/infra 4 (Cloudflare/GitHub/Stripe/Segment) · marketplace/mobility 5 (Uber/Airbnb/DoorDash/Shopify) · comms/media/payroll 6 (Twilio/Netflix/Spotify/Dropbox/Gusto-class) | **21** | §3.9 (wave 7) |
| **Wave-8 Python-library/tooling ecosystem (reusable import-time leaf layer)** — data-structures/ADTs 9 (bloom/HLL/count-min/consistent-hash/trie/union-find/Fenwick/order-stat/interval) · text&format 8 (fuzzy-distance/phonetic/Aho-Corasick/num-to-words/inflector/diff-patch/template/readability) · serialization&codecs 7 (msgpack/bencode/TOML/CSV-RFC4180/fixed-width/canonical-JSON/base-N) · data-validation 3 (check-digit/IP-CIDR/format-validators) · date-time 2 (ISO-8601 duration/fiscal-calendar) · algorithms&engines 6 (Dijkstra/shunting-yard/spreadsheet-recalc/content-defined-chunking/Huffman-LZ77/checksums) · numeric-units 3 (unit-conversion/financial-functions/descriptive-stats) · files-paths 3 (glob-matcher/safe-path-join/MIME-detect) | **41** | §3.10 (wave 8) |

### 2.3 Status breakdown (current reality)

Status values: **unmapped** → **mapped** → **on-roadmap** → **building** → **verified**.

| Status | Count | Classes |
|---|---|---|
| **verified** (utility tier — real, but being demoted as "toys-are-the-floor") | 5 | retry-backoff-lib, memoize-lib, ini-config-cli, file-organizer, csv-etl (≈ atlas class **S45 ETL**) |
| **building** | 1 | **REST+DB CRUD service** (create+modify — first SaaS rung; service oracle just landed) |
| **mapped** | ≈ 541 | everything else in this atlas (incl. 73 wave-1 G-rows §3.4, 50 wave-2 SH-rows §3.5, 60 wave-3 W-rows §3.6, 33 wave-4 P-rows §3.7, 30 wave-5 A11–A40, 57 wave-6 X-rows §3.8, 21 wave-7 EB-rows §3.9, 41 wave-8 PL-rows §3.10) |
| on-roadmap | 0 (roadmap owns this; assigned as classes are promoted from §5/§6) | — |
| unmapped | 0 (this atlas is the completeness boundary; new discoveries append here) | — |

**Honest read:** the *verified* tier today is the small utility/leaf class (config/CLI/file/etl/
memoize/retry). It is **real but demoted** — those are the FLOOR, not the frontier. The frontier is
the first **service** rung (REST+DB CRUD, `building`) and the **agent** cluster — whose gate has
**lifted: the agent-loop oracle is LANDED** (`harness/agent_oracle.py`, commit `2ee7efa`, validated
by the plain-tool-calling-agent class measuring 3/3), making A1–A40's agent-loop-gradable rows
**gradable TODAY**. Coverage today ≈ **5 verified + 1 building / 547** — the number this ledger
exists to move.

### 2.4 Reconciliation notes (dedupe)

`saas_taxonomy_research.md` (35 rows) is an **earlier, narrower** SaaS enumeration — it is **fully
subsumed** by the SaaS/devtools slice and is retained only for its **oracle-substrate framing**
(fake-clock, SMTP-sink, mock-payment fixture, multi-service harness, cross-tenant leak probe), which
is merged into §4. Cross-slice duplicates collapsed to one canonical row: idempotency store
(S19=F11=V56), rate limiter (S7=V55), full-text search (S34/35=V54), notification fan-out (S31=V53),
tax engine (F31=V51), invoicing (S38=F20), escrow ledger (F55=V33), order matching (F38=V32),
webhook receiver (S13=F14), dunning (S40=F23), subscription/proration (S36–40 ≈ F21–23), mock-payment
webhook handler (S41=F12/14).

---

## 3. Master tables (per slice)

**Legend.** Tier: 1 stdlib-now · 2 stdlib-easy · 3 stdlib-moderate/stateful · 4 multi-component ·
5 hard/distributed. **Oracle (existing):** HTTP · DB (SQLite/Postgres/Redis) · FS · CLI (exact
stdout/rc) · IMPORT (import-driver) · AGENT (stub-model + fake-tool + transcript). **`NEW: …`** =
substrate gap (ranked in §4). Stdlib? yes / dep. Status per §2.3 (blank = mapped). Example task
sentences live in the source detail files (`atlas/*.md`) + the seed shortlist §6 — not duplicated
per row here to keep the ledger compact.

### 3.1 SaaS-core + DevTools/Infra  (`saas_devtools.md`)

| ID | Class | Category | Tier | C/M | Oracle | Stdlib? | Status |
|---|---|---|---|---|---|---|---|
| S1 | REST CRUD API (resource + DB) | API | 2 | C+M | HTTP+DB | yes | **building** |
| S2 | Auth: signup/login/session cookie | auth | 2 | C+M | HTTP+DB | yes | |
| S3 | JWT issue/verify + protected routes | auth | 2 | C+M | HTTP+IMPORT | yes | |
| S4 | Password hash + reset-token flow | auth | 2 | C+M | HTTP+DB | yes | |
| S5 | RBAC / permission middleware | auth | 2 | C+M | HTTP+IMPORT | yes | |
| S6 | Multi-tenancy row-scoping (isolation) | auth | 3 | C+M | HTTP+DB (leak probe) | yes | |
| S7 | Rate limiter (token-bucket/window) | rate-limit | 2 | C+M | HTTP + NEW:clock | yes | |
| S8 | Quota / usage-counter enforcement | rate-limit | 2 | C+M | HTTP+DB | yes | |
| S9 | In-process TTL/LRU cache | caching | 1 | C+M | IMPORT | yes | |
| S10 | Cache-aside read-through wrapper | caching | 2 | C+M | IMPORT | yes | |
| S11 | Feature-flag evaluation service | feature-flags | 2 | C+M | HTTP+IMPORT | yes | |
| S12 | Outbound webhook dispatcher (HMAC) | webhooks | 3 | C+M | HTTP(fixture recv)+DB | yes | |
| S13 | Inbound webhook receiver (verify+dedup) | webhooks | 2 | C+M | HTTP+DB | yes | |
| S14 | Background job queue + worker | jobs | 3 | C+M | DB+IMPORT | yes | |
| S15 | Cron/interval scheduler | jobs | 2 | C+M | NEW:clock | yes | |
| S16 | Retry w/ backoff + dead-letter queue | jobs | 3 | C+M | DB+IMPORT | yes | |
| S17 | In-memory pub/sub / event bus | messaging | 2 | C+M | IMPORT | yes | |
| S18 | Append-only event log / sourcing | messaging | 3 | C+M | DB+IMPORT | yes | |
| S19 | Idempotency-key store + middleware | API | 2 | C+M | HTTP+DB | yes | |
| S20 | Pagination / filter / sort | API | 2 | C+M | HTTP | yes | |
| S21 | Schema migration runner (up/down) | db/migrations | 3 | C+M | DB (schema assert) | yes | |
| S22 | Audit-log / activity trail | audit | 2 | C+M | DB+HTTP | yes | |
| S23 | Health/readiness endpoint | observability | 1 | C+M | HTTP | yes | |
| S24 | Metrics + `/metrics` (Prometheus text) | observability | 2 | C+M | HTTP + NEW:expo-parse | yes | |
| S25 | Structured JSON logging middleware | observability | 1 | C+M | CLI/FS | yes | |
| S26 | Request-tracing / correlation-ID | observability | 2 | C+M | HTTP+IMPORT | yes | |
| S27 | API-key issue/verify/revoke | dev-platform | 2 | C+M | HTTP+DB | yes | |
| S28 | Config loader (env+file+validate) | config | 1 | C+M | IMPORT+FS | yes | |
| S29 | Secrets manager (encrypted-at-rest) | secrets | 2 | C+M | DB/FS+IMPORT | yes | |
| S30 | Email/notification sender (templated) | notifications | 2 | C+M | NEW:SMTP-sink | yes | |
| S31 | In-app notification feed (fan-out) | notifications | 2 | C+M | HTTP+DB | yes | |
| S32 | File/blob upload + storage | storage | 3 | C+M | HTTP+FS | yes | |
| S33 | Presigned-URL / signed-download tokens | storage | 2 | C+M | HTTP+IMPORT | yes | |
| S34 | Full-text search (SQLite FTS5) | search | 3 | C+M | HTTP+DB | yes | |
| S35 | Faceted / ranked search (BM25) | search | 3 | C+M | IMPORT | yes | |
| S36 | Billing: subscription state machine | billing | 3 | C+M | DB+HTTP + NEW:state-machine | yes | |
| S37 | Metering / usage aggregator | billing | 3 | C+M | DB+IMPORT | yes | |
| S38 | Invoice generator (lines+totals+tax) | billing | 3 | C+M | IMPORT + NEW:conservation | yes | |
| S39 | Proration calculator (mid-cycle) | billing | 3 | C+M | IMPORT (exact math) | yes | |
| S40 | Dunning / failed-payment retry SM | billing | 3 | C+M | DB+IMPORT + NEW:clock | yes | |
| S41 | Payment-provider webhook handler | billing | 3 | C+M | HTTP+DB + NEW:mock-payment | yes | |
| S42 | Coupon / discount / entitlement engine | billing | 3 | C+M | IMPORT | yes | |
| S43 | Admin dashboard / internal CRUD | admin | 3 | C+M | HTTP+DB | yes | |
| S44 | CLI operational tool (subcommands+rc) | cli | 2 | C+M | CLI | yes | |
| S45 | ETL / batch pipeline (E→T→L) | data-pipeline | 3 | C+M | DB/FS+IMPORT | yes | **verified** (csv-etl) |
| S46 | Streaming windowed aggregation | data-pipeline | 3 | C+M | IMPORT | yes | |
| S47 | CDC / outbox pattern | data-pipeline | 4 | C+M | DB+IMPORT | yes | |
| S48 | Analytics / reporting rollup + API | analytics | 3 | C+M | HTTP+DB | yes | |
| S49 | A/B experiment assignment + metrics | experiment | 3 | C+M | IMPORT+DB | yes | |
| S50 | API gateway (route+auth+limit compose) | gateway | 4 | C+M | NEW:multi-service | yes | |
| S51 | Reverse proxy / load balancer | gateway | 3 | C+M | NEW:multi-service | yes | |
| S52 | Circuit-breaker service client | microservices | 3 | C+M | IMPORT+HTTP | yes | |
| S53 | Service registry / discovery | microservices | 3 | C+M | HTTP+DB | yes | |
| S54 | GraphQL-style query resolver | API | 3 | C+M | HTTP | yes | |
| S55 | WebSocket / SSE push service | API | 3 | C+M | NEW:streaming-client | yes | |
| S56 | OAuth2 authorization-server flow | auth | 4 | C+M | HTTP + NEW:protocol | yes | |
| S57 | OAuth2 client / SSO (relying party) | auth | 3 | C+M | HTTP(fixture IdP)+DB | yes | |
| S58 | SAML / OIDC SSO integration | auth | 4 | C+M | HTTP + NEW:protocol | dep(SAML) | |
| S59 | TOTP / 2FA enroll + verify (RFC6238) | auth | 2 | C+M | IMPORT (test vectors) | yes | |
| S60 | Distributed lock / leader election | infra | 3 | C+M | DB/IMPORT + NEW:concurrency | yes | |
| S61 | Message-queue broker (SQS-shape) | messaging | 4 | C+M | HTTP/IMPORT+DB | yes | |
| S62 | Deploy/release tool (blue-green) | ci/cd | 3 | C+M | FS+CLI | yes | |
| S63 | CI pipeline runner (stages/gating) | ci/cd | 3 | C+M | CLI+FS | yes | |
| S64 | IaC apply/plan reconciler | ci/cd | 4 | C+M | FS/DB (desired-vs-actual) | yes | |
| S65 | Hand-rolled SDK / client library | dev-platform | 3 | C+M | IMPORT + NEW:multi-service | yes | |
| S66 | Docs / OpenAPI spec generator | dev-platform | 2 | C+M | FS+IMPORT | yes | |
| S67 | Data-export / GDPR download job | data-pipeline | 2 | C+M | FS/HTTP (zip) | yes | |
| S68 | Soft-delete + restore / sweeper | CRUD | 2 | C+M | DB | yes | |
| S69 | Optimistic-concurrency version updates | CRUD | 2 | C+M | HTTP+DB (409) | yes | |
| S70 | Saga / distributed-txn coordinator | microservices | 4 | C+M | IMPORT+DB + NEW:state-machine | yes | |
| **A1** | **LLM agent loop (plan→act→observe)** | agent | 3 | C+M | **AGENT** | yes | |
| **A2** | **Tool-registry + dispatch** | agent | 2 | C+M | **AGENT**+IMPORT | yes | |
| **A3** | **Agent-behind-an-API (`/chat`)** | agent | 3 | C+M | HTTP+**AGENT** | yes | |
| **A4** | **ReAct parser + step-cap/loop-guard** | agent | 3 | C+M | **AGENT** | yes | |
| **A5** | **Multi-agent orchestrator (router→workers)** | agent | 4 | C+M | **AGENT** | yes | |
| **A6** | **Agent memory / conversation store** | agent | 3 | C+M | DB+**AGENT** | yes | |
| **A7** | **RAG retrieve→augment→generate** | agent | 3 | C+M | IMPORT+**AGENT** | yes | |
| **A8** | **State-graph agent (LangGraph-shape)** | agent | 4 | C+M | **AGENT** | yes | |
| **A9** | **Human-in-the-loop approval gate** | agent | 3 | C+M | **AGENT** | yes | |
| **A10** | **Agent guardrails / schema validator** | agent | 2 | C+M | IMPORT+**AGENT** | yes | |

*The AGENT oracle is **LANDED** (`harness/agent_oracle.py`, commit `2ee7efa`; validated by the
plain-tool-calling-agent class measuring 3/3) — A1–A4 are the immediate seed (§6), and every
AGENT-oracle row above and below is gradable **today**.*

#### §3.1-W5 — Agent-cluster extension A11–A40 (wave 5, 2026-07-10)

**Provenance:** framework-shaped decomposition of the production agent/LLM-app stack (LangGraph,
CrewAI, AutoGen, OpenAI Agents SDK/Assistants, Pydantic-AI, smolagents, LangChain, A2A, MCP, NeMo
Guardrails, LiteLLM, Langfuse, mem0). Every LLM seam points at a **scripted stub model** or local
Gemma — never a paid API; grading targets **wiring/orchestration, never agent IQ** (Tenet-2/3
clean). All rows: status = `mapped`, stdlib = yes. Stager pre-dropped 18 near-dups of A1–A10 /
S14/S16/S17/S26/S35/S55/G32/G35 (e.g. sessions≈A6, ReAct scratchpad≈A4, assembled RAG≈A7, message
bus≈S17, replay-resume≈G32, automation graph≈G35, BM25≈S35); final-merge check also confirmed
A18 ≠ P12 (LRO), A24 ≠ P39 (dynamic config), A36 ≠ S37 (metering), A33 ≠ G67 (SQL guard).
**17 of these 30 rows are AGENT-oracle-gradable today** (oracle landed); the rest use existing
IMPORT/HTTP/DB oracles — only A39 waits on the streaming-client oracle (§4 #13).

| ID | Class | Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| A11 | Handoff-based agent switching (`transfer_to_X` tool swaps active agent, history carries over) | orchestration | 3 | C+M | **AGENT** | Build an agent runner where a triage agent, driven by a scripted stub model, hands a billing question off to a billing specialist agent by calling a transfer tool, and the transcript shows the specialist produced the final reply. | OpenAI Agents SDK (handoffs) |
| A12 | Group-chat conversation manager (speaker-selection policies + composable termination) | orchestration | 3 | C+M | **AGENT** | Build a group-chat coordinator where three stub-driven agents take turns selected round-robin, every message is delivered to all members, and the chat ends exactly when one agent says the agreed stop word. | AutoGen (GroupChatManager) |
| A13 | Sequential role-crew pipeline (task N's output injected into task N+1's context) | orchestration | 3 | C+M | **AGENT** | Build a crew runner where a researcher agent's stub answer is passed into the writer agent's prompt for the next task and the run report lists each task's role, input context, and output in order. | CrewAI (sequential) |
| A14 | Manager-delegation crew (decompose, delegate, validate results, bounded re-delegate) | orchestration | 4 | C+M | **AGENT** | Build a hierarchical crew where a stub manager assigns two sub-tasks to worker agents, rejects one result once, re-assigns it, and the transcript proves the re-delegation happened before the final summary. | CrewAI (hierarchical) — ≠A5: A5 routes once; this validates + re-delegates |
| A15 | Map-reduce fan-out dispatch (Send-style per-item worker spawn + deterministic reducer) | orchestration | 3 | C+M | **AGENT**+IMPORT | Build a dispatcher that, given five documents, launches five stub worker calls with one document each and a reducer that merges the five outputs into a single report in input order. | LangGraph (Send API) |
| A16 | Agent state checkpoint + time-travel fork (rewind to any checkpoint, edit state, branch) | orchestration | 4 | C+M | DB+IMPORT (replay determinism) | Build an agent runner that saves its state after every step to SQLite, then rewinds two steps back, changes one state value, and re-runs forward producing a divergent second branch while the original history stays intact. | LangGraph (time travel) — ≠G32: G32 resumes forward after a crash; this rewinds/edits/forks |
| A17 | Durable interrupt/resume pause point (serialize state, exit process, resume with injected value) | orchestration | 3 | C+M | **AGENT**+DB | Build an agent that pauses mid-run asking for a shipping address, survives a full process restart, and when resumed with the address completes the remaining steps exactly once. | LangGraph (interrupt) — ≠A9: A9 is an in-run gate; this is durable cross-process pause |
| A18 | Thread/run lifecycle service (queued→in_progress→requires_action→completed; thread locking; run deadline) | orchestration | 3 | C+M | HTTP + NEW:state-machine | Build an assistant-run service where starting a run locks its conversation, the run halts in a requires_action state until tool results are submitted by id, and submitting them lets it finish and unlock the conversation. | OpenAI Assistants (thread/run) — the canonical async submit-then-poll agent deployment shape |
| A19 | Inter-agent task protocol (A2A shape: capability cards, task lifecycle, typed message parts) | orchestration | 4 | C+M | HTTP + NEW:state-machine | Build two small HTTP agents where one discovers the other's advertised skills from its capability card, sends it a task, answers one input-required follow-up, and receives the completed result artifact. | Google A2A protocol |
| A20 | Output-parser library (format-instructions + strict typed `parse()` per format) | model-io | 2 | C+M | IMPORT | Build a parser toolkit where each parser emits the instruction text to append to a prompt and turns a model's reply into the typed value, rejecting replies that do not conform. | LangChain (output parsers) |
| A21 | Validation-retry repair loop (schema-fail error text fed back to stub model, bounded retries) | model-io | 2 | C+M | **AGENT** | Build a wrapper that asks a stub model for a structured record, detects the first reply is missing a required field, sends the error back for one correction, and returns the fixed second reply — with the transcript proving exactly one retry happened. | Pydantic-AI (ModelRetry) — ≠A10: A10 validates; this wires the retry conversation |
| A22 | Tool-schema derivation from function signatures (annotations+docstrings → JSON-schema; validate args) | model-io | 2 | C+M | IMPORT | Build a decorator that turns annotated Python functions into machine-readable tool descriptions and rejects a call whose arguments do not match the derived types. | Pydantic-AI / OpenAI function tools — ≠A2: A2 dispatches; this derives schemas |
| A23 | Streaming tool-call assembly (reassemble call from partial chunks, dispatch exactly once when JSON whole) | model-io | 3 | C+M | IMPORT+**AGENT** | Build a stream handler that receives a tool call split across seven chunks, assembles the argument text, executes the tool exactly once when the JSON is whole, and never dispatches on a partial fragment. | OpenAI/Anthropic streaming delta shape |
| A24 | Prompt-template registry (versions + env labels moving independently, rollback, strict interpolation) | model-io | 2 | C+M | DB+IMPORT | Build a prompt store where saving a template creates version 2 while the production label still serves version 1 until promoted, and rendering fails loudly if a placeholder has no value. | Langfuse / MLflow prompt registry |
| A25 | Context-window manager (deterministic token budget, sliding-window trim, stub-summarizer condensation) | memory | 3 | C+M | **AGENT**+IMPORT | Build a conversation manager that, when the counted size passes its limit, condenses the oldest turns into one summary message via a stub model and proves the final prompt contains the summary, the system prompt, and the newest turns only. | LangChain trim_messages / compaction — ≠A6: A6 stores turns; this decides what fits |
| A26 | Entity/fact memory with upsert (stub extractor → ADD/UPDATE/DELETE dedupe; query returns current facts) | memory | 3 | C+M | **AGENT**+DB | Build a memory service where "I moved to Denver" updates the previously stored city fact instead of adding a duplicate, and a later question retrieves exactly the current city. | mem0 / Zep entity memory |
| A27 | Document chunker library (fixed/recursive/sentence splitters; ≤max size, exact overlap, no text lost) | rag | 2 | C+M | IMPORT + NEW:conservation (no text lost) | Build a splitter toolkit where the recursive strategy breaks a document at paragraph then sentence boundaries, no chunk exceeds the limit, and rejoining the chunks reproduces the original text exactly. | LangChain text splitters |
| A28 | Vector-index sim + hybrid rank fusion (deterministic toy embedding, exact cosine top-k, RRF merge) | rag | 3 | C+M | IMPORT | Build a retriever that ranks passages by a deterministic embedding similarity, merges that ranking with a keyword ranking using reciprocal-rank fusion, and returns the exact fused top five. | Qdrant/Weaviate hybrid shape — ≠S35: S35 is lexical only; this adds vector sim + fusion |
| A29 | Citation-grounding checker (cited ids exist, quoted spans literal, uncited sentences flagged) | rag | 2 | C+M | IMPORT | Build a checker that takes a drafted answer with bracketed source references and the source passages, and reports exactly which claims are supported, which citations misquote their source, and which sentences cite nothing. | RAGAS faithfulness pattern |
| A30 | Rails pipeline (ordered input/output filter chain: pass / mask PII / block-before-model) | guardrails | 2 | C+M | **AGENT**+IMPORT | Build a filter chain where a message containing a phone number reaches the stub model with the number masked, and a message on a banned topic is refused without the model ever being called — proven by the call transcript. | NeMo Guardrails |
| A31 | Tool-call policy gate (allowlist + per-tool argument policy; structured refusal fed back into loop) | guardrails | 2 | C+M | **AGENT** | Build a gate where a stub agent's attempt to call the file-delete tool is refused by policy, the refusal is fed back as the observation, and the agent's permitted read call then executes normally. | NeMo agentic rails / SDK tool guardrails — ≠A10: A10 checks shape; this enforces authorization |
| A32 | Budget-cap run governor (accumulate per-run token/cost usage; abort at cap with exact totals) | guardrails | 2 | C+M | **AGENT**+IMPORT | Build a governor that stops an agent run the moment its accumulated usage passes the configured allowance and reports the exact step at which the limit was crossed. | OpenAI SDK usage limits / LiteLLM budgets — ≠A4: A4 caps steps; this caps spend |
| A33 | Restricted Python executor (AST-walking interpreter: import allowlist, op-count ceiling, no dunder escape) | guardrails | 4 | C+M | IMPORT | Build a safe evaluator that runs a submitted arithmetic-and-loops snippet, rejects any snippet importing the os module or reaching a million operations, and names the violated rule. | smolagents LocalPythonInterpreter |
| A34 | Tool-result sanitizer/truncator (size-cap with marker, secret-pattern redaction, field-wise elision) | guardrails | 2 | C+M | IMPORT+**AGENT** | Build an observation filter that shortens a huge tool output to the cap with a visible truncation notice and blanks anything matching an API-key pattern before the stub model sees it. | Claude Code / production agent hygiene |
| A35 | Agent span-tree tracer (nested run/model/tool spans with timing+tokens; deterministic JSON tree export) | observability | 2 | C+M | IMPORT | Build a tracer where one agent run with two tool calls exports a tree of one root span holding four correctly ordered child spans with their recorded inputs and token counts. | Langfuse / OTel GenAI — ≠S26: S26 propagates an id; this records the call tree |
| A36 | Token/cost accounting ledger (row per model call; per-key/per-day rollups; Σ key totals == grand total) | economics | 2 | C+M | DB + NEW:conservation | Build a usage ledger that records every stub model call and produces a per-team report whose line items add up exactly to the overall total. | LiteLLM SpendLogs shape |
| A37 | Model gateway with virtual keys + fallback (key allowances/permissions; failing primary → fallback chain) | platform | 4 | C+M | HTTP + NEW:multi-service | Build a gateway where a request under a restricted key is refused for a disallowed model, and a request whose primary backend errors is transparently answered by the fallback backend — with the routing decision recorded. | LiteLLM proxy/router |
| A38 | Agent trajectory eval harness (scripted cases → grade recorded trajectory vs expected; scorecard) | evaluation | 3 | C+M | IMPORT+**AGENT** | Build an evaluator that replays three scripted scenarios through an agent, compares which tools it called and in what order against the expected sequence, and prints per-case pass/fail with a precision score. | LangSmith/DeepEval trajectory evals — the agent-loop-oracle pattern as a product |
| A39 | Streaming agent event relay (SSE: token deltas + tool started/finished markers + terminal done, in order) | deployment | 3 | C+M | NEW:streaming-client | Build a service that streams an agent's reply as it is produced, interleaving tool-progress notices between text fragments, so the client receives every event exactly once and in order. | OpenAI/Anthropic streaming events — ≠S55: S55 pushes generic events; this relays the typed agent event grammar |
| A40 | MCP-shape tool server (JSON-RPC initialize handshake, `tools/list`, `tools/call` w/ arg validation) | platform | 3 | C+M | IMPORT+HTTP | Build a tool server a client can handshake with, ask for its tool catalog, and invoke a tool by name over JSON-RPC, getting a schema-validation error object for bad arguments. | Model Context Protocol — ≠A2: A2 is the in-process registry; this is the wire-protocol server |

*Subgraph composition (child-graph-as-node with interrupt bubbling) is folded into A8 as its natural
MODIFY variant, not a new row.*

### 3.2 Fintech / FinOps / Payments  (`fintech_finops.md`)

Fintech is the **best-gradable** slice: correctness = hard numeric invariants (no-float, debits==credits,
Σparts==whole, idempotency, hash-chain) an exact oracle checks with no fuzzy judgement.

| ID | Class | Category | Tier | C/M | Oracle | Stdlib? |
|---|---|---|---|---|---|---|
| F1 | Money value type (minor units, no float) | money-math | 1 | C+M | IMPORT + NEW:money-invariant | yes |
| F2 | Money allocation / split (remainder pennies) | money-math | 1 | C+M | IMPORT + NEW:conservation | yes |
| F3 | Rounding policies (banker's/half-up) | money-math | 1 | C+M | IMPORT | yes |
| F4 | Currency registry (ISO 4217) | money-math | 1 | C | IMPORT/CLI | yes |
| F5 | FX conversion (fixture rate, inverse-consistent) | fx | 2 | C+M | IMPORT + NEW:money-invariant | yes |
| F6 | Double-entry ledger core (debits==credits) | ledger | 2 | C+M | DB + NEW:double-entry | yes |
| F7 | Account balance derivation (Σ postings) | ledger | 2 | C+M | DB+IMPORT | yes |
| F8 | Chart of accounts / normal-balance rules | ledger | 2 | C+M | DB+IMPORT | yes |
| F9 | Journal + trial balance | ledger | 2 | C | CLI/IMPORT | yes |
| F10 | Hash-chained audit trail (tamper-evident) | audit | 2 | C+M | DB/FS + NEW:hash-chain | yes |
| F11 | Idempotency-key store | payments | 2 | C+M | DB + NEW:idempotency-replay | yes |
| F12 | Mock payment gateway (charge/PaymentIntent) | payments | 3 | C+M | HTTP + NEW:mock-payment | yes |
| F13 | Refunds (full/partial, ledger reversal) | payments | 3 | C+M | HTTP/DB + NEW:double-entry | yes |
| F14 | Payment webhook receiver (HMAC+dedup) | payments | 3 | C+M | HTTP + NEW:webhook-sign | yes |
| F15 | Webhook retry / dead-letter | payments | 3 | C+M | HTTP/DB+AGENT | yes |
| F16 | PaymentIntent state machine (3DS) | payments | 3 | C+M | IMPORT/HTTP + NEW:state-machine | yes |
| F17 | Capture / authorize (auth-capture) | payments | 3 | C+M | HTTP/DB | yes |
| F18 | Payment reconciliation (settlement vs ledger) | reconciliation | 3 | C+M | DB+CLI | yes |
| F19 | Settlement / payout batching (net==gross−fees) | settlement | 3 | C+M | DB + NEW:double-entry/conservation | yes |
| F20 | Invoicing (total==Σlines) | billing | 2 | C+M | IMPORT/FS + NEW:conservation | yes |
| F21 | Subscription billing + proration | billing | 3 | C+M | DB/IMPORT + NEW:proration/period | yes |
| F22 | Usage metering / rating | billing | 3 | C+M | DB+IMPORT | yes |
| F23 | Dunning / failed-payment retry | billing | 3 | M | DB+AGENT | yes |
| F24 | Wallet / stored balance (no-overdraft) | wallet | 2 | C+M | DB + NEW:non-negative-balance | yes |
| F25 | Transfers / P2P (atomic, balanced) | transfers | 2 | C+M | DB + NEW:double-entry | yes |
| F26 | Payouts / ACH file (NACHA fixed-width) | transfers | 4 | C | FS/CLI + NEW:NACHA-format | yes |
| F27 | Bank statement import (CSV/OFX/MT940/CAMT) | recon | 3 | C+M | FS+IMPORT | dep |
| F28 | Bank reconciliation (match) | recon | 3 | C+M | DB+CLI | yes |
| F29 | General-ledger close (period lock) | accounting | 4 | M | DB + NEW:period-lock/double-entry | yes |
| F30 | Financial statements (A==L+E) | reporting | 3 | C | CLI + NEW:accounting-equation | yes |
| F31 | Tax calculation engine | tax | 3 | C+M | IMPORT + NEW:conservation/rounding | yes |
| F32 | Fraud / risk scoring (rules) | risk | 3 | C+M | IMPORT+AGENT | yes |
| F33 | KYC / AML screening (rules, fixture) | compliance | 3 | C+M | IMPORT | yes |
| F34 | Transaction monitoring / velocity | compliance | 3 | C+M | DB/IMPORT+AGENT | yes |
| F35 | Disputes / chargeback workflow | payments | 3 | M | DB + NEW:state-machine | yes |
| F36 | Interest / amortization schedule (→0 exact) | lending | 2 | C | IMPORT/CLI + NEW:conservation | yes |
| F37 | Interest accrual (daily, day-count) | lending | 3 | C+M | IMPORT + NEW:rounding | yes |
| F38 | Order matching engine (price-time FIFO) | markets | 4 | C+M | IMPORT + NEW:order-book | yes |
| F39 | Portfolio / positions (avg cost, PnL) | markets | 3 | C+M | IMPORT + NEW:conservation | yes |
| F40 | Realized PnL / cost basis (FIFO/LIFO) | markets | 3 | C+M | IMPORT (exact per method) | yes |
| F41 | Trade/settlement lifecycle (T+N) | markets | 4 | M | DB + NEW:state-machine | yes |
| F42 | FinOps cost allocation (Σ==bill) | cost-alloc | 2 | C+M | DB/IMPORT + NEW:conservation | yes |
| F43 | Showback / chargeback report | cost-alloc | 2 | C | CLI + NEW:conservation | yes |
| F44 | FOCUS / billing-CSV ingest | ingest | 2 | C+M | FS/DB+IMPORT | yes |
| F45 | Cost anomaly detection (z-score/EWMA) | anomaly | 3 | C+M | IMPORT+AGENT | yes |
| F46 | Budget & alerting (thresholds) | budget | 2 | C+M | IMPORT/DB+AGENT | yes |
| F47 | Cost forecasting (run-rate/trend) | forecast | 3 | C | IMPORT (tolerance band) | yes |
| F48 | Rightsizing recommender | optimize | 3 | C | IMPORT+AGENT | yes |
| F49 | Commitment/RI/savings-plan analysis | optimize | 4 | C | IMPORT | yes |
| F50 | Unit economics / cost-per-X | reporting | 2 | C | IMPORT/CLI | yes |
| F51 | Tagging / governance policy check | governance | 2 | C+M | IMPORT/CLI+AGENT | yes |
| F52 | Cloud invoice/statement reconciliation | recon | 3 | C+M | DB+CLI | yes |
| F53 | Fee/pricing/rate calc (tiered/graduated) | pricing | 2 | C+M | IMPORT + NEW:rounding | yes |
| F54 | Statement generation (open+Σ==close) | reporting | 2 | C | CLI/FS + NEW:conservation | yes |
| F55 | Escrow / hold-release | ledger | 3 | C+M | DB + NEW:double-entry | yes |
| F56 | Multi-currency ledger (FX gain/loss) | ledger | 4 | C+M | DB + NEW:double-entry/money-invariant | yes |
| F57 | Payment routing / cascading (mock) | payments | 4 | C+M | HTTP + NEW:mock-payment | yes |
| F58 | Card BIN / Luhn validation / PAN mask | payments | 1 | C+M | IMPORT/CLI | yes |
| F59 | Double-spend / concurrency guard | ledger | 4 | C+M | DB + NEW:concurrency | yes |

### 3.3 Verticals — EdTech / Health / E-comm / Logistics / Media / Marketplaces  (`verticals.md`)

Honest signal here = **invariant preservation under a replayed (sometimes concurrent) op-script**
through the HTTP/datastore boundary — not "prints the right string." Leak-proof, non-memorizable.

| ID | Class | Vertical | Tier | C/M | Oracle | Stdlib? |
|---|---|---|---|---|---|---|
| V1 | Product catalog CRUD | E-comm | 2 | C+M | HTTP/DB | yes |
| V2 | Shopping cart | E-comm | 2 | C+M | HTTP (session) | yes |
| V3 | LMS course/module/lesson tree | EdTech | 2 | C+M | DB (hierarchy) | yes |
| V4 | Enrollment service (capacity/no-dup) | EdTech | 2 | C+M | DB + invariant | yes |
| V5 | Order service (place/read/cancel) | E-comm | 3 | C+M | NEW:state-machine | yes |
| V6 | Inventory + stock reservation | E-comm | 4 | C+M | NEW:conservation/no-oversell | yes |
| V7 | Appointment scheduling | Health | 3 | C+M | NEW:no-double-book (concurrency) | yes |
| V8 | Patient records (EHR-lite, FHIR-shaped) | Health | 3 | C+M | DB (versioned) | yes |
| V9 | Assignments + grading | EdTech | 3 | C+M | NEW:rule-engine/state-machine | yes |
| V10 | Quiz / assessment engine | EdTech | 3 | C+M | IMPORT+DB | yes |
| V11 | Product search & filtering | E-comm | 3 | C+M | HTTP (exact result-set) | yes |
| V12 | Pricing / discounts / coupons | E-comm | 3 | C+M | IMPORT (exact-total) | yes |
| V13 | Shipment tracking | Logistics | 3 | C+M | NEW:state-machine | yes |
| V14 | Progress tracking (monotonic) | EdTech | 2 | C+M | DB (monotonic invariant) | yes |
| V15 | Reviews & ratings | E-comm/Mkt | 2 | C+M | DB (aggregate) | yes |
| V16 | Subscriptions / entitlements | Media | 3 | C+M | NEW:entitlement-vs-plan | yes |
| V17 | Content / media library | Media | 2 | C+M | DB | yes |
| V18 | Playlists / watchlists | Media | 2 | C+M | DB (ordered) | yes |
| V19 | Prescriptions (med requests) | Health | 3 | C+M | NEW:Rx state-machine+interaction | yes |
| V20 | Lab results / observations | Health | 2 | C+M | DB + IMPORT (range→flag) | yes |
| V21 | Provider directory | Health | 2 | C+M | HTTP (search) | yes |
| V22 | Insurance claims adjudication | Health | 4 | C+M | NEW:state-machine+adjudication-rule | yes |
| V23 | HIPAA audit log + consent | Health | 3 | C+M | NEW:append-only audit+access-control | yes |
| V24 | Secure clinical messaging | Health | 2 | C+M | HTTP+DB | yes |
| V25 | Checkout / payment orchestration | E-comm | 4 | C+M | NEW:idempotent-payment saga+mock-payment | yes |
| V26 | Fulfillment / pick-pack-ship | E-comm | 3 | C+M | NEW:state-machine (shipped≤ordered) | yes |
| V27 | Shipping rates & label gen | E-comm/Log | 3 | C+M | IMPORT (rate) + sim carrier | yes |
| V28 | Returns / RMA | E-comm | 3 | C+M | NEW:state-machine+refund-conservation | yes |
| V29 | Recommendations (collab/content) | E-comm/Media | 4 | C+M | IMPORT (deterministic ranker) | yes |
| V30 | Marketplace listings | Marketplace | 2 | C+M | DB | yes |
| V31 | Buyer/seller accounts + roles | Marketplace | 3 | C+M | HTTP (RBAC invariant) | yes |
| V32 | Matching / bid-ask engine | Marketplace | 4 | C+M | NEW:price-time-priority | yes |
| V33 | Escrow / transaction ledger | Marketplace | 4 | C+M | NEW:double-entry | yes |
| V34 | Dispute resolution workflow | Marketplace | 3 | C+M | NEW:state-machine | yes |
| V35 | Seller ratings / reputation | Marketplace | 2 | C+M | DB (aggregate) | yes |
| V36 | Warehouse / WMS bin management | Logistics | 4 | C+M | NEW:conservation (Σbin==on_hand) | yes |
| V37 | Route optimization (VRP/TSP-lite) | Logistics | 5 | C+M | NEW:feasibility/cost-bound | yes |
| V38 | Delivery dispatch / assignment | Logistics | 5 | C+M | NEW:feasibility+no-double-assign | yes |
| V39 | Delivery scheduling / time-windows | Logistics | 4 | C+M | NEW:time-window feasibility | yes |
| V40 | Geofencing / zone lookup | Logistics | 3 | C+M | IMPORT (point-in-polygon) | yes |
| V41 | Carrier integration adapter | Logistics | 3 | C+M | HTTP (sim carrier) | yes |
| V42 | Transcoding job queue | Media | 4 | C+M | NEW:job-DAG/idempotent-retry | yes |
| V43 | Playback session / manifest gen | Media | 3 | C+M | HTTP (manifest+entitlement gate) | yes |
| V44 | Video comments + moderation | Media | 3 | C+M | DB + NEW:state-machine | yes |
| V45 | Certificates / credentialing | EdTech | 2 | C+M | FS+IMPORT (verifiable hash) | yes |
| V46 | Cohorts / sections / groups | EdTech | 2 | C+M | DB | yes |
| V47 | Proctoring / exam-integrity events | EdTech | 3 | C+M | NEW:event-timeline flag-rule | yes |
| V48 | Gradebook aggregation & weighting | EdTech | 3 | C+M | IMPORT (exact weighted grade) | yes |
| V49 | Content delivery / SCORM/xAPI pkg | EdTech | 3 | C+M | FS+IMPORT | yes |
| V50 | Wishlist / saved-for-later | E-comm | 1 | C+M | DB | yes |
| V51 | Tax calculation engine | E-comm | 3 | C+M | IMPORT (exact-tax) | yes |
| V52 | Loyalty / points / rewards | E-comm | 3 | C+M | NEW:points-ledger conservation | yes |
| V53 | Notification / event fan-out | cross | 3 | C+M | HTTP+DB (delivery invariant) | yes |
| V54 | Full-text search / inverted index | cross | 3 | C+M | IMPORT (exact ranked hits) | yes |
| V55 | Rate limiting / quota | cross | 2 | C+M | IMPORT + NEW:clock | yes |
| V56 | Idempotency-key store | cross | 2 | C+M | DB (dedup invariant) | yes |
| V57 | Waitlist / backorder queue | E-comm | 3 | C+M | NEW:FIFO-fairness/allocation | yes |
| V58 | Flash-sale / drop concurrency | E-comm | 4 | C | NEW:exactly-N-sold concurrency | yes |
| V59 | LTI 1.3 tool-launch handshake | EdTech | 4 | C+M | HTTP + NEW:protocol-conformance | yes |
| V60 | FHIR resource REST server | Health | 4 | C+M | HTTP + NEW:protocol-conformance | yes |

### 3.4 Wave-1 OSS-product decomposition additions (GitHub-mined, 2026-07-10)

**Provenance:** flagship production OSS products decomposed into their constituent components via
read-only web research (Sentry, PostHog, Plausible/Umami, Zulip/Mattermost, Discourse, Cal.com,
Temporal, Airflow/Dagster, n8n, Nextcloud, Etherpad, ERPNext/Odoo, Snipe-IT, Chatwoot, listmonk,
Uptime Kuma/Healthchecks, Grafana, Ghost/Strapi/Directus, Keycloak/Authentik, Medusa/Saleor,
Firefly III, Metabase/Superset, Plane/OpenProject, Shlink, Formbricks/LimeSurvey). Every row was
deduped against §3.1–§3.3 (near-duplicates were dropped, not padded). **All rows: status =
`mapped`, stdlib-buildable = yes.** The Source column names the real product that ships the
component (grounding, not endorsement).

| ID | Class | Vertical/Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| G1 | Error-event grouping / dedup engine (fingerprint→issue) | observability | 3 | C+M | IMPORT+DB | Build a service that ingests error reports and files each one under an existing issue when its signature matches, or opens a new issue otherwise. | Sentry |
| G2 | Release tracking + regression reopen | observability | 3 | C+M | DB + NEW:state-machine | Build an issue tracker where a resolved error reopens automatically if it is seen again in a newer release version. | Sentry |
| G3 | Symbolication (minified frame → original source lookup) | observability | 3 | C+M | FS+IMPORT | Build a tool that rewrites minified error frames back to original file and line numbers using a source-map-style lookup file. | Sentry |
| G4 | Data-retention purge job (per-project policy) | observability/cross | 2 | C+M | DB + NEW:clock | Build a job that permanently removes records older than each project's configured retention period and reports exactly what it deleted. | Sentry / Zulip |
| G5 | Ownership / assignment rules (path→owner matching) | devtools | 2 | C+M | IMPORT | Build a matcher that assigns each incoming issue to a team based on CODEOWNERS-style path patterns, most-specific rule wins. | Sentry |
| G6 | Notification digest / rollup (batched summaries) | cross | 3 | C+M | NEW:clock + SMTP-sink | Build a notifier that groups all alerts for a user within a period into one summary message instead of sending each alert separately. | Sentry / Zulip |
| G7 | Alerting rule engine (threshold/for-duration, pending→firing→resolved) | observability | 3 | C+M | IMPORT + NEW:state-machine/clock | Build an alert evaluator that fires when a metric stays above a threshold for a set duration and sends a resolved notice when it recovers. | Grafana / Sentry |
| G8 | Alert routing by label matchers (policy tree + grouping) | observability | 3 | C+M | IMPORT | Build a router that walks a policy tree of label matchers to decide which contact channel each alert goes to, grouping related alerts together. | Grafana |
| G9 | Silence / maintenance-window suppression | observability | 2 | C+M | NEW:clock | Build a suppression layer where alerts matching an active maintenance window are held back and delivery resumes when the window ends. | Grafana / Uptime Kuma |
| G10 | Identity resolution / person merge (anon→identified) | analytics | 3 | C+M | DB+IMPORT (attribution invariant) | Build an event store where an anonymous visitor's history merges into their account when they log in, so every event maps to exactly one person. | PostHog |
| G11 | Funnel conversion analysis (ordered steps) | analytics | 3 | C+M | IMPORT (exact counts) | Build an analyzer that computes how many users completed each ordered step of signup, activation, and purchase within a window. | PostHog |
| G12 | Retention cohort matrix (first-seen × return period) | analytics | 3 | C | IMPORT | Build a report that groups users by first-seen week and counts exactly how many returned in each following week. | PostHog |
| G13 | Sessionization of event streams (inactivity gap) | analytics | 2 | C+M | IMPORT | Build a processor that splits a user's event stream into visits whenever more than thirty minutes of inactivity passes. | PostHog |
| G14 | Segmentation / cohort predicate engine | analytics/marketing | 2 | C+M | IMPORT+DB | Build a segment evaluator that returns the exact set of users matching property and behavior conditions combined with and/or logic. | PostHog / listmonk |
| G15 | Privacy-preserving unique-visitor counting (rotating salted hash) | analytics | 2 | C+M | IMPORT+DB | Build a page-view counter that counts distinct visitors using a salted hash of address and user agent, with the salt rotated daily. | Plausible / Umami |
| G16 | Traffic attribution (referrer/UTM parse + breakdown) | analytics | 2 | C+M | IMPORT | Build a report that classifies each visit's origin from its referrer and campaign parameters and totals visits per source, medium, and campaign. | Plausible |
| G17 | Team-chat channels + threaded topics | collaboration | 3 | C+M | HTTP+DB | Build a chat service with channels and per-topic threads where members post, edit, and fetch messages in order. | Zulip / Mattermost |
| G18 | Unread-count / read-state tracking | collaboration | 2 | C+M | DB (exact-count invariant) | Build per-user read markers so each member sees an exact count of messages they have not read in each conversation. | Zulip |
| G19 | Presence tracking (online/idle/offline from pings) | collaboration | 2 | C+M | NEW:clock | Build a presence service that marks a user idle after no activity for N minutes and offline after M, driven by periodic client pings. | Zulip |
| G20 | Mention parsing + notification targeting | collaboration | 2 | C+M | IMPORT | Build a parser that finds @user and @group references in a message and returns exactly the set of accounts to notify. | Zulip / Mattermost |
| G21 | Poll / voting service (one vote per user) | collaboration/community | 2 | C+M | DB (invariant) | Build a poll service where each member gets one changeable vote per poll and totals always match the votes stored. | Discourse / Zulip |
| G22 | Trust-level progression engine (activity thresholds) | community | 2 | C+M | DB+IMPORT | Build a member-level system that promotes users when their activity counters cross thresholds and never demotes below an earned floor. | Discourse |
| G23 | Flag-threshold auto-moderation workflow | community | 3 | C+M | NEW:state-machine | Build a moderation flow where a post is hidden automatically once enough distinct members flag it and a reviewer can restore or remove it. | Discourse |
| G24 | Badge / achievement award engine (award-once) | community | 2 | C+M | DB+IMPORT (idempotent award) | Build an award system that grants each badge at most once per user when their activity meets the badge's criteria. | Discourse |
| G25 | Time-decay trending / "hot" ranking | community/media | 2 | C+M | IMPORT + NEW:clock | Build a front-page ranker that scores topics by engagement discounted by age so newer active topics outrank stale popular ones. | Discourse / HN-style |
| G26 | Availability / slot computation (interval math) | scheduling | 3 | C+M | IMPORT (exact slots) | Build a slot finder that returns bookable meeting times from working hours minus busy periods, honoring meeting length and per-day caps. | Cal.com |
| G27 | Timezone-aware schedule presentation (DST-correct) | scheduling | 3 | C+M | IMPORT (fixture zoneinfo) | Build a converter that renders a host's weekly availability in any viewer's timezone, correct across daylight-saving changes. | Cal.com |
| G28 | Recurrence-rule expansion (calendar patterns) | scheduling | 2 | C+M | IMPORT | Build an expander that lists the concrete dates for rules like "every second Tuesday" or "last Friday of each month" up to a horizon. | Cal.com / Firefly III |
| G29 | ICS calendar file generate/parse round-trip | scheduling | 2 | C+M | FS+IMPORT | Build a tool that writes bookings out as an ICS calendar file and reads one back into the same booking records. | Cal.com |
| G30 | Round-robin / capacity-weighted assignment engine | scheduling/support | 2 | C+M | IMPORT (deterministic) | Build an assigner that hands each new booking to the least-recently-chosen eligible host, respecting per-host weights and load caps. | Cal.com / Chatwoot |
| G31 | Timed hold / reservation auto-release | scheduling/e-comm | 3 | C+M | NEW:clock+concurrency | Build a hold service that reserves a slot while a visitor checks out and frees it automatically if they do not finish in time. | Cal.com |
| G32 | Durable workflow via event-history replay | workflow | 4 | C+M | IMPORT+DB (replay determinism) | Build a workflow runner that logs every step's outcome and, after a crash, replays the log to resume exactly where it left off without redoing completed steps. | Temporal |
| G33 | Task lease / worker-liveness reassignment | workflow | 3 | C+M | NEW:clock+concurrency | Build a work distributor where a task claimed by a worker returns to the pool if the worker stops reporting in before finishing. | Temporal |
| G34 | Data-pipeline scheduler (logical dates + backfill/catchup) | data-pipeline | 3 | C+M | DB/FS + NEW:clock | Build a pipeline scheduler that runs each job once per period, records which periods completed, and re-runs any missed past periods on request. | Airflow / Dagster |
| G35 | Integration workflow runner (trigger→steps, branch/merge) | automation | 4 | C+M | IMPORT (step transcript) | Build an automation runner that executes a stored graph of steps — fetch, transform, branch on a condition, act — passing each step's output to the next. | n8n / Huginn |
| G36 | Safe template-expression evaluator (sandboxed interpolation) | automation | 2 | C+M | IMPORT | Build an interpolator that fills double-brace placeholders in step parameters from prior step outputs without allowing arbitrary code execution. | n8n |
| G37 | Multi-stage approval chain (role-gated sign-offs) | workflow/ERP | 3 | C+M | NEW:state-machine | Build a purchase-approval flow where requests pass through ordered role-based sign-offs and any rejection returns them to the requester. | ERPNext / Odoo |
| G38 | Inventory valuation ledger (FIFO / moving-average COGS) | ERP/e-comm | 3 | C+M | NEW:conservation (exact COGS) | Build a stock ledger that records receipts and issues and computes cost of goods for each issue under first-in-first-out costing. | ERPNext |
| G39 | Multi-level BOM explosion / material requirements | ERP/manufacturing | 3 | C+M | IMPORT (exact rollup) | Build a bill-of-materials expander that computes total raw-material quantities needed for N units of a product with nested sub-assemblies. | ERPNext |
| G40 | Payroll run (salary components → exact net) | ERP/HR | 3 | C+M | IMPORT + NEW:conservation | Build a payroll calculator that turns salary components, allowances, and deductions into exact per-employee net pay and a run total that balances. | ERPNext |
| G41 | Leave/PTO accrual + balance enforcement | ERP/HR | 2 | C+M | DB + NEW:clock (non-negative) | Build a leave tracker that accrues days per policy each month and rejects requests that would take a balance below zero. | ERPNext |
| G42 | Asset checkout/checkin registry (single custody) | ERP/internal-ops | 2 | C+M | DB + NEW:conservation | Build an equipment registry where each asset can be signed out to only one person at a time and its custody history is complete. | Snipe-IT |
| G43 | Help-desk ticket lifecycle + assignment | support | 2 | C+M | NEW:state-machine | Build a ticket service where conversations move through open, waiting, snoozed, and resolved states with agent and team ownership. | Chatwoot / Zammad |
| G44 | SLA timer tracking (business-hours aware, breach flags) | support | 3 | C+M | NEW:clock | Build an SLA tracker that measures first-response and resolution times counting only business hours and flags breaches. | Chatwoot |
| G45 | Event automation rules (condition→action on records) | support/cross | 2 | C+M | IMPORT+DB | Build a rules engine that, when a record is created or updated, evaluates and/or conditions and applies actions like labeling and assigning. | Chatwoot / Firefly III |
| G46 | Business-hours / holiday calendar computation | support/cross | 2 | C+M | IMPORT + NEW:clock | Build a calendar helper that answers whether a moment is inside working hours and when the next working period starts, holidays included. | Chatwoot / Cal.com |
| G47 | Campaign batch-send engine (pause/resume, exactly-once) | marketing | 3 | C+M | NEW:SMTP-sink + DB | Build a mail-out engine that sends a templated message to every subscriber of chosen lists in capped batches, with pause, resume, and exactly one send per subscriber. | listmonk |
| G48 | Double opt-in subscription flow (single-use confirm) | marketing | 2 | C+M | NEW:state-machine + SMTP-sink | Build a signup flow where a subscriber only becomes active after clicking a single-use confirmation link sent by mail. | listmonk |
| G49 | Bounce processing + suppression list | marketing | 2 | C+M | DB+IMPORT | Build a bounce handler that records delivery failures per address and blocklists an address after N hard failures so it is never mailed again. | listmonk |
| G50 | Uptime monitor scheduler (K-failure debounce, transitions) | monitoring | 3 | C+M | NEW:clock + state-machine (fixture upstream) | Build a monitor that probes each target on its interval, requires K consecutive failures before declaring it down, and records every status change. | Uptime Kuma |
| G51 | Public status page + exact uptime percentage | monitoring | 2 | C+M | HTTP+DB | Build a status page service that shows each component's current state and its exact uptime percentage computed from check history. | Uptime Kuma / Cachet |
| G52 | Dead-man-switch push monitoring (missed check-in) | monitoring | 2 | C+M | NEW:clock | Build a watcher that alerts when a job fails to check in within its expected window, and clears when check-ins resume. | Healthchecks.io / Uptime Kuma |
| G53 | File-sync state detection / change planner (conflict copies) | files | 3 | C+M | FS+IMPORT | Build a sync planner that compares a local folder against a remote listing using stored change tags and emits the exact upload, download, and conflict-copy plan. | Nextcloud |
| G54 | Chunked / resumable upload assembly (checksum-verified) | files | 3 | C+M | HTTP+FS + NEW:conservation (bytes) | Build an upload service that accepts file parts out of order, verifies the assembled checksum, and completes only when every byte is accounted for. | Nextcloud |
| G55 | File version history + prune policy | files | 2 | C+M | FS+DB | Build a store that keeps prior versions of each file on every save, restores any version exactly, and thins old versions per policy. | Nextcloud |
| G56 | Collaborative text merge (OT/CRDT convergence) | files/collab | 4 | C+M | IMPORT (convergence property) | Build a merge engine where two editors' concurrent edits to the same document produce the same final text regardless of arrival order. | Etherpad / Nextcloud |
| G57 | Slug generation + uniqueness (collision suffix) | CMS | 1 | C+M | IMPORT+DB | Build a helper that turns titles into URL-safe identifiers and appends a counter when a duplicate exists. | Ghost / Strapi |
| G58 | Content draft/publish lifecycle (dual versions, timed go-live) | CMS | 2 | C+M | DB + NEW:state-machine | Build a content store keeping a draft and a published copy per document, with publish, unpublish, and modified-since-publish status; a timed publish goes live at its set moment. | Strapi / Ghost |
| G59 | RSS/Atom feed + sitemap generation (exact XML) | CMS | 1 | C+M | FS/HTTP (exact XML) | Build a generator that emits a valid RSS feed and sitemap for published posts, newest first, matching the stored content exactly. | Ghost |
| G60 | Markdown render + HTML sanitization (XSS strip) | CMS | 2 | C+M | IMPORT (fixture tables) | Build a renderer that converts markdown to HTML while stripping script tags and event-handler attributes from embedded HTML. | Ghost / Discourse |
| G61 | Dynamic content-model CRUD generator (runtime schema) | CMS | 4 | C+M | HTTP+DB | Build a service where an admin defines a content type's fields at runtime and the matching validated CRUD endpoints exist immediately. | Strapi / Directus |
| G62 | Brute-force lockout with progressive delay | auth | 2 | C+M | HTTP + NEW:clock | Build login protection that temporarily locks an account after repeated failures, doubling the lock time on each subsequent burst. | Keycloak |
| G63 | Password-policy engine (composition / history rules) | auth | 2 | C+M | IMPORT | Build a validator that enforces length, character-class, and no-reuse-of-last-N rules when a user sets a new password. | Keycloak |
| G64 | SCIM-style user-provisioning sync API | auth | 3 | C+M | HTTP+DB | Build a provisioning endpoint where an upstream directory creates, patches, and deactivates users and a downstream mirror stays consistent. | Keycloak / Authentik |
| G65 | Gift-card issue/redeem (code + non-negative balance) | e-comm | 2 | C+M | DB + NEW:conservation | Build a gift-card service that issues coded cards and applies partial redemptions so a card's remaining value never goes below zero. | Medusa / Saleor |
| G66 | Envelope budgeting with period limits + carryover | personal-finance | 2 | C+M | NEW:conservation + clock | Build a budgeting tracker that allots an amount per category per month, records spending against it, and reports exact remaining amounts with optional carryover. | Firefly III |
| G67 | Guarded read-only SQL executor (row cap, single statement) | BI | 3 | C+M | IMPORT+DB | Build a query runner that executes only single read statements against a database, enforcing a row cap and rejecting any write or multi-statement input. | Metabase / Superset |
| G68 | Query-AST → SQL compiler (filters/groups/aggregates) | BI | 3 | C+M | IMPORT (exact results) | Build a compiler that turns a JSON description of filters, groupings, and aggregations into SQL and returns exact result rows. | Metabase |
| G69 | Scheduled report delivery (saved-query subscriptions) | BI | 3 | C+M | NEW:clock + SMTP-sink + DB | Build a subscriptions service that runs saved queries on a schedule and mails the rendered results to each recipient list. | Metabase / Superset |
| G70 | Kanban rank ordering (stable fractional ranks, column moves) | PM | 2 | C+M | DB (ordering invariant) | Build a board service where cards keep a stable total order within columns as they are inserted, moved, and re-ranked between neighbors. | Plane / OpenProject |
| G71 | Issue dependency graph (cycle prevention) | PM | 2 | C+M | IMPORT (graph invariant) | Build a linker that records blocks and blocked-by relations between issues and rejects any link that would create a circular dependency. | OpenProject / Plane |
| G72 | URL shortener + exact visit stats | web | 1 | C+M | HTTP+DB | Build a link service that mints short codes redirecting to long URLs and counts visits per code exactly. | Shlink / Kutt |
| G73 | Form builder + validated submissions (runtime fields) | forms | 2 | C+M | HTTP+DB+IMPORT | Build a form service where an admin defines fields with types and required flags and submissions are validated and stored accordingly. | Formbricks / LimeSurvey |

**Dedupe record (honesty, Tenet 3):** candidates found in the same products but **dropped as
near-duplicates of existing rows**: DSN/ingest keys (≈S27), inbound event sampling/quotas (≈S7/S8),
row-level security/data sandboxing (≈S6), trash-bin restore (≈S68), share links with signed tokens
(≈S33), cart promotions/vouchers (≈V12), warehouse stock transfers (≈V36 conservation), credential
vault (≈S29), invitation/magic-link tokens (≈S4 token flow), procurement three-way match (≈F18/F28
recon), time-series downsampling (≈S46), canned-response templating (≈S30), cron next-fire (≈S15),
member tier gating (≈V16), payment authorize/capture (≈F17), forum post CRUD (≈generic CRUD),
reaction aggregates (≈V15), wiki page tree (≈V3+G55).

**Oracle-demand signal from this wave:** injectable-clock recurs in **~17** of the 73 rows —
this wave materially raises its §4 priority; state-machine ~8, conservation ~6, SMTP-sink ~4,
concurrency ~2. No genuinely new oracle *kind* was needed — every component graded onto the
existing §4 vocabulary, which is evidence the substrate list is converging.

### 3.5 Wave-2 selfhosted-ecosystem additions (awesome-selfhosted sweep, 2026-07-10)

**Provenance:** category-by-category sweep of the awesome-selfhosted catalog (101 categories;
representative projects decomposed via read-only research: Miniflux, Grocy, Snipe-IT, Vaultwarden,
PrivateBin, Firefly III, FreeScout, Kimai, Mealie, DocuSeal, Wiki.js/BookStack, Joplin, Navidrome,
Immich/PhotoPrism, Mastodon, ArchiveBox, Kanboard). **All rows: status = `mapped`, stdlib = yes.**
The stager deduped against S/A/F/V but **not wave-1's G-rows — which mined the same OSS space** —
so the final merge dropped **31 of 81** staged rows (record below); the 50 survivors are the
genuinely new selfhosted/prosumer tier.

| ID | Class | Vertical/Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| SH-B1 | Bookmark manager (tags + normalized-URL dedupe) | PIM/bookmarks | 2 | C+M | HTTP+DB | Build a JSON API to save bookmarks with tags where saving the same URL twice (ignoring tracking params and trailing slash) updates the existing entry instead of duplicating it. | linkding |
| SH-B2 | HTML metadata extractor (title/description/canonical) | PIM/bookmarks | 2 | C | IMPORT | Write a module that, given a saved HTML file, returns its title, meta description, and canonical URL. | Shiori |
| SH-B3 | Dead-link checker over stored bookmarks | PIM/bookmarks | 2 | C+M | NEW:multi-service | Given a bookmark database and a set of local test sites, mark each bookmark as alive, redirected, or broken. | LinkAce |
| SH-B4 | Readability-style article extractor | PIM/read-later | 3 | C+M | IMPORT | From a saved news-page HTML file, extract just the article's headline and body paragraphs, dropping navigation and ads. | Wallabag/Miniflux |
| SH-B5 | Netscape bookmark-file import/export round-trip | PIM/bookmarks | 2 | C+M | FS+IMPORT | Import a browser-exported bookmarks.html into the database and export it back so a re-import produces identical records. | linkding |
| SH-D3 | E-sign envelope workflow (ordered signers, completion gate, out-of-turn rejected) | doc-mgmt/e-sign | 3 | C+M | NEW:state-machine | Build a signing service where a document goes to three signers in order and only becomes completed when the last one signs; out-of-turn signing is rejected. | DocuSeal |
| SH-FR1 | RSS/Atom/JSON-feed parser + normalizer | PIM/feeds | 2 | C+M | IMPORT | Parse RSS 2.0, Atom, and JSON-feed files into one normalized entry record with id, title, link, and published time. | Miniflux |
| SH-FR2 | Feed poller w/ conditional GET (ETag/Last-Modified, per-feed interval) | PIM/feeds | 3 | C+M | HTTP + NEW:multi-service/clock | Build a fetcher that re-checks each feed on its own interval and sends If-None-Match so an unchanged feed answers 304 and no entries are re-stored. | Miniflux |
| SH-FR3 | Entry state service (read/unread/starred) w/ GUID dedupe | PIM/feeds | 2 | C+M | HTTP+DB | Store fetched entries keyed by feed GUID so a re-fetch never duplicates, and let a user mark entries read or starred. | FreshRSS |
| SH-FR4 | Ingest filter rules (keyword/regex keep-or-drop per feed) | PIM/feeds | 2 | M | IMPORT | Add per-feed rules that drop entries whose title matches a block pattern before they are stored. | Miniflux |
| SH-FR5 | OPML subscription import/export round-trip | PIM/feeds | 2 | C+M | FS+IMPORT | Import an OPML file of feed subscriptions with folders, and export one that re-imports to the identical subscription set. | FreshRSS |
| SH-FR6 | Google-Reader-compatible API facade | PIM/feeds | 3 | C | NEW:protocol | Expose the reader's data through the Google Reader API endpoints so an existing mobile-client fixture can log in and list unread items. | FreshRSS/Miniflux |
| SH-I2 | License seat allocation (never exceed purchased seats) | IT-ops/licenses | 2 | C+M | NEW:conservation | Track software licenses with 10 seats; assigning an 11th user is refused and releasing a seat makes it assignable again. | Snipe-IT |
| SH-I3 | Consumable stock w/ reorder threshold | IT-ops/consumables | 2 | C+M | DB + NEW:conservation | Track printer toner stock that decrements on issue, never goes below zero, and flags the item once quantity falls under its reorder point. | Snipe-IT |
| SH-I4 | Straight-line depreciation schedule (exact final residual) | IT-ops/depreciation | 2 | C | IMPORT | Compute a monthly straight-line depreciation table for an asset from purchase price to residual value, with the final month landing exactly on the residual. | Snipe-IT |
| SH-I6 | Physical audit reconciliation (scan list vs records) | IT-ops/audit | 2 | C | CLI+IMPORT | Given a scanned list of asset tags from a walkthrough, report assets missing from the floor and tags not present in the database. | Snipe-IT |
| SH-W1 | Wiki page store w/ revision history, diff, revert | collaboration/wiki | 3 | C+M | HTTP+DB | Build a wiki where each edit stores a new revision, any two revisions can be diffed, and revert creates a new revision equal to an old one. | Wiki.js |
| SH-W2 | Wiki-link backlink indexer + orphan-page report | collaboration/wiki | 2 | C+M | IMPORT | Parse [[wiki-style]] links across pages, maintain a backlinks list per page, and report pages nothing links to. | DokuWiki/Trilium |
| SH-W4 | Hierarchical permission inheritance (space defaults, page overrides) | collaboration/wiki | 3 | C+M | HTTP+IMPORT | Give shelves a default read/edit role set that pages inherit unless a page sets its own, and prove a viewer denied at the shelf can read an explicitly opened page. | BookStack — ≠S5: inheritance is the new bit |
| SH-N1 | Two-replica note-sync reconciler (converge, newest-wins, no loss) | PIM/notes | 3 | C+M | IMPORT | Sync two offline note stores edited independently so both end identical, the newer edit wins per note, and no note is lost. | Joplin |
| SH-N2 | Notes-to-folder export/import round-trip (.md + front-matter) | PIM/notes | 2 | C+M | FS | Export all notebooks as a folder tree of Markdown files with metadata front-matter, and re-import to identical notes. | Joplin |
| SH-M1 | Photo de-duplication by content digest | media/photo | 2 | C | FS+IMPORT | Scan a photo folder, group byte-identical images, and move duplicates aside keeping the earliest-modified copy. | Immich |
| SH-M2 | Metadata-driven photo organizer (date-taken → Year/Month layout) | media/photo | 2 | C+M | FS | Sort photos into Year/Month folders using each image's date-taken from a metadata sidecar, leaving unknown-dated files in a review folder. | PhotoPrism |
| SH-M3 | Music library scanner (tag parse → artist/album/track DB, idempotent re-scan) | media/music | 3 | C+M | DB+FS | Scan a music folder, read each file's title/artist/album tags, and build a browsable library that re-scans without duplicating tracks. | Navidrome |
| SH-M4 | Pattern-based media renamer (parsed episode info → canonical filename) | media/video | 2 | C+M | FS+CLI | Rename downloaded episode files like show.s01e02.x264.mkv to "Show - S01E02 - Title.mkv" using a lookup table of titles. | Sonarr |
| SH-M5 | Smart-album rule engine (declarative rules → recomputed membership) | media/photo | 2 | C+M | IMPORT | Support smart albums defined by rules such as camera model plus date range, recomputing membership when photos change. | PhotoPrism |
| SH-P1 | Password generator w/ policy + strength scoring | security/passwords | 1 | C+M | IMPORT | Generate passwords honoring length and character-class policy with no ambiguous characters, and score arbitrary passwords by entropy class. | Vaultwarden |
| SH-P2 | Offline breach lookup (k-anonymity digest-prefix over local corpus) | security/passwords | 2 | C | IMPORT | Check a password against a local corpus of breached digests by matching on a 5-hex-character digest prefix, without ever storing the full password. | Vaultwarden/HIBP |
| SH-PB1 | Pastebin service (visibility levels + owner deletion token) | sharing/pastebin | 2 | C+M | HTTP+DB | Build a paste service with public/unlisted/private pastes and a secret deletion token returned at creation that is the only way to remove one. | PrivateBin |
| SH-PB2 | Burn-after-first-view secret link (+ deadline removal) | sharing/secret-share | 2 | C+M | HTTP + NEW:clock | Create one-time secret links where the first retrieval returns the secret and destroys it; a second request and any request after the deadline get 404. | PrivateBin / Vaultwarden Send |
| SH-PB3 | Download-limited, password-gated file drop | sharing/file-drop | 2 | C+M | HTTP+FS + NEW:conservation | Share an uploaded file behind a password with a maximum of N downloads, after which the link is dead and the file is removed. | Gokapi |
| SH-PD1 | Config-driven start-page generator (config → static HTML) | ops/dashboard | 2 | C+M | FS+CLI | Render a YAML config of service groups into a single static HTML start page, failing with a clear error on unknown keys. | Homer |
| SH-PD2 | Service-health tile aggregator (poll N services → summary) | ops/dashboard | 2 | C+M | NEW:multi-service | Poll the health endpoints of the configured services and serve a JSON summary marking each tile up, down, or degraded. | Homepage/Dashy |
| SH-PS2 | Date-poll best-slot selection (yes/ifneedbe/no grid) | collaboration/scheduling-poll | 2 | C+M | IMPORT | Given participants' yes/ifneedbe/no answers per proposed time, pick the slot with most yes then fewest no, with deterministic tie-breaks. | Rallly |
| SH-PS4 | Survey branching / skip-logic runner (path recorded) | collaboration/surveys | 3 | C+M | NEW:state-machine | Serve a survey where the next question depends on prior answers, and a completed response records exactly the path taken. | LimeSurvey |
| SH-R1 | schema.org Recipe JSON-LD importer | household/recipes | 2 | C+M | IMPORT | Extract the recipe (name, ingredients, steps, servings) from a saved page's embedded JSON-LD, tolerating both @graph and top-level forms. | Mealie |
| SH-R2 | Ingredient scaling + kitchen unit conversion (exact fractions) | household/recipes | 2 | C+M | IMPORT | Scale a recipe from 4 to 6 servings converting units sensibly (750 ml stays ml, 16 tbsp becomes 1 cup) with exact fractions. | Tandoor |
| SH-R3 | Meal-plan → aggregated shopping list (merge, unit-normalize, pantry-subtract) | household/meal-plan | 3 | C+M | IMPORT + NEW:conservation | Turn a week's meal plan into one shopping list that merges repeated ingredients, sums their quantities in a common unit, and omits what the pantry already holds. | Mealie/Grocy |
| SH-T1 | Punch-in/punch-out timer (at most one running per user) | business-ops/time | 2 | C+M | HTTP + NEW:state-machine | Build a timer API where starting work while a timer runs stops the old one; durations are computed server-side and never overlap. | Kimai |
| SH-T2 | Timesheet overlap rejection (conflicting entry named) | business-ops/time | 2 | M | DB | Add validation so a manually entered time slice that overlaps an existing one for the same user is rejected with the conflicting entry named. | Kimai |
| SH-T4 | Timesheet approval workflow + period lock | business-ops/time | 3 | C+M | NEW:state-machine + NEW:period-lock | Let a user submit a week for approval; once approved the week is locked and any edit or new entry in it is rejected. | Kimai |
| SH-H2 | Email-to-ticket ingestion w/ threading (In-Reply-To/References) | business-ops/helpdesk | 3 | C+M | IMPORT + NEW:SMTP-sink | Parse incoming mail files into tickets, appending a reply to its original ticket via In-Reply-To/References instead of opening a new one. | FreeScout |
| SH-H3 | Agent collision lock on a conversation | business-ops/helpdesk | 3 | C+M | NEW:concurrency | When two agents open the same ticket, the second sees who holds it and their reply is blocked until the first releases it. | FreeScout |
| SH-BU3 | Recurring transaction materializer (month-end date math, exactly-once) | personal-finance | 2 | C+M | DB + NEW:clock | Generate instances of a monthly bill due on the 31st so short months book it on their last day, exactly once per month. | Firefly III |
| SH-BU4 | Savings-goal reservations ("piggy banks", Σ reserved ≤ balance) | personal-finance | 2 | C+M | NEW:conservation | Reserve amounts from an account toward named goals so total reservations never exceed the account balance and freed reservations return to available. | Firefly III |
| SH-C3 | Follow graph + assembled home timeline (blocks/mutes honored) | community/social-graph | 3 | C+M | DB | Build follows so a user's timeline merges followed users' posts newest-first while never showing authors they blocked or muted. | Mastodon |
| SH-C4 | ActivityPub-lite federation handshake (WebFinger + signed inbox delivery) | community/federation | 4 | C | NEW:protocol | Deliver a post from one local server to another's inbox with WebFinger discovery and a verified request signature, using two in-process servers. | Mastodon/Pixelfed |
| SH-MO5 | TLS certificate deadline watcher (against local TLS fixture) | ops/monitoring | 3 | C | NEW:multi-service (TLS) | Connect to each internal service over TLS and warn when a certificate's remaining validity drops below 14 days. | Uptime Kuma |
| SH-AR1 | Page snapshot archiver (versioned folder layout + index) | PIM/web-archive | 3 | C+M | FS+HTTP (fixture site) | Save a page and its images from a local test site into a timestamped snapshot folder, and archive it again later as a second version with an index listing both. | ArchiveBox |
| SH-TK1 | Kanban board w/ per-column WIP limits | collaboration/kanban | 2 | C+M | HTTP + NEW:conservation | Build a kanban API where moving a card into a column at its work-in-progress limit is rejected until a card leaves. | Kanboard |

**Final-dedupe record (Tenet 3 — 31 staged rows dropped at merge, target row in parens).** Vs
wave-1 G-rows (same OSS space, stager couldn't see them): URL shortener (=G72) · short-link
visit/date limits (G72 MODIFY variant) · uptime monitor (=G50) · dead-man's-switch (=G52) · status
page + availability % (=G51) · incident lifecycle w/ maintenance suppression (≈G9+G51) · iCal
RRULE expander (=G28) · vCard/ICS round-trip + free/busy (≈G29+G26) · timed seat hold auto-release
(=G31) · availability slot computation (=G26) · asset custody check-out/in (=G42, same Snipe-IT
class) · chore rotation (≈G30 round-robin) · helpdesk ticket lifecycle (=G43) · SLA tracker
(=G44) · envelope budgeting (=G66) · txn auto-categorization rules (≈G45) · one-vote-per-user poll
(=G21) · form schema validation (≈G73) · chunked resumable upload (=G54) · one-way dir mirror
(≈G53 subset) · markdown renderer (=G60) · task dependency graph (=G71) · threaded forum (≈G17 +
wave-1 forum-CRUD drop precedent) · vote-ranked feed (≈G21+G25) · doc auto-tagging rules (≈G45) ·
retention + legal hold (≈G4, same call as P34) · signed-doc digest chain (≈F10 hash-chain) ·
check-out/check-in doc versioning (≈G55 + collision-lock kept as SH-H3). Vs wave-3 rows (kept the
more specific row): pantry best-before FEFO lots (=W24) · ranked-choice IRV tally (=W18) · billable
rollup→invoice (≈W45). Stager's adjacency flags resolved: SH-I1-vs-V6 and SH-H1-vs-V34 and
SH-BK1-vs-V57/58 and SH-BU1-vs-F46 all mooted by the G-row drops above; SH-W4-vs-S5 and SH-N1
confirmed distinct and kept.

**Oracle-demand signal from this wave (surviving rows):** injectable-clock +3 direct (burn-links,
recurring bills, feed-poll intervals; 8 more staged votes folded onto their G-row dup targets,
which already demand clock) · **multi-service-fixture +5 staged votes** (dead-link checker,
conditional-GET poller, dashboard tiles, TLS watcher; uptime-monitor vote folded into G50) —
monitoring is its killer category · conservation +6 · state-machine +4 · protocol-conformance +2
(Google-Reader facade, ActivityPub-lite) · SMTP-sink +1 · concurrency +1 · **period-lock +1**
(timesheet approval — narrow, §4 bottom row).

### 3.6 Wave-3 industry-vertical additions (regulated/specialized OSS decomposition, 2026-07-10)

**Provenance:** read-only decomposition of regulated-industry OSS (OpenMRS/OpenEMR/OpenELIS/Mirth,
CKAN/Decidim/Consul/Alaveteli/Open311, OpenBoxes/Karrio, Jellyfin/PeerTube, Moodle/Open edX,
openIMIS/OpenUnderwriter, docassemble/CourtListener/ClinicCases, microrealestate, farmOS,
OpenEnergyMonitor + utility MDMS practice). **Opens SIX entirely new verticals** (Gov/Civic, Legal,
Proptech, Agriculture, Energy/Utilities, Insurance-non-health — the atlas previously had zero rows
in each) plus depth for Healthcare/Logistics/EdTech/Media. **All rows: status = `mapped`, stdlib =
yes.** Final dedupe dropped 2 of 62 staged rows: EdTech threaded course forum (≈G17 + wave-1
forum-CRUD precedent), podcast RSS generator (≈G59; enclosure/GUID-stability contract noted as
G59's MODIFY surface). The stager's own drops (course-seat waitlist=V57, drug-interaction⊂V19,
consent=V23, watch-progress=V14, prepaid meter=F24, endorsement proration=F21/F39, freight-invoice
audit=F18/F28/F52, carrier rate lookup=V27/V41, farm sensor validation=W57, badge issuance=V45,
P&C claim SM=V22) were verified sound.

| ID | Class | Vertical/Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| W1 | HL7 v2 message parser + transform (ADT/ORU pipe-and-hat → normalized JSON, version remap) | Health/interop | 2 | C+M | CLI+IMPORT | Parse an HL7 ADT^A01 admission message into a JSON patient record and re-emit it with the facility code remapped per a lookup table. | Mirth Connect / OIE |
| W2 | Lab order lifecycle (ordered→accessioned→resulted→QC-verified→released; release gated on validator role) | Health/lab | 3 | C+M | NEW:state-machine | Build a lab worklist where a test result cannot be released to the ordering doctor until a reviewer with the validator role approves it. | OpenELIS Global |
| W3 | Immunization registry + next-dose-due forecast (series rules, min intervals, age gates) | Health/registry | 3 | C+M | IMPORT + NEW:clock | Given a child's vaccine history and the CDC-style series table, list which doses are due today and the earliest valid date for each remaining dose. | OpenMRS / WHO EIR |
| W4 | Patient identity merge / MPI dedup (deterministic match, survivor record, merge audit) | Health/registry | 3 | C+M | DB+IMPORT | Detect duplicate patient registrations by exact-normalized name, birth date and ID number, merge them keeping the oldest record, and log what was merged. | OpenMRS MPI — ≠G10: G10 merges an anon event stream at login; this is record dedupe + survivorship |
| W5 | Bed management / ADT census (one patient per bed, one bed per patient, census == occupied) | Health/ops | 3 | C+M | NEW:conservation | Track hospital beds so admitting a patient claims a free bed, transferring moves them atomically, and the ward census always equals occupied beds. | OpenMRS/OpenEMR ADT |
| W6 | Referral workflow (requested→accepted/declined→scheduled→completed→report-returned) | Health/care-coord | 2 | C+M | NEW:state-machine | Build a specialist-referral tracker where a referral can only be scheduled after the receiving clinic accepts it, and completion requires an attached report. | OpenMRS/OpenEMR referral |
| W7 | Encounter charge capture / superbill (CPT/ICD lines from fee schedule, Σ lines == claim total) | Health/revenue | 3 | C+M | IMPORT + NEW:conservation | From a visit's recorded procedure and diagnosis codes, produce a superbill whose line amounts come from the fee schedule and sum exactly to the claim total. | OpenEMR billing |
| W8 | Open-data portal catalog (dataset/resource/org CRUD, tags, licenses, per-org edit rights) | Gov/open-data | 2 | C+M | HTTP+DB | Build a data-portal API where an agency publishes a dataset with several downloadable resources and only that agency's users can edit it. | CKAN |
| W9 | Catalog harvest sync (pull remote listing, upsert changed, retire vanished) | Gov/open-data | 3 | C+M | HTTP(fixture upstream)+DB | Sync a local data catalog from a remote portal's listing endpoint so re-running after remote edits updates changed entries and marks vanished ones retired. | ckanext-harvest |
| W10 | DCAT metadata export (catalog → DCAT JSON/XML, byte-stable, required fields) | Gov/open-data | 2 | C | CLI+FS | Export every dataset in the catalog as a DCAT JSON document with publisher, license and distribution entries, byte-stable across runs. | ckanext-dcat |
| W11 | Permit application workflow (completeness review → inspection → approve/deny → issue; fee gates issue) | Gov/permitting | 3 | C+M | NEW:state-machine | Build a building-permit tracker where a permit cannot be issued until its inspection passed and the fee is recorded as paid. | OpenGov/Accela shape |
| W12 | Business-license issue + renewal (grace window, late penalty, lapse → reinstatement path) | Gov/licensing | 3 | C+M | NEW:state-machine + NEW:clock | Build a license registry where renewing within the grace window costs the base fee, after it adds a late penalty, and long-lapsed licenses need reinstatement. | civic licensing suites |
| W13 | Inspection scheduling + checklist scoring (weighted pass/fail/N-A; critical fail forces reinspection) | Gov/inspections | 2 | C+M | IMPORT + NEW:state-machine | Score a restaurant inspection from a weighted checklist and automatically require a follow-up inspection when any critical item fails. | Accela/OpenGov shape |
| W14 | FOIA / public-records request tracker (statutory business-day deadline, extensions, overdue flags) | Gov/records | 3 | C+M | NEW:state-machine + NEW:clock | Track public-records requests with a 10-business-day statutory deadline, one allowed extension, and a report of every request past due today. | Alaveteli / RecordTrac |
| W15 | Participatory budgeting (votes allocate; greedy winning set with Σ costs ≤ budget) | Gov/participation | 3 | C+M | NEW:conservation | Run a participatory-budget round where each resident gets 5 votes and the selected projects are the most-voted ones whose combined cost fits the budget. | Decidim / Consul |
| W16 | Citizen proposal w/ support-threshold escalation (one signature per verified user, qualify at N) | Gov/participation | 2 | C+M | NEW:state-machine + DB (dedup) | Build a citizen-proposal service where a proposal advances to a council vote only after 1,000 distinct verified residents support it, double-signing rejected. | Consul / Decidim |
| W17 | 311 service-request tracker (Open311 GeoReport shape: category/location/status timeline, public endpoint) | Gov/service-requests | 2 | C+M | HTTP + NEW:state-machine | Build a pothole-report API where residents file a request with a location and category and can poll a public endpoint for its status history. | Open311 GeoReport v2 |
| W18 | Ranked-choice (IRV) ballot tally (round-by-round elimination, deterministic ties, per-round report) | Gov/elections | 2 | C | CLI | Tally ranked-choice ballots from a CSV, eliminating the lowest candidate each round and printing every round's counts until a majority winner emerges. | OpenSTV/pyrankvote shape |
| W19 | Sealed-bid procurement (bids unreadable until deadline, late rejected, lowest responsive wins) | Gov/procurement | 3 | C+M | NEW:state-machine + NEW:clock | Run a tender where bids submitted before the deadline are unreadable until opening, late bids are refused, and award goes to the lowest bid meeting requirements. | Open Contracting shape |
| W20 | Customs declaration / commercial invoice gen (HS lines, incoterms, Σ line values == declared) | Logistics/customs | 2 | C+M | FS+CLI + NEW:conservation | Generate a commercial invoice and customs declaration for an international parcel whose line values, weights and declared total must reconcile exactly. | Karrio |
| W21 | Proof-of-delivery capture (POD record append-only/immutable; delivered only from out-for-delivery) | Logistics/delivery | 2 | C+M | NEW:state-machine + NEW:hash-chain | Extend a shipment tracker so marking delivered requires a proof-of-delivery record that can never be edited afterward, only superseded with an audit note. | OpenBoxes / Karrio |
| W22 | ASN receiving w/ discrepancy handling (received + over/short/damaged == announced) | Logistics/receiving | 3 | C+M | NEW:conservation | Receive a purchase-order shipment line by line against its advance notice, recording shortages and damage so booked-in stock plus discrepancies equals what was announced. | OpenBoxes |
| W23 | Cycle-count variance + adjustment postings (Σ adjustments == variance; recount above threshold) | Logistics/inventory | 3 | C+M | NEW:conservation + DB | Run a cycle count for a bin list and post signed adjustment entries so the stock ledger lands exactly on the counted quantities, flagging large variances for recount. | OpenBoxes |
| W24 | Lot/batch tracking + earliest-use-by (FEFO) picking (dated-out lots unpickable) | Logistics/inventory | 3 | C+M | IMPORT+DB + NEW:clock | Add lot tracking to an inventory service so pick lists always draw from the lot with the soonest use-by date and refuse lots already past it. | OpenBoxes / FEFO practice |
| W25 | Inter-facility stock requisition (origin + in-transit + destination conserved at every step) | Logistics/movements | 3 | C+M | NEW:conservation | Move 40 boxes from the central depot to a clinic so at any moment origin + in-transit + destination quantities sum to the original total. | OpenBoxes |
| W26 | Container/trailer manifest w/ capacity feasibility (Σ weight ≤ payload, Σ volume ≤ cube) | Logistics/load-planning | 3 | C+M | NEW:conservation + IMPORT | Build a trailer-loading tool that assigns parcels to a trailer without exceeding its weight or volume limits and prints the exact manifest of what was loaded. | Karrio / WMS practice |
| W27 | XMLTV EPG ingest + lineup merge (channel map, overlap preference, gap detection) | Media/live-tv | 3 | C+M | IMPORT+FS | Ingest two XMLTV guide files for the same channel lineup, prefer the richer listing on overlap, and report any hour with no programming. | Jellyfin Live TV |
| W28 | Subtitle parse + re-sync (SRT/VTT shift/scale, overlap/negative-duration rejection) | Media/subtitles | 2 | C+M | CLI | Shift every cue in an SRT file 2.3 seconds later and rescale for a 25→23.976 fps mismatch, writing byte-exact valid output with no overlapping cues. | Jellyfin / SRT-VTT |
| W29 | Play-count + royalty pool split (pro-rata, Σ payouts == pool to the cent, deterministic pennies) | Media/royalties | 3 | C+M | NEW:conservation + NEW:double-entry | Split a $10,000 monthly royalty pool across artists proportionally to qualified plays so payouts sum exactly to the pool, with a deterministic penny remainder rule. | PeerTube / streaming royalty model |
| W30 | Content-rating / parental gate (rating honored on every route; PIN elevates session only) | Media/access-control | 3 | C+M | HTTP+DB (leak probe) | Add profiles to a media server so a kids profile can never retrieve a mature title by any route, and a correct PIN temporarily lifts the limit for that session only. | Jellyfin parental controls |
| W31 | DVR recording scheduler w/ tuner-conflict detection (series rules → timers; priority decides) | Media/dvr | 3 | C+M | IMPORT | Given guide data, series recording rules and 2 tuners, compute the week's recording timers and list exactly which shows lose out during conflicts by priority. | Jellyfin / TvHeadend |
| W32 | Quiz attempt limits + timed attempts (max N, countdown, auto-submit at timeout, best-score policy) | EdTech/assessment | 3 | M | NEW:state-machine + NEW:clock | Extend a quiz service so students get 3 attempts of 20 minutes each, an attempt past its window auto-submits with what was answered, and the best score counts. | Moodle quiz |
| W33 | Plagiarism fingerprint similarity (n-gram hashing + winnowing, threshold report w/ offsets) | EdTech/integrity | 3 | C+M | IMPORT | Compare submitted essays pairwise using n-gram fingerprints and report every pair above 40% similarity with the matching passages' offsets. | Moodle plugin API / MOSS |
| W34 | Prerequisite enforcement (course DAG; enroll blocked until passed; authoring cycle refusal) | EdTech/curriculum | 2 | C+M | IMPORT+DB | Stop a student enrolling in Calculus II until Calculus I shows a passing grade, and refuse curriculum edits that would create a circular prerequisite. | Open edX/Moodle — ≠G71: gating on completion state, not just link cycles |
| W35 | Academic term calendar (add/drop + withdrawal deadlines govern action legality; late drop → W grade) | EdTech/administration | 2 | C+M | IMPORT + NEW:clock | Build a registrar calendar where dropping before the add/drop date removes the course cleanly, after it records a withdrawal, and nothing changes once the term closes. | Canvas/Moodle registrar |
| W36 | Attendance tracking (present/late/absent/excused; excused leaves the denominator) | EdTech/administration | 1 | C+M | DB+IMPORT | Record roll call for each class session and compute every student's attendance percentage where excused absences don't count against them. | Moodle attendance |
| W37 | GPA / credit-hour transcript (credit-weighted 4.0 GPA, repeat-replacement policy, exact rounding) | EdTech/records | 2 | C+M | IMPORT (CLI) | Compute term and cumulative GPA from a transcript with credit-weighted grades where retaking a course replaces the old grade in the calculation. | SIS/registrar — ≠V48 (course-internal weighting) |
| W38 | Insurance policy lifecycle (quote→bind→active→renew/lapse→cancel→reinstate; grace; lapse blocks claims) | Insurance/policy-admin | 3 | C+M | NEW:state-machine + NEW:clock | Build a policy service where a missed renewal payment starts a 30-day grace window, lapse blocks claim payment, and reinstatement needs payment plus a declaration. | openIMIS / OpenUnderwriter |
| W39 | Premium rating-table engine (base rate × factor lookups; itemized breakdown sums to total) | Insurance/rating | 2 | C+M | IMPORT + NEW:conservation | Price a policy from rating tables where the premium is the base rate times the age-band, region and coverage factors, with an itemized breakdown summing exactly. | OpenUnderwriter / openIMIS |
| W40 | Deductible + coverage-limit application (per-claim deductible, per-item limits, aggregate drawdown) | Insurance/claims-math | 2 | C+M | IMPORT + NEW:conservation | Compute the payout for a sequence of claims applying a $500 deductible, per-item limits and a $50,000 annual aggregate that later claims draw down but never overshoot. | openIMIS / P&C practice |
| W41 | Matter/docket management (sequential immutable docket numbers per matter) | Legal/practice-mgmt | 2 | C+M | DB+HTTP | Build a case-management API where filings get sequential docket numbers per matter that never change or reuse even after a filing is withdrawn. | ClinicCases / CourtListener |
| W42 | Court-deadline computation (court days, weekend/holiday roll, service-method extra days) | Legal/docketing | 2 | C+M | IMPORT (CLI) | Compute the response deadline as 21 court days after service, skipping weekends and the given holiday table, adding 3 days when served by mail. | court-rules date math |
| W43 | Conflict-of-interest check (normalize parties, intersect vs all prior matters, hit report) | Legal/ethics | 2 | C+M | IMPORT+DB | Before opening a matter, screen the prospective client and opposing parties against every prior matter's party list and report any overlap with its role and matter. | LegalServer practice |
| W44 | IOLTA client trust accounting (per-client sub-ledgers, no negative, no commingle, 3-way recon) | Legal/trust-accounting | 3 | C+M | NEW:double-entry + NEW:conservation | Build trust accounting where disbursements over a client's balance are refused, fee transfers move earned money out to operating, and client sub-ledgers always sum to the trust balance. | bar-association IOLTA rules |
| W45 | Billable-time capture + invoice (6-minute round-up, per-role rates, budget overage warnings) | Legal/billing | 2 | C+M | IMPORT + NEW:conservation | Turn a month of time entries into a client invoice rounding each entry up to a tenth of an hour at the timekeeper's rate, warning when the matter budget is exceeded. | ClinicCases / legal billing convention |
| W46 | Guided-interview document assembly (conditional question tree → filled template, missing-answer validation) | Legal/documents | 3 | C+M | FS+CLI | Build a guided interview that asks only the questions relevant to earlier answers and renders a completed lease-termination letter from the template. | docassemble |
| W47 | Bates numbering / production stamping (sequential prefixed IDs, continuous across productions, no gaps/dupes) | Legal/discovery | 1 | C+M | FS+CLI | Stamp a folder of documents with Bates numbers ABC000001 onward, continuing from the last production's final number with no gaps or repeats. | e-discovery convention |
| W48 | Lease lifecycle (fixed-term → month-to-month roll, notice periods, deposit-settled closeout) | Proptech/leasing | 3 | C+M | NEW:state-machine + NEW:clock | Build a lease tracker where an unrenewed fixed-term lease rolls to month-to-month, termination needs 30 days' notice, and closeout waits for deposit settlement. | microrealestate |
| W49 | Rent invoicing + late fees (grace period, late fee, partial payments oldest-first, exact balance) | Proptech/rent | 3 | C+M | NEW:conservation + NEW:clock | Post monthly rent for each active lease, add a $50 late fee once the grace period passes, and apply a partial payment to the oldest open charge first. | microrealestate |
| W50 | Security-deposit accounting (refund == deposit − Σ deductions; excess → balance due) | Proptech/deposits | 2 | C+M | NEW:double-entry + NEW:conservation | Account for a tenant's deposit so move-out deductions are itemized and the refund plus deductions equals the deposit exactly, any excess becoming a balance due. | landlord-tenant statutes |
| W51 | Maintenance work-order workflow (triage→vendor-assign→schedule→complete→close; emergency skips triage; reopen window) | Proptech/maintenance | 2 | C+M | NEW:state-machine | Build a repair-ticket service where emergency leaks skip triage straight to assignment and a ticket can be reopened within 14 days of closing. | Condo / ORPMS |
| W52 | Unit availability / no-double-lease (overlapping lease dates rejected; exact vacancy report) | Proptech/occupancy | 2 | C+M | NEW:conservation + DB | Prevent two leases with overlapping date ranges on the same unit and produce an exact list of units vacant on any queried date. | microrealestate / ORPM |
| W53 | Farm asset + activity-log registry (assets + dated logs; future logs become a task list) | Agriculture/records | 2 | C+M | DB+HTTP | Build a farm-records API where a corn planting is an asset and every seeding, fertilizing and observation is a dated log tied to it, future-dated logs listing as upcoming tasks. | farmOS |
| W54 | Harvest yield aggregation (Σ per planting/field/season, unit normalization, exact yield-per-area) | Agriculture/harvest | 2 | C | IMPORT (CLI) | Aggregate a season's harvest logs into total yield per field and per crop, converting mixed lb/kg entries and computing exact yield per acre. | farmOS |
| W55 | Spray/input application w/ withholding enforcement (pre-harvest interval blocks harvest logs) | Agriculture/compliance | 3 | C+M | IMPORT + NEW:clock | Record pesticide applications with a 14-day pre-harvest interval and make the system refuse a harvest log for that planting until the interval has fully passed. | farmOS / GAP audits |
| W56 | Herd head-count conservation (moves/births/sales/deaths; total == Σ paddock counts) | Agriculture/livestock | 2 | C+M | NEW:conservation | Track a cattle herd across paddocks so every move, birth, sale and death is a log and the herd total always equals the sum of paddock counts. | farmOS |
| W57 | Meter-reading VEE validation (spike/negative/missing/static/sum checks → flags + deterministic estimates) | Utilities/metering | 3 | C+M | IMPORT (CLI) | Validate a month of 15-minute meter reads, flagging spikes, negatives and gaps, filling gaps with the documented interpolation rule, and reporting the sum check. | utility MDMS VEE practice |
| W58 | Tiered + time-of-use bill calculator (read pairs w/ rollover; Σ block + fixed charges == bill) | Utilities/billing | 3 | C+M | IMPORT + NEW:conservation | Compute a power bill from start/end reads with rollover handling, splitting usage into tier blocks and peak/off-peak windows so itemized charges sum exactly to the total. | utility tariff practice — ≠F53 (calendar-TOU + read-pair derivation) |
| W59 | Outage ticket management (reports roll up to one asset outage; restore closes children) | Utilities/outage | 3 | C+M | NEW:state-machine | Build an outage tracker where customer reports group under one feeder outage, the affected count comes from meters on that feeder, and restoring it closes every linked report. | utility OMS practice |
| W60 | Net-metering credit ledger (export credits offset imports oldest-first, never negative, annual true-up) | Utilities/net-metering | 3 | C+M | NEW:conservation + NEW:double-entry | Track a solar customer's exported kWh as credits that offset later consumption oldest-first, never going negative, with an annual true-up paying out leftovers. | NEM tariff / OpenEnergyMonitor |

**Oracle-demand signal from this wave:** state-machine **+18** · import-driver exact-fixture rule
tables **+17** · conservation **+13** · injectable-clock **+12** (statutory deadlines, grace
periods, withholding intervals, renewals — the regulated world runs on the clock) · double-entry
+4 · hash-chain +1. No genuinely novel oracle kind needed; the one borderline addition is a tiny
business-day/holiday-calendar **fixture table** over import-driver (W14/W42 deadline math — §4
rule-engine-fixtures shape, not new code).

### 3.7 Wave-4 infra/integration pattern-layer additions (2026-07-10)

**Provenance:** read-only research of the SaaS connective-tissue layer (Svix, Singer/Airbyte,
SCIM/Okta/Entra/WorkOS, Ory Keto/Zanzibar, OPA/Casbin, Novu, Lago/Kill Bill, Unleash, Auth0
rotation, KMS envelope-encryption, PagerDuty, Stripe API-versioning). Patterns are **contracts,
and contracts are exactly what deterministic oracles grade** — 25+ of the 33 surviving rows are
gradable with existing oracles today. **All rows: status = `mapped`, stdlib = yes.** Final dedupe
dropped **11 of 44** staged rows, almost all against wave-1 G-rows the stager couldn't see:
P1 SCIM server (=G64) · P9 lockout (=G62) · P19 durable workflow (=G32 — its **workflow-replay
oracle proposal is retained in §4 #18**) · P20 trigger→action engine (=G35) · P22 heartbeat
monitor (=G52) · P24 approval chain (=G37) · P25 RRULE expansion (=G28+G27) · P31 sessionization
(=G13) · P34 retention sweeper (=G4) · P44 preference+digest (=G6; the per-subscriber preference
surface is G6/S31's MODIFY variant) · P7 magic-link (≈S4 single-use-token flow — same call wave 1
made on invitation/magic-link tokens). Surviving IDs keep their staged P-numbers (gaps =
documented drops).

| ID | Class | Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| P2 | Directory-sync reconciler (external directory snapshot → local users; idempotent re-run) | identity-provisioning | 3 | C+M | DB+IMPORT | Given a fixture file of a company directory, reconcile the local user table to match it and report exactly what changed. | WorkOS Directory Sync shape |
| P3 | ReBAC relationship-tuple engine (Zanzibar-shape: `object#relation@subject`, transitive resolution, check/expand) | authorization | 3 | C+M | IMPORT (graph fixtures) | Build a permission checker where document access flows through folder and team relationships, answering whether a user can view a given document. | Ory Keto / Zanzibar |
| P4 | ABAC policy engine (attribute matchers, deny-overrides, default-deny) | authorization | 3 | C+M | IMPORT (decision tables) | Build a policy evaluator that decides allow or deny from user department, resource sensitivity, and time-of-day rules, where any matching deny wins. | OPA / Casbin |
| P5 | Refresh-token rotation + reuse detection (token families; reuse revokes the family) | auth-sessions | 3 | C+M | HTTP+DB + NEW:clock | Add rotating refresh tokens to a login service so that presenting an already-used token logs the whole device family out. | Auth0 / Duende |
| P6 | OAuth 2.0 device-authorization grant (RFC 8628: device/user codes, polling, slow_down) | auth-sessions | 3 | C+M | HTTP + NEW:clock | Build the login flow a CLI uses: it shows a short code, the user approves it in a browser page, and the CLI polls until it receives credentials. | RFC 8628 / gh CLI |
| P8 | Organizations / teams / invitations (roles, invite tokens, seat limits, ownership transfer) | tenancy-model | 3 | C+M | HTTP+DB + NEW:SMTP-sink | Build workspace management where an admin invites teammates by email, invites are accepted with a token, and the workspace never exceeds its seat limit. | B2B SaaS spine (WorkOS orgs shape) |
| P10 | Cursor/keyset pagination (opaque cursor, provably no skips/dupes under concurrent writes) | API | 2 | C+M | HTTP+DB (pages-union invariant) | Convert a list endpoint to opaque-cursor paging and prove that rows added mid-scan never cause repeats or gaps. | Stripe/Slack; extends S20 — the stability invariant is the new class |
| P11 | Bulk/batch endpoint (per-item status, partial-failure report, all-or-nothing mode) | API | 2 | C+M | HTTP+DB | Add a batch endpoint that applies up to 100 creates and updates in one call and returns an individual outcome for each item. | Stripe batch / SCIM /Bulk |
| P12 | Long-running-operation pattern (202 + operation resource, polling, result, cancel) | API | 3 | C+M | HTTP + NEW:state-machine | Make a slow report-generation endpoint return immediately with an operation ID the client polls until the result is ready or cancelled. | Google/Azure LRO convention |
| P13 | API version gates + transform chain (date-pinned versions; per-version request/response transforms) | API | 3 | C+M | HTTP (two pinned versions → exact shapes) | Add date-based API versioning so old clients keep receiving the old response shape while new logic serves only the newest schema. | Stripe api-versioning |
| P14 | Request-schema validation middleware (declarative schema → 422 + JSON-path error list) | API | 2 | C+M | HTTP+IMPORT | Add declarative input validation to an API so malformed requests return a structured list of every failing field path. | FastAPI/JSON-Schema shape |
| P15 | Signed API requests (canonical request, HMAC, skew window, nonce replay rejection) | API-security | 2 | C+M | IMPORT + NEW:clock | Build request signing for an API client and server so tampered, stale, or replayed requests are rejected with the exact reason. | AWS SigV4 / Svix — ≠S12/S13 webhook HMAC (client-request signing) |
| P16 | Graceful shutdown / connection drain (readiness flips, intake stops, in-flight finish, deadline) | runtime | 3 | C+M | HTTP + NEW:process-lifecycle | Make a service drain cleanly on shutdown: it stops advertising ready, finishes requests already in progress, and exits within a deadline. | k8s SIGTERM practice |
| P17 | Webhook subscription-management service (per-endpoint secrets, event filtering, attempt log, redrive, auto-disable) | webhooks | 3 | C+M | HTTP+DB (fixture receiver) | Build the management layer of a webhook platform: customers register endpoints, pick event types, inspect delivery attempts, and redrive failures. | Svix; extends S12 — the management/redrive surface is the new class |
| P18 | Event collection + destination fan-out (CDP-shape: ingestion, per-destination transform + isolated delivery log) | event-pipeline | 4 | C+M | HTTP+DB | Build an event hub that accepts product events and forwards each to three configured destinations with its own mapping and failure record. | Segment / RudderStack |
| P21 | Fair multi-tenant job dispatch (round-robin, per-tenant caps, starvation-freedom) | jobs | 3 | C+M | DB + NEW:concurrency (fairness) | Change a job worker so one tenant submitting thousands of jobs cannot delay another tenant's single job beyond its fair turn. | noisy-neighbor practice — ≠S14/V57 |
| P23 | Alert escalation policy engine (dedup-key incidents, ack timers, level escalation, on-call resolution) | incident-response | 3 | C+M | NEW:state-machine + NEW:clock | Build alert routing where an unacknowledged incident escalates to the secondary on-call after thirty minutes and duplicate alerts fold into the open incident. | PagerDuty — ≠G7/G8 (firing/routing); the escalation ladder is the new class |
| P26 | Singer-protocol tap + target pair (SCHEMA/RECORD/STATE JSONL over stdio, pipe composition, resume) | connectors | 3 | C+M | CLI+FS (byte-exact stream) | Build a data extractor and loader that speak the Singer message protocol over pipes and resume from the last saved state file. | Singer spec — ideal fit for the existing CLI oracle |
| P27 | Incremental sync connector (cursor checkpointing, interrupt-resume, exactly-once on load) | connectors | 3 | C+M | DB+FS (kill mid-sync, re-run) | Build a sync job that copies only rows changed since its last checkpoint and, after being interrupted, resumes without duplicating rows. | Airbyte sync modes — ≠S45 (one-shot ETL) / S47 (outbox emit) |
| P28 | Bulk import w/ staged validation (per-row error report, atomic commit or full reject) | data-admin | 2 | C+M | HTTP/CLI+DB | Build a contact importer that validates an uploaded CSV, reports each bad row with its reason, and commits nothing unless the file is clean. | every SaaS admin importer |
| P29 | Zero-downtime expand-contract migration (dual-write → batched backfill → verify → cutover → drop) | migrations | 3 | C+M | DB (per-phase assertions) | Rename a column on a live table by dual-writing both names, backfilling in batches, verifying counts match, then dropping the old one. | online schema-change practice; extends S21 |
| P30 | Event schema registry + upcaster (versioned payloads, old→current chain on read) | eventing | 2 | C+M | IMPORT | Build an event reader that transparently upgrades version-1 and version-2 payloads to the current shape through chained converters. | Axon upcasters; complements S18 |
| P32 | GDPR erasure workflow (cascading anonymization, tombstone, idempotent, ledger integrity preserved) | privacy | 3 | C+M | DB (residual-PII scan) + NEW:idempotency-replay | Build account erasure that anonymizes a user's personal data everywhere it appears while keeping order totals intact, and is safe to run twice. | GDPR Art. 17; complements S67 (export) |
| P33 | Consent registry (per-purpose grant/withdraw, versioned policy text, enforcement API, immutable audit) | privacy | 2 | C+M | DB+HTTP | Build a consent service where marketing mail is only sendable to users whose latest recorded choice for that purpose is a grant. | GDPR/CCPA; generalizes V23 |
| P35 | Credit notes + account credit application (credit against invoice, auto-apply, never negative, conserved) | billing | 3 | C+M | NEW:conservation + NEW:double-entry | Add credit notes to a billing system so an overcharged customer's credit reduces their next invoice and every cent is accounted for. | Kill Bill — ≠F13 (refund to payment method) |
| P36 | License-key issue/verify (signed offline keys: feature bits, end date, revocation list) | licensing | 2 | C+M | IMPORT | Build a license system that mints signed keys unlocking specific features until a date and validates them fully offline. | Keygen / desktop licensing |
| P37 | Encryption-key rotation service (envelope encryption, dual-read grace, background re-wrap, retirement) | secrets | 3 | C+M | IMPORT+DB (all rows readable throughout) | Rotate the master key of an encrypted datastore without downtime: old rows stay readable, a background job re-wraps them, then the old key is retired. | KMS envelope practice; extends S29 |
| P38 | Field-level PII encryption / crypto-shredding (per-tenant keys, deterministic vs randomized modes) | secrets | 3 | C+M | DB+IMPORT | Encrypt email and phone columns with a per-tenant key such that deleting one tenant's key makes only that tenant's data unreadable. | per-tenant KMS practice; pairs with P37 |
| P39 | Dynamic config service (versioned sets, validate-on-publish, staged rollout, instant rollback, version-fingerprint polling) | config | 3 | C+M | HTTP+DB | Build a runtime configuration service where a bad publish is rejected by validation and a good one can be rolled back to the prior version in one call. | LaunchDarkly/consul shape — ≠S28 (static) / S62 (deploy) |
| P40 | Flag gradual rollout + sticky bucketing (hash → 0–100 bucket, percentage gate, OR-combined strategies) | feature-flags | 2 | C+M | IMPORT (deterministic buckets) | Extend a flag evaluator with a 20% rollout that always gives the same user the same answer and combines with a country-segment strategy as OR. | Unleash; extends S11 — the deterministic bucketing math is the new class |
| P41 | Unique-ID generation service (snowflake-shape: time-ordered, worker bits, sequence rollover, clock-regression guard) | infra | 2 | C+M | IMPORT + NEW:clock | Build an ID generator producing sortable unique 64-bit IDs across four workers, refusing to emit if the clock moves backwards. | Twitter Snowflake |
| P42 | Message catalog w/ locale fallback (fallback chain, plural rules, interpolation, missing-key report) | i18n | 2 | C+M | IMPORT | Build a translation lookup where Austrian German falls back to German then English, and counts pick the right plural form. | ICU MessageFormat / gettext |
| P43 | Plugin/hook registry (ordered hook chains, filter pipelines, per-plugin error isolation, enable/disable) | extensibility | 2 | C+M | IMPORT | Build a plugin system where three plugins register for a save-hook in priority order and one crashing plugin doesn't stop the others. | WordPress hooks / pytest plugins |

**Oracle-demand signal from this wave (surviving rows):** injectable-clock +5 direct (rotation,
device-grant, request-skew, escalation timers, snowflake IDs; 5 more staged votes folded onto
G-row dup targets) · state-machine +2 · idempotency-replay +1–3 (erasure re-run, sync resume,
credit application) · SMTP-sink +1 · concurrency +1 · **two genuinely NEW oracle kinds proposed:
workflow-replay-determinism and process-lifecycle probe** (now §4 #18/#19).

### 3.8 Wave-6 not-covered-backlog additions (leftover-cluster sweep, 2026-07-10)

**Provenance:** systematic sweep of the 24 clusters every earlier wave listed as "not covered yet"
(Rasa/Botpress, MinIO/S3 internals, Kill Bill deep billing, GitLab-CI/Harbor/Verdaccio, OpenCATS,
Gramps/GEDCOM, GPX/RDP tooling, ThingsBoard, Frigate, Kea/wg-easy/octoDNS, CalDAV RFCs, Suite/
EspoCRM, Postfix/postgrey/DKIM, Koha/Evergreen, restic/borg, MobilityData GTFS, IRS Pub 15-T +
CCPA garnishment, Procore, QloApps, telecom mediation/LNP, Odoo MRP, Tickets CAD/Resgrid).
**All rows: status = `mapped`, stdlib = yes** (X40 notes a dep for full RSA signing only). The
stager deduped against the full atlas **including G-rows** (16 pre-drops recorded in its staging
file, e.g. object versioning≈S68+G55, payment-retry≈S40/F23, offer approval≈G37, BOM≈G39,
telemetry rollups≈S46, camera heartbeat≈G52, CRM timeline≈S22, rating≈F22, water tier math≈F53).
Final merge dropped **6 more cross-wave collisions** the stager couldn't see (other staging
files): X8 (=P35 Kill Bill credit notes) · X18 (=SH-W1 wiki revision diff/revert) · X19 (=SH-W4
BookStack cascading permissions) · X7 (≈P15 signed API requests — P15's oracle note absorbs the
official-SigV4-test-vector grading idea) · X4 (≈P4 policy-document evaluator, deny-overrides —
IAM wildcard/condition-key fixtures noted as P4 oracle enrichment) · X60 (≈W57 meter VEE
validation — the estimate/true-up flow is W57's MODIFY surface). Surviving IDs keep their staged
X-numbers (gaps = documented drops).

| ID | Class | Vertical/Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| X1 | Intent classification router (keyword/feature scoring, confidence threshold, fallback intent) | chat-NLU/routing | 2 | C+M | IMPORT (utterance→intent fixtures) | Build a message router that scores each incoming utterance against keyword tables per intent and returns the best intent, or the fallback intent when no score clears the confidence threshold. | Rasa NLU / Botpress |
| X2 | Slot-filling form state machine (required slots, per-slot validation, interrupt + resume) | chat-NLU/dialogue | 3 | C+M | NEW:state-machine | Build a booking dialogue that keeps asking for the missing pieces of date, party size, and name, rejects invalid answers with a re-prompt, and resumes where it left off after an off-topic question. | Rasa Forms |
| X3 | NLU training-data validator (min examples, cross-intent duplicates, entity consistency) | chat-NLU/training-data | 2 | C+M | CLI (exact error list) | Build a checker that scans a chatbot training file and reports every intent with too few examples, every sentence assigned to two intents, and every entity label used inconsistently. | `rasa data validate` |
| X5 | S3 multipart-completion contract (part registry, per-part checksum, composite tag = hash-of-hashes-N) | object-storage/multipart | 3 | C+M | IMPORT + NEW:conservation (every byte accounted) | Build an upload service where a large file arrives as numbered parts, completion requires the client's part list to match what was stored, and the object's identity tag is the hash of all part hashes suffixed with the part count. | S3 multipart ETag — ≠G54: grades the part-ledger/composite-tag CONTRACT |
| X6 | Object lifecycle rule engine (prefix/tag filters, N-days-after-creation delete, noncurrent-version cleanup, legal hold precedes) | object-storage/lifecycle | 3 | C+M | NEW:clock + DB/FS | Build a nightly job that applies per-bucket rules deleting objects a set number of days after creation, only for matching prefixes or tags, while never touching an object under an active legal hold. | MinIO ILM — ≠G4: version/delete-marker/hold semantics |
| X9 | Account overdue-state ladder (balance age drives ordered states + entitlement changes; instant clear on payment) | billing/collections | 3 | C+M | NEW:state-machine + NEW:clock | Build an account-status engine that moves a customer through warning, restricted, and blocked states as their unpaid balance ages, downgrades their entitlements at each step, and restores everything the moment they pay. | Kill Bill Overdue — ≠S40 dunning (account ladder, not retry schedule) |
| X10 | Effective-dated catalog versioning + plan-change alignment (version pinned at signup; up/downgrade timing rules) | billing/catalog | 3 | C+M | NEW:state-machine + NEW:clock | Build a plan catalog where price changes only apply to customers who subscribe after the new version's effective date, and a downgrade takes effect at the end of the current term while an upgrade applies immediately. | Kill Bill catalog/alignments |
| X12 | CI job-matrix expansion + needs-DAG compiler (matrix permutations → concrete job set; cycle rejection; stage inference) | devtools-CI/pipeline | 3 | C+M | IMPORT (exact expanded graph) | Build a pipeline compiler that expands a job defined over two OS values and three versions into six concrete jobs and wires each one's dependencies, rejecting any configuration whose dependencies form a loop. | GitLab parallel:matrix + needs |
| X13 | Artifact tag-immutability rules (pattern-matched immutable tags; overwrite/delete rejected) | devtools/registry | 2 | C+M | DB+HTTP | Build a package registry where any tag matching a protected pattern can never be overwritten or deleted once pushed, while other tags stay mutable. | Harbor tag immutability |
| X14 | Tag-retention policy engine (keep latest-K per pattern, exclusions, immutable always survive, dry-run) | devtools/registry | 3 | C+M | IMPORT+DB (+NEW:clock for last-pull rules) | Build a cleanup engine that keeps the newest five tags matching release patterns in each repository, never touches protected tags, and can print exactly what a real run would delete without deleting it. | Harbor retention — ≠G4: latest-K selection algebra, not age purge |
| X15 | Dependency-proxy registry (first request fetches from fixture upstream + caches; upstream-newer refresh) | devtools/registry | 3 | C+M | NEW:multi-service + FS | Build a pass-through package registry that fetches an artifact from the upstream source the first time it is requested, serves its stored copy afterwards, and re-fetches when the upstream copy is newer. | Harbor proxy cache / Verdaccio uplinks |
| X16 | Package publish + semver range resolution (dist-tags; `^1.2.0` → exact best version; republish rejected) | devtools/registry | 3 | C+M | HTTP+IMPORT (exact resolution) | Build a private package registry where publishing the same version twice fails and an install request carrying a version range returns exactly the highest satisfying published version. | Verdaccio |
| X17 | Candidate pipeline state machine (per-job-order stages, guarded transitions, rejection reasons, activity log) | HR-ATS/pipeline | 2 | C+M | NEW:state-machine + DB | Build a recruiting tracker where each candidate advances through screening, interview, and offer stages for a specific job opening, can never jump from applied straight to hired, and every stage change is logged with who moved them. | OpenCATS |
| X20 | GEDCOM parse/write round-trip (INDI/FAM records, cross-references, byte-consistent write-back) | genealogy/interchange | 3 | C+M | FS+IMPORT (round-trip equality) | Build a family-tree file reader that loads people and family records with their parent and child links from a GEDCOM file and writes the same tree back out without losing any relationship. | GEDCOM spec / Gramps |
| X21 | Person merge w/ lineage integrity (union facts, rewrite family links, reject circular ancestry) | genealogy/merge | 3 | C+M | IMPORT (acyclic-ancestry invariant) | Build a duplicate-person merger that combines two records for the same ancestor, repoints every family relationship to the surviving record, and refuses a merge that would create a circular ancestry. | Gramps merge tool |
| X22 | GPS track simplification (RDP w/ tolerance; property: every dropped point within tolerance of the line) | maps-GPS/simplification | 2 | C+M | IMPORT (property check) | Build a route thinner that reduces a recorded GPS track to far fewer points while guaranteeing no original point ends up farther than the chosen tolerance from the simplified path. | RDP / gpxpy ecosystem |
| X23 | Geofence entry/exit event detection (stateful crossing + dwell threshold, per-zone log) | maps-GPS/geofence | 2 | C+M | IMPORT (exact event sequence) | Build a monitor that replays a vehicle's timestamped positions against named zones and emits one entry event and one exit event per visit, ignoring blips shorter than the dwell threshold. | fleet tracking — ≠V40: stateless point-in-polygon there |
| X24 | Route distance + moving-time accumulation (haversine, moving/stopped split, elevation gain) | maps-GPS/metrics | 2 | C+M | IMPORT | Build a workout summarizer that computes total distance from raw coordinates, splits elapsed time into moving and stopped portions using a speed threshold, and totals the elevation climbed. | GPX tooling |
| X25 | Device registry + claim provisioning (provision key issues credentials exactly once; last-seen activity) | IoT/provisioning | 3 | C+M | HTTP+DB + NEW:clock | Build a device registry where a new sensor presenting a valid provisioning key receives credentials exactly once, a second claim with the same key is refused, and any device silent too long shows as inactive. | ThingsBoard |
| X26 | Alarm rule lifecycle w/ ack×clear axes (threshold-for-duration, independent ack/clear, severity escalation) | IoT/alarms | 3 | C+M | NEW:state-machine + NEW:clock | Build an alarm service where a temperature staying too high for five minutes raises a major alarm that an operator can acknowledge while it is still active, escalates to critical if it persists, and only fully closes once both cleared and acknowledged. | ThingsBoard — ≠G7: two-axis lifecycle + escalation |
| X27 | Tiered recording retention (continuous D1 / motion D2 / event D3 ladders; protected clips immune) | NVR/retention | 3 | C+M | FS + NEW:clock | Build a recording janitor that keeps all footage three days, motion footage seven, footage overlapping a tagged event thirty, never touches locked clips, and lists exactly which segments each nightly pass removed. | Frigate — ≠G4: tiered/overlap semantics |
| X28 | Recording continuity gap detector (segment index vs expected coverage; offline-vs-disk-full causes) | NVR/health | 2 | C+M | FS+IMPORT (exact gap list) | Build an auditor that walks each camera's stored recording segments for a day and reports every stretch longer than a minute where footage that should exist is missing. | Frigate/ZoneMinder ops |
| X29 | Zone-file generator + validator (single SOA, serial must increase, CNAME conflicts, exact error list) | DNS/zone-files | 2 | C+M | CLI+FS | Build a zone-file tool that renders records into a valid zone with an auto-bumped serial and refuses to emit a zone where a CNAME name also carries any other record type. | named-checkzone / octoDNS |
| X31 | Address-pool lease allocation (unique from CIDR pool; allocated + free == pool; no double-alloc concurrent) | VPN-DHCP/leases | 2 | C+M | NEW:conservation + NEW:concurrency | Build an address allocator that hands each new client a unique address from a configured range, reclaims released ones for reuse, and never gives the same address to two active clients even under simultaneous requests. | Kea DHCP / wg-easy |
| X32 | VPN peer config lifecycle (keypair registry, per-peer rendered config, atomic revocation) | VPN/peer-config | 2 | C+M | FS+IMPORT (exact rendered configs) | Build a VPN admin service that creates a new peer with its own address and downloadable config file, and whose server config no longer contains any trace of a peer once revoked. | wg-easy shape |
| X30 | Multi-attendee free/busy aggregation + slot intersection (union of N calendars; all-K-free slots) | groupware/free-busy | 2 | C+M | IMPORT (exact interval math) | Build a meeting finder that merges four people's busy times and returns every one-hour slot this week where all four are simultaneously free. | RFC 4791 — ≠G26: single-host there, N-party intersection here; also serves ATS interview panels |
| X33 | Recurrence override handling (RRULE + EXDATE + RECURRENCE-ID overrides → exact instance list) | groupware/recurrence | 3 | C+M | IMPORT (exact instance lists) | Build an expander for a weekly meeting where two dates are cancelled and one occurrence is moved an hour later, producing exactly the right final set of concrete meeting times. | RFC 5545 — ≠G28: the exception/override layer |
| X34 | Meeting invite reply state (accept/decline/tentative per attendee; reschedule resets replies) | groupware/invitations | 2 | C+M | NEW:state-machine + DB | Build an invitation service where each invitee's accept, decline, or tentative reply is tracked per meeting and every reply resets to unanswered when the organizer changes the time. | RFC 6638 iTIP shape |
| X35 | Sales pipeline stage machine + weighted forecast (per-stage probability; forecast == Σ amount × prob; terminal states) | CRM/pipeline | 2 | C+M | NEW:state-machine + IMPORT (exact forecast) | Build an opportunity tracker where deals move through qualification and proposal stages, closed deals can never reopen, and the pipeline forecast is the exact probability-weighted sum of open deal amounts. | SuiteCRM |
| X36 | Rule-based lead scoring w/ decay (points per attribute/event, inactivity decay, MQL threshold exactly once) | CRM/scoring | 2 | C+M | IMPORT + NEW:clock | Build a lead scorer that adds points for job title and site visits, subtracts points after weeks of silence, and marks a lead sales-ready the first time its score crosses the bar. | SuiteCRM shape |
| X37 | Record dedupe + merge w/ survivorship (normalized-key candidates, per-field rules, relation re-parenting, tombstone) | CRM/dedupe-merge | 3 | C+M | DB+IMPORT | Build a contact deduper that finds records sharing a normalized email or phone, merges them keeping the most recently updated value per field, and moves every note and task onto the surviving record. | EspoCRM/SuiteCRM — ≠G10 (event attribution) / ≠W4 (exact-match MPI, oldest-survivor) |
| X64 | Lead conversion split (lead → linked contact + account + opportunity; duplicate check; lead locked) | CRM/conversion | 2 | C+M | DB (referential integrity) | Build a lead converter that turns one qualified lead into a linked contact, company, and deal in a single step, warns when a matching company already exists, and freezes the original lead afterwards. | SuiteCRM |
| X38 | Virtual alias routing resolver (per-address + catch-all entries, recursive expansion, fan-out, loop detection) | mail/routing | 2 | C+M | IMPORT (exact recipient sets) | Build an address resolver that expands mail for sales@ into its three members, forwards anything@old-domain to the new domain, and detects an alias that eventually points back to itself. | Postfix virtual(5) |
| X39 | Greylisting policy engine (unknown triplet → temp reject; retry-after-delay accepted; auto-allowlist; aging) | mail/anti-spam | 2 | C+M | NEW:state-machine + NEW:clock | Build a mail policy service that temporarily refuses the first delivery attempt from an unknown sender triple, accepts the retry arriving after five minutes, and stops challenging a sender who has passed several times. | postgrey |
| X40 | DKIM record generation + header canonicalization (selector TXT record; relaxed/simple canonical signing input) | mail/authentication | 3 | C+M | IMPORT+CLI (canonicalization vectors) | Build a tool that renders the DNS text record for a mail signing key under a chosen selector and produces the exact canonicalized header block that would be signed for a given message. | RFC 6376 (full RSA sign needs a dep; canonicalization is stdlib) |
| X41 | Loan lifecycle (per-item-type period, renewal limit, renewal blocked when a hold waits, check-in closes) | library-ILS/circulation | 3 | C+M | NEW:state-machine + NEW:clock | Build a lending service where a book checks out for three weeks, renews at most twice, refuses renewal when someone else is waiting for it, and closes cleanly on return. | Koha circulation |
| X42 | Hold-list fulfillment (priority queue per title; hold-shelf window lapse → next patron; never double-promised) | library-ILS/holds | 3 | C+M | NEW:conservation + NEW:state-machine + NEW:clock | Build a holds service where a returned book is set aside for the first person in line, moves to the next person if not picked up within seven days, and never gets promised to two patrons at once. | Evergreen — ≠V57: adds shelf-window lapse + re-offer |
| X43 | Fine accrual engine (daily fine after grace, per-item cap, forgiveness option, exact settle) | library-ILS/fines | 2 | C+M | NEW:clock + NEW:conservation | Build a fines calculator that starts charging a daily amount once a grace period passes, stops at the per-item cap, and settles the exact balance when the patron pays at return. | Koha fines |
| X65 | Incremental snapshot manifest diff (exact new/changed/deleted plan; snapshots self-contained via references) | backup/snapshots | 3 | C+M | FS+IMPORT (self-containment invariant) | Build a backup planner that compares a folder against the last snapshot's manifest, copies only new or changed files, and still lets any snapshot be listed as a complete point-in-time picture. | restic/borg model |
| X45 | GFS retention pruning (keep-daily/weekly/monthly/yearly calendar buckets → exact keep/delete; newest always kept) | backup/retention | 2 | C+M | IMPORT + NEW:clock | Build a pruner that, given ninety dated snapshots and a policy of seven daily, four weekly, and twelve monthly, returns exactly which snapshots survive and never removes the most recent one. | restic forget / borg prune — ≠X14: calendar buckets vs latest-K |
| X46 | Restore verification (restore to fresh dir; byte/hash tree comparison; corrupted chunk → named damaged file) | backup/verification | 2 | C+M | FS (independent tree comparison) | Build a verify command that restores a snapshot to an empty folder, proves every file matches its recorded hash, and pinpoints the affected file when a stored piece has been tampered with. | restic/borg check |
| X47 | GTFS stop-times validator (strictly increasing sequences, non-decreasing times, implausible speeds; exact findings) | transit/feed-validation | 3 | C+M | CLI+FS (fixture feeds → exact report) | Build a transit-feed checker that reports every trip whose stop order repeats a sequence number, runs backwards in time, or implies a bus travelling faster than plausible between stops. | MobilityData GTFS validator |
| X48 | Transfer-window feasibility checker (min transfer times vs scheduled arrivals/departures → infeasible list) | transit/transfers | 3 | C+M | IMPORT (exact infeasible list) | Build an analyzer that flags every advertised connection where the next vehicle leaves before the minimum walking time from the arriving vehicle has passed. | GTFS transfers.txt |
| X44 | Progressive tax-bracket withholding (marginal brackets per filing status; annualize→compute→de-annualize; exact) | payroll/withholding | 2 | C+M | IMPORT (published-table fixtures) | Build a withholding calculator that annualizes a paycheck, applies each tax bracket only to the income inside it for the employee's filing status, and returns the exact per-period amount to withhold. | IRS Pub 15-T shape — ≠G40: bracket math, not component arithmetic |
| X66 | Garnishment ordering + disposable-earnings cap (priority stacking; cap == lesser of 25% or excess over 30× min wage) | payroll/garnishment | 3 | C+M | IMPORT + NEW:conservation | Build a garnishment engine that stacks several court orders in priority order and never withholds more in a pay period than the legal ceiling allows, paying later orders only from what headroom remains. | CCPA Title III |
| X50 | Pay-period lock + retro adjustment (closed period immutable; correction lands as retro item on open period + audit) | payroll/period-control | 3 | C+M | NEW:state-machine + DB (append-only audit) | Build a payroll ledger where finished pay periods can never be edited, and fixing an underpayment from a locked period automatically adds a clearly-labelled catch-up line to the next run. | retro-pay practice — sibling of F29 GL close, ≠ by retro carry-forward |
| X51 | RFI workflow w/ ball-in-court (exactly one responsible party; due-date aging; reopen with reason) | construction/RFI | 2 | C+M | NEW:state-machine + NEW:clock | Build a question-tracking service for job sites where every open question shows exactly whose move it is, turns overdue when the answer deadline passes, and closes only after the asker accepts the answer. | Procore RFI |
| X52 | Submittal review cycle (approved / approved-as-noted / revise-and-resubmit → revision N+1; approval freezes) | construction/submittals | 2 | C+M | NEW:state-machine | Build a document-approval flow where a rejected shop drawing must come back as the next numbered revision and an approved one can never be replaced silently. | Procore submittals |
| X53 | Punch-list closeout (complete → verify or bounce; closeout gate == every item verified) | construction/punch-list | 2 | C+M | NEW:state-machine + NEW:conservation (gate) | Build a defect-list service where a fixed item only counts once the inspector signs it off and the project cannot be marked finished while any item remains unverified. | Procore punch list |
| X54 | Room-block / allotment booking (group block w/ cutoff; pickups draw down; auto-release at cutoff; never oversold) | hospitality/group-blocks | 3 | C+M | NEW:conservation + NEW:clock | Build a group-booking service that sets aside twenty rooms for a wedding until a cutoff date, counts each guest booking against that block, and returns whatever is left to normal sale the day the cutoff passes. | hotel PMS / QloApps |
| X55 | No-show / cancellation fee engine (free-until-D-days policy, window fees, no-show charge + room release) | hospitality/penalties | 2 | C+M | NEW:clock + IMPORT (exact fee) | Build a reservations policy engine that cancels free of charge a week out, charges the first night inside the window, and automatically charges a no-show and frees the room at midnight on arrival day. | QloApps cancellation rules |
| X56 | CDR mediation (multi-format parse, reject-with-reason, dedupe, partial-record assembly; every input accounted) | telecom/mediation | 3 | C+M | IMPORT + NEW:conservation | Build a usage-record processor that ingests raw call records in two formats, throws out malformed and repeated ones with reasons, stitches multi-part records of a single call together, and accounts for every input record in its output report. | telecom mediation — upstream of F22 rating |
| X57 | Number-porting state machine (FOC confirmation gates activation; cancel only pre-activation; reason codes) | telecom/porting | 3 | C+M | NEW:state-machine + NEW:clock | Build a number-transfer tracker where a port request must receive the losing carrier's confirmation before it can schedule activation, can be cancelled any time before activation but never after, and records every status change. | LNP/NPAC + FOC |
| X67 | Work-order routing execution (routing spawns ordered operations; predecessor gates start; exact quantity hand-offs) | manufacturing/routing | 3 | C+M | NEW:state-machine + NEW:conservation | Build a shop-floor tracker where making fifty brackets generates cut, mill, and inspect steps in order, milling can only begin on pieces cutting has finished, and piece counts match at every hand-off. | Odoo MRP routings |
| X59 | Scrap conservation tracking (started == good + scrap + rework per operation; write-offs; exact yield report) | manufacturing/scrap | 2 | C+M | NEW:conservation + DB | Build a production-quality ledger where every unit that enters an operation is accounted for as good, scrapped, or sent to rework, and the order's final yield report reconciles exactly. | Odoo MRP scrap |
| X62 | Incident dispatch state machine (received→dispatched→enroute→on-scene→cleared; append-only timestamped log) | public-safety/CAD | 3 | C+M | NEW:state-machine + NEW:hash-chain | Build an emergency-call tracker where an incident moves from received through on-scene to cleared, a unit can never be marked on-scene before being dispatched, and the timestamped history can never be rewritten. | Tickets CAD / Resgrid |
| X63 | Unit availability conservation (available/assigned/out-of-service exactly-one; typed pools; no double-dispatch) | public-safety/CAD | 3 | C+M | NEW:conservation + NEW:concurrency | Build a unit-status board where two simultaneous fire calls can never grab the same engine, a unit marked out-of-service is never dispatchable, and clearing an incident puts its units straight back in the available pool. | CAD practice — ≠V38: typed-unit pools + status conservation |

**Oracle-demand signal from this wave (surviving rows):** state-machine **+17** ·
injectable-clock **+16** · conservation **+13** · import-driver fixture tables ~+24 ·
concurrency +2 · multi-service +1 · hash-chain +1. **Unusually rich in exact-math classes
gradable TODAY** (tax brackets, GFS pruning, matrix expansion, interval math, RDP property,
semver resolution, composite-tag math, canonicalization vectors — ~24 rows on import/fs/cli/DB
alone). **Still not covered after this wave (honest boundary, carried to §6):** SCADA/industrial
control protocols, LoRaWAN network servers, ham/SDR, hotel channel-manager (OTA) sync feeds, POS
hardware integration, the NVR video pipeline itself (ffmpeg-bound — only its metadata/retention
logic is mapped), real crypto mail signing (DKIM full RSA needs a dep).

### 3.9 Wave-7 engineering-blog-mining additions (2026-07-10)

**Provenance:** read-only mining of real-company engineering blogs + architecture write-ups
(Figma multiplayer, Linear sync engine, Notion block model, Slack reminders, Discord
permissions/lazy-guilds, Cloudflare Waiting Room, GitHub merge queue, Stripe/brandur idempotency
keys, Segment Protocols, Uber H3/surge, Airbnb availability rules, DoorDash menu configuration,
Shopify/Instacart order editing, Twilio segments/E.164, Netflix buffer-based ABR, Spotify balanced
shuffle, Dropbox block sync, DOL/Gusto-class FLSA overtime; Datadog/Plaid/Pinterest researched and
yielded **zero** new rows — fully subsumed). This wave overlaps prior waves the most, as predicted:
the stager dropped **~35 candidates** as dups with per-row nearest-neighbor notes (record below);
final merge dedupe against the full §3.1–§3.8 atlas confirmed every survivor and dropped **0 more**.
**All rows: status = `mapped`, stdlib = yes, CREATE+MODIFY.** Unusually rich in
deterministic-algebra classes gradable TODAY on the existing import-driver oracle.

| ID | Class | Vertical/Category | Tier | C/M | Oracle | Example task sentence | Source |
|---|---|---|---|---|---|---|---|
| EB1 | Per-property last-writer-wins object sync (server-ordered map of object×property → latest value; concurrent edits to different properties both survive; same property → server order wins; late-joiner snapshot equals replay) | SaaS-collab/multiplayer-sync | 3 | C+M | IMPORT (convergence property: replay two clients' interleaved edit streams in different arrival orders → identical final document) | Build a design-document sync server where two editors changing different properties of the same shape both keep their change, changing the same property keeps whichever the server received last, and a client joining late receives exactly the state every other client has. | Figma "How Figma's multiplayer technology works" — ≠G56: G56 is text OT/CRDT convergence; this is the object-property LWW register map Figma chose INSTEAD of text CRDTs |
| EB2 | Op-log delta sync engine (server-assigned monotonic sync-id per workspace; client bootstraps a snapshot then catches up from last-synced-id; offline local mutations held pending, acknowledged or rebased on reconnect; LWW per field) | SaaS-collab/client-sync | 3 | C+M | IMPORT+DB (kill client mid-stream, reconnect from lastSyncId → no gaps/dupes; offline edits reconcile) | Build a workspace sync service where a client that was offline for an hour submits its held edits, pulls every change since its last recorded sync number, and ends byte-identical to a client that never disconnected. | Linear "Scaling the Linear Sync Engine" + wzhudev reverse-engineering — ≠SH-N1: file-level two-replica reconcile; this is the server-authoritative incremental op-log contract |
| EB3 | Block-tree document engine (everything-is-a-block: typed blocks with ordered child pointers; move/indent/outdent re-parent subtrees; cycle refusal; subtree duplicate and archive/restore keep order and depth) | SaaS-collab/document-model | 3 | C+M | IMPORT (tree invariants: single parent, order preserved, no cycles, restore == pre-archive tree) | Build a page store where indenting a paragraph makes it a child of the block above, moving a block carries its whole subtree, duplicating a section copies every descendant in order, and any operation that would make a block its own ancestor is refused. | Notion "The data model behind Notion's flexibility" — ≠V3 (static course tree) / ≠SH-W1 (page revisions): the op surface (move/indent/duplicate/restore over one uniform block type) is the class |
| EB4 | Natural-language reminder-time parser ("in 2 hours", "tomorrow at 2pm", "next Friday", "every weekday at 9am", "first Monday of every month" → concrete fire time or recurrence rule; ambiguous input → clarify error, never silent failure) | SaaS-collab/scheduling-NL | 2 | C+M | IMPORT (phrase→timestamp fixture tables vs a fixed injectable now) + NEW:clock (firing) | Build a reminder command that turns phrases like "in 45 minutes", "tomorrow at 9", and "every other Thursday" into exact scheduled times from a fixed current time, and answers with a clarification error for a phrase it cannot parse. | Slack /remind + reminders.add API — ≠G28/X33: those expand formal RRULEs; this parses human phrases INTO them |
| EB5 | Layered permission-overwrite resolution (base = union of role bitmasks; then @everyone channel overwrite, then union-of-role overwrites, then member overwrite; deny before allow within each layer; admin bypass; computed-permissions API) | SaaS-collab/authorization | 2 | C+M | IMPORT (decision-table fixtures: role/channel/member overwrite combos → exact effective bitmask) | Build a channel-permission resolver where a role-level deny of viewing is re-granted by another role's channel allow, a member-specific deny beats everything, and the resolver returns the exact effective permission set for any member in any channel. | Discord permissions docs + Statbot deep-dive — ≠SH-W4 (hierarchy inheritance w/ overrides) / ≠P3 (relationship graph) / ≠P4 (attribute policies): ordered bitmask layers with per-layer deny-then-allow is a fourth, distinct authz algebra |
| EB6 | Windowed member-list range subscription (client subscribes to visible index ranges of a huge sorted list; server answers SYNC snapshots per range and emits INSERT/UPDATE/DELETE index ops as membership or sort position changes; client applying ops == server list) | SaaS-collab/list-sync | 3 | C+M | IMPORT (op-sequence fixtures: apply emitted ops to the client copy → equals server's sorted list for the subscribed window) | Build a member-directory service where a client subscribed to rows 0–99 of an alphabetically sorted list receives exactly the operations needed to keep that window correct as people join, leave, and change display names — and never receives updates for rows it did not subscribe to. | Discord "lazy guilds" gateway protocol (discord-api-docs #582) — ≠S55 (transport) / ≠EB2 (whole-workspace op-log): the windowed-range projection contract is the class |
| EB7 | Virtual waiting room (arrival-minute cohort buckets; oldest cohort admitted first as capacity slots free; admitted session token valid N minutes; position + estimated-wait answers; abandoned slots re-issued; never more than N active) | SaaS-infra/admission-control | 3 | C+M | NEW:conservation (≤N active at all times) + NEW:clock + NEW:FIFO-fairness (older cohort never admitted after a newer one) | Build an admission gate for a product-drop page that lets at most 200 visitors shop at once, holds everyone else in a line grouped by arrival minute, admits the oldest group first as shoppers leave, and tells each waiting visitor their position and estimated wait. | Cloudflare "How Waiting Room makes queueing decisions" — ≠V57 (backorder allocation) / ≠V58 (exactly-N sale): admission control over live sessions with fairness cohorts is the class |
| EB8 | Merge-train coordinator (PRs enter an ordered train; each is tested against target + everything ahead; batch up to K; a failing batch bisects, ejects the culprit, re-tests survivors; passing head fast-forwards the target branch) | DevTools/ci-cd | 3 | C+M | CLI+FS + NEW:state-machine (simulated check-runner fixture; assert exact test-target compositions, bisect sequence, final branch order) | Build a merge coordinator where three approved changes are each validated against the main branch plus the changes ahead of them, a failure in the middle change removes only it from the train, and the remaining two land in order without re-testing from scratch. | GitHub "How GitHub uses merge queue…" + Mergify speculative checks — ≠S63 (single-pipeline stages) / ≠X12 (matrix expansion): the speculative train/bisect protocol is the class |
| EB9 | Recovery-point request executor (multi-step API request whose local DB writes are grouped into atomic phases between foreign-state mutations; a named recovery point persists on the idempotency key after each phase; a retry resumes at the recorded point so the external call happens exactly once; a completer sweeps stuck requests) | SaaS-infra/request-reliability | 3 | C+M | NEW:idempotency-replay + NEW:workflow-replay (kill mid-request between phases, retry same key → exactly one external effect, identical final response) + DB | Build a ride-booking endpoint that records a checkpoint after reserving locally and after charging the payment fixture, so a client retry after a crash between the two never double-charges and always drives the request to the same completed response. | brandur.org "Implementing Stripe-like Idempotency Keys in Postgres" + Stripe idempotency blog — ≠S19 (cached-response replay) / ≠G32 (event-history replay engine): named-checkpoint resume WITHIN one API request is the pattern |
| EB10 | Tracking-plan enforcement gateway (per-event-type schemas; violation handling modes per source: block unplanned events, strip unplanned properties, or pass-with-flag; violations forwarded to a violations sink as events; counts by type reportable) | SaaS-analytics/data-governance | 2 | C+M | HTTP+DB+IMPORT (event fixtures → exact accepted/blocked/stripped outcome per mode + exact violations report) | Build an event gateway that drops events not named in the source's tracking plan, removes properties the plan does not define, forwards a description of every violation to a separate audit endpoint, and reports violation counts by event type. | Segment Protocols docs (schema-configuration, forward-violations) — ≠P14 (request 422 validation) / ≠P18 (destination fan-out): the per-source enforcement MODES + violations sink is the class |
| EB11 | Hierarchical hex-grid spatial index (lat/lng → cell id at a resolution; cell → neighbors and k-rings; coarse cell → children; polygon → covering cell set; same-cell and adjacency answers without geometry at solve time) | Logistics-geo/spatial-index | 3 | C+M | IMPORT (fixture tables: point→cell, k-ring sets, polygon covers; adjacency-symmetry property) | Build a grid indexer that assigns every pickup coordinate to a hexagonal cell, lists the cells within two rings of it, and returns the exact set of cells covering a delivery zone polygon. | Uber "H3: Uber's Hexagonal Hierarchical Spatial Index" — ≠V40: point-in-polygon lookup there; discretized grid algebra (cells/rings/covers) here |
| EB12 | Surge multiplier engine (per-zone open-demand vs available-supply ratio → stepped multiplier from a table; smoothing/hysteresis so the multiplier moves at most one step per tick; city cap; a rider's quoted multiplier locked for M minutes) | Marketplace/dynamic-pricing | 3 | C+M | IMPORT (ratio→step fixture tables) + NEW:clock (tick smoothing, quote lock) | Build a zone-pricing service that recomputes each zone's price multiplier every minute from waiting requests versus free drivers, never jumps more than one step at a time, and honors a rider's quoted multiplier for five minutes even if the zone price rises. | Uber H3/surge write-ups — ≠F53 (static tiered pricing) / ≠V12 (discounts): the supply-demand-driven stepped multiplier with hysteresis + quote lock is the class |
| EB13 | Stay-availability rule engine (nightly calendar; min/max stay by check-in day; advance-notice window with same-day cut-off hour; preparation nights blocked around each booking; availability window of N months; answers "can these dates be booked?" with the exact violated rule) | Marketplace-travel/booking-rules | 3 | C+M | IMPORT + NEW:clock (date-range→decision fixture tables from a fixed now) | Build a listing-availability checker that refuses a two-night request when Friday check-ins require three nights, blocks the night after every departure for cleaning, refuses same-day requests after the 3pm cut-off, and names which rule failed. | Airbnb availability settings + preparation-time docs — ≠W52 (overlap-only lease conflict) / ≠V7 (slot double-book): the composable nightly rule gates are the class |
| EB14 | Option-group product configuration engine (items own modifier groups with min/max selections; nested modifier groups one level down; each option carries an up-charge; K-cheapest-selected-free rules; item price == base + Σ selected options; invalid combinations refused with the violated group) | E-comm-delivery/product-config | 2 | C+M | IMPORT (selection→exact-price and accept/reject fixture tables) | Build a menu-item configurator where a burrito requires exactly one protein, allows up to three toppings of which the cheapest is free, lets a chosen salsa carry a light/regular/extra sub-choice, and prices the final item exactly. | DoorDash menu-configuration reference + Toast modifier-group docs — ≠V1 (flat catalog) / ≠V12 (discount math): the constrained option-group selection algebra is the class |
| EB15 | Post-order amendment and substitution settlement (edit a placed order: add/remove/substitute items with customer approve/reject per substitution; totals, tax and inventory recomputed; delta settled as an extra charge or refund; invariant: final charge == Σ final line items and every cent of the difference is accounted) | E-comm/order-amendment | 3 | C+M | NEW:conservation + NEW:state-machine (amendment log legal; charge/refund delta exact) + DB | Build an order-amendment service where an out-of-stock item is swapped for an approved substitute and one item is removed, the customer is refunded exactly the difference, inventory reflects the final lines, and the order's charge history reconciles to the delivered total. | Shopify order-editing docs + Instacart replacements flow — ≠V28 (post-delivery returns) / ≠F13 (payment-side refund): amending the LIVE order with delta settlement is the class |
| EB16 | SMS segmentation calculator (GSM-7 vs UCS-2 auto-detection incl. extension-table double-width chars; 160/70 single vs 153/67 concatenated with data headers; per-message segment count + per-segment breakdown; smart-encoding substitutions of lookalike unicode) | SaaS-comms/messaging-math | 2 | C+M | IMPORT (message→encoding/segment-count/split-offset fixture tables) | Build a message-cost estimator that reports a 320-character plain message as three segments, the same message with one emoji as five, and shows exactly where each segment splits. | Twilio "What the heck is a segment?" + GSM-7/UCS-2 glossary docs |
| EB17 | Phone-number normalization and validation (national digits + country rules → E.164; trunk-prefix stripping; length/prefix validity per fixture country table; national/international/E.164 formatting; invalid numbers rejected with reason) | SaaS-comms/identity-normalization | 2 | C+M | IMPORT (number×country → normalized/formatted/reject fixture tables) | Build a phone normalizer that turns "(303) 555-0142" dialed in the US into +13035550142, strips the leading zero from a UK national number, and rejects a nine-digit US number with the reason. | Twilio lookup/E.164 practice (libphonenumber-shape, fixture-table subset) — not previously in the atlas despite being in every signup flow |
| EB18 | Adaptive-rendition selector (rendition ladder + per-segment size table; pick next segment's rendition from seconds-of-video-downloaded thresholds with an up/down hysteresis band; startup phase uses recent throughput; property: never picks a rendition predicted to stall playback) | Media/streaming-logic | 3 | C+M | IMPORT (scripted throughput/playhead traces → exact rendition choice sequence; no-stall property) | Build a playback rendition chooser that steps quality down before the downloaded seconds run out, steps up only after the reserve crosses a higher threshold so it never flaps, and never rebuffers on the given network trace. | Netflix/Stanford "A Buffer-Based Approach to Rate Adaptation" (SIGCOMM '14) — ≠V43 (manifest/entitlement): the deterministic selection policy is the class |
| EB19 | Spread shuffle (seeded playlist shuffle that distributes same-artist tracks as evenly as possible: per-artist offsets + jitter; deterministic for a seed; property: no two same-artist tracks adjacent whenever the multiset allows it) | Media/ordering-ux | 2 | C+M | IMPORT (seeded determinism + spacing property + permutation-validity check) | Build a playlist shuffler that, given four songs each from three artists and a seed, always produces the same order, uses every song exactly once, and never plays the same artist twice in a row. | Spotify "How to shuffle songs?" (balanced shuffle, ex-Fisher-Yates) — ≠V18 (playlist storage): the constrained-permutation algorithm is the class |
| EB20 | Content-addressed block store with dedupe (files split into fixed-size blocks, each stored once under its digest; upload negotiation returns only the missing block digests; per-block reference counts; unreferenced-block sweep; file content hash == digest of concatenated block digests; byte-exact reconstruction) | Files-storage/content-addressing | 3 | C+M | FS+IMPORT + NEW:conservation (Σ refcounts consistent; sweep removes exactly the unreferenced; reconstruct byte-equal) | Build a file store where saving a second file that shares most blocks with an existing one transfers only the new blocks, deleting one file never breaks the other, and a sweep afterward removes exactly the blocks no file references. | Dropbox "Streaming File Synchronization" + content-hash reference — ≠G54 (resumable assembly) / ≠X5 (multipart completion contract) / ≠X65 (manifest diff): dedupe + refcount GC is the class |
| EB21 | Blended-overtime calculator (one workweek at multiple hourly rates: regular rate == total straight-time earnings ÷ total hours; overtime premium == 0.5 × regular rate × hours over 40 — never 1.5 re-paying straight time; nondiscretionary bonus folds into the regular rate; exact cents) | HR-payroll/wage-compliance | 2 | C+M | IMPORT (timesheet→exact-pay fixture tables incl. the classic 1.5× double-pay trap as a must-fail case) | Build a weekly pay calculator for an employee who worked 30 hours at $20 and 15 at $28, paying the overtime premium on the weighted-average rate so the total comes out exact to the cent — and prove it rejects the naive rate-at-time-of-overtime answer. | 29 CFR §778.115 + DOL Fact Sheet #23 (the Gusto-class payroll component) — ≠G40 (component arithmetic) / ≠X44 (tax brackets) / ≠X66 (garnishment caps): the FLSA regular-rate weighting is its own exact-math class |

**Dedupe record (Tenet 3 — ~35 candidates researched and dropped by the stager, verified at merge;
target row in parens).** **Stripe:** token-bucket rate-limiter suite (=S7) · API version transform
chain (=P13) · webhook signing + timestamp tolerance (=F14/S13) · money-movement double-entry
ledger (=F6) · Radar rule-based fraud scoring (=F32) · payout reconciliation (=F19). **Slack:**
channels + threads (=G17) · unread counts (=G18) · durable job queue (=S14/S16) · workspace export
(=S67) · per-method tiered API rate limits (=S7 MODIFY) · message-ts dedupe (≈S19/S13+EB2).
**Figma:** presence (=G19; cursor broadcast ⊂ S55) · file version history (=G55). **Notion:**
block-tree permission inheritance (=SH-W4) · comments (≈V44/G17). **Linear:** per-team sequential
issue IDs (=W41) · issue dependency graph (=G71). **Discord:** snowflake IDs (=P41) · read states
(=G18) · slowmode (=S7-shape). **Cloudflare:** sliding-window rate-limit approximation (=S7) · DNS
zones (=X29) · conditional writes (=S69). **Uber:** dispatch/matching (=V38) · fare card math
(=F53-shape; GPS-trace part =X24) · trip receipts (=F54/S38). **Netflix:** circuit breaker (=S52)
· A/B cell allocation (=S49) · download license windows (=V16+clock). **Dropbox:** sync change
planner (=G53) · chunked resumable upload (=G54) · shared-namespace mounts (too thin beyond
SH-W4+G53 — dropped for honesty). **Shopify:** flash-sale exactly-N (=V58) · checkout holds
(=G31) · metafields (=G61) · idempotent checkout (=S19/EB9). **Segment:** collection+fan-out
(=P18) · message-id dedupe (=S13/SH-FR3). **Twilio:** delivery-status callback lifecycle
(≈V13-shape) · STOP/HELP opt-out (=P33) · OTP verify (≈S59+S7). **Gusto-class:** PTO accrual
(=G41) · withholding brackets (=X44) · pay-schedule generation (=SH-BU3+W42) · garnishment
stacking (=X66). **Instacart:** shopper batching (=V37/V38) · ML replacement suggestion (out of
scope — only the deterministic approval/settlement workflow kept, merged into EB15). **DoorDash:**
ETA estimation (ML, out) · dasher assignment (=V38). **Airbnb:** payments idempotency (=S19/EB9)
· payments ledger (=F6) · smart pricing (ML, out). **Spotify:** royalty split (=W29) ·
collaborative playlists (=G56/V18). **Zero-row companies (fully subsumed):** **Pinterest** (feed
ranking ML-bound), **Datadog** (=G7/G8/G9, pipelines ≈G35+P43), **Plaid** (delta-sync ≈S47+P10+P27
composition; webhook JWT =F14; institution health =G51).

**Oracle-demand signal from this wave (surviving rows):** **import-driver exact-fixture tables
+10** (EB4, EB5, EB11–EB14, EB16–EB19, EB21 — unusually rich in deterministic-algebra classes
gradable TODAY) · **convergence-property import grading +3** (EB1, EB2, EB6 — the same shape G56
already uses) · injectable-clock +4 (EB4 firing, EB7 admission ticks, EB12 quote lock, EB13
cut-offs) · conservation +4 (EB7 ≤N active, EB14 price==base+Σ, EB15 charge==Σ lines, EB20
refcounts/sweep) · state-machine +3 (EB8 train, EB9 phases, EB15 amendment log) ·
idempotency-replay/workflow-replay +1 (EB9 — strengthens §4 #18) · FIFO-fairness +1 (EB7, the
same oracle V57 already wants) · concurrency +1 (EB7/EB8 under simultaneous arrivals). **No new
oracle KIND needed — the 7th consecutive wave confirming the §4 convergence finding.**

---

### 3.10 Wave-8 Python-library / tooling-ecosystem additions (reusable import-time leaf layer, 2026-07-10)

**Provenance:** category-by-category sweep of `github.com/vinta/awesome-python` (Date&Time, Data
Validation, Data Structures, Serialization, Specific-Formats Processing, Text&Format Processing,
Algorithms & Design Patterns, Configuration, CLI, Files, Cryptography, Caching, Job Scheduling) +
the file-format sub-index + probabilistic-structures research (representative libs named per row for
grounding, not endorsement). **This is the FIRST wave to target the import-time reusable-COMPONENT
layer** — the parsers, validators, serializers, codecs, ADTs, algorithms, and calculators a developer
`import`s and composes, which sits *below* the atlas's deployed-system rows and was only incidentally
sampled by waves 1–7. That is why the haul is mid-range (41 survivors) despite the atlas already
holding 506 classes: the dedupe is heaviest against the ADT/parser/calculator theme, but the leaf
universe beneath it was largely unmapped.

**Oracle demand — the most import-driver-PURE slice in the atlas:** 39 of 41 rows grade purely on
**import-driver**, in three ALREADY-USED variants — **(a) fixture-table** input→exact-output
(validators, parsers, calculators, converters), **(b) round-trip** encode∘decode==identity /
canonical-form (codecs, diff/patch, serializers — the SH-B5/W20/X20 shape), **(c) property-based**
(probabilistic + ADT + algorithm rows: bloom "no false negatives", HLL "within error band",
consistent-hash "minimal key movement", union-find/order-stat "matches reference model" — the
G56/EB1 convergence-property shape). Only 2 rows touch a second oracle (FS for MIME/fixed-width file
cases). **Near-ZERO clock/state-machine/http/db demand** — leaf components are mostly pure functions.
**No new oracle KIND needed — the 8th consecutive wave confirming the §4 convergence finding** (now
DEFINITIVE). The actionable takeaway: the single highest-leverage substrate investment for THIS
layer is not a new oracle but a **strong property/round-trip/fixture import-driver RUNNER with good
failure diffs** (the EXT-059 C1 direction) — that one runner grades essentially all 39.

All rows: status = `mapped`, stdlib = yes. Final-dedupe pass confirmed the stager's biggest-cluster
drops (recurrence/calendar time-math ≈ G28/X33/G46/W14/W42/G27/S15 · schema-validation ≈
P14/A20/A10/S28 · graph-service overlaps topo-sort/bin-packing/MST/FSM-lib/rules-engine ≈
X12/G71/W26/W15+state-machine oracle · caching/rate leaves token-bucket/LRU/retry/memoize/circuit ≈
S7/S9/verified/S52) and added **0 further drops** — every survivor carries an explicit ≠ distinction.

*Top-10 gradable-TODAY by impact × buildability (all import-driver, no new substrate): PL24
check-digit validators · PL13 fuzzy string-distance · PL36 glob/gitignore matcher · PL30 unit
conversion · PL25 base-N codecs · PL31 financial functions · PL1 bloom filter · PL9 interval-set
algebra · PL16 number-to-words · PL5 trie autocomplete.*

**Data structures (specialized collections / ADTs)**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL1 | devtools/lib | Bloom filter (k hashes, m bits, tunable FPR) | IMPORT (property: never a false negative; measured FPR ≤ target) | 2 | C+M | Build a compact membership structure answering "have I seen this id" via several hashes over a bit array, never saying no to something added while keeping the false-yes rate under the target. | mapped | Data Structures / pybloom-shape |
| PL2 | devtools/lib | HyperLogLog cardinality estimator (registers, harmonic-mean, bias correction) | IMPORT (property: estimate within std-error band) | 3 | C+M | Build a distinct-count estimator that counts unique visitors of a stream in a few kilobytes and proves it stays within the expected error margin on a million-item fixture. | mapped | probabilistic-structures / Redis HLL |
| PL3 | devtools/lib | Count-min sketch (d×w counters, never underestimates) | IMPORT (property: reported ≥ true count, error ≤ ε·N) | 3 | C+M | Build a frequency estimator over a fixed counter grid that never reports fewer than the true count of any item. | mapped | probabilistic-structures |
| PL4 | devtools/lib | Consistent-hashing ring (virtual nodes; key→node; add/remove) | IMPORT (property: node change moves only ~1/N keys; deterministic) | 3 | C+M | Build a hash ring mapping keys to servers so removing one server reassigns only its keys and leaves every other key put. | mapped | Algorithms / hash_ring-shape |
| PL5 | devtools/lib | Trie / prefix tree + top-k autocomplete (insert, prefix walk, frequency rank) | IMPORT (prefix→exact ranked completions vs reference) | 2 | C+M | Build a typeahead index where inserting weighted words lets a prefix query return the highest-weighted completions in order. | mapped | Data Structures / marisa-trie/pygtrie |
| PL6 | devtools/lib | Disjoint-set / union-find (rank, path compression, components, cycle check) | IMPORT (property: same partition as reference; cycle detected) | 2 | C+M | Build a connectivity structure that groups elements as pairs are unioned, answers whether two share a group, and detects when an edge closes a cycle. | mapped | Algorithms & Design Patterns |
| PL7 | devtools/lib | Order-statistics sorted container (balanced/skip-list: rank-of, select-kth, range-count) | IMPORT (property: rank/select/range match sorted-list reference over op-script) | 3 | C+M | Build a sorted collection that answers "what rank is this value", "what is the k-th smallest", and "how many fall in this range" in sub-linear time. | mapped | Data Structures / sortedcontainers |
| PL8 | devtools/lib | Fenwick / segment tree (point update + range aggregate sum/min/max) | IMPORT (property: range answers equal brute-force recompute) | 3 | C+M | Build an array structure supporting fast single-element updates and fast range sum/min queries, proven against a plain recomputation. | mapped | Algorithms & Design Patterns |
| PL9 | devtools/lib | Interval-set / interval-tree algebra (insert, stab/overlap, union-merge, subtract, complement) | IMPORT (interval op-script → exact resulting set; overlap-symmetry) | 2 | C+M | Build an interval collection that merges overlaps on insert, answers which ranges cover a point, and computes difference and complement of two range sets exactly. | mapped | Algorithms / intervaltree — ≠X30/G26 (calendar free-busy SERVICES; this is the range algebra) |

**Text & format processing**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL13 | devtools/lib | Fuzzy string-distance (Levenshtein, Damerau, Jaro-Winkler, Hamming, ratio) | IMPORT (string-pair → exact distance/ratio vectors) | 2 | C+M | Build a text-similarity toolkit reporting edit distance and a 0-to-1 similarity under several metrics, matching a published vector table. | mapped | Text / python-Levenshtein/rapidfuzz — ≠W33/W4/X37 |
| PL14 | devtools/lib | Phonetic encoder (Soundex, Metaphone, NYSIIS, Double-Metaphone) | IMPORT (name → exact phonetic-code vectors) | 2 | C+M | Build a name-sounds-like encoder that gives "Robert" and "Rupert" the same Soundex code, matching reference codes. | mapped | Text / jellyfish-shape |
| PL15 | devtools/lib | Aho-Corasick multi-pattern matcher (build automaton once, all dictionary hits + positions) | IMPORT (text × dictionary → exact match list w/ offsets) | 3 | C+M | Build a matcher that finds every occurrence of any word in a given list within a document in a single pass, reporting each hit's start. | mapped | Algorithms / pyahocorasick — ≠G20/X1 |
| PL16 | fintech/lib | Number-to-words / cheque-amount speller (cardinal, ordinal, currency) | IMPORT (number → exact word-string vectors, multiple styles) | 2 | C+M | Build a converter writing 1,234.50 as "one thousand two hundred thirty-four dollars and 50/100" and 21 as "twenty-first". | mapped | Text / num2words |
| PL17 | devtools/lib | Inflector / pluralizer (singular↔plural incl. irregulars, camelize/underscore, ordinalize, titleize) | IMPORT (word → exact inflected-form vectors) | 2 | C+M | Build a word-form helper that pluralizes "person"→"people", turns "user_id"→"userId", and renders 3→"3rd". | mapped | Text / inflection/inflect — ≠P42 (locale plural) |
| PL18 | devtools/lib | Unified-diff generate + apply/patch (Myers diff, hunk format, 3-way merge, conflict markers) | IMPORT (round-trip: apply(diff(a,b),a)==b; 3-way fixtures) | 3 | C+M | Build a text-diff tool producing a unified diff between two files and applying it to reproduce the target exactly, flagging conflicts on a 3-way merge. | mapped | Text / diff-match-patch — ≠SH-W1 (wiki revision SERVICE) |
| PL19 | devtools/lib | Logic-ful template engine (mustache/handlebars subset: sections, inverted, partials, auto-escape, dotted lookups) | IMPORT (template + data → exact rendered output; escaping fixtures) | 3 | C+M | Build a template renderer that loops over a list, hides inverted sections when falsy, includes partials, and HTML-escapes by default. | mapped | Text — ≠G36 (flat interpolation) / A20 (LLM output parser) |
| PL20 | media/lib | Readability scorer (Flesch-Kincaid grade, reading-ease, syllable count, SMOG) | IMPORT (text → exact score vectors) | 2 | C | Build a content-readability tool reporting grade level and reading-ease of a passage from its sentence and syllable counts. | mapped | Text / textstat-shape |

**Serialization / specific-formats (codecs & parsers)**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL21 | devtools/lib | MessagePack-subset codec (int/float/str/bin/array/map/nil/bool) | IMPORT (round-trip: decode(encode(x))==x; byte-exact vs spec) | 2 | C+M | Build a binary serializer that packs nested dicts and lists into MessagePack bytes and unpacks to the identical value, matching the spec's byte sequences. | mapped | Serialization / msgpack |
| PL22 | devtools/lib | Bencode codec (ints, byte-strings, lists, sorted-key dicts) | IMPORT (round-trip + canonical form: keys sorted, single valid encoding) | 2 | C+M | Build a bencode encoder/decoder that round-trips a nested structure and always emits dict keys sorted so equal data encodes to identical bytes. | mapped | Specific-Formats / bencode.py |
| PL23 | devtools/lib | TOML-subset parser (tables, inline tables, arrays, typed scalars incl. datetimes, dotted keys) | IMPORT (TOML text → exact structure; error on duplicate key) | 2 | C+M | Build a TOML reader parsing tables, arrays-of-tables, and typed values into nested dicts, rejecting a file that defines the same key twice. | mapped | Specific-Formats / tomllib — ≠ INI (verified) / S28 |
| PL25 | devtools/lib | Base-N codec family (RFC-4648 base16/32/32hex/64/64url + base58 + base62, alphabets & padding) | IMPORT (round-trip per alphabet; spec test vectors) | 1 | C+M | Build an encoder/decoder converting bytes to and from base32, base64url, and base58 with the standard alphabets, round-tripping exactly. | mapped | Cryptography/encoding — no base-N codec in the atlas |
| PL26 | data/lib | RFC-4180 CSV reader/writer + dialect sniffer (quoting, embedded commas/newlines, delimiter detection) | IMPORT (round-trip on edge-case fixtures; sniffed dialect matches) | 2 | C+M | Build a CSV parser correctly reading quoted commas and newlines, writing them back identically, and auto-detecting comma vs semicolon vs tab. | mapped | Specific-Formats / csvkit/tablib — ≠S45 (E→T→L pipeline) |
| PL27 | data/lib | Fixed-width / copybook record parser+writer (offsets/widths/types; padding/justification) | IMPORT + FS (round-trip: parse then write reproduces record bytes) | 2 | C+M | Build a fixed-width parser driven by a field layout that decodes each line into typed fields and re-emits byte-identical records. | mapped | Specific-Formats — ≠F26 (NACHA write only) |
| PL28 | devtools/lib | Canonical-JSON serializer (RFC-8785 subset: sorted keys, minimal number formatting, deterministic bytes) | IMPORT (equal inputs → byte-identical output; round-trip preserves value) | 2 | C+M | Build a JSON serializer emitting sorted keys and canonical numbers so two equal documents produce byte-identical output suitable for hashing. | mapped | Serialization — the deterministic-bytes leaf under F10/EB1 |

**Data validation**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL24 | fintech/lib | Check-digit validator suite (IBAN mod-97, ISBN-10/13, EAN-8/13 & UPC, ABA routing, mod-10/11) | IMPORT (identifier → valid/invalid + reason vectors) | 2 | C+M | Build an identifier validator confirming an IBAN by mod-97, an ISBN-13 by its weighted digit, and a routing number by ABA checksum, naming which check failed. | mapped | Data Validation / python-stdnum — ≠F58 (Luhn only) |
| PL11 | devtools/lib | IP / CIDR math library (parse v4/v6, contains, overlaps, supernet/summarize, split-subnets, host enum) | IMPORT (address/prefix ops → exact results; containment vectors) | 2 | C+M | Build an address toolkit that says whether an IP falls in a CIDR block, whether two blocks overlap, and splits a /24 into four /26 subnets. | mapped | Data Validation/net — ≠X31 (DHCP SERVICE) / X29 (zone-file) |
| PL39 | devtools/lib | Syntactic format validators (email RFC-5322 subset + normalize, URL parse/normalize, hostname, UUID, MAC) | IMPORT (string → valid/invalid + normalized form vectors) | 2 | C+M | Build a validator set that accepts a well-formed email and returns its normalized lowercase form, canonicalizes a URL, and rejects a bad hostname with a reason. | mapped | Data Validation / validators-lib — ≠EB17 (E.164) / SH-B1 |

**Date & time**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL32 | devtools/lib | ISO-8601 duration parse/format (`P1Y2M10DT2H30M` ↔ components ↔ total seconds) | IMPORT (duration string ↔ seconds/components vectors) | 1 | C+M | Build a duration helper parsing "P1DT2H30M" into components and total seconds and formatting a second count back into the shortest valid ISO-8601 duration. | mapped | Date and Time / isodate — no duration codec in the atlas |
| PL33 | fintech/lib | Fiscal/retail-calendar mapper (4-4-5 / 4-5-4 & custom FY-start: date → fiscal year/quarter/period/week) | IMPORT (date → exact fiscal-period label vectors) | 2 | C | Build a calendar mapper that, given a February fiscal-year start and a 4-5-4 pattern, reports which fiscal year, quarter, period, and week a date falls in. | mapped | Date and Time — ≠G46/W14/W42 (business-day/holiday/deadline) |

**Algorithms & engines**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL10 | devtools/lib | Weighted shortest-path (Dijkstra + A* heuristic; path + cost; negative-edge rejection) | IMPORT (graph fixture → exact path & cost; unreachable → none) | 3 | C+M | Build a router finding the least-cost path between two nodes of a weighted graph, returning path and total cost, refusing negative edges. | mapped | Algorithms — ≠V37 (NP-hard VRP); this is the polynomial exact class |
| PL12 | devtools/lib | Shunting-yard arithmetic evaluator (infix→postfix, precedence, parens, functions, safe—no eval) | IMPORT (expression + vars → exact numeric result; malformed → error) | 2 | C+M | Build a safe calculator evaluating "3 + 4 * (2 - 1)" and "max(a, b) / 2" with correct precedence and no eval, erroring on unbalanced parens. | mapped | Algorithms — ≠A33 (runs Python) / G36 (flat interpolation) |
| PL34 | data/lib | Spreadsheet formula recalc engine (dependency graph, topological recompute, cycle detect, SUM/IF/refs) | IMPORT (cell edits → exact recomputed grid; cycle → error naming cell) | 3 | C+M | Build a mini spreadsheet where cells hold numbers or formulas, editing one recomputes exactly the affected cells, and a self-reference is refused. | mapped | Algorithms/engines — ≠G71 (issue dep graph, no recompute) |
| PL29 | devtools/lib | Content-defined chunking (rolling-hash/FastCDC variable boundaries; min/avg/max size) | IMPORT (property: same content→same boundaries; local insert re-chunks only nearby) | 3 | C+M | Build a file chunker splitting a byte stream at content-defined boundaries so inserting a few bytes near the start leaves almost all later boundaries unchanged. | mapped | Algorithms — ≠EB20 (fixed-size dedup) / G54 (resumable upload) |
| PL35 | devtools/lib | Huffman / LZ77 compressor (code table or sliding window; encode+decode round-trip) | IMPORT (round-trip: decompress(compress(x))==x; ratio<1 on redundant fixtures) | 3 | C+M | Build a self-contained compressor that shrinks a redundant byte string and restores it exactly, proving the compressed form is smaller on repetitive input. | mapped | Algorithms |
| PL37 | devtools/lib | Non-crypto checksums & hashes (CRC-32, Adler-32, Fletcher-16/32, FNV-1a, MurmurHash3) | IMPORT (input → exact checksum vectors) | 1 | C+M | Build a checksum library computing CRC-32 and Adler-32 of a byte string and MurmurHash3 of a key, all matching published test vectors. | mapped | Cryptography (non-crypto) — ≠F58 (Luhn) / SH-P2 |

**Numeric / units**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL30 | devtools/lib | Unit conversion / dimensional analysis (length/mass/volume/temp/time; compound units; dimension check) | IMPORT (quantity + target-unit → exact value; incompatible → error) | 2 | C+M | Build a unit converter turning "5 km" into meters, 20°C to °F, rejecting kilograms→meters, and handling compound units like meters per second. | mapped | pint-shape — ≠SH-R2 (kitchen) / W54 (harvest) domain converters |
| PL31 | fintech/lib | Financial functions (NPV, IRR via bisection/Newton, PMT/FV/PV, effective/nominal rate) | IMPORT (cashflow/rate inputs → known result within tolerance) | 2 | C | Build a finance math module computing NPV and IRR of a cashflow series and the level monthly payment of a loan, matching reference values. | mapped | numpy-financial-shape — ≠F36 (amortization schedule) |
| PL38 | data/lib | Descriptive statistics + quantile + simple linear regression (mean/median/mode/var, percentile methods, Pearson r, OLS) | IMPORT (dataset → exact statistic vectors; documented quantile methods) | 2 | C | Build a statistics module reporting mean, standard deviation, the 90th percentile under a chosen interpolation method, and the least-squares line through points. | mapped | Data Analysis — narrower than F45/F47; the descriptive-stats leaf |

**Files / paths**

| ID | Vertical | Concrete class | Oracle | Tier | C/M | Example task sentence | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PL36 | devtools/lib | Glob / gitignore-style path matcher (`*`, `**`, `?`, `[…]`, negation, anchoring, dir-only rules) | IMPORT (path × pattern-set → exact match/ignore vectors) | 2 | C+M | Build a path matcher that, given gitignore-style rules incl. double-star and negation, decides for each path whether it is ignored, honoring rule order. | mapped | Files / pathspec/fnmatch-extended |
| PL40 | devtools/lib | Safe path join + normalization (`..` collapse, cross-platform sep, canonicalization, traversal-escape rejection) | IMPORT (base + user-path → normalized path or rejection vectors) | 2 | C+M | Build a path helper safely joining a user subpath under a base dir, collapsing "." and "..", and refusing any input that would escape the base. | mapped | Files — the traversal-prevention leaf (security-relevant) |
| PL41 | devtools/lib | MIME-type detection (extension map + magic-byte sniffing; confidence when they disagree) | IMPORT + FS (filename/bytes → exact media-type vectors) | 2 | C+M | Build a file-type detector identifying a PNG from its leading bytes even when the extension is wrong, falling back to the extension map when no signature matches. | mapped | Files / python-magic |

*Wave-8 dedupe record (Tenet-3 honesty): ~34 researched candidates dropped as dup/too-thin, the
biggest clusters being date/time recurrence math (cron/RRULE/business-day/DST ≈ S15/G28/X33/G27),
schema-validation (JSON-Schema/type-coercer/env-loader ≈ P14/A20/A10/S28), graph-service overlaps
(topo-sort/bin-packing/MST/FSM-lib/rules-engine ≈ X12/G71/W26/W15+state-machine oracle),
caching/rate leaves (token-bucket/LRU/retry/memoize/circuit = S7/S9/verified/S52), and
trivial-stdlib leaves (plist/querystring/punycode/hexdump/roman/base-radix/textwrap/Fraction). See
the staging file's DROP record for the full list.*

---

## 4. RANKED NEW-ORACLE SUBSTRATE — the lever

The substrate, not any single build, is what moves coverage: **each oracle flips a whole sub-cluster
from `mapped` to buildable.** Ranked by **(classes-unblocked × reuse-breadth)**, counts merged across
all three slices (a class that needs two oracles is counted under each). Every oracle is **stdlib +
offline**; the honesty note is load-bearing (Tenet 3) — a low-fidelity oracle that always passes is
worse than none.

> **⭐ CONVERGENCE FINDING (2026-07-10, waves 1–8 merged — now DEFINITIVE):** **eight consecutive**
> independent research waves — OSS-product decomposition, the selfhosted ecosystem, six new industry
> verticals, the infra/pattern layer, the agent stack, the 24-cluster leftover backlog,
> real-company engineering-blog mining, and the **Python-library/tooling reusable-component layer** —
> needed **NO new oracle KIND** beyond this table (the only two additions, #18 workflow-replay-
> determinism and #19 process-lifecycle probe, are small refinements of existing replay/HTTP grading,
> and every other one of the ~290 newly staged rows graded onto the existing vocabulary). Wave 8 is
> the strongest confirmation yet: a whole fresh *layer* of 41 pure-function leaf components — the
> most **import-driver-PURE** slice in the atlas (39/41 grade on import-driver fixture/round-trip/
> property variants alone, near-ZERO clock/state-machine/http/db demand) — needed no new judge.
> **The substrate vocabulary is complete in kind; the remaining work is demand-ranked instances.**
> The one actionable sharpening from wave 8: the highest-leverage substrate investment for the
> leaf-component layer is not a new oracle but a **strong property/round-trip/fixture import-driver
> RUNNER with good failure diffs (the EXT-059 C1 direction)** — that single runner grades ~all 39.
> Final merged demand: **injectable-clock ~70 wave
> votes** (w1 17 · w2 11 · w3 12 · w4 10 · w6 16 · w7 4; ~79 total consumers with the original
> ~10) — **decisively the next oracle, ALREADY BEING BUILT as EXT-059 REQ-10 `clock_oracle`** ·
> state-machine +~48 new (≈73 total, biggest absolute count) · conservation +~44 (≈61 total) ·
> import-driver fixture tables +~70 (existing oracle — just write fixtures; wave 7 alone added
> +10 plus 3 convergence-property gradings) · **agent-loop LANDED, unlocks ~27 rows** (A1–A40's
> AGENT-gradable set) · multi-service-fixture rising (~15) · double-entry ≈21 · streaming-client
> ~5 · FIFO-fairness +1 (EB7 joins V57) · idempotency/workflow-replay +1 (EB9). **Wave-7's top
> gradable-TODAY board candidates:** EB9 recovery-point executor, EB5 permission-overwrite
> resolution, EB21 blended overtime, EB16 SMS segments, EB14 option-group configurator.

| Rank | Oracle | ~Classes unblocked | Stdlib? | What it is / honesty note |
|---|---|---|---|---|
| **1** | **Agent-loop oracle** `[LANDED — harness/agent_oracle.py, commit 2ee7efa; validated by the plain-tool-calling-agent class 3/3]` | **~27** (A1–A10 + 17 of A11–A40, gradable **today**) | yes | Scripted **stub-model** (replays a canned tool-call/final sequence) + **fake tools** that record calls + assertions over the resulting **transcript** (which tool, what args, order, stopped at step-cap). The most differentiated cluster, fully verifiable with **no network / no paid model**. Honesty: assert the *orchestration actually happened*, not that prose "looks agentic." |
| **2** | **Generic state-machine / lifecycle oracle** | **~73 post-merge (largest absolute count: +18 w3, +17 w6, +4 w2, +2 w4, +4 w5, +3 w7)** | yes | Given a declared transition graph + an op-script through HTTP/DB, assert every transition taken was **legal** and terminal invariants hold. Covers order, shipment, fulfillment, RMA, prescription, claim, dispute, comment-moderation, transcode-job, appointment, PaymentIntent, dunning, chargeback, trade-lifecycle, subscription. **Highest reuse in the atlas.** Honesty: leak-proof — grades structure, not memorizable strings. |
| **3** | **Double-entry balance invariant oracle** | **~21 post-merge (+ W29/W44/W50/W60, P35)** | yes | For any ledger: Σdebits==Σcredits per txn AND balance==Σpostings per account. One oracle grades an **open-ended** ledger implementation → best generality-per-oracle ratio. Covers F6–9, F13, F19, F24–25, F29, F55–56, F59, V33 escrow, V52 points. |
| **4** | **Conservation / no-oversell / allocation invariant oracle** | **~61 post-merge (+13 w3, +13 w6, +6 w2, +6 w1, +2 w5, +1 w4, +4 w7)** | yes | Σparts==whole and quantity ledger never negative under a replayed (optionally concurrent) op-script: allocation pennies, invoice totals, payout net==gross−fees, `available+committed==on_hand`, `Σbin==on_hand`, refund≤paid, points≥0, cost-alloc Σ==bill. Covers F2, F19–20, F31, F36, F42–43, F50, F54 + V6, V28, V36, V52, V57. |
| **5** | **Money-invariant checker (no-float / exact-cent)** | ~7 (grades every money-touching class) | yes | Static+dynamic: assert **no `float` ever touched a monetary value**, results exact to the minor unit, currency-consistent ops only. Cheap, universal, catches the #1 real money bug. Unblocks/hardens F1–5, F53, F56. |
| **6** | **High-fidelity mock-payment-provider (stripe-mock-shape)** | ~13 | yes | Offline HTTP server mirroring Stripe's official `stripe-mock`: PaymentIntent lifecycle incl. 3DS `requires_action`→`succeeded`, idempotency-key replay (one effect), HMAC-signed webhooks, decline/error codes, refund/partial, retry-after. Unlocks F12–19, F35, F57, S41, V25. Honesty: **a `{"status":"succeeded"}` stub is a Tenet-3 trap — the mock's fidelity IS the test's validity.** |
| **7** | **Injectable-clock / fake-time harness** `[BUILDING — EXT-059 REQ-10 clock_oracle]` | **~79 post-merge — THE SINGLE MOST-DEMANDED ORACLE (~70 wave votes: w1 17 · w2 11 · w3 12 · w4 10 · w6 16 · w7 4, on top of the original ~10). DECISIVELY THE NEXT ORACLE TO BUILD — and it is already being built.** | yes | Build accepts an injectable clock (env/module-seam/`?now=` hook) so the grader advances time deterministically: rate-limiter refill, scheduler fire, TTL expiry, token expiry, dunning/backoff timers — plus the merged waves' statutory deadlines, grace windows, withholding intervals, renewals, retention ladders, SLA timers, hold releases, greylist delays, no-show fees. Without it, timing is only real-`sleep`-gradable → slow+flaky. The regulated/prosumer/pattern tiers all run on the clock even when their apps are otherwise time-poor. |
| **8** | **Idempotency-replay oracle** | ~10 (+EB9 w7) | yes | Apply same key/event twice → exactly one effect + identical response; different key → new effect. Unblocks F11, F14–16, F21–23, S19, V56, EB9 (overlaps mock-payment but independently useful). |
| **9** | **Hash-chain integrity + append-only audit / access-control oracle** | ~6 | yes | Recompute an append-only chain, detect any mutated row (tamper-evident); assert every PHI/PII access logged, log immutable, denied-without-consent holds. Reuses jaros-code's own hash-chain discipline. Unblocks F10, F29, F35, S22, V23 (HIPAA), RBAC hardening. |
| **10** | **Multi-service fixture-upstream harness** | **~15 post-merge (rising: +5 w2 — dead-link checker, conditional-GET poller, dashboard tiles, TLS watcher — monitoring is its killer category; +A37 gateway, +X15 proxy registry)** | yes | Start ≥2 in-process HTTP upstreams, wire URLs via env, drive an end-to-end flow with **fault injection**. Unblocks S50 gateway, S51 LB, S52 circuit-breaker, S53 registry, S65 SDK-vs-server, S57 OAuth-client↔IdP, S70 saga, S60 dist-lock. Generalizes the HTTP oracle to N cooperating processes. |
| **11** | **SMTP-capture sink oracle** | ~4 | yes | In-process SMTP sink (`aiosmtpd`/`smtpd`-style) capturing sent mail → assert recipient/subject/rendered body/idempotent send. Unblocks S30 email, S4 reset-email, F23 dunning email, V-notifications. |
| **12** | **Concurrency / exactly-N oracle** | ~5 | yes | Spawn K>N concurrent clients at a scarce resource under a seeded interleaving; assert exactly N succeed and no invariant breaks. Unblocks V58 flash-sale, V6 last-unit, V7 no-double-book, V38 no-double-assign, F59 double-spend, S60 dist-lock. |
| **13** | **SSE / WebSocket streaming-client oracle** | ~5 (+2 w5: A39 agent event relay, A23 partially) | yes(SSE) | Client opens a long-lived connection, collects N pushed events, asserts payloads + ordering + close. Unblocks S55 realtime push, streaming agent responses (A39), V43-adjacent. SSE stdlib; WS needs a small frame codec. |
| **14** | **Feasibility / cost-bound oracle (optimization)** | ~3 | yes | For VRP/route/dispatch/time-window: assert the solution is **feasible** (capacity/windows/no-double-assign) AND cost ≤ a held-out bound (or within ε of brute-forced optimum on small instances). Avoids grading NP-hard on a single gold answer. Unblocks V37, V38, V39. |
| **15** | **Matching / price-time-priority oracle** | ~3 | yes | Best-price-first + FIFO-at-price + filled-qty conservation + non-crossed book, deterministic fills for a fixture sequence. Unblocks F38, F39, V32. |
| **16** | **Protocol-conformance oracle (OIDC / LTI 1.3 / FHIR REST)** | ~5 | yes | Drive a simulated counterparty (IdP / FHIR client), assert protocol-correct handshake (signed JWT/nonce/PKCE, FHIR read/search/`_history`/validate). Unblocks S56, S57, S58, V59, V60. Higher effort; simulate the peer in-process. |
| **17** | **Rule-engine exact-output fixtures** (mostly reuse import-driver) | **~75 post-merge** | yes | Deterministic input→exact-output tables for tax, grade weighting, coupon totals, claim adjudication, reference-range flags — plus the merged waves' rating tables, deadline math, tax brackets, GFS pruning, interval math, semver resolution, canonicalization vectors (+17 w3, +24 w6, +16 w5) — plus wave-7's decision-table cluster (+10: permission bitmasks, SMS segments, E.164, hex-grid algebra, surge steps, stay rules, option-group pricing, ABR traces, spread shuffle, blended overtime) and its 3 convergence-property gradings (EB1/EB2/EB6, the G56 shape). Not new code — **fixture tables** over the existing import-driver oracle. A business-day/holiday-calendar fixture (W14/W42) is the one recurring table to write once. |
| **18** | **Workflow-replay-determinism oracle** *(wave-4 proposal — NEW kind)* | ~4 (G32 Temporal-shape; stronger honest grader for S70 saga + V42 job-DAG; +EB9 Stripe recovery points, w7) | yes | Kill a durable-workflow run mid-flight, restart, assert **exactly-once activity effects + an identical final state** from the event history. Jaros already has replay-determinism DNA (`jaros replay`) — cheap to build, high honesty value. |
| **19** | **Process-lifecycle probe** *(wave-4 proposal — NEW kind)* | ~1 direct (P16) + hardens every HTTP row's MODIFY surface | yes | SIGTERM a running service; assert readiness flips before intake stops, in-flight requests complete, hard deadline enforced. Small build. |
| — | **Narrow format oracles** (NACHA fixed-width, proration/period, accounting-equation A==L+E, order-book already at #15, **period-lock** — F29 GL close, SH-T4 timesheet lock, X50 payroll retro) | 1–3 each | yes | Small, each unlocks 1–3: F26, F21, F30/F54, F29/SH-T4/X50. Build opportunistically when their parent class is scheduled. |
| — | **Prometheus-exposition + structured-log parser** (light) | 2 | yes | Tiny parsers so S24 metrics / S25 logging assert on `# TYPE`/counter lines + JSON records. Sharpens observability verification. |
| — | **Cloud-emulator harness** (moto / official emulators, simulated only) | escape hatch | dep | For S3/SQS/DynamoDB-shape tasks wanting real SDK surfaces without egress. Lower priority than the stdlib path; documented as the "cloud-shaped" escape hatch, Tenet-2 clean. |

**Build order (max coverage per unit effort — re-ranked 2026-07-10 after the wave-2/3/4/5/6/7
merge):** agent-loop `[LANDED]` → **injectable-clock `[BUILDING — EXT-059 REQ-10 clock_oracle]`**
(decisively next: ~70 wave votes, ~79 total consumers) → **state-machine** (~73) →
**conservation** (~61) → **double-entry** (~21) → money-invariant + rule-engine fixtures (cheap —
fixture tables over existing import-driver, ~75 consumers; wave 7's decision-table cluster is the
richest gradable-today seam) → **multi-service harness** (moved up: ~15, monitoring cluster) →
mock-payment → idempotency-replay + hash-chain/audit → workflow-replay-determinism +
process-lifecycle probe (small wave-4 proposals, #18/#19; EB9 strengthens both) → SMTP-sink →
concurrency → streaming → feasibility → matching → protocol (~7 incl. Google-Reader facade +
ActivityPub-lite). **Clock + state-machine + conservation alone flip well over 150 of the 547
classes to honestly gradable; with the landed agent-loop and the existing HTTP/DB/FS/CLI/IMPORT
oracles, the majority of the atlas is then reachable.**

---

## 5. Stdlib-buildable-now seed shortlist (immediate roadmap candidates)

Ranked by value × cheapness. All CREATE **and** MODIFY. All zero-dep, offline, gradable by an
**existing** oracle (HTTP/DB/FS/CLI/IMPORT) or a **soon-to-land** one (state-machine, conservation,
double-entry, agent-loop). MODIFY variants are typically *more* robust for the small model
(start from a composed system) per the compositional finding — sample them heavily.

1. **REST CRUD API** (S1) `[building]` — HTTP+DB, the reusable base. *"Build a JSON REST API for `notes` with create/list/get/update/delete, persisted in SQLite."* Modify: *"add a `pinned` boolean and a `?pinned=true` filter."*
2. **Auth pack** — session login (S2), JWT HS256 (S3), password-hash+reset (S4), RBAC (S5), TOTP/2FA (S59). All stdlib `hmac`/`hashlib`. HTTP + IMPORT oracles today.
3. **Multi-tenant row-scoping** (S6) — the isolation/leak-probe test; highest *honesty* value in SaaS.
4. **Rate limiter** (S7) + **quota** (S8) — needs only the injectable-clock oracle.
5. **Idempotency store** (S19/F11/V56) + **pagination/filter/sort** (S20) + **soft-delete** (S68) — ubiquitous MODIFY surface.
6. **Webhook receiver** (S13/F14) + **outbound dispatcher** (S12) — HMAC, fixture receiver.
7. **Background job queue+worker** (S14) + **scheduler** (S15) + **retry+DLQ** (S16) + **pub/sub** (S17).
8. **Migration runner** (S21) + **audit log** (S22) — DB schema + hash-chain.
9. **Observability**: health (S23), metrics (S24), JSON logging (S25).
10. **Catalog/cart/order CRUD** (V1/V2/V5) — e-commerce base; order needs the state-machine oracle.
11. **Inventory + stock reservation** (V6) — the conservation/no-oversell flagship.
12. **LMS course/module/lesson tree** (V3) + **enrollment** (V4) + **gradebook** (V48) — EdTech seed, datastore + exact-weighted-grade.
13. **Money math pack** (F1–F4) + **allocation** (F2) — the fintech leaf-library; money-invariant + conservation oracles.
14. **Double-entry ledger** (F6) + **wallet/transfers** (F24/F25) — the fintech spine, one oracle grades all.
15. **Proration** (F39/F21) + **invoice totals** (F20/S38) + **FinOps cost allocation** (F42) — exact-math wins, conservation oracle.
16. **Full-text search** (S34/V54) + **blob storage** (S32) + **presigned URLs** (S33).
17. **CLI operational tool** (S44) + **config loader** (S28) + **API keys** (S27) + **ETL** (S45).
18. **The agent quartet** — agent loop (A1), tool registry (A2), agent-behind-API (A3), loop-guard (A4) — the highest-differentiation cluster, gated on the agent-loop oracle `[building]`.

That is ~40 distinct classes immediately buildable-and-verifiable with the oracles jaros-code has
today plus the four soon-to-land invariant oracles.

---

## 6. Boundary / honesty notes

- **Covered whole categories, not cherry-picks** — every vertical has ≥1 concrete class and most a
  create+modify pair. This ledger is the completeness boundary; new discoveries **append here**, not
  into the roadmap directly.
- **Kept simulated-only** — payments (stripe-mock-shape signed fixtures), cloud storage/queues
  (moto/emulators), external IdPs (in-proc fixture), carriers, DRM, SMTP, ffmpeg, DICOM, LTI
  platform, FHIR client. No real egress, $0, Tenet-2/3 clean.
- **Deliberately out-of-atlas (other slices, noted for the completeness critic):** browser/frontend
  SPA, mobile, ML-training, game/graphics, embedded/firmware, blockchain, raw-protocol network
  servers. **Wave-6 honest boundary additions (researched, judged out-of-scope or dep-bound):**
  SCADA/industrial-control protocols, LoRaWAN network servers, ham/SDR, hotel channel-manager (OTA)
  sync feeds, POS hardware integration, the NVR **video pipeline itself** (ffmpeg-bound — its
  metadata/retention logic IS mapped as X27/X28), and real crypto mail signing (DKIM full RSA sign
  needs a dep; canonicalization/record math is mapped as X40).
- **Every oracle grades structural invariants over a replayed op-script**, never a memorizable output
  string — the model cannot fake it by branching on a known task. Optimization classes grade on
  **feasibility + cost-bound**, never a single gold solution.
- **The `verified` tier is honest and small (5 utility + 1 building / 547).** The utility tier is the
  FLOOR being demoted; the frontier is the first service rung and the agent cluster (whose oracle is
  now LANDED). Moving `verified` up — by landing the ranked oracles in §4, clock first — is the
  whole game.
