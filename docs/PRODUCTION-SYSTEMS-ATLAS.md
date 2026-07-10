# Production-Systems Atlas — jaros-code Completeness Ledger

**Status:** living planning artifact (a coverage ledger, like `docs/GAP-MAP.md`) — **NOT product code.**
**Last assembled:** 2026-07-09 · **Sources:** `.jaros-data/artifacts/atlas/{saas_devtools,fintech_finops,verticals}.md` + `.jaros-data/artifacts/saas_taxonomy_research.md` (folded in / reconciled below).

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

---

## 2. Coverage summary

### 2.1 Totals

| Metric | Count |
|---|---|
| Raw class rows across the 3 slices | **199** (SaaS/devtools 80 · fintech/finops 59 · verticals 60) |
| Cross-slice duplicates reconciled | **~17** (see §2.4) |
| **Distinct production-system classes** | **≈ 182** |
| Stdlib-buildable-now (zero deps, offline) | **≈ 176 / 182 (~97%)** |
| Needs a 3rd-party dep (all have a stdlib/simulated path) | **~6** (CAMT/OFX/MT940 parse, NACHA validator, real broker, Postgres/Redis wire — Docker-backed oracles exist) |

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

### 2.3 Status breakdown (current reality)

Status values: **unmapped** → **mapped** → **on-roadmap** → **building** → **verified**.

| Status | Count | Classes |
|---|---|---|
| **verified** (utility tier — real, but being demoted as "toys-are-the-floor") | 5 | retry-backoff-lib, memoize-lib, ini-config-cli, file-organizer, csv-etl (≈ atlas class **S45 ETL**) |
| **building** | 2 | **REST+DB CRUD service** (create+modify — first SaaS rung; service oracle just landed) · **agent-loop oracle** (the AGENT-oracle substrate itself, unblocking A1–A10) |
| **mapped** | ≈ 175 | everything else in this atlas |
| on-roadmap | 0 (roadmap owns this; assigned as classes are promoted from §5/§6) | — |
| unmapped | 0 (this atlas is the completeness boundary; new discoveries append here) | — |

**Honest read:** the *verified* tier today is the small utility/leaf class (config/CLI/file/etl/
memoize/retry). It is **real but demoted** — those are the FLOOR, not the frontier. The frontier is
the first **service** rung (REST+DB CRUD, `building`) and the **agent** cluster (gated on the
agent-loop oracle, `building`). Coverage today ≈ **5 verified + 2 building / 182** — the number this
ledger exists to move.

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

*The AGENT oracle itself is `building` (§2.3). Once it lands, A1–A4 are the immediate seed (§6).*

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

---

## 4. RANKED NEW-ORACLE SUBSTRATE — the lever

The substrate, not any single build, is what moves coverage: **each oracle flips a whole sub-cluster
from `mapped` to buildable.** Ranked by **(classes-unblocked × reuse-breadth)**, counts merged across
all three slices (a class that needs two oracles is counted under each). Every oracle is **stdlib +
offline**; the honesty note is load-bearing (Tenet 3) — a low-fidelity oracle that always passes is
worse than none.

| Rank | Oracle | ~Classes unblocked | Stdlib? | What it is / honesty note |
|---|---|---|---|---|
| **1** | **Agent-loop oracle** `[BUILDING]` | ~10 (A1–A10) | yes | Scripted **stub-model** (replays a canned tool-call/final sequence) + **fake tools** that record calls + assertions over the resulting **transcript** (which tool, what args, order, stopped at step-cap). The most differentiated cluster, fully verifiable with **no network / no paid model**. Honesty: assert the *orchestration actually happened*, not that prose "looks agentic." |
| **2** | **Generic state-machine / lifecycle oracle** | **~18–20** | yes | Given a declared transition graph + an op-script through HTTP/DB, assert every transition taken was **legal** and terminal invariants hold. Covers order, shipment, fulfillment, RMA, prescription, claim, dispute, comment-moderation, transcode-job, appointment, PaymentIntent, dunning, chargeback, trade-lifecycle, subscription. **Highest reuse in the atlas.** Honesty: leak-proof — grades structure, not memorizable strings. |
| **3** | **Double-entry balance invariant oracle** | **~16** | yes | For any ledger: Σdebits==Σcredits per txn AND balance==Σpostings per account. One oracle grades an **open-ended** ledger implementation → best generality-per-oracle ratio. Covers F6–9, F13, F19, F24–25, F29, F55–56, F59, V33 escrow, V52 points. |
| **4** | **Conservation / no-oversell / allocation invariant oracle** | **~17** | yes | Σparts==whole and quantity ledger never negative under a replayed (optionally concurrent) op-script: allocation pennies, invoice totals, payout net==gross−fees, `available+committed==on_hand`, `Σbin==on_hand`, refund≤paid, points≥0, cost-alloc Σ==bill. Covers F2, F19–20, F31, F36, F42–43, F50, F54 + V6, V28, V36, V52, V57. |
| **5** | **Money-invariant checker (no-float / exact-cent)** | ~7 (grades every money-touching class) | yes | Static+dynamic: assert **no `float` ever touched a monetary value**, results exact to the minor unit, currency-consistent ops only. Cheap, universal, catches the #1 real money bug. Unblocks/hardens F1–5, F53, F56. |
| **6** | **High-fidelity mock-payment-provider (stripe-mock-shape)** | ~13 | yes | Offline HTTP server mirroring Stripe's official `stripe-mock`: PaymentIntent lifecycle incl. 3DS `requires_action`→`succeeded`, idempotency-key replay (one effect), HMAC-signed webhooks, decline/error codes, refund/partial, retry-after. Unlocks F12–19, F35, F57, S41, V25. Honesty: **a `{"status":"succeeded"}` stub is a Tenet-3 trap — the mock's fidelity IS the test's validity.** |
| **7** | **Injectable-clock / fake-time harness** | ~10 (cross-cutting) | yes | Build accepts an injectable clock (env/module-seam/`?now=` hook) so the grader advances time deterministically: rate-limiter refill, scheduler fire, TTL expiry, token expiry, dunning/backoff timers. Without it, timing is only real-`sleep`-gradable → slow+flaky. Unblocks S7, S15, S40, F23, F37, V55 + all TTL/backoff. |
| **8** | **Idempotency-replay oracle** | ~9 | yes | Apply same key/event twice → exactly one effect + identical response; different key → new effect. Unblocks F11, F14–16, F21–23, S19, V56 (overlaps mock-payment but independently useful). |
| **9** | **Hash-chain integrity + append-only audit / access-control oracle** | ~6 | yes | Recompute an append-only chain, detect any mutated row (tamper-evident); assert every PHI/PII access logged, log immutable, denied-without-consent holds. Reuses jaros-code's own hash-chain discipline. Unblocks F10, F29, F35, S22, V23 (HIPAA), RBAC hardening. |
| **10** | **Multi-service fixture-upstream harness** | ~8 | yes | Start ≥2 in-process HTTP upstreams, wire URLs via env, drive an end-to-end flow with **fault injection**. Unblocks S50 gateway, S51 LB, S52 circuit-breaker, S53 registry, S65 SDK-vs-server, S57 OAuth-client↔IdP, S70 saga, S60 dist-lock. Generalizes the HTTP oracle to N cooperating processes. |
| **11** | **SMTP-capture sink oracle** | ~4 | yes | In-process SMTP sink (`aiosmtpd`/`smtpd`-style) capturing sent mail → assert recipient/subject/rendered body/idempotent send. Unblocks S30 email, S4 reset-email, F23 dunning email, V-notifications. |
| **12** | **Concurrency / exactly-N oracle** | ~5 | yes | Spawn K>N concurrent clients at a scarce resource under a seeded interleaving; assert exactly N succeed and no invariant breaks. Unblocks V58 flash-sale, V6 last-unit, V7 no-double-book, V38 no-double-assign, F59 double-spend, S60 dist-lock. |
| **13** | **SSE / WebSocket streaming-client oracle** | ~3 | yes(SSE) | Client opens a long-lived connection, collects N pushed events, asserts payloads + ordering + close. Unblocks S55 realtime push, streaming agent responses, V43-adjacent. SSE stdlib; WS needs a small frame codec. |
| **14** | **Feasibility / cost-bound oracle (optimization)** | ~3 | yes | For VRP/route/dispatch/time-window: assert the solution is **feasible** (capacity/windows/no-double-assign) AND cost ≤ a held-out bound (or within ε of brute-forced optimum on small instances). Avoids grading NP-hard on a single gold answer. Unblocks V37, V38, V39. |
| **15** | **Matching / price-time-priority oracle** | ~3 | yes | Best-price-first + FIFO-at-price + filled-qty conservation + non-crossed book, deterministic fills for a fixture sequence. Unblocks F38, F39, V32. |
| **16** | **Protocol-conformance oracle (OIDC / LTI 1.3 / FHIR REST)** | ~5 | yes | Drive a simulated counterparty (IdP / FHIR client), assert protocol-correct handshake (signed JWT/nonce/PKCE, FHIR read/search/`_history`/validate). Unblocks S56, S57, S58, V59, V60. Higher effort; simulate the peer in-process. |
| **17** | **Rule-engine exact-output fixtures** (mostly reuse import-driver) | ~5 | yes | Deterministic input→exact-output tables for tax, grade weighting, coupon totals, claim adjudication, reference-range flags. Not new code — **fixture tables** over the existing import-driver oracle. Unblocks V9, V12, V22, V48, V51, F31. |
| — | **Narrow format oracles** (NACHA fixed-width, proration/period, accounting-equation A==L+E, order-book already at #15) | 1–2 each | yes | Small, each unlocks 1–2: F26, F21, F30/F54. Build opportunistically when their parent class is scheduled. |
| — | **Prometheus-exposition + structured-log parser** (light) | 2 | yes | Tiny parsers so S24 metrics / S25 logging assert on `# TYPE`/counter lines + JSON records. Sharpens observability verification. |
| — | **Cloud-emulator harness** (moto / official emulators, simulated only) | escape hatch | dep | For S3/SQS/DynamoDB-shape tasks wanting real SDK surfaces without egress. Lower priority than the stdlib path; documented as the "cloud-shaped" escape hatch, Tenet-2 clean. |

**Build order (max coverage per unit effort):** agent-loop `[BUILDING]` → **state-machine** →
**double-entry** → **conservation** → money-invariant + rule-engine fixtures (cheap) →
mock-payment + injectable-clock → idempotency-replay + hash-chain/audit → multi-service harness →
SMTP-sink → concurrency → streaming → feasibility → matching → protocol. **The first four oracles
alone make ~55 classes honestly gradable across every vertical.**

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
  servers.
- **Every oracle grades structural invariants over a replayed op-script**, never a memorizable output
  string — the model cannot fake it by branching on a known task. Optimization classes grade on
  **feasibility + cost-bound**, never a single gold solution.
- **The `verified` tier is honest and small (5 utility + 2 building / 182).** The utility tier is the
  FLOOR being demoted; the frontier is the first service rung and the agent cluster. Moving
  `verified` up — by landing the ranked oracles in §4 — is the whole game.
