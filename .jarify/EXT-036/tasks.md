# EXT-036 Tasks

### [TASK-1] CLI UX: conversational session state + resume (REQ-12 backbone)

`harness/cli.py` today handles each REPL line in ISOLATION (`handle(line)` routes slash-command / intent /
orchestrator per line; no conversation carried across turns, no persistence, no resume). Fill the REQ-12 backbone:
a conversational, resumable session — the Tenet-5 Claude-Code feel. Scope = session state + resume ONLY (inline
ask-user REQ-8 and mid-task steering are follow-ups that build on this).

#### Steps
1. Add a lightweight `Session` (in `harness/cli.py` or a small `harness/session.py`): an ordered transcript of
   turns `{role: "user"|"assistant", text, ts?}` plus a session `id`. `JcodeCli` holds a `Session`; `handle()`
   APPENDS the user line and the assistant response to it each turn.
2. Make plain-language routing CONVERSATION-AWARE: when routing a plain request through the orchestrator (and the
   NL-fix path), include a BOUNDED recent transcript (e.g. last ~6 turns, truncated) as context so follow-ups like
   "now add error handling to that" resolve against the prior turn. Keep it bounded (small model = small context);
   slash commands stay stateless/direct. Do NOT change slash-command behavior.
3. PERSIST the session: write the transcript to `.jaros-data/sessions/<id>.json` (gitignored) after each turn
   (best-effort, never crash the REPL). Add `/resume <id>` (and a `--resume <id>` main-arg) that loads a prior
   session's transcript and continues it; `/new` starts a fresh session; `/sessions` lists recent ones.
4. Keep the REPL robust: one bad turn never kills the session (existing guard), persistence failure is non-fatal.
   Banner/`/help` mention the new commands. UX only — NEVER changes solve/routing correctness (Tenet 5 is lowest).
5. Tests (`tests/test_ext036_cli_session.py`, OFFLINE — no live model; stub the orchestrator/llm): assert (a) the
   Session accumulates user+assistant turns across `handle()` calls; (b) the bounded transcript is passed into the
   plain-language routing path (assert the orchestrator/handler received prior-turn context, bounded to the cap);
   (c) persist→`/resume` round-trips a transcript; (d) slash commands remain stateless + unchanged. Full `tests/`
   stays green.

#### Implements
- [REQ-12] CLI UX parity with Claude Code (conversational session state + resume — the backbone)

### [TASK-2] JAROS.md — per-repo project instructions auto-injected every prompt (REQ-17)

Analog of Claude Code's CLAUDE.md: a per-repo `JAROS.md` (project instructions/conventions) loaded and injected into
the agent's context on EVERY plain-language turn, so the system always honors the project's rules. Composes on the
TASK-1 routing/session path.

#### Steps
1. Add `harness/project_md.py` (or a small helper in cli.py): `load_project_md(root)` discovers `JAROS.md` at the repo
   root (fall back to `.jaros/JAROS.md`); returns its text BOUNDED (e.g. first ~2000 chars, small-model context) or ""
   if absent. Pure/deterministic, never raises.
2. In `harness/cli.py`, inject the JAROS.md content into the SAME plain-language routing augmentation that TASK-1 added
   (`_augment_with_history` / the orchestrator + `_nl_fix` request) — as a clearly-labeled `PROJECT INSTRUCTIONS:`
   preamble, BEFORE the conversation history. Absent file = graceful no-op (request byte-identical, like empty history).
   Slash commands unaffected. Load once per session (cache), not per keystroke.
3. Tests (`tests/test_ext036_project_md.py`, OFFLINE): (a) `load_project_md` reads a JAROS.md from a temp root, bounds
   it, and returns "" when absent; (b) when a JAROS.md exists, its content appears in the request passed to the
   orchestrator/_nl_fix on a plain-language turn; (c) absent → request unchanged (no-op); (d) slash commands unaffected.
   Full `tests/` stays green.

#### Implements
- [REQ-17] Project-instructions file auto-injected every prompt (JAROS.md ≈ CLAUDE.md)

### [TASK-3] Per-repo long-term memory + memory-AGENT recall (REQ-16)

The measured small-model memory design (docs/GAP-MAP.md): raw transcript is fine IN-session; the memory-AGENT's value
is CROSS-SESSION + large-scale recall (where the transcript isn't available). Build that: a per-repo persistent fact
store + an agent that SELECTS the few relevant facts for the current request (validated: it picks correctly) and
injects ONLY those (precise recall — never a dump, guarding the retrieval-negative regression).

#### Steps
1. `harness/repo_memory.py`: a per-repo fact store persisted to `.jaros/memory.jsonl` (keyed to the repo/cwd).
   `add_fact(text, root=".")` appends a durable fact; `load_facts(root)` returns the list; both deterministic,
   guarded (never raise). Bound the store read (cap facts loaded).
2. Memory-AGENT recall: `select_relevant(request, facts)` — a NARROW model judgment that returns the indices/subset of
   facts directly relevant to the request (mirror `.jaros-data/mem_experiment2.py`'s selection prompt; return [] if
   none). Deterministic fallback: if the model output is unparseable, return [] (no injection) — never dump all facts.
3. Wire into `harness/cli.py`: on plain-language turns, recall the relevant facts and inject them into the routing
   augmentation as a `RELEVANT MEMORY:` block (after JAROS.md PROJECT INSTRUCTIONS, before conversation history).
   Empty selection = no-op (byte-identical). Add a `/remember <fact>` command to capture a fact; `/memory` lists them.
4. Tests (`tests/test_ext036_repo_memory.py`, OFFLINE — stub the memory-agent + orchestrator, no live model):
   (a) add_fact→load_facts round-trips per-repo + is isolated by root; (b) select_relevant returns only the stubbed
   relevant subset, [] on unparseable; (c) selected facts injected into the plain-turn request as RELEVANT MEMORY,
   empty selection = no-op; (d) `/remember` persists, `/memory` lists; (e) slash commands unaffected. Full tests green.

#### Implements
- [REQ-16] Long-term + PER-REPO memory (memory-agent selective recall — cross-session)

### [TASK-4] Productionize the sentence-to-system pipeline into the harness (REQ-1/3/4 core)

The end-to-end pipeline is PROVEN in probes (`.jaros-data/s2s_build_probe.py`, `s2s_doneness_probe.py`) but only lives
there. Productionize it into `harness/system_builder.py` as a real, tested capability composing the proven pieces.

#### Steps
1. `harness/system_builder.py::build_system(spec, root, *, llm=None) -> dict`: (a) PLAN — model emits a coherence-valid
   JSON plan (modules+signatures+imports+entrypoint), deterministic validator checks the DAG (reuse the probe's
   validate()); (b) topological BUILD — for each module leaves-first, model writes the body given
   responsibility+signature+already-built sibling code, then a deterministic py_compile SYNTAX GATE + bounded repair
   loop (the two gaps already discovered+fixed in the probe); (c) ASSEMBLE into `root`; (d) ACCEPTANCE — derive an
   executable acceptance checklist from the spec+API (REQ-2/7 probe logic) and RUN it; return
   `{modules, shipped: bool, done: bool, unmet: [...], plan}`. Never raises; on any failure returns shipped/done False.
2. Two-plane: model = plan + module bodies + acceptance-checklist authoring; deterministic = DAG validation, syntax
   gate, assembly, running the checklist. Bound token budgets (the truncation gap). Honest: `done` requires the
   acceptance checklist to PASS (Tenet 3), not prose.
3. Add a `/build <sentence>` CLI command wiring build_system (writes into a subdir, reports shipped/done/unmet).
4. Tests (`tests/test_ext036_system_builder.py`, OFFLINE — stub `llm` to return a CANNED plan, canned module bodies,
   canned acceptance checks; NO live model): assert the pipeline plans→builds→assembles→runs the checklist and returns
   the right dict; assert the syntax-gate+repair path (canned first body has a SyntaxError, repair returns valid) works;
   assert a failing acceptance check → done=False + unmet lists it. Full `tests/` stays green.

#### Implements
- [REQ-4] End-to-end plan→build→wire→assemble→acceptance (productionized)
- [REQ-1] Planner (coherence-validated) + [REQ-3] per-module syntax-gate/repair, composed into the pipeline

### [TASK-5] System-level repair — drive a built system from shipped→DONE (REQ-5)

MEASURED (live TASK-4 run): `build_system` on the CSV spec SHIPS (runnable) but reports done=False with unmet acceptance
checks (edge cases like "handle empty data gracefully"). REQ-5: when acceptance checks fail, REPAIR the responsible
module(s) from the failure feedback and re-validate — the cross-level repair that turns shipped→DONE. Analog of the
write-tests/syntax repair loops, at the acceptance level.

#### Steps
1. `harness/system_builder.py`: add a bounded repair loop inside (or wrapping) `build_system`. When the acceptance
   checklist has unmet checks, for each unmet check feed (the failing check's code + its run error + the CURRENT module
   sources) to the model asking for a TARGETED fix: which module file + its corrected complete content. Apply the fix
   (deterministic write), re-assemble, re-run the FULL checklist. Repeat up to `max_repair` (default 2) rounds; stop
   early when done=True. Deterministic guards: syntax-gate any repaired module (reuse `syntax_ok`+syntax-repair); if a
   repair round reduces no unmet checks, stop (no infinite loop). Return the improved `{shipped, done, unmet, repairs}`.
2. HONESTY (Tenet 3): `done` still requires the FULL acceptance checklist to PASS after repair — never mark done on a
   partial fix. Non-degrading: repair can only improve or leave unmet unchanged; a system already done skips repair.
   Never raises.
3. Tests (`tests/test_ext036_system_repair.py`, OFFLINE — canned llm): (a) a build with 1 unmet check where the canned
   repair fixes the module → done=True after 1 repair round, `repairs` records it; (b) a build where repair never fixes
   it → stays done=False after exactly max_repair rounds (bounded, non-degrading); (c) an already-done build → 0 repair
   rounds (skip). Full `tests/` stays green.

#### Implements
- [REQ-5] Cross-level repair (system-level acceptance-driven repair: shipped→DONE)

### [TASK-6] Robust executable-acceptance derivation (REQ-2 refinement — unblock done-ness)

MEASURED (docs/GAP-MAP.md difficulty spectrum): systems SHIP to 4 modules but report done=False because the acceptance
DERIVATION is weak — the small model emits vague/non-executable "conceptual" checks (easy) or fails to produce a
parseable checklist at all (medium: "no acceptance checklist derived"). done-ness is honest (never false-passes) but
pessimistic. Fix the derivation so a WORKING system can reach done. Two-plane: deterministic filtering + fallback.

#### Steps
1. In `harness/system_builder.py::_derive_acceptance_checklist` (and `_run_check`): after the model proposes checks,
   DETERMINISTICALLY FILTER to EXECUTABLE ones — a check survives only if its `code` parses (ast) AND contains a real
   `assert` (drop prose/"conceptual"/non-assertion checks). If the model output is unparseable or yields ZERO surviving
   checks, RETRY once with a stricter prompt (demand ONLY runnable Python asserting real behavior against the module
   API, no prose). 
2. Deterministic FALLBACK: if still no executable checks, synthesize a minimal deterministic check — the entrypoint /
   each exported module IMPORTS without error and the entrypoint is callable (a smoke check). `done` requires ≥1 real
   executable check present AND all surviving checks pass — never done on an EMPTY checklist (an empty checklist must
   NOT count as done; today "no checklist" → not done, keep that, but prefer the fallback smoke check so a working
   system can pass).
3. HONESTY (Tenet 3): filtering/fallback must never make a BROKEN system pass — the fallback smoke check still requires
   real import+run success; dropping a vague check never turns a failing system green. `done` still means real checks pass.
4. Tests (`tests/test_ext036_acceptance.py`, OFFLINE — canned llm): (a) a vague/"conceptual" model check is FILTERED
   out (not run as-is); (b) unparseable/zero-executable → stricter retry, then deterministic smoke fallback; (c) the
   smoke fallback passes for a working entrypoint and FAILS for a broken one (no false-pass); (d) an empty checklist
   never counts as done. Full `tests/` stays green.

#### Implements
- [REQ-2] Executable acceptance — robust derivation (filter to runnable checks + deterministic smoke fallback)

### [TASK-7] Modification from a sentence — modify_system, regression-gated (REQ-14)

Owner-emphasized: not just CREATE but MODIFY an existing system from a sentence ("add median to the CSV CLI").
Compose the CREATE pipeline's pieces (syntax_ok, _build_module, _derive_acceptance_checklist, _run_check) + the
non-degrading pattern from TASK-5. The HONESTY core: a modification must PRESERVE existing behavior (regression-gated).

#### Steps
1. `harness/system_builder.py::modify_system(modules, mod_sentence, root, *, llm=None) -> dict` where `modules` is the
   existing `{name: code}`: (a) BASELINE — derive + run the acceptance checklist on the CURRENT system, record the set
   of checks that PASS (existing behavior); (b) the model identifies which module(s) the mod_sentence targets and
   regenerates them WITH the change (given the current sources + the mod_sentence), syntax-gate + bounded repair;
   (c) assemble the modified system; (d) REGRESSION GATE — re-run the baseline-passing checks; if ANY regressed
   (previously-passing now fails), REVERT the modified module(s) to their pre-mod content and set `applied=False`
   (non-degrading, mirrors TASK-5's revert); (e) best-effort NEW-behavior check derived from the mod_sentence.
2. Return `{modules, applied: bool, regressed: [names], new_behavior_ok: bool, note}`. HONESTY (Tenet 3): `applied=True`
   ONLY if no regression (existing behavior preserved). Never raises. A modification that breaks existing behavior is
   reverted, not accepted.
3. Add a `/modifysystem <sentence>` CLI command (operates on the last-built system dir or a given dir), reporting
   applied/regressed/new_behavior. Additive; don't disturb existing commands.
4. Tests (`tests/test_ext036_modify.py`, OFFLINE — canned llm): (a) a clean modification (adds a feature, existing
   checks still pass) → applied=True; (b) a modification that BREAKS an existing check → reverted, applied=False,
   regressed lists it, modules restored to pre-mod content; (c) never raises on unparseable model output. Full tests green.

#### Implements
- [REQ-14] Modification from a sentence (regression-gated modify_system)

### [TASK-8] Todo task management, user-facing (REQ-18)

Claude-Code-style task tracking for the user's work: create/list/update/complete tasks, plus a model-proposed
breakdown of a request into tracked steps. Composes on the session/per-repo state (TASK-1/TASK-3).

#### Steps
1. `harness/task_store.py`: a per-repo task store persisted to `.jaros/tasks.jsonl`. `add_task(text, root, status="pending")`,
   `list_tasks(root)`, `update_task(id, status/text, root)` (statuses: pending/in_progress/done). Deterministic, guarded,
   never raises. Bounded read.
2. Model-proposed breakdown: `propose_tasks(request, llm) -> list[str]` — ONE narrow model call that decomposes a
   request into 2-6 concrete task strings (JSON list, `[]` on failure — never fabricate). Deterministic parse/guard.
3. `harness/cli.py`: `/task <text>` (add), `/tasks` (list with ids+status), `/task done <id>` / `/task doing <id>`
   (update). Additive; existing commands untouched. Surface tasks compactly.
4. Tests (`tests/test_ext036_tasks.py`, OFFLINE — canned llm): (a) add/list/update round-trips + per-repo isolation +
   status transitions; (b) propose_tasks returns the stubbed breakdown, `[]` on unparseable (never fabricates);
   (c) CLI commands add/list/update correctly; (d) slash commands unaffected. Full `tests/` stays green.

#### Implements
- [REQ-18] TODO task creation + management (user-facing)

### [TASK-9] Experiment management, user-facing (REQ-19)

Claude-Code-style experiments: define (hypothesis + how to run + how to measure) → run → record the result against the
hypothesis. Mirrors TASK-8's store pattern; the "run" is a real deterministic subprocess execution (never faked).

#### Steps
1. `harness/experiment_store.py`: per-repo store at `.jaros/experiments.jsonl`. `define_experiment(hypothesis, run_cmd,
   root, measure="")` → `{id, hypothesis, run_cmd, measure, status:"defined"}`; `run_experiment(id, root, *,
   timeout=60)` → executes `run_cmd` via subprocess in `root` (guarded, bounded timeout, tree-kill-safe if available),
   records `{exit_code, output(tail), status:"run"}` — a REAL run, never fabricated; `list_experiments(root)`.
   Deterministic, guarded, never raises. Bounded read.
2. `harness/cli.py`: `/experiment <hypothesis> :: <run_cmd>` (define), `/experiments` (list w/ id+status+last result),
   `/experiment run <id>` (run + report exit/output). Additive; existing commands untouched.
3. HONESTY (Tenet 3): the result is the ACTUAL subprocess exit/output — never invented. A run failure records the real
   failure, not a pass.
4. Tests (`tests/test_ext036_experiments.py`, OFFLINE — no model needed; use trivial real run_cmds like
   `python -c "import sys;sys.exit(0)"` (pass) and `...sys.exit(1)` (fail)): (a) define/list/run round-trip + per-repo
   isolation; (b) a passing run_cmd → exit_code 0 recorded, a failing one → non-zero recorded (real, not faked);
   (c) run guards a bad/hanging cmd (timeout) without raising; (d) CLI commands work; (e) slash unaffected. Tests green.

#### Implements
- [REQ-19] Experiment creation + management (user-facing)

### [TASK-10] Multi-level tests: integration + performance (REQ-6)

Beyond unit tests (write-tests) + the acceptance checklist (which exercises the assembled system's API): explicit
INTEGRATION tests (cross-module flows) + PERFORMANCE tests (measure + assert a threshold). Composes system_builder +
the test-gen. Offline-testable with canned/deterministic runs.

#### Steps
1. `harness/system_builder.py` (or a small `harness/multi_tests.py`): `integration_check(modules, root, flows, llm)` —
   for a multi-module system, derive/run a cross-module INTEGRATION scenario (calls spanning >=2 modules) as an
   executable check; `perf_check(modules, root, entry, threshold_s)` — run the entry on a workload, MEASURE wall-time,
   assert it's under `threshold_s` (a REAL measurement, honest — a slow system fails). Deterministic, guarded, never raises.
2. HONESTY (Tenet 3): integration/perf results are REAL (actual cross-module execution / actual measured time) — never
   fabricated; a failing integration or an over-threshold perf is recorded as a failure, not a pass.
3. Optionally surface via `build_system` (add integration/perf to the returned dict, advisory — don't change `done`'s
   acceptance gate unless the flows are part of the spec).
4. Tests (`tests/test_ext036_multitests.py`, OFFLINE — canned modules): (a) an integration flow across 2 modules passes
   when they cooperate, fails when one is broken; (b) perf_check passes a fast entry, fails a deliberately slow one
   (real measured time, honest); (c) never raises on bad input. Full `tests/` stays green.

#### Implements
- [REQ-6] Multi-level test generation — integration + performance

### [TASK-11] Short-term memory condensation (REQ-15)

Completes the memory subsystem: when the session transcript (TASK-1 `Session`) grows past a budget (the small model's
finite context), CONDENSE the oldest turns into a running summary so context stays within budget without losing the
thread. Safe + additive: only activates over-budget; never changes behavior for short sessions. (Measured: raw is fine
to ~30 facts, but real long transcripts exceed the window — this is the guard for that.)

#### Steps
1. `harness/session.py`: add a budget (e.g. `MAX_TURNS`/`MAX_CHARS` for the injected slice) and
   `condense(session, llm) -> None` (or return a condensed view): when the transcript exceeds the budget, summarize the
   OLDEST turns (a narrow model call) into a single `role:"summary"` entry, keep it + the most-recent turns; the
   `recent()` slice returned to the router then = summary + recent turns, staying within budget. Deterministic budget
   check; the only model step is the summary. Guarded, never raises (on model failure, fall back to truncating oldest).
2. Wire into the CLI's history-injection path (the existing `_augment_with_history`/`recent()` consumer): the injected
   context is the condensed view when over budget, the raw recent turns otherwise. No change for short sessions.
3. HONESTY: condensation must preserve task-relevant facts — a follow-up needing an old fact should still resolve after
   condense (best-effort via the summary). It's a lossy summary, honestly labeled `summary`, not a claim of full recall.
4. Tests (`tests/test_ext036_condense.py`, OFFLINE — canned llm summary): (a) under budget → no condense, raw turns
   returned unchanged; (b) over budget → oldest turns replaced by a `summary` entry, recent turns kept, slice within
   budget; (c) model-failure fallback truncates without raising; (d) a fact stated in an old (now-summarized) turn is
   present in the summary (canned) so it's still injected. Full `tests/` stays green.

#### Implements
- [REQ-15] Short-term memory management + condensation

### [TASK-12] Ask-the-user when ambiguous (REQ-8) — additive, safe

Complete REQ-12's interaction loop: when a plain-language request is genuinely AMBIGUOUS/under-determined, ASK a
targeted clarifying question rather than guessing. Additive + safe: no regression risk (worst case = an occasional
unneeded question in interactive mode); headless/one-shot falls back to a sensible default (never blocks).

#### Steps
1. `harness/ask_user.py` (or a helper): `detect_ambiguity(request, llm) -> str|None` — ONE narrow, CONSERVATIVE model
   judgment returning a single clarifying question ONLY when the request is genuinely ambiguous (missing a critical
   choice), else None. Grounded/degeneracy-guarded so it does NOT over-ask (default to None on any doubt — under-asking
   is safer than annoying over-asking). Deterministic parse; None on model failure.
2. `harness/cli.py`: in the interactive REPL path only, before routing a plain request, if `detect_ambiguity` returns a
   question, PRINT it + read the user's answer via input(), then fold the answer into the request. In headless/one-shot
   mode (`main()` arg path) or non-interactive, SKIP asking entirely (fall back to the default = proceed with the
   request as-is). Slash commands never ask. Session records the Q+A turn.
3. HONESTY: only ask on GENUINE ambiguity (conservative); never fabricate a question to seem helpful; headless never
   blocks waiting for input.
4. Tests (`tests/test_ext036_ask.py`, OFFLINE — canned llm + stubbed input): (a) `detect_ambiguity` returns the canned
   question for an ambiguous request, None for a clear one, None on model failure; (b) interactive path asks + folds
   the stubbed answer into the routed request; (c) headless/non-interactive path NEVER asks (falls back); (d) slash
   commands never trigger a question. Full `tests/` stays green.

#### Implements
- [REQ-8] Ask-the-user when needed — clarify ambiguity (interactive; headless falls back)

### [TASK-13] Hard-tier escalation core for build_system (REQ-13)

MEASURED (2026-07-03, commit c182c33): on complex sentence->system builds, gemma-4-e2b SHIPS 2/3
(fully-completes 1) while Qwen2.5-Coder-7B SHIPS 3/3 but never fully-completes and costs ~3x
latency. Routing EVERYTHING to the 7B is a bad trade; the honest lever for REQ-13's hard tier is
ESCALATE-ONLY-ON-FAILURE: run the default model first, and only pay the 7B's cost when the default
actually failed to ship — capturing the marginal coverage (e.g. the case gemma ships 0 modules for)
without losing gemma's done-ness or latency on the common case. OFFLINE, test-gated core only; live
CLI/Jetson wiring (via `collaborative_solve._http_swap`) is an explicit OUT-OF-SCOPE follow-up.

#### Steps
1. Add `harness/system_builder.py::build_system_escalating(spec, root, *, primary_llm,
   fallback_llm=None, swap_fn=None, fallback_model_id=None, primary_model_id=None) -> dict`: run
   `build_system(spec, root, llm=primary_llm)`; if it `shipped`, return it AS-IS (fallback_llm and
   swap_fn are NEVER invoked — the common, low-latency path). Add `escalated: False` and
   `model: "primary"` to the returned dict for a consistent shape (do not touch `build_system`
   itself or its return shape).
2. If the primary result is NOT shipped and `fallback_llm` is provided: call `swap_fn(fallback_model_id)`
   when `swap_fn` is given (two-plane serving swap — activates the fallback model), then run
   `build_system(spec, root, llm=fallback_llm)`. Pick the BETTER of the two results by a
   deterministic rule: prefer shipped over not-shipped, then prefer done over not-done, then prefer
   more built modules. Tag the returned dict `escalated: True` and `model: "fallback"` or
   `"primary"` depending on which result won.
3. Cleanup: when a swap to the fallback happened and `primary_model_id` + `swap_fn` are both given,
   swap back to the primary model in a `finally` block so the default model is restored even if the
   fallback build raises.
4. Robustness (Tenet 3, never-raise like `build_system`): if `swap_fn` raises or the fallback
   `build_system` call raises, catch it and return the primary result (with the escalation metadata
   keys added) — never raise, never leave the caller worse off than primary-only.
5. Tests (`tests/test_ext036_escalate.py`, OFFLINE — canned/fake llms + a stub `swap_fn` recording
   calls, no network/Jetson): (a) primary ships -> returns primary, fallback_llm/swap_fn never
   invoked, `escalated: False`; (b) primary fails + fallback ships -> escalates, swap_fn called with
   fallback then primary (restore), returns the fallback result, `escalated: True`; (c) both fail ->
   returns the better/primary result, never raises; (d) `swap_fn` raises -> gracefully returns the
   primary result, never raises; (e) the fallback build raises -> returns the primary result, never
   raises. Run full `tests/` — stays green.

#### Implements
- [REQ-13] Full difficulty spectrum — easy / medium / hard / highly-complex creation (offline
  escalation core toward the hard tier; live wiring + the difficulty-spectrum sweep remain open)

### [TASK-14] Creation-suite framework + first slice (REQ-20)

REQ-20 needs a broad, DIVERSE, HELD-OUT benchmark of sentence->system CREATION tasks with an
INDEPENDENT oracle (Tenet 3 — the acceptance check must NOT be the model's own self-derived
checklist, and must NEVER be leaked into the solving prompt). Build the framework + a first
concrete slice, BLACK-BOX: each task's sentence specifies a CLI contract, and acceptance runs the
built system's entrypoint as a subprocess with given args/stdin and asserts on stdout/exit-code —
independent of module/function names the model chooses (API-agnostic).

#### Steps
1. New `harness/system_suite.py`: a `CreationTask` dataclass (`name, cls, tier ("easy"|"medium"|
   "hard"), sentence, checks`), where `checks` is a list of either `(argv, stdin, expected_substring)`
   black-box CLI checks or a `callable(root, plan) -> bool` for cases the black-box CLI contract
   doesn't fit. Deterministic, no model involved in this module.
2. `run_creation_suite(build_fn, tasks=None, python_exe=None) -> dict`: for each task, call
   `build_fn(task.sentence, root)` (same signature as `harness.system_builder.build_system`) in an
   isolated temp root, then run each check as a GUARDED subprocess (`python <root>/<entrypoint>
   <argv...>` fed `stdin`, timeout + tree-safe kill, mirroring `harness/multi_file.py::_run`'s
   pattern) and assert the expected substring appears in stdout. Record per-task
   `{name, cls, tier, shipped, done, accepted, n_checks_passed}`. NEVER raise per task — a
   build/exec failure records `accepted=False` and the suite continues to the next task. Return
   `{results: [...], aggregate: {overall: {...}, by_tier: {...}}}` (ship-rate/done-rate/accept-rate).
3. Define a FIRST SLICE of 6 `CreationTask`s (2 easy, 2 medium, 2 hard) across distinct classes
   (aggregator/text CLI, todo-list, unit-converter, kv-store with TTL, priority job-queue), each
   with a precisely-specified CLI contract in the sentence and concrete deterministic checks (no
   real-time sleeps — e.g. TTL-expiry uses a `ttl=0` immediate-expiry case, not a timed wait).
4. Tests `tests/test_ext036_suite.py` (OFFLINE — no model, no network): a stub `build_fn` writes a
   known-correct tiny CLI system for one task and a deliberately-broken/missing-entrypoint one for
   another; assert (a) aggregation (accept-rate, per-tier breakdown) is correct; (b) a passing stub
   → `accepted=True`; (c) a broken/missing-entrypoint stub → `accepted=False`, no raise; (d) a
   `build_fn` that raises for one task → that task records `accepted=False`, suite continues; (e)
   the first-slice `CreationTask` registry has the expected tasks with valid tiers/classes. Full
   `tests/` stays green.

#### Implements
- [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence->system CREATION
  classes (framework + first slice; live gemma-vs-escalating measurement and growing class
  coverage remain open follow-ups)

### [TASK-15] Make creation-suite task sentences contract-precise (oracle-honest)

MEASURED (2026-07-03, first live run): the FIRST_SLICE suite scored 0% accept + an INVERTED
tier ordering (easy 0/2 shipped, medium/hard 0.5 accept) — a HARNESS bug in the task
definitions, not a gemma capability ceiling. Root cause (probe
`.jaros-data/hyp_precise_sentence.py`, `.jaros-data/debug_suite_v2.py`): the original
`FIRST_SLICE` sentences left the entrypoint FILENAME and exact CLI/stdout contract unstated,
so (1) gemma sometimes plans an entrypoint filename that isn't one of its own listed
modules, which `validate_plan` correctly rejects ("entrypoint not a listed module"),
yielding 0 built modules; and (2) even when it ships, gemma may build a CLI surface that
diverges from what the oracle's hardcoded `checks` assume, so the independent oracle
correctly can't run/match it — a false negative caused by an under-specified sentence, not a
broken build. PROVEN FIX: a CONTRACT-PRECISE sentence — pinning the entrypoint filename
`main.py`, the exact `python main.py` invocation (or exact argv/stdin protocol), the exact
stdout format including the trailing newline, and the `if __name__ == "__main__":`
requirement — made `sum-cli` ship AND the independent oracle ACCEPT it. This is honest, not
leakage (Tenet 3): the sentence IS the spec the independent oracle checks against; the model
still has to build a working system that satisfies it.

#### Steps
1. In `harness/system_suite.py`, rewrite each of the 6 `FIRST_SLICE` task `sentence` fields to
   be contract-complete: every task's system is pinned to a SINGLE entrypoint file named
   `main.py` ("in a file named main.py", requiring an `if __name__ == "__main__":` block),
   making the plan coherent (`entrypoint` in the model's own listed modules) and the oracle's
   entrypoint resolution unambiguous.
2. Pin the EXACT invocation + I/O contract in each sentence: how args/stdin are supplied and
   the exact stdout format (state the format explicitly, including a trailing newline). For
   the multi-command tasks (`todo-list-cli`, `kv-store-ttl-cli`, `priority-jobqueue-cli`)
   spell out a deterministic line-based stdin command protocol precisely enough that the
   existing fixed `checks` are unambiguous against it. Keep the same 6 classes/tiers (easy:
   `sum-cli`, `wordcount-cli`; medium: `todo-list-cli`, `temp-converter-cli`; hard:
   `kv-store-ttl-cli`, `priority-jobqueue-cli`).
3. Align each task's `checks` to its rewritten contract exactly, keeping them deterministic
   (no wall-clock; the kv-store TTL check keeps `ttl=0` immediate-expiry) and derivable from
   the stated output format.
4. Add a minimal, GENERIC entrypoint-resolution fallback in `harness/system_suite.py`'s
   `_run_single_check` (not task-specific): if the plan-declared entrypoint file is not found
   on disk but `root/main.py` exists (the convention every task's sentence now pins), fall
   back to running `main.py`. Do NOT otherwise change `run_creation_suite`/`_run_cli`/the
   oracle mechanism (proven working on the medium `temp-converter-cli` task, which already
   shipped+done in the live run).
5. Update `tests/test_ext036_suite.py` only where it depended on old sentence/check text (none
   currently assert exact `FIRST_SLICE` sentence content) or the stub systems it writes so
   they still satisfy the rewritten `checks`; run the FULL `python -m pytest tests/ -q` suite
   and confirm it stays green at its prior count.

#### Implements
- [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence->system CREATION
  classes (this task fixes a measured harness precision bug in the first slice's task
  definitions so ship/accept rates reflect genuine model capability, not sentence ambiguity;
  live gemma-vs-escalating re-measurement after this fix remains the follow-up)

### [TASK-16] Modification-suite framework + first slice (REQ-21)

REQ-21 needs the harder, more realistic parity instrument: MODIFYING an existing working
system from a one-sentence change, isolated from the CREATION capability (REQ-20) by starting
each task from a FIXED, known-good ``start_system`` (a small hand-written fixture) rather than
a model-built one. Mirrors TASK-14's framework shape and REUSES its independent black-box CLI
oracle rather than duplicating it, and pairs with REQ-14's ``modify_system``.

#### Steps
1. New `harness/modification_suite.py`: a `ModificationTask` dataclass (`name, cls, tier
   ("easy"|"medium"|"hard"), start_system (dict[filename->code], a small KNOWN-GOOD system
   always with a `main.py` entrypoint following the same single-file CLI contract convention
   as `system_suite.FIRST_SLICE`), mod_sentence, new_checks (list of (argv, stdin,
   expected_substring)), regression_checks (list of (argv, stdin, expected_substring))`.
   Deterministic, no model involved in this module.
2. `run_modification_suite(modify_fn, tasks=None, python_exe=None) -> dict`: for each task,
   write `start_system` onto a fresh isolated temp root, call
   `modify_fn(modules, mod_sentence, root)` (same positional signature as
   `harness.system_builder.modify_system(modules, mod_sentence, root, *, llm=...)` — callers
   pass a partial/wrapper binding `llm` so the suite stays model-agnostic and offline-testable),
   then run the INDEPENDENT black-box CLI oracle against the resulting root for every
   `new_check` AND every `regression_check`. REUSE `harness.system_suite._run_single_check`
   (and transitively `_run_cli`/`_resolve_entry`) rather than duplicating that logic — one
   shared oracle mechanism for both suites. Record per task `{name, cls, tier, applied,
   new_behavior_ok (all new_checks pass), no_regression (all regression_checks still pass),
   accepted (new_behavior_ok AND no_regression)}` — `accepted`/`no_regression` are decided by
   THIS suite's own oracle, never by trusting a `modify_fn`'s self-reported `applied` flag
   (the critical regression-gate honesty property). Aggregate accept-rate + new-behavior-rate +
   no-regression-rate (+ applied-rate) overall and per tier. NEVER raise per task — a
   modify/exec failure records `accepted=False` and the suite continues.
3. Define a FIRST SLICE of 5 `ModificationTask`s across tiers (2 easy / 2 medium / 1 hard):
   easy — sum-CLI + "also print the count"; easy — wordcount-CLI + "also print the char
   count"; medium — C↔F temperature converter + "add Kelvin as a target unit"; medium —
   todo-list (add/list) + "add a remove command"; hard — kv-store (set/get) + "add a delete
   command". Each start_system genuinely correct + checks deterministic (no wall-clock).
4. Tests `tests/test_ext036_modsuite.py` (OFFLINE — no model/network): stub `modify_fn`s that
   (a) correctly apply a change → accepted=True; (b) apply the new behavior but BREAK a
   regression check (while dishonestly self-reporting `applied=True`) → accepted=False (the
   critical regression-gate test, proving the suite's oracle is independent of the thing under
   test); (c) fail to apply → accepted=False, suite continues; (d) a raising modify_fn →
   accepted=False, suite continues; (e) the first-slice registry's shape. Run the FULL
   `python -m pytest tests/ -q` and confirm it stays green.

#### Implements
- [REQ-21] Parity instrument: matching sentence->system MODIFICATION classes (framework +
  first slice + the regression-gate honesty property; live gemma-vs-escalating measurement
  and growing change-class coverage remain open follow-ups)

### [TASK-17] Grow creation suite — 6 more classes (REQ-20)

Owner directive: the parity instrument needs "way way more classes of
development-systems-from-a-sentence." TASK-14/15 proved the framework + made the first 6
sentences contract-precise; this task GROWS the class coverage, doubling `FIRST_SLICE` to 12
tasks (4 easy / 4 medium / 4 hard) across 6 NEW classes not yet represented, following the
EXACT contract-precise pattern TASK-15 proved (single `main.py` entrypoint, exact
argv/stdin invocation, exact stdout format including the trailing newline, `if __name__ ==
"__main__":` required, deterministic checks with no wall-clock dependence).

#### Steps
1. In `harness/system_suite.py`, ADD 6 new `CreationTask`s to `FIRST_SLICE` (append after the
   existing 6, keeping them unchanged): 2 easy (`reverse-lines-cli` — reverses each line of
   stdin; `max-of-stdin-cli` — prints the max of a line of stdin integers), 2 medium
   (`rpn-calc-cli` — a Reverse-Polish-Notation calculator reading one line of tokens;
   `kv-lines-sorted-cli` — parses `key=value` stdin lines and prints them sorted by key, last
   value wins on repeat), 2 hard (`pubsub-cli` — a subscribe/publish event simulator;
   `rate-limiter-cli` — a fixed-window allow/deny limiter over a `request <id>` command
   stream). Each sentence pins the `main.py` entrypoint, the exact invocation (argv and/or a
   precise line-based stdin protocol), the exact stdout format, and the
   `if __name__ == "__main__":` requirement — the sentence IS the spec the independent
   black-box oracle checks against; never leak the checks into the sentence.
2. Do NOT modify `run_creation_suite`/`_run_cli`/`_resolve_entry`/`_run_single_check` (the
   proven oracle mechanism) or the existing 6 `FIRST_SLICE` tasks. Do NOT touch
   `build_system`/`modify_system`/escalation core or `harness/modification_suite.py`.
3. Update `tests/test_ext036_suite.py`: bump `test_first_slice_registry_shape`'s expectations
   to 12 tasks / 4-4-4 tiers. Add reference (known-correct) implementations for each of the 6
   new tasks and a coherence test that runs each through the real `run_creation_suite` oracle,
   asserting `accepted=True` and every check passes — proving each new task's `checks` are
   genuinely determined by its stated contract (not trivially-always-true), mirroring how
   `test_first_slice_actually_runs_offline_with_real_stub_entrypoint` validates `sum-cli`.
4. Run the FULL `python -m pytest tests/ -q` (was 1368) and confirm it stays green at the new
   count. Update `.jarify/EXT-036/index.json`'s `REQ-20` range to the file's grown line count.

#### Implements
- [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence->system CREATION
  classes (doubles the class/tier coverage to 12 tasks across 12 classes; live
  gemma-vs-escalating measurement against the grown suite and further class growth remain
  open follow-ups)

### [TASK-18] Wire /buildsystem to the escalating harness (REQ-13)

MEASURED (TASK-13, commit c182c33): the offline escalation core (`build_system_escalating`)
lifts the hard-tier creation ship-rate from 25% -> 58% (3/12 -> 7/12) by escalating to
Qwen2.5-Coder-7B ONLY when gemma-4-e2b fails to ship. Owner steer 2026-07-03: "use the whole
harness with routing" -- today `harness/cli.py::cmd_buildsystem` still calls plain
`build_system(sentence, subdir, llm=self.llm)` (gemma-alone), so the measured win is NOT yet
live in the product. Wire the CLI to route through `build_system_escalating` whenever
escalation is genuinely CONFIGURED (a model-manager URL is reachable in principle AND the
model registry has MEASURED coverage for the `complex-system-build-specialist` class),
falling back to plain `build_system` with NO behavior change when it is not -- so an
unconfigured/offline environment (e.g. CI, a laptop with no Jetson) never regresses.

#### Steps
1. In `harness/cli.py`, add a small helper `_buildsystem_escalation_config()` that returns
   `(manager_url, fallback_model_id, primary_model_id)` when escalation is CONFIGURED, else
   `None`: load `harness.model_registry.load_registry()`, call
   `registry.lookup_by_class("complex-system-build-specialist")` (the honest, evidence-gated
   lookup already used elsewhere in the registry) and use its first id as
   `fallback_model_id`, `registry.default_model()` as `primary_model_id`, and
   `os.environ.get("JCODE_MODEL_MANAGER_URL", "http://192.168.1.183:8001")` as the manager
   URL (the same LAN-default convention as `harness/model_rewire.py::_manager_base()`). Any
   registry-load failure or an empty `lookup_by_class` result returns `None` (not
   configured) -- never raises.
2. In `harness/cli.py::cmd_buildsystem`, call `_buildsystem_escalation_config()`. When it
   returns a config, build a `swap_fn` via `harness.collaborative_solve._http_swap(manager_url)`
   and call `harness.system_builder.build_system_escalating(sentence, subdir,
   primary_llm=self.llm, fallback_llm=self.llm, swap_fn=swap_fn,
   fallback_model_id=fallback_model_id, primary_model_id=primary_model_id)` (both
   `primary_llm`/`fallback_llm` point at the same `:8000` endpoint client -- the injected
   `swap_fn` re-pointing the Jetson's SERVED model is what makes the second call actually
   run the 7B, mirroring how the TASK-13 measurement runner drives it). When
   `_buildsystem_escalation_config()` returns `None`, call plain
   `build_system(sentence, subdir, llm=self.llm)` exactly as today -- no swap_fn is ever
   constructed on this path.
3. Extend `cmd_buildsystem`'s output to report which model actually shipped the result,
   reading the `model`/`escalated` keys `build_system_escalating` already returns (e.g.
   `"[buildsystem] shipped, DONE via qwen2.5-coder-7b (escalated) -- into <dir>"` vs
   `"... via gemma-4-e2b -- into <dir>"`); when escalation isn't configured, keep today's
   plain (unlabeled) output shape.
4. Do NOT modify `build_system_escalating`/`build_system`/`ModelRegistry`/`_http_swap`
   themselves, and do NOT change `cmd_modifysystem` or any other command -- this task is
   `/buildsystem`'s wiring only.
5. Tests `tests/test_ext036_buildsystem_escalate.py` (OFFLINE -- no network/Jetson; monkeypatch
   `harness.system_builder.build_system_escalating`/`build_system` with recording stubs and
   `harness.cli._buildsystem_escalation_config`/`harness.collaborative_solve._http_swap` with
   canned/stub values, mirroring the stubbing patterns already used across the other
   `tests/test_ext036_*.py` CLI tests): assert (a) when escalation is configured,
   `cmd_buildsystem` calls `build_system_escalating` with the right `primary_llm`/
   `fallback_llm`/`fallback_model_id`/`primary_model_id` and a real swap_fn callable; (b) when
   `_buildsystem_escalation_config()` returns `None` (no specialist registered / disabled), it
   falls back to plain `build_system` and never constructs a swap_fn; (c) the CLI output
   reflects escalated-vs-not and which model shipped; (d) `build_system_escalating` raising or
   an unreachable-manager `swap_fn` never crashes `cmd_buildsystem` (relies on
   `build_system_escalating`'s own never-raise guarantee -- assert `cmd_buildsystem` still
   returns a string). Run the FULL `python -m pytest tests/ -q` and confirm it stays green at
   the new count.

#### Implements
- [REQ-13] Full difficulty spectrum -- easy / medium / hard / highly-complex creation (live
  CLI wiring of the offline escalation core: `/buildsystem` now genuinely routes through
  `build_system_escalating` when a hard-tier specialist is configured, carrying the measured
  25%->58% ship-rate lift into the actual product path, not just the offline test-gated core)

### [TASK-19] Deterministic plan-repair: entrypoint-not-listed (REQ-1)

MEASURED ROOT CAUSE (`.jaros-data/diag_residuals.py`, 2026-07-03): 4 of 5 creation-suite
RESIDUALS (`temp-converter-cli`, `priority-jobqueue-cli`, `rpn-calc-cli`,
`rate-limiter-cli`) fail identically -- gemma's plan lists exactly ONE logic module (e.g.
`calculator.py`/`conversion.py`/`job_queue.py`/`rate_limiter.py`) but sets
`entrypoint: "main.py"` (matching the sentence's pinned entrypoint convention from
TASK-15), and `validate_plan` correctly rejects the plan ("entrypoint not a listed
module"), so 0 modules build and the task is never shipped. gemma clearly INTENDS
`main.py` as the entrypoint -- it just named its single module descriptively rather than
`main.py`. This is a deterministic coherence-REPAIR opportunity (the analog of the
write-tests repair loop, but here the "defect" has exactly one honest, unambiguous fix
rather than needing a re-plan call), not a model reasoning failure.

#### Steps
1. In `harness/system_builder.py` (REQ-1 section, alongside `validate_plan`/`_topo_order`),
   add a deterministic `_repair_plan_entrypoint(plan: dict) -> tuple[dict, str | None]`: if
   `plan["modules"]` is a list of EXACTLY ONE module and `plan["entrypoint"]` is a non-empty
   string that does not match that module's `name`, rename the sole module's `name` (and any
   self-referencing `imports` entry) to the entrypoint filename, so the one module BECOMES
   the entrypoint the sentence asked for. Return `(plan, note)` where `note` is a short
   string (e.g. `"plan-repair: renamed sole module calculator.py -> main.py"`) when a repair
   was made, else `(plan, None)`. Multi-module plans with a mismatched entrypoint are left
   UNTOUCHED (ambiguous which module should host the entrypoint) -- do not add a driver
   module or otherwise guess; a genuinely incoherent multi-module plan must still be
   rejected by `validate_plan` exactly as before. Pure/deterministic, no model call, never
   raises.
2. In `build_system`, call `_repair_plan_entrypoint(plan)` immediately after the plan is
   parsed (`_extract_json`) and BEFORE the `validate_plan(plan)` coherence gate, so a
   single-module/mismatched-entrypoint plan is repaired first and then passes coherence
   validation (and proceeds to build) instead of being rejected. Do not change
   `validate_plan`'s own checks or weaken any other defect it catches.
3. Thread the repair note into the returned result for honesty/traceability: add a
   `plan_repair` field to `_result()` (default `""`), and pass the note through on every
   `build_system` return path reached after the repair call (so it's visible whether the
   build later ships, fails to build, or fails acceptance). Never raises; a plan needing no
   repair returns `plan_repair: ""` unchanged (byte-identical behavior to today).
4. Tests `tests/test_ext036_planrepair.py` (OFFLINE -- canned `llm`, no network, following
   `tests/test_ext036_system_builder.py`'s `_CannedLlm` pattern): (a) a single-module plan
   whose `entrypoint` is NOT among its listed modules is REPAIRED (module renamed to the
   entrypoint) and the build proceeds past coherence validation to ship (not rejected with
   "entrypoint not a listed module"); (b) a plan whose `entrypoint` already matches a listed
   module is UNCHANGED (`plan_repair == ""`, `_repair_plan_entrypoint` is a no-op); (c) a
   MULTI-module plan with a mismatched entrypoint is NOT silently repaired -- it still fails
   `validate_plan`'s coherence check exactly as before (no regression, no wrong guess); (d)
   `build_system` still never raises on a malformed/edge-case plan (empty modules list, non-
   dict module entry, entrypoint that's not a string). Run the FULL `python -m pytest
   tests/ -q` (was 1376) and confirm it stays green at the new count.

#### Implements
- [REQ-1] Planner: sentence -> structured, coherence-validated plan (a deterministic
  plan-repair for the MEASURED single-module/mismatched-entrypoint defect -- fills part of
  the "plan-repair loop... feed back for a coherent re-plan" acceptance criterion; a
  general re-plan-on-defect loop for OTHER defect classes remains open)

### [TASK-20] Grow modification suite — harder change classes (REQ-21)

PRIME-001 ratchet: the `harness/modification_suite.py` `FIRST_SLICE` (TASK-16) has 5 tasks
that are all simple ADD-a-feature edits (append a line, add a target unit, add a
subcommand) -- an eval suite the harness can ace with a straightforward append is too easy
and MUST be made harder to stay an honest, informative parity instrument. Grow it with
change CLASSES that require the model to genuinely UNDERSTAND and PRECISELY EDIT existing
logic (change/replace/tighten), not just append new code at the end.

#### Steps
1. In `harness/modification_suite.py`, ADD 5 new HARDER `ModificationTask`s to
   `FIRST_SLICE` (append after the existing 5, keeping them byte-for-byte unchanged),
   each with a FIXED, genuinely-correct hand-written `start_system` (always a single
   `main.py` following the established single-file CLI convention) across 5 distinct
   harder change classes: (a) BEHAVIOR CHANGE -- a line-sorting CLI that sorts ascending
   is changed to sort DESCENDING; (b) CONSTRAINT/VALIDATION TIGHTENING -- a `key=value`
   store CLI is changed to reject (with an error message) any key longer than 8
   characters while still accepting valid keys; (c) ALGORITHM SWAP -- a running-average
   CLI is changed to compute a running MEDIAN instead; (d) ADD A BRANCH TO EXISTING LOGIC
   -- a `+`/`-` calculator CLI gains `*`/`/` operator support; (e) CROSS-CUTTING EDIT -- a
   multi-command CLI gains an optional `--verbose` flag that adds a log line before every
   command's output, while the default (non-verbose) invocation's output stays
   byte-identical. Each task's `new_checks` verify the new/changed behavior and
   `regression_checks` verify what must NOT break (e.g. still reads all lines / handles
   empty input; valid short keys still accepted; the CLI I/O contract/format unchanged;
   the untouched operators still work; default output is byte-identical to today) --
   deterministic, no wall-clock dependence, REUSING `harness.system_suite._run_single_check`
   via the existing `run_modification_suite` plumbing (do not duplicate or weaken the
   oracle).
2. Every new `start_system` must genuinely, verifiably pass its OWN `regression_checks`
   BEFORE any modification (Tenet 3 -- the regression gate must be honest: a fixture that
   doesn't already satisfy what it claims must never regress is not a valid fixture). Do
   NOT modify `run_modification_suite`/the existing 5 tasks/`harness/system_suite.py`/
   `harness/system_builder.py` -- this task only grows `FIRST_SLICE`.
3. Update `tests/test_ext036_modsuite.py`: bump `test_first_slice_registry_shape`'s
   expected count to 10 (tiers as actually distributed). Extend
   `test_first_slice_tasks_are_internally_coherent`'s reference-implementation map with a
   genuinely correct modification for each of the 5 new tasks (a positive control proving
   each new task's `new_checks` AND `regression_checks` are honestly satisfiable through
   the REAL `run_modification_suite` oracle, not trivially-always-true). Add a dedicated
   regression-gate test for at least one NEW task: a stub `modify_fn` that satisfies the
   new behavior but BREAKS a regression check (while self-reporting `applied=True`) is
   still `accepted=False` -- proving the honesty gate holds on the harder classes too, not
   just the TASK-16 fixture.
4. Run the FULL `python -m pytest tests/ -q` and confirm it stays green at the new count.
   Update `.jarify/EXT-036/index.json`'s `REQ-21` range to the file's grown line count.

#### Implements
- [REQ-21] Parity instrument: matching sentence->system MODIFICATION classes (grows the
  change-class coverage from 5 simple ADD-only tasks to 10 tasks spanning behavior-change,
  constraint-tightening, algorithm-swap, branch-addition, and cross-cutting change
  classes -- the harder, edit-precision-testing classes the requirement calls out; live
  gemma-vs-escalating measurement against the grown suite remains an open follow-up)

### [TASK-21] Deterministic import smoke-gate for modify_system (REQ-14 hardening)

MEASURED BUG (live multi-file-modification probe, 2026-07-03): `modify_system`'s regression
gate (TASK-7) only re-runs the model-derived `baseline_passing` acceptance checks; those
checks can ALL exercise only a subset of modules. Replicated case: a 2-file system
(`statlib.py` exporting `mean`, `main.py` doing `from statlib import mean`) modified by "add
a max subcommand" produced a `main.py` with `from statlib import max` (a name `statlib`
never exports) -- `main.py` no longer imports AT ALL -- yet `modify_system` returned
`applied=True, regressed=[]`, because both surviving `baseline_passing` checks only did
`import statlib; assert statlib.mean(...)` and never imported `main` (the one check that did
import `main` had already failed on the ORIGINAL system, so it was excluded from
`baseline_passing`). A modification that breaks the whole system's import was silently
accepted as "no regression" -- a false honesty signal. Fix with a DETERMINISTIC,
model-independent import smoke-gate, additive to (never replacing) the existing
model-derived-check regression gate.

#### Steps
1. In `harness/system_builder.py::modify_system`, right after the current system is
   assembled onto `root` and BEFORE the modules are regenerated (around where
   `baseline_passing` is computed), add a deterministic helper (e.g.
   `_importable_modules(modules, root, python_exe=None) -> set[str]`) that, for each module
   name (e.g. `statlib.py`, `main.py`), runs `[sys.executable, "-c", "import <stem>"]` with
   `cwd=root`, a short timeout (e.g. 15s), `capture_output=True`, and treats the module as
   importable iff `returncode == 0`. Any subprocess error (`OSError`, timeout, etc.) counts
   that module as NOT importable -- never raises. Compute `baseline_importable =
   _importable_modules(modules, root)` (the set of module names that import cleanly BEFORE
   any modification).
2. In the regression-gate step (alongside the existing `regressed` computation, after the
   modified modules are assembled onto `root`), re-run `_importable_modules` on the
   POST-MODIFICATION `root` and compute `import_regressed = {name for name in
   baseline_importable if name not in post_mod_importable}` -- modules that imported cleanly
   at baseline but no longer import after the change. A module NOT importable at baseline
   must never appear in `import_regressed` even if it's still broken after (only
   baseline-importable-to-now-broken counts).
3. Trigger the EXISTING revert path (revert `changed_names` to `pre_mod` on disk via the
   same jailed-write mechanism already used, and in the returned `modules` dict, set
   `applied=False`) when EITHER the existing behavioral `regressed` is non-empty OR
   `import_regressed` is non-empty. Merge `import_regressed` into the reported `regressed`
   list so the returned `note` honestly reflects an import-breaking modification (e.g.
   include "import-broken: <names>" in the note text). Keep the returned dict's existing keys
   (`modules`, `applied`, `regressed`, `new_behavior_ok`, `note`) backward-compatible --
   additive fields only.
4. Do not weaken or remove the existing model-derived-check regression logic (TASK-7); this
   is purely additive. `modify_system` must still never raise -- wrap all subprocess calls in
   `try/except`.
5. Tests (add to `tests/test_ext036_modify.py`, OFFLINE -- canned/fake llm, no live model,
   mirroring the existing fake-llm injection pattern in that file): (a) REPRODUCE THE BUG -- a
   2-file system (`statlib.py`/`main.py`) where an injected fake llm regenerates `main.py`
   with a broken `from statlib import max` import; assert `modify_system` now returns
   `applied=False`, `main.py` is REVERTED to its original content both in the returned
   `modules` dict and on disk, and the import break is reflected in `regressed`/`note`; (b) NO
   FALSE REVERT -- a good modification that keeps all imports working still returns
   `applied=True` (add a 2-file happy-path test if none already covers one); (c) a module NOT
   importable at BASELINE (a deliberately broken start system) does not, by itself, cause a
   spurious revert when it remains not-importable after modification. Run the FULL `python -m
   pytest tests/ -q` synchronously in the foreground and confirm it stays green at the new
   count.

#### Implements
- [REQ-14] Modification from a sentence — evolve an existing system (hardens the
  regression gate with a deterministic, model-independent import smoke-check so a modification
  that breaks the whole system's import can no longer slip past `applied=True` just because the
  surviving model-derived checks happened not to exercise the broken module)

### [TASK-22] Grow modification suite — multi-file modification tier (REQ-21)

`FIRST_SLICE` is entirely single-file (`main.py`-only) and gemma aces it 10/10 (saturated per
PRIME-001's ratchet). `run_modification_suite` already writes EVERY file in a task's
`start_system` onto the temp root and drives an independent black-box CLI oracle against the
resolved `main.py` entrypoint, so multi-file start systems already work at the framework
level — this task is mostly DATA (a new `MULTIFILE_SLICE`) plus a docstring correction.

#### Steps
1. In `harness/modification_suite.py`, correct the `ModificationTask` and module docstrings
   (previously implying a single-file-only convention) to note `start_system` MAY contain
   multiple modules, always with `main.py` as the CLI entrypoint.
2. Add `MULTIFILE_SLICE: list[ModificationTask]` (inside the existing `#EXT-036-REQ-21`
   traceability span) with 5 hand-verified tasks: 3 on a 2-file `statlib.py`+`main.py`
   stats-cli base (`mf-add-median-subcmd`, `mf-add-total-subcmd`, `mf-empty-guard`) and 2 on
   a 3-file `mathlib.py`+`formatter.py`+`main.py` calculator base (`mf3-add-mul-op`,
   `mf3-change-format`). Each `start_system` genuinely passes its own `regression_checks`
   unmodified, and a correct implementation of its `mod_sentence` satisfies its `new_checks`
   (Tenet 3). Fix two fixture defects caught by the suite's own no-op-rejection test: give
   `mf-add-median-subcmd` input values where the median genuinely differs from the mean
   (the mod sentence's literal example numbers coincidentally have median == mean), and give
   `mf-empty-guard` a `statlib.py` variant without the pre-existing empty-input ternary guard
   (otherwise the task's premise — "the mean path currently crashes on empty input" — is
   already false against the unmodified fixture).
3. Add `ALL_TASKS = FIRST_SLICE + MULTIFILE_SLICE`; keep `run_modification_suite`'s default
   `tasks=FIRST_SLICE` unchanged (backward-compatible) — callers opt into the fuller set by
   passing `ALL_TASKS` or `MULTIFILE_SLICE`.
4. Add tests to `tests/test_ext036_modsuite.py`: (a) TENET-3 fixture coherence — for every
   task in `MULTIFILE_SLICE`, write its `start_system` to a temp dir and assert the
   unmodified system passes all its `regression_checks` (reusing
   `harness.system_suite._run_single_check`); (b) `run_modification_suite` accepts
   `MULTIFILE_SLICE` with a no-op `modify_fn` and rejects (`accepted=False`) every task,
   proving the oracle isn't trivially passing; (c) every `MULTIFILE_SLICE` task has a
   multi-file `start_system` (`len(start_system) >= 2`) with a `main.py` key; (d) a
   hand-verified correct `modify_fn` for each of the 5 new tasks is `accepted=True` through
   the real `run_modification_suite` oracle (proves the new_checks are honestly satisfiable,
   not just well-shaped).
5. Run the FULL `python -m pytest tests/ -q` and confirm it stays green at the new count.
   Update `.jarify/EXT-036/index.json`'s `REQ-21` range(s) to the grown file's line count.

#### Implements
- [REQ-21] Parity instrument: matching sentence->system MODIFICATION classes (grows the
  change-class coverage with a MULTI-FILE modification tier — editing a helper module, or
  editing `main.py`'s wiring to a helper module, while a resolved-entrypoint CLI oracle checks
  the whole system — the measured next frontier now `FIRST_SLICE` is single-file-saturated;
  live gemma-vs-escalating measurement against the grown suite remains an open follow-up)

### [TASK-23] Deterministic server/HTTP acceptance oracle for REAL web-service builds (REQ-22)

MEASURED gap (owner directive 2026-07-03): `harness/system_builder.py::build_system`'s
acceptance checklist runs each check via `_run_check`, which executes `python <entry>.py`
and inspects STDOUT; a FastAPI/Flask service has no stdout (it blocks serving HTTP) so its
checks get filtered out and the build silently falls back to `_smoke_checklist`
(import-only), which passes the instant the module imports without ever starting the server
or hitting an endpoint — a Tenet-3 hollow pass measured on a genuinely-working gemma-built
FastAPI service. This task builds a NEW deterministic, two-plane execution-plane module
`harness/server_oracle.py` that actually starts the detected app and HTTP-checks it.
Explicitly scoped to the new module + its tests only — wiring it into
`build_system`/`cli.py`/`system_suite.py` is a follow-up task, not done here.

#### Steps
1. `harness/server_oracle.py::detect_web_service(modules: dict) -> dict | None` — scans
   module SOURCES ({filename: code}) with regex/best-effort parsing for a FastAPI/Starlette
   app object (`= FastAPI(`/`= Starlette(` plus a `from fastapi`/`from starlette` import) or
   a Flask app object (`= Flask(` plus a `from flask` import); returns `{"kind":
   "asgi"|"wsgi", "entry": <module stem>, "app": <attr name>}` for the first match, else
   None. Never raises.
2. `harness/server_oracle.py::serve_and_check(root, service, http_checks, *,
   startup_timeout=15, request_timeout=5) -> dict` — picks a FREE ephemeral localhost port
   (bind :0, read the port, close), launches the detected app as a real subprocess (`python
   -m uvicorn <entry>:<app> --port <port>` for ASGI, `python -m flask --app <entry>:<app>
   run --port <port>` for WSGI) with `cwd=root`, polls the port until it accepts a TCP
   connection (bounded by `startup_timeout`, bails early if the process already died), then
   runs each `http_check` (method/path/optional status/json_contains/body_contains) as a
   real HTTP request via `urllib` and grades it. ALWAYS tears the server process tree down
   in a `finally` block (mirrors `.jaros-data/tools/shell_exec_tool.py::_kill_tree` —
   `taskkill /F /T /PID` on Windows, `killpg` on POSIX). Returns `{"ok": bool, "results":
   [...], "note": str}`; never raises — any failure (bad input, never-binds server,
   malformed check) is reported honestly as `ok=False` with a diagnostic note.
3. Self-contained, no model call, no dependency on `system_builder`/`cli`/`system_suite` —
   purely an importable execution-plane utility for now.
4. Tests `tests/test_ext036_server_oracle.py` (OFFLINE beyond 127.0.0.1; fastapi/uvicorn/
   flask ARE installed, guarded with `pytest.importorskip`): a real FastAPI fixture app (GET
   /health, GET /add) — detect + serve_and_check both pass with genuine HTTP responses; a
   real Flask fixture app — detect + serve_and_check pass; a NEGATIVE check expecting a
   wrong value genuinely fails (proves the oracle isn't a trivial pass); a broken
   (import-crashing) app fails within the timeout without hanging and leaves no orphan
   process; `detect_web_service` returns None for a plain stdin/stdout CLI;
   `serve_and_check`/`detect_web_service` never raise on garbage input (bad root, non-dict
   service, non-list checks, malformed check entries). Run the FULL `python -m pytest
   tests/ -q` and confirm it stays green at the new count (was 1489 passed / 1 skipped).

#### Implements
- [REQ-22] Server/HTTP acceptance oracle for REAL web-service builds (the oracle module
  itself, proven standalone; wiring into `build_system` remains an explicit open follow-up)

### [TASK-24] Grow creation suite — 8 harder + more-diverse classes (REQ-20)

Owner directive (2026-07-03): "make it harder, build more classes." The creation parity
instrument is gemma's WEAK half (~83% gemma / ~92% escalating) so it has the most headroom and
must keep getting harder to stay informative (PRIME-001 difficulty ratchet). TASK-17 grew
`FIRST_SLICE` to 12; this task adds a SEPARATE `HARDER_SLICE` of 8 tougher, more diverse classes
(medium/hard/highly-complex) following the EXACT contract-precise pattern (single `main.py`
entrypoint, exact argv/stdin invocation, exact stdout format, `if __name__ == "__main__":`
required, deterministic checks with no wall-clock dependence), and exposes `ALL_CREATION_TASKS =
FIRST_SLICE + HARDER_SLICE` — leaving `run_creation_suite`'s default (`FIRST_SLICE`) unchanged.

#### Steps
1. In `harness/system_suite.py` (inside the existing `#EXT-036-REQ-20` span), add
   `HARDER_SLICE: list[CreationTask]` with 8 new contract-precise classes: `json-config-
   validator-cli` (medium), `graph-bfs-shortest-path-cli` (hard), `bracket-balance-cli`
   (medium), `run-length-codec-cli` (medium), `csv-column-aggregator-cli` (hard),
   `traffic-light-sequencer-cli` (medium), `lru-cache-cli` (highly-complex),
   `matrix-transpose-cli` (hard). Widen `CreationTask.tier`'s docstring to note the
   `"highly-complex"` tier. Add `ALL_CREATION_TASKS = FIRST_SLICE + HARDER_SLICE`. Do NOT modify
   `run_creation_suite`/`_run_cli`/`_resolve_entry`/`_run_single_check` or the existing
   `FIRST_SLICE` tasks; keep `run_creation_suite`'s default `tasks=FIRST_SLICE` (backward-compatible).
2. Update `tests/test_ext036_suite.py`: add a `HARDER_SLICE` registry-shape test, an
   `ALL_CREATION_TASKS == FIRST_SLICE + HARDER_SLICE` composition test, and an internal-coherence
   test that runs a known-correct REFERENCE implementation of each of the 8 tasks through the real
   `run_creation_suite` oracle, asserting `accepted=True` — proving each contract is genuinely
   satisfiable AND non-trivial (a no-op program is separately confirmed to score 0/8). This caught
   and fixed a real unsatisfiable-contract bug in `lru-cache-cli` (missing `<capacity>` argv) before
   finalizing (Tenet 3).
3. Run the FULL `python -m pytest tests/ -q` and confirm it stays green (1503 passed / 1 skipped).
   Update `.jarify/EXT-036/index.json`'s `REQ-20` range to the grown file's `#EXT-036-REQ-20`
   markers (41–628).

#### Implements
- [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence->system CREATION
  classes (adds `HARDER_SLICE` — 8 harder/more-diverse classes incl. a highly-complex LRU cache —
  and `ALL_CREATION_TASKS`, growing coverage to 20 tasks / 17 classes; live gemma-vs-escalating
  measurement against the grown suite remains an open follow-up)

### [TASK-25] Wire server/HTTP acceptance oracle into build_system (REQ-22)

MEASURED gap (owner directive 2026-07-03, TASK-23's explicit follow-up): `harness/system_builder.py::build_system`'s
acceptance checklist derives checks and runs each via the stdout-based `_run_check`; a FastAPI/Flask service has no
stdout, so every proposed check for it is filtered out and the build silently falls back to the import-only
`_smoke_checklist`, reporting `done=True` the instant the module imports without ever hitting an endpoint — a
Tenet-3 hollow pass on exactly the class of system this product most needs to nail. `harness/server_oracle.py`
(TASK-23) already builds + proves the real HTTP-verification primitives standalone (`detect_web_service`,
`serve_and_check`); this task wires them into `build_system` so a detected web service is HONESTLY HTTP-verified.

#### Steps
1. In `harness/system_builder.py::build_system`, immediately after ASSEMBLE (before the existing stdout-based
   acceptance derivation), call `detect_web_service(built)` (lazy-imported from `harness/server_oracle.py`, never
   raises). If it detects a service:
   a. Derive `http_checks` for it via a NEW model round-trip (`_derive_http_checklist`/`HTTP_CHECKLIST_PROMPT`)
      that proposes HTTP endpoint checks from the SPEC (the prompt already describes the endpoints + expected
      responses) — each `{"method","path","status"(opt),"json_contains"(opt),"body_contains"(opt)}` —
      deterministically FILTERED to well-formed http-check dicts by a new `_is_http_check` gate (mirrors
      `_is_executable_check`'s parse-and-assert discipline: a check must assert at least one of
      status/json_contains/body_contains to survive — an assertion-free check is dropped as a vacuous pass, same
      as a prose/"conceptual" stdout check). Guarded: never raises, returns `[]` on any model/parse failure.
   b. If `http_checks` is non-empty, run `serve_and_check(root, service, http_checks)` and GATE `done` on its
      `ok` field — folding the per-check pass/fail into the returned `note`/`unmet` for transparency (which
      endpoints passed/failed).
   c. HONESTY (Tenet 3): if `http_checks` is empty (no valid checks derivable), return `done=False` with an
      explicit "not HTTP-verified" note/unmet entry — `shipped=True` (the app assembled + imports fine) but
      `done` is never hollow. A detected web service NEVER falls through to the stdout/smoke acceptance path
      below this new block, regardless of the http_checks/serve_and_check outcome.
2. Non-web-service builds are COMPLETELY UNCHANGED: `detect_web_service` returns `None` for a plain CLI/library
   system, so control falls through to the existing stdout-based `_derive_acceptance_checklist`/`_run_check`
   path exactly as before (byte-identical behavior; no change to `_repair_system`/TASK-5's repair loop, which
   stays scoped to the non-web stdout path). Do not modify `harness/server_oracle.py`, `harness/cli.py`, or
   `harness/system_suite.py` — this task is `build_system`'s wiring only.
3. `build_system` must NEVER raise (mirrors every existing stage); the `build_system_escalating` wrapper
   (TASK-13) needs no changes — it composes `build_system` unmodified.
4. Tests (added to `tests/test_ext036_system_builder.py`, OFFLINE via an injected fake `llm` mirroring the
   existing `_CannedLlm` pattern; `fastapi`/`uvicorn` ARE installed, guarded with `pytest.importorskip`): (a)
   POSITIVE — a fake llm plans a single-file FastAPI service, writes a CORRECT app (`app=FastAPI()`, GET
   /health -> `{"status": "ok"}`), and derives an http check for `/health` expecting
   `json_contains={"status":"ok"}` -> `build_system` detects the service, runs `serve_and_check`, and returns
   `done=True`; (b) CONTROL — the SAME flow with a BROKEN app (`/health` returns `{"status":"bad"}`) ->
   `done=False` (proves the pass above is real, not coincidental); (c) HONESTY — a fake llm returns a FastAPI app
   but NO derivable `http_checks` -> `done=False` with the "not HTTP-verified" note (never a hollow `done=True`);
   (d) REGRESSION — the pre-existing non-web `_CannedLlm` fixture's full-pipeline test still returns the exact
   same `done=True`/`shipped=True`/`unmet=[]`, and the new HTTP-checklist prompt is never even issued for it. Run
   the FULL `python -m pytest tests/ -q` synchronously in the foreground and confirm it stays green at the new
   count (was 1503 passed / 1 skipped). Verify no orphaned uvicorn processes survive the run.

#### Implements
- [REQ-22] Server/HTTP acceptance oracle for REAL web-service builds (wires the standalone TASK-23 oracle into
  `build_system` so a detected web service is HONESTLY HTTP-verified — closing the measured hollow-pass gap;
  `done=True` on a web-service build now REQUIRES a real `serve_and_check` pass)

### [TASK-26] Long-horizon build coherence instrument — minimal first version (REQ-23)

PRIME-001 intent capability (g), the LONG-HORIZON BUILD COHERENCE instrument, is the north-star measurement: the
creation suite (REQ-20) and modification suite (REQ-21) each measure a SINGLE-behavior prompt end to end; neither
measures whether a build stays ALIGNED across a LARGE, MULTI-REQUIREMENT ask without drift. Build the MINIMAL
first version of that instrument — deterministic + independent-oracle-graded, starting at minute-scale — before
wiring the full governed decompose->task->alignment-gate loop that would LIFT the number (an explicit follow-up
capstone, not this task).

#### Steps
1. New `harness/coherence_suite.py` (mirroring `harness/system_suite.py`'s structure/oracle discipline): a
   `CoherenceTask` dataclass (`name`, `tier`, `prompt` — ONE contract-precise sentence/paragraph describing a
   system with N DISTINCT requirements, `requirements` — a list of `(req_id, argv, stdin, expected_substring)`
   tuples, each an INDEPENDENT black-box CLI check for exactly ONE requirement). REUSE
   `harness.system_suite._run_cli`/`_resolve_entry` (the same proven subprocess-execution/entrypoint-resolution
   primitives REQ-20/21 already built) rather than duplicating that logic; do NOT modify `system_suite.py`.
2. `run_coherence_suite(build_fn, tasks=None, python_exe=None) -> dict`: for each task, build via
   `build_fn(prompt, root)` (same positional shape as `build_system(sentence, root, llm=...)` — callers pass a
   partial binding `llm`), then run EVERY requirement's independent check against the built entrypoint. Record
   per task `requirements_total`, `requirements_satisfied` (count of checks that pass), `coherence =
   satisfied/total`, `all_satisfied` (bool), and `wall_seconds` (the build's measured duration — reported only,
   never a correctness dependency). Aggregate mean coherence + fully-coherent rate, overall and per tier. NEVER
   raises: a build/exec failure records that task's honest `requirements_satisfied=0` and the suite continues.
3. Define a FIRST_SLICE of 2-3 minute-scale `CoherenceTask`s (4-5 requirements each) across tiers, each
   contract-precise (pins a single `main.py` entrypoint, exact argv/stdin invocation, exact stdout format, `if
   __name__ == "__main__":` required) and INTERNALLY COHERENT (Tenet 3): a correct reference implementation must
   satisfy ALL its requirements.
4. Tests `tests/test_ext036_coherence.py` (OFFLINE — no live model, no network): for each FIRST_SLICE task, a
   known-correct reference implementation (stub `build_fn` writing it) run through `run_coherence_suite` asserts
   `all_satisfied=True`/`coherence=1.0`; a DELIBERATELY PARTIAL implementation (satisfies only k of N
   requirements, with the unmet ones genuinely wrong) scores `coherence = k/N` EXACTLY, proving the instrument
   measures per-requirement coverage (the drift signal), not all-or-nothing; a no-op `build_fn` (writes nothing)
   scores `coherence=0.0` for every task (no trivial pass); aggregate shape is well-formed (including an empty
   task list and a mixed fully-coherent/zero-coherent pair); a raising/non-dict-returning `build_fn` never aborts
   the suite. Run the FULL `python -m pytest tests/ -q` synchronously in the foreground and confirm it stays
   green at the new count.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (the minimal, deterministic + independent-oracle-graded
  measurement instrument itself, proven internally coherent on a first minute-scale slice; wiring the governed
  decompose->task->alignment-gate loop that LIFTS the coherence number, and a live gemma-vs-escalating
  measurement run, remain explicit open follow-ups)

### [TASK-27] Governed build path — decompose->build->independently-verify->re-ground-repair (REQ-23)

TASK-26 built the INSTRUMENT that measures long-horizon build coherence honestly (a MEASURED 10/11 = 0.91 on an
11-requirement kvdb-cli, with `build_system` silently dropping `incr` and its own self-derived checklist sharing
the same blind spot, reporting `done=True` anyway). This task builds the GOVERNED build path that LIFTS the
coherence number — an explicit, INDEPENDENTLY-verified requirement list so no requirement is silently dropped
from code OR acceptance, realizing PRIME-001 intent capability (g).

#### Steps
1. Add `harness/system_builder.py::build_system_governed(prompt, root, *, llm=None, max_repair=3) -> dict` (a
   NEW function; `build_system`'s existing behavior/signature is UNCHANGED). Pipeline: (a) DECOMPOSE — one
   model call enumerates the DISTINCT requirements from the prompt as `[{req_id, description, check}]`, each
   `check` an executable acceptance for that ONE requirement (deterministically filtered to real assertions via
   `_is_executable_check`, de-duped) — this list is the SPEC OF RECORD, independent of whatever
   `build_system`'s own checklist later contains; (b) BUILD via the existing, unmodified `build_system` pipeline
   (plan -> topo-build -> assemble); (c) VERIFY EACH enumerated requirement's check against the assembled system
   (reusing `_run_check`), recording the UNMET set; (d) RE-GROUND + REPAIR — for each unmet requirement, a
   repair call feeds the model the FULL requirement list (not just the failing one) + the current module
   sources, asking it to ADD/fix that requirement WITHOUT removing already-working behavior; re-assemble;
   RE-VERIFY ALL requirements so a repair that re-drops a different requirement is caught (mirrors TASK-5's
   `_repair_system` non-degrading guard — a regressing round is REVERTED, best-seen `(built, unmet)` tracked),
   bounded to `max_repair` rounds; (e) DONE = ALL enumerated requirements independently verified — NEVER
   `build_system`'s own self-checklist. Returns `{modules, shipped, done, requirements_total, requirements_met,
   unmet: [...], note, rounds}`. NEVER raises. Reuses `_call`, `_derive_acceptance_checklist`'s executable-check
   filter (`_is_executable_check`), `_run_check`/`_run_check_verbose`, `syntax_ok`, and the jailed-write/assemble
   patterns wherever possible — no duplicated oracle logic.
2. Tests (`tests/test_ext036_system_builder.py`, OFFLINE — a fake llm mirroring the `_CannedLlm` pattern, no live
   model): (a) THE CORE LIFT TEST — a fake llm whose first (ungoverned) build genuinely drops one of N
   independently-decomposed requirements (mirroring the measured `incr`-dropping defect at small scale) while
   `build_system`'s own narrow checklist is fooled (still ships+dones); `build_system_governed` reaches
   `requirements_met == N`/`done=True` via its re-ground repair round — proving the LIFT from (N-1)/N to N/N;
   (b) ANTI-REGRESSION — a repair round that fixes the unmet requirement but silently BREAKS a different,
   previously-met one is REJECTED (reverted), the met-count never decreases, and `done` reflects the true
   independently-verified state; (c) HONESTY — when the repair budget is exhausted with a requirement still
   unmet, `done=False` with the unmet requirement listed, never a false `done=True`; (d) CONFIRM `build_system`'s
   existing tests stay byte-identical (this is an additive, new function only). Run the FULL
   `python -m pytest tests/ -q` synchronously in the foreground and confirm it stays green at the new count.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (the GOVERNED build path — decompose -> build ->
  independently-verify-every-requirement -> re-ground-repair — that LIFTS the coherence number the TASK-26
  instrument measures; a live gemma-vs-escalating measurement run of `build_system` vs `build_system_governed`
  against a grown, harder `FIRST_SLICE`, and wiring `build_system_governed` into the `/buildsystem` CLI command,
  remain explicit open follow-ups)

### [TASK-28] Fix build_system_governed's live-caught defects — parser, black-box checks, no-regress floor (REQ-23)

A LIVE gemma diagnostic (`.jaros-data/diag_decompose.py`, run before fixing) caught `build_system_governed`
(TASK-27) LIVE-BROKE: 0 requirements decomposed -> 0/11, WORSE than plain `build_system`'s 10/11. Root cause,
confirmed from the raw model output, is THREE defects: (A) gemma emits the decompose list as ONE JSON ARRAY PER
LINE (`[{"req_id":"R1",...}]` then `[{"req_id":"R2",...}]` on separate lines), which the naive
single-outermost-bracket extractor cannot parse, silently yielding 0 requirements; (B) gemma's per-requirement
`check` assumes an imagined import-and-assert-class API (`import main; main.KeyValueStore().set(...)`) that never
matches the ACTUAL built system (a stdin-driven CLI, `python main.py`), so even a parsed check errors against the
real interface and every requirement is falsely "unmet"; (C) `build_system_governed` must never do worse than
plain `build_system` — a 0-requirement decompose must degrade gracefully to `build_system`'s own result, never a
hollow 0/N regression.

#### Steps
1. In `harness/system_builder.py`, add `_extract_requirements_json(raw: str) -> list`: try the single COMBINED
   JSON array/object case first (back-compat), then fall back to a line-by-line scan collecting every parseable
   JSON array or bare object — handling one-array-per-line, multiple arrays, or bare JSONL objects alike. Wire it
   into `_decompose_requirements` in place of the old single-outermost-bracket `_extract_json(raw, "[", "]")` call.
2. Change `GOVERNED_DECOMPOSE_PROMPT` to tell the model the system is run as `python main.py` reading commands
   from STDIN, and to emit each requirement's check as a BLACK-BOX `{"argv": [...], "stdin": "...", "expect":
   "<substring>"}` object instead of standalone import-and-assert Python code. Add
   `_is_blackbox_requirement_check` (validates `argv` is a list of strings, `stdin` is a string, `expect` is a
   non-empty string) and update `_dedup_requirements` to filter/de-dup on this shape instead of
   `_is_executable_check`. Update `GOVERNED_REPAIR_PROMPT` and `_repair_module_for_requirement` to describe the
   unmet requirement's black-box check (argv/stdin/expect) instead of Python check code.
3. Add `_verify_requirement(root, plan, req, python_exe=None) -> tuple[bool, str]`: verifies ONE decomposed
   requirement via the PROVEN black-box CLI oracle, reusing `harness.system_suite._run_cli`/`_resolve_entry`
   (resolving the entrypoint from `plan`, falling back to `root/main.py`) rather than an imagined class API. Wire
   it into `build_system_governed`'s `_verify_all`/repair-loop verification calls in place of
   `_run_check`/`_run_check_verbose`.
4. In `build_system_governed`, ALWAYS run the underlying `build_system(spec, root, llm=llm)` pipeline — even when
   `_decompose_requirements` yields nothing — so a decompose failure degrades to `build_system`'s own
   `shipped`/`done`/`modules` result (the NO-REGRESS FLOOR) instead of returning early with a hollow
   0-requirement/0-module result. Add a defensive final check ensuring the returned module set is never smaller
   than `build_system`'s own. Do not modify `build_system` itself or its return shape.
5. Update `tests/test_ext036_system_builder.py`: rewrite the governed-path fixtures
   (`SPEC_GOV`/`GOVERNED_DECOMPOSE_JSON`/`GOV_PLAN_JSON`/`MAIN_MISSING_MUL`/`MAIN_WITH_MUL`/`MAIN_MUL_DROPS_SUB`)
   to a real stdin-driven CLI with black-box (argv/stdin/expect) checks; adapt the existing lift/anti-regression/
   honesty tests to verify via `_verify_requirement` against the actual built CLI; add tests proving (a)
   `_decompose_requirements` parses the ONE-ARRAY-PER-LINE format into ALL N requirements, (b) a single combined
   array still works (back-compat), (c) an old imagined-class `check` shape is correctly dropped by the black-box
   filter, and (d) an empty/garbage decompose falls back to `build_system`'s own shipped/done result (never a
   degenerate 0-module regression) when `build_system` itself ships. Run the FULL `python -m pytest tests/ -q`
   synchronously in the foreground and confirm it stays green at the new count.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (fixes the GOVERNED build path's THREE live-caught defects — a
  robust decompose parser, black-box argv/stdin/expect requirement checks matching the system's real CLI
  interface instead of an imagined class API, and a no-regress floor that falls back to `build_system`'s own
  result — so the mechanism genuinely LIFTS live coherence instead of regressing it; a live gemma-vs-escalating
  re-measurement after this fix, and wiring `build_system_governed` into the `/buildsystem` CLI command, remain
  open)

### [TASK-29] Make build_system_governed's NO-REGRESS FLOOR actually hold end to end (REQ-23)

A LIVE measurement (an 11-requirement kvdb-cli) caught a safety-critical gap TASK-28's defect-(C) floor did not
actually close: `build_system` (single-pass) satisfies 10/11 behavioral requirements, but
`build_system_governed`'s re-ground REPAIR LOOP — chasing its own unmet requirements (incr/keys) — DAMAGES
previously-working behavior (clear/usage broke), ending at 8/11 on an independent behavioral check: a genuine
regression BELOW single-pass. The existing floor only falls back to `build_system` when decompose yields ZERO
requirements; it never compared the governed repair loop's FINAL verified quality against `build_system`'s own
initial output, so a repaired-but-worse system could ship.

#### Steps
1. In `harness/system_builder.py::build_system_governed`, right after ASSEMBLE (before any governed repair
   round runs), capture `build_system`'s own INITIAL output as an explicit BASELINE: its modules (already
   assembled on `root`) plus their verified count against the SAME independently-decomposed requirement checks
   (`_verify_requirement`) — `baseline_built`/`baseline_unmet_ids`/`baseline_met`.
2. After the existing re-ground repair loop finishes (regardless of how it ended — done, budget-exhausted, or
   aborted by an exception mid-round), independently RE-VERIFY the actual CURRENT on-disk state FRESH (never
   trust the loop's own in-memory bookkeeping, which can go stale if a round aborts mid-way after some of its
   writes already landed on disk) — `governed_met`.
3. If `governed_met < baseline_met` (repair made it WORSE) OR the final state fails to re-verify at all, REVERT:
   re-assemble the baseline's modules back onto `root` (undoing whatever the repair loop left on disk) and
   return the baseline's own modules/shipped/done/`requirements_met`, with an honest note that governed repair
   did not improve on `build_system` so the single-pass result was kept (no-regress floor).
4. Keep the existing TASK-28 empty-decompose fallback and the round-level non-degrading guard untouched
   (defense-in-depth, not a replacement) — this is an ADDITIONAL, explicit, independently-re-verified final
   guarantee layered on top. Keep NEVER-RAISE.
5. Update `tests/test_ext036_system_builder.py`: add a dedicated fake-llm floor test where the initial build
   satisfies K requirements and the repair round genuinely ends up satisfying FEWER than K (including a
   round aborted mid-way by a simulated model/network failure, so the round's own end-of-round check never
   runs) — assert `build_system_governed` returns the BASELINE (K met), not the regressed result, and that the
   returned `main.py` on disk is the baseline's (re-verified by running it for real). Keep the existing lift
   test, the round-level anti-regression test, the empty-decompose fallback test, the never-raises test, and
   the `build_system`-unchanged confirmation. Run the FULL `python -m pytest tests/ -q` synchronously in the
   foreground and confirm it stays green at the new count.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (the NO-REGRESS FLOOR now actually holds end to end: an
  explicit baseline captured before repair, and an independent final re-verification of the ACTUAL on-disk
  state — never stale in-memory bookkeeping — guarantee `build_system_governed` is always
  `max(baseline, governed)` on the independently-decomposed requirement set, reverting to `build_system`'s own
  single-pass result with a disk re-sync whenever repair ends up worse. Honest scope: this does not fix
  decompose-completeness blind spots — a requirement decompose never enumerates at all remains invisible to
  this check set — it only guarantees governed never regresses below build_system on the requirements it does
  check. A live gemma re-measurement against the kvdb-cli confirming the floor holds live remains an explicit
  follow-up.)

### [TASK-30] Harden the coherence instrument's task slice with a HARD_SLICE (REQ-23)

MEASURED: `harness/coherence_suite.py`'s `FIRST_SLICE` (stats-cli 4 reqs, text-tools-cli 5, ledger-cli 5)
scored `build_system` at coherence=1.00 (saturated) — a separately-probed 11-requirement interdependent
kvdb-cli broke it (single-pass 10/11), showing FIRST_SLICE alone had stopped being discriminating. Add HARD,
MANY-requirement, INTERDEPENDENT tasks to the slice — including the kvdb-cli that already discriminates — so
the instrument keeps measuring genuine drift instead of floor/ceiling-ing out.

#### Steps
1. In `harness/coherence_suite.py`, add a `HARD_SLICE: list[CoherenceTask]` right after `FIRST_SLICE`, inside
   the `#EXT-036-REQ-23` span, with 2 "highly-complex"-tier tasks: `kvdb-cli` (11 requirements: set/get/
   get-missing/delete/exists-yes/exists-no/count/keys/incr/clear/usage, an in-memory stdin-driven key-value
   store) and `taskmgr-cli` (11 requirements: add/add-increments-id/done/done-missing/list-shows-status/
   list-empty/remove/remove-missing/count-after-remove/pending-count/usage, an in-memory stdin-driven task
   list) — a DIFFERENT domain, also interdependent (later commands' checks depend on state built up by earlier
   commands in the same stdin stream). Each prompt is contract-precise (single `main.py` entrypoint, exact
   stdin/argv invocation, exact stdout format, `if __name__ == "__main__":` required), following the same
   convention `FIRST_SLICE`/`harness.system_suite.FIRST_SLICE` already prove.
2. Expose `ALL_COHERENCE_TASKS = FIRST_SLICE + HARD_SLICE`. Do NOT change `run_coherence_suite`'s own default
   (stays `FIRST_SLICE`) — backward compatible with existing callers/tests.
3. TENET-3 (mandatory): for every `HARD_SLICE` task, write a correct REFERENCE `main.py` in the test module and
   prove via `run_coherence_suite` that it scores `all_satisfied=True`/`coherence=1.0` (every requirement is
   genuinely satisfiable by a correct program), that a PARTIAL implementation scores exactly `k/N`, and that a
   no-op scores `0.0`.
4. Tests (`tests/test_ext036_coherence.py`): each `HARD_SLICE` task's reference scores 1.0/all_satisfied; a
   partial implementation (kvdb-cli) scores exact `k/N`; a no-op scores 0.0 for every `HARD_SLICE` task;
   `ALL_COHERENCE_TASKS == FIRST_SLICE + HARD_SLICE`; each `HARD_SLICE` task has >=8 requirements;
   `run_coherence_suite`'s bare default still returns `len(FIRST_SLICE)` results (backward-compat). Run the
   FULL `python -m pytest tests/ -q` synchronously in the foreground and confirm it stays green.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (hardens the task slice with `HARD_SLICE` — 2
  "highly-complex", many-requirement, interdependent tasks including the kvdb-cli that measurably broke the
  saturated `FIRST_SLICE` — so the instrument stays discriminating instead of floor/ceiling-ing out; growing
  `HARD_SLICE` further and a live gemma-vs-escalating measurement against it remain open follow-ups)

### [TASK-31] n>1 (median-of-k) stability option for the coherence instrument (REQ-23)

MEASURED (a live run of the hardened `HARD_SLICE`, TASK-30): single-pass (`repeats=1`) `build_system` is
HIGH-VARIANCE on the hard, 11-requirement tasks — `kvdb-cli` scored 0/11 on one draw (a fast BROKEN build,
~49s) but 10/11 on another (~158s); `taskmgr-cli` hit 11/11. A single run is not a stable coherence number.
The instrument needs to build each task `k` times and aggregate, distinguishing a genuine BUILD FAILURE
(the entrypoint never produced anything runnable) from a run that ran fine but DROPPED a requirement.

#### Steps
1. In `harness/coherence_suite.py::run_coherence_suite`, add a `repeats: int = 1` parameter (default 1 =
   the ORIGINAL behavior, byte-for-byte back-compatible — implemented as a literal branch that leaves the
   pre-existing `repeats<=1` code path untouched, never refactored to share code with the new path). When
   `repeats > 1`, build + independently verify each task `repeats` times and aggregate per task: report
   `coherence_median` (median of the per-run coherence values), `coherence_mean`, `coherence_min`,
   `coherence_max`, and `runs` (the list of per-run `requirements_satisfied`). Keep `coherence`/
   `requirements_satisfied` in the record = the MEDIAN run's own actual value (`statistics.median_low` over
   the per-run satisfied counts, a stable, reproducible pick) so existing consumers of those keys get a
   stable central number. NEVER raises (a failed run counts as coherence 0.0 for that run).
2. Distinguish BUILD-FAILURE from DROPPED-REQUIREMENT in the per-run record: add a deterministic `build_ok`
   per run (the resolved entrypoint genuinely exists on disk AND — when the task has requirements — at
   least one was satisfied, i.e. the build produced something runnable at all). Report `build_failed_count`
   (runs where `build_ok` is False) and `dropped_requirements_count` (runs where `build_ok` is True but not
   every requirement was satisfied) across the `k` runs — two distinct measured failure modes.
3. Aggregate: the suite-level aggregate reports the mean of each task's `coherence_median` (the stable
   central number) plus a `build_failure_rate` across all individual runs (overall and per tier).
4. Tests (`tests/test_ext036_coherence.py`, OFFLINE — a deterministic call-COUNTER stub, never randomness,
   varying its build across calls): (a) `repeats=1` (omitted or explicit) preserves the EXACT pre-TASK-31
   record/aggregate shape (byte-for-byte, existing tests unchanged); (b) an alternating good/build-failed
   stub under `repeats=4` yields exact `runs`/`coherence_median`/`min`/`max`/`mean` and the correct
   `build_failed_count`; (c) a stub whose "bad" draw runs fine but drops exactly one requirement yields
   `build_failed_count == 0` / `dropped_requirements_count > 0` (proving the two failure modes are
   genuinely distinguished); (d) a stub that always fails (or always raises) scores `build_failed_count`
   equal to `repeats` and `coherence` 0.0 throughout, never raising; (e) the aggregate's
   `build_failure_rate`/mean-of-`coherence_median` are correct on a mixed always-good/always-broken
   two-task suite; (f) both `HARD_SLICE` tasks' reference implementations stay `all_satisfied=True` with 0
   build-failed/dropped runs under `repeats=3`. Run the FULL `python -m pytest tests/ -q` synchronously in
   the foreground and confirm it stays green.

#### Implements
- [REQ-23] Long-horizon build coherence instrument (adds an n>1/median-of-k stability option to
  `run_coherence_suite`, motivated by a MEASURED single-pass high-variance draw on the hard tier; a live
  gemma-vs-escalating measurement run WITH `repeats>1` against `HARD_SLICE` — the actual stabilized number
  this task was motivated by — remains an open follow-up)

### [TASK-32] Episodic (action+rationale) memory store + deterministic recall (REQ-24)

PRIME-001 intent capability (f): a durable, referenceable record of what the system DID and WHY, so a
planner can retrieve similar past work and reconcile a new plan against it. GUARD (measured negative, see
memory `jaros-code-retrieval-fewshot-negative`): this is PLAN + PROVENANCE recall, NOT behavior-keyed
few-shot CODE examples — recall informs the plan's context, it never pastes stale code. v1 is
DETERMINISTIC — no model call, no embeddings (lexical/tag match only); embeddings are an explicit later
follow-up. Self-contained new module, isolated from every other harness path (wiring is a follow-up).

#### Steps
1. Create `harness/episodic_memory.py`: a `DEFAULT_STORE` path constant under the data dir (e.g.
   `.jaros-data/artifacts/episodic/actions.jsonl`). `record_action(action, rationale, *, tags=None,
   outcome=None, meta=None, store=DEFAULT_STORE) -> dict` appends one JSON record `{seq, action,
   rationale, tags, outcome, meta}` to the JSONL store (creating parent dirs as needed); `seq` is a
   monotonic integer counter derived from the current line count of the store (no wall-clock dependency,
   Python's `time`/`datetime` are NOT required — a simple incrementing counter is sufficient and
   deterministic for ordering). Never raises: any bad/garbage/non-serializable input is coerced to a safe
   string/`None` before writing, and a write failure (e.g. unwritable path) is swallowed, returning the
   attempted record dict regardless.
2. Add `load_actions(store=DEFAULT_STORE) -> list[dict]`: reads and `json.loads`s each line of the JSONL
   store, SKIPPING any line that fails to parse (malformed JSON) or isn't a dict, and returning `[]` when
   the store file doesn't exist — never raises.
3. Add `recall_similar(query, *, k=5, tags=None, store=DEFAULT_STORE) -> list[dict]`: loads all actions via
   `load_actions`, computes a DETERMINISTIC similarity score per action — token-set Jaccard overlap between
   the lowercased whitespace-tokenized `query` and the action's `action + " " + rationale` text, PLUS a
   fixed bonus per shared tag when `tags` overlaps the action's own `tags` — filters to a `tags` argument
   when given (only actions containing at least one of the requested tags are considered), sorts by score
   descending with ties broken by INSERTION ORDER/`seq` (stable, reproducible — never Python's unstable
   dict/set iteration), and returns the top `k`. Empty store, no matches (all scores 0 and none share a
   tag), or bad/`None`/non-string `query` all return `[]`; never raises.
4. Add a `reset(store=DEFAULT_STORE)` helper that deletes/truncates the given store file (best-effort, no
   error if it doesn't exist) so tests and callers can isolate state with a scoped/temp store path passed
   via the `store=` keyword on every function above.
5. Do NOT modify `harness/system_builder.py`, `harness/coherence_suite.py`, `harness/cli.py`, or any other
   existing harness module — wiring `record_action`/`recall_similar` into the planner/orchestrator is an
   explicit follow-up (noted in REQ-24), out of this task's scope.
6. Tests (`tests/test_episodic_memory.py`, OFFLINE — no model, no network, each test uses a scoped temp
   `store=` path via `reset()`/a tmp_path fixture so no test shares state): (a) record several actions with
   distinct action/rationale text and tags, then assert `recall_similar(query)` returns the most
   lexically/tag-similar ones in the EXACT expected rank order for a hand-crafted set; (b) a `tags` filter
   narrows results to only actions sharing a requested tag; (c) `k` bounds the returned count; (d) an empty
   store and a query with no lexical/tag overlap both return `[]` without raising; (e) a JSONL store file
   with one malformed/non-JSON line among valid ones is skipped by `load_actions`/`recall_similar` without
   raising; (f) garbage input to `record_action`/`recall_similar` (e.g. `None` action, non-string rationale,
   non-list tags) never raises; (g) `reset(store)` isolates state — two different scoped stores never see
   each other's actions. Run `python -m pytest tests/test_episodic_memory.py -q` then the FULL
   `python -m pytest tests/ -q` synchronously in the foreground and confirm both stay green.

#### Implements
- [REQ-24] Episodic (action+rationale) memory — groundwork + experience-recall for planning

### [TASK-33] Best-of-k build reliability wrapper for build_system (REQ-25)

MEASURED (median-of-3 coherence run on `HARD_SLICE`): single-pass `build_system` scores median coherence
1.0 with ZERO dropped requirements when it succeeds, but suffers an occasional TOTAL BUILD FAILURE (~17%:
1/6 builds produced nothing runnable). The governed decompose→repair capstone (REQ-23) is the WRONG lever
for this failure mode (no requirements to repair — the failure is binary total-failure, not partial
drift). The right lever is BEST-OF-K: build the same spec up to `k` times into isolated attempts, keep the
best by an INDEPENDENT acceptance check. Self-contained NEW function; `build_system`'s own
behavior/signature is untouched.

#### Steps
1. Add `build_system_best_of_k(spec: str, root: "str | Path", *, llm=None, k: int = 3) -> dict` to
   `harness/system_builder.py`. For each attempt `i` in `range(max(1, k))`: create a FRESH temp subdir
   (`tempfile.mkdtemp`) so attempts never contaminate each other or the caller's `root`; call
   `build_system(spec, attempt_dir, llm=llm)` (guarded — a raised exception is treated as a failed attempt,
   never propagated).
2. Add a private `_score_build_attempt(spec, attempt_root, result, llm) -> tuple[int, int]` helper that
   independently scores an attempt: extract `result["plan"]["modules"]` (the module list); if there is no
   plan or no built modules, return `(0, 0)` (a total build failure, scored 0/0); otherwise call
   `_derive_acceptance_checklist(spec, mods, llm)` (a FRESH, independent derivation — never trust the
   attempt's own self-reported `done`) and run each check for real via `_run_check(attempt_root, check)`,
   counting passes. Return `(passed, total)`. Guarded — any exception during derivation/running counts that
   check as not passing, never raises.
3. In `build_system_best_of_k`, after each attempt is built+scored, EARLY-EXIT the loop immediately when
   `total > 0 and passed == total` (the attempt passes every one of its acceptance checks) — do not build the
   remaining `k - i - 1` attempts. Otherwise continue to the next attempt.
4. SELECT the winner: the early-exit attempt if one occurred; otherwise the attempt with the highest
   `passed` count (ties broken by the FIRST/earliest-evaluated attempt, i.e. lowest index — deterministic,
   never random). ASSEMBLE the winner's `modules` dict onto the caller's `root` (reusing the same
   `_jailed_write` helper `build_system` itself uses for every module write), NOT onto any temp attempt dir.
   Clean up every temp attempt directory in a `finally` block (best-effort `shutil.rmtree`, never raises).
5. Return `{"modules": <winner modules>, "shipped": <bool>, "done": <bool>, "attempts_run": <int>,
   "best_score": <int>, "note": <str>}`. `done` is `True` only when the winner's independently-verified
   `passed == total` and `total > 0` (never a fabricated pass); `shipped` reflects whether any modules were
   actually assembled. The `note` honestly reports attempts run + best score, and — when every attempt
   scored `0` total — explicitly says all `k` attempts failed to produce a checkable system (least-bad
   returned, no manufactured pass). Add `import shutil` to `harness/system_builder.py`'s existing import
   block if not already present.
6. Do NOT modify `build_system`, `build_system_governed`, `build_system_escalating`, `coherence_suite.py`,
   `server_oracle.py`, `system_suite.py`, or `cli.py` — wiring `build_system_best_of_k` into `/buildsystem`
   is an explicit follow-up (noted in REQ-25), out of this task's scope.
7. Tests, appended to `tests/test_ext036_system_builder.py` (OFFLINE — a fake/canned llm mirroring the
   existing `_CannedLlm` pattern in that file, no live model, no network):
   (a) **BEST-OF-K MASKS A FAILURE** — a fake llm whose first `build_system()` invocation produces a
   broken/empty system (module never compiles, so the attempt ships nothing checkable — 0 checks pass) and
   whose second invocation produces a fully-correct system (all checks pass): assert
   `build_system_best_of_k(spec, root, llm=fake, k=2)` returns `done=True`, a full `best_score` (score ==
   total), `root` ends up containing the WORKING build's modules on disk, and `attempts_run == 2` (it
   genuinely tried again after the first failure);
   (b) **EARLY-EXIT** — a fake llm whose first invocation already produces a fully-passing system: assert
   `attempts_run == 1` with `k=3` (the remaining budget is never spent);
   (c) **ALL-FAIL HONESTY** — a fake llm where every invocation produces a broken/uncheckable system: assert
   `done=False` with an honest note (never a fabricated pass), and the function still returns the
   least-bad attempt's (possibly empty) `modules` without raising;
   (d) a confirmation that plain `build_system` itself is byte-identical/unaffected (reuse the file's
   existing `SPEC`/`_CannedLlm` fixture). Run `python -m pytest tests/test_ext036_system_builder.py -q`
   then the FULL `python -m pytest tests/ -q` synchronously in the foreground and confirm both stay green.

#### Implements
- [REQ-25] Best-of-k build reliability — mask occasional total build failure

### [TASK-34] Fix validate_plan: stdlib imports wrongly flagged as dangling local references (REQ-1)

MEASURED LIVE (2026-07-04): building the `notes-sqlite-cli` DATASTORE_SLICE task
(`harness/system_suite.py`) produced `done=False`, an empty root, and the note
`plan failed coherence validation: database.py: imports unknown 'sqlite3'; entrypoint not
a listed module`. ROOT CAUSE: `validate_plan`'s import-coherence check
(`harness/system_builder.py`) treats EVERY entry in a module's `imports` list as a
reference to another PLANNED LOCAL module — when gemma legitimately lists a STDLIB import
(`sqlite3`, and by extension `os`/`json`/`datetime`/etc.) the check flags it as
`imports unknown '<stdlib module>'` and the WHOLE plan is rejected as incoherent, so 0
modules build. This blocks any system whose plan cross-references a standard-library
module by name (the datastore capability and others). The check's real job — catching a
genuinely-missing LOCAL module reference — must be preserved; only stdlib names should be
exempted.

#### Steps
1. In `harness/system_builder.py::validate_plan`'s per-module `imports` loop, change the
   "unknown import" test from `if imp not in names` to also exempt standard-library
   modules: for each `imp`, skip it (no defect) when `imp in names` (already-listed local
   module, existing behavior) OR when its TOP-LEVEL name (`imp.split(".")[0]` to handle
   dotted imports like `os.path`) is a member of `sys.stdlib_module_names` (already
   imported as `sys` at the top of the file). Only append `f"{m.get('name')}: imports
   unknown '{imp}'"` when NEITHER condition holds — a genuinely-missing local module (not
   listed, not stdlib) must still be flagged exactly as before.
2. Do not change any other `validate_plan` check (exports, entrypoint-listed, acceptance
   present, import-cycle DFS) and do not touch `_repair_plan_entrypoint` (TASK-19) or any
   other function — the cycle-check's graph (`if i in names`) already naturally excludes
   stdlib imports from the DAG, so it needs no change.
3. Tests, appended to `tests/test_ext036_system_builder.py` (OFFLINE, pure unit tests
   against `validate_plan` — no model/network needed): (a) a module whose `imports` lists
   a stdlib module (`sqlite3`) yields NO "imports unknown" defect; (b) `os`, `json`,
   `datetime`, and a dotted `os.path` are all exempt in one plan; (c) VALUE-PRESERVING — a
   module importing a genuinely-missing LOCAL module (`helpers`, neither listed nor
   stdlib) STILL yields `imports unknown 'helpers'`; (d) a valid cross-module LOCAL import
   (module `a.py` imports listed module `b.py`) remains coherent. Run
   `python -m pytest tests/test_ext036_system_builder.py -q` then the FULL
   `python -m pytest tests/ -q` synchronously in the foreground and confirm both stay
   green.

#### Implements
- [REQ-1] Planner: sentence -> structured, coherence-validated plan (fixes a coherence-
  validator FALSE POSITIVE that rejected otherwise-valid plans referencing a stdlib module
  by name, unblocking the datastore/DB-backed system class)
