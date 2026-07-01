# IDEA BANK — novel levers for the Pursuit (outside review, 2026-07-01)

Companion to `PURSUIT.md`. Each idea: the concept, why it fits THIS system's measured
evidence, the cheapest probe, and a pre-registered kill criterion. Ideas are queued by
(impact × tractability) like everything else — this bank feeds the experiment chain,
it does not bypass the held-out gate.

Grouping: A = exploit being always-on/local (structural advantages a metered cloud
tool cannot have) · B = control the decode itself · C = convert model weakness into
strength via information format · D = widen the oracle surface · E = make the system
learn itself · F = UX physics · G = horizon.

---

## A. Exploit being ALWAYS-ON and LOCAL

**N1. The overnight brain (temporal arbitrage).** The Jetson idles ~80% of the day;
inference is free. Overnight: pre-build repo maps and semantic indexes, pre-generate
+ verify tests for uncovered functions, pre-solve TODO/FIXME comments into a drawer
of test-verified candidate patches, mine repo idioms, run distillation training.
Cloud tools are stateless and metered — they can never work ahead of the user. We
can. *Probe:* one overnight run that drafts+verifies patches for every TODO in a
target repo; count usable-by-owner next morning. *Kill:* <20% usable.

**N2. Speculative solving (the drawer).** While the user reads/thinks, watch the
working repo (file saves, failing tests) and speculatively solve the current failure
in the background. When asked, the verified answer may already exist. Perceived
latency → zero for anticipated asks. *Probe:* wire a watcher → background
solve_from_failure on test failure; measure hit-rate over 2 dogfood days. *Kill:*
<15% of asks pre-solved.

**N3. Shadow-mode parity logging (the sharpest possible instrument).** While the
owner still uses real Claude Code, log those tasks locally (fully private) and replay
them against jcode. The owner's ACTUAL workload becomes the parity benchmark — no
authored-suite bias, and it yields honest side-by-side "CC did / jcode did" rows.
This should eventually REPLACE the authored daily-driver suite as the headline
instrument. *Probe:* 20 real tasks hand-logged in a week, replayed. *Kill:* none —
this is measurement; it cannot lose.

**N4. Per-repo adapters ("your repo gets its own model").** Every repo's git history
is a free (commit-message → diff) training set in that repo's idiom. Overnight LoRA
on the WORKING repo → an adapter (MBs, hot-swappable) that speaks its conventions.
Cloud economics forbid per-repo fine-tunes; sovereign hardware makes them free. A
genuinely novel product mechanic. *Probe:* LoRA gemma/qwen on jaros-code's own
600-commit history; measure commit-replay + daily-driver lift on held-out. *Kill:*
no held-out lift after 2 data-recipe attempts.

## B. Control the DECODE itself

**N5. Grammar-constrained decoding (GBNF) — likely the cheapest big win in the bank.**
llama.cpp supports GBNF grammars: constrain output to valid Decision-JSON, exact
SEARCH/REPLACE format, or syntactically-valid-Python subsets. The ~60% broken-
indentation class and the malformed-S/R class get PREVENTED at decode time instead of
repaired after. Format failure classes → deterministically impossible. *Probe:* GBNF
for the S/R block format + JSON decisions; re-run the format-failure slice. *Kill:*
throughput cost >30% with no pass-rate gain (unlikely).

**N6. Skeleton-constrained fills.** Extend N5: the harness emits the deterministic
skeleton (signature, docstring, control-flow outline from the reduction library) as
grammar scaffolding; the model can ONLY fill bodies/holes. Merges reductions (L5)
with decode control — the strongest form of "the model only fills bounded blanks."
*Probe:* multi-function build flow with skeleton grammar vs free splice. *Kill:* no
lift on build-class evals.

## C. Convert weakness into strength via INFORMATION FORMAT

**N7. Execution-grounded exemplification ("trace-and-fill").** Measured fact: this
2B-class roster is weak at spec comprehension, strong at transform-by-example. So
NEVER show an abstract spec when you can show concrete I/O: run the failing test,
capture actual-vs-expected values, and prompt with the example table
("largest([1,5,2]) returned [1,5,2], must return 5"). The harness systematically
converts abstractions → examples before every solve. Doctrine, not just a jig.
*Probe:* wrong-impl class with value-tables vs raw asserts. *Kill:* no flip on 10
probes.

**N8. The knowledge compiler (docs → facts, offline).** Small models don't know
APIs. At repo-setup time, deterministically compile every dependency's API surface
(signatures, docstrings, examples harvested from the dep's OWN test suite) into a
compact local fact-base. Fact-injection (L3) then draws from compiled knowledge, not
model memory. The model doesn't need to know pandas; the harness knows where to look
it up. *Probe:* compile more-itertools' API; measure injection-hit-rate on the
commit-replay wrong-impl class. *Kill:* facts retrieved but flips <2/10.

**N9. Micro-context zoom protocol (attention via the harness, not the window).**
4096-token contexts are the wall behind the wall. Never show raw files: show a
multi-resolution view (repo map → file skeleton → full target function), and let the
model emit inert `zoom(symbol)` decisions; the harness re-renders at higher
resolution. Bounded context forever; navigation becomes decisions. *Probe:* repo-QA
tasks with zoom loop vs stuffed context. *Kill:* more steps AND no accuracy gain.

**N10. The failure museum (negative exemplars).** Mirror of the verified-solution
store: verified FAILURES, mined automatically per (class, model) — e.g. "on list-max,
this model returns the list itself." Inject as concrete prohibitions ("do NOT return
the list") — small models follow concrete prohibitions far better than abstract
specs. *Probe:* top-5 recurring failure patterns as prohibitions on their classes.
*Kill:* no lift or regression on held-out (prohibitions can distract — measure).

## D. Widen the ORACLE surface (more verifiable = more flywheel fuel)

**N11. Property/metamorphic oracle synthesis.** Tasks without tests can't be
test-gated — so synthesize oracles deterministically: round-trip properties,
idempotence, invariants (sorted output is ordered + length-preserved), metamorphic
relations (rename-refactor preserves behavior on random inputs). Verification without
knowing the answer → more of the daily-driver surface becomes gradeable → more
verified data for the flywheel. *Probe:* auto-property-tests for the refactor family.
*Kill:* >20% false-positive oracle rate.

**N12. Mutation task factory (infinite curriculum, perfect ground truth).** Generate
unlimited training/eval tasks from ANY codebase: AST-mutate a function (realistic bug
classes), the repo's tests fail, task = fix it — and the original code is the known
answer. Difficulty is controllable (mutation depth), volume is unlimited, ground
truth is perfect. Feeds evals, auditions, AND distillation data at scale with zero
human authoring. *Probe:* 100 mutation tasks from more-itertools; check
difficulty-spread vs commit-replay. *Kill:* mutations trivially greppable (then
harden mutation operators).

**N13. Static pre-gates (spend Jetson-hours only on plausible candidates).** Test
runs are the expensive verification step. Insert free static gates first: parse →
type-consistency → None-safety → exception-path sanity, then self-tests, then full
suite. Rejecting a doomed candidate in 5ms instead of 90s multiplies effective
search width. *Probe:* measure % of failing candidates catchable statically on
logged history. *Kill:* <10% early-catch rate.

## E. Make the system LEARN ITSELF

**N14. Confidence calibration micro-model (know-when-you-don't-know).** Train a tiny
classifier on eval logs: (class, model, output logprobs, self-test signals) →
P(correct). Enables honest "I'm not sure" UX (a real CC-parity trait), smart retry
budgets (spend compute only on middling-P candidates), and principled escalation
triggers. Logprobs are free at inference. *Probe:* fit on existing eval logs; check
calibration curve (Brier) on held-out runs. *Kill:* no better than class-baserate.

**N15. Cost-model planner (make "as fast as possible" literal).** Build an explicit
cost model — tokens/sec per model, swap costs, P(success | class, model, strategy),
expected retries — and let the deterministic planner choose the strategy that
minimizes expected wall-clock per SOLVED task. The router matures from classifier
into optimizer. *Probe:* offline replay of logged runs under the cost model; compare
predicted-vs-actual best strategy. *Kill:* model mispredicts best strategy >40%.

**N16. Verified-process distillation.** When gated thinking produces a test-passing
solution, the <think> trace is itself verified training data. Distill traces (only
the ones that END in verified answers) so the model's reasoning improves, not just
its answers. Extends the flywheel from outcomes to processes. *Probe:* collect 200
verified traces; LoRA; measure think-mode lift held-out. *Kill:* no lift.

**N17. The amortization ratio (metricize "jigs compound").** New scoreboard metric:
% of daily tasks served from memory / deterministic paths / drawer WITHOUT a full
model solve. The "second time is free" invariant, measured. If the thesis is right,
this ratio climbs indefinitely and is the honest signature of compounding capital.
*Probe:* instrument telemetry; report weekly. *Kill:* none — pure measurement.

## F. UX physics

**N18. Anytime answers (perceived latency beats raw latency).** Answer in layers:
deterministic result instantly (grep/AST in ms), model draft streams next, verified
answer replaces it when the test gate lands — visibly self-correcting. CC feels fast
partly because it streams; we can feel fast by being USEFUL at t=0 and TRUSTWORTHY at
t=verify. *Probe:* layer the 3 highest-traffic commands; dogfood-rate the feel.
*Kill:* users (owner/agent) prefer blocking output.

## G. Horizon

**N19. The Jetson tier, not the Jetson board.** Define the constraint as the PRICE
TIER ("inference on a ~$250-class owned device"), not this 2023 board forever.
Sovereignty is the invariant; the silicon improves (Orin successors, 16GB-class
boards). Re-baseline when the tier's hardware refreshes — honestly labeled.

**N20. Federation formats (the owner's mission, made concrete).** The dreamed
"cache of tiny specialized models": design the artifact formats NOW — adapter
registry entries (base model, class coverage, held-out numbers, provenance),
solution-store interchange schema — so after open-sourcing, other people's sovereign
devices can contribute and consume verified capability. The little guys compound
together. *Timing:* post-release; costs a schema design today.

---

## Suggested first pulls (highest impact × tractability)

1. **N5 GBNF constrained decoding** — prevents measured failure classes at decode
   time; cheapest big win here.
2. **N7 execution-grounded exemplification** — directly attacks the #1 failure class
   (wrong-impl) using the roster's measured strength.
3. **N3 shadow-mode parity logging** — the sharpest instrument; makes every other
   claim honest against the real workload.
4. **N12 mutation task factory** — unblocks unlimited curriculum + distillation fuel.
5. **N1 overnight brain** — the structural advantage; start with index/test
   pre-computation, grow into the drawer (N2).
