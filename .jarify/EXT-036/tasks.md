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

### [TASK-35] Close a Tenet-3 false-done: acceptance never exercises the real CLI entrypoint (REQ-2)

DIAGNOSED + REPRODUCED LIVE (2026-07-04, via a scratch probe, not committed): building
`notes-sqlite-cli` (`harness/system_suite.py` DATASTORE_SLICE) through `build_system`
returned `done=True` with note `"DONE (all acceptance checks pass)"` on the FIRST draw --
yet a genuinely fresh `python main.py add buy milk` in a clean directory CRASHED with
`sqlite3.OperationalError: no such table: notes` (the generated CLI's `add` branch calls
`insert_note()` without ever calling `initialize_db()` first; `initialize_db()` is only
called at the very end of the `__main__` block, after the crash already happened). The
independent held-out oracle (`system_suite.py`'s own `CreationTask.checks`) correctly
rejects this build (`accepted=False`) -- this is NOT a sandbox/security issue (a
plain-subprocess control reproduces the crash identically), it is a genuine overclaim by
`build_system`'s own self-derived acceptance.

ROOT CAUSE (instrumented via `_derive_acceptance_checklist`/`_run_check_verbose`): the
checklist actually used for this draw was the deterministic SMOKE fallback (a single check
named `"smoke: modules import and expose their API"`, asserting only `import main` plus
`hasattr(main, 'initialize_db')` / `'insert_note'` / etc for each exported name) --
`_smoke_checklist` never calls any exported function and never invokes the module's
`if __name__ == "__main__":` CLI dispatch at all, so it structurally cannot observe a bug
that only surfaces when the real entrypoint is invoked the way a user actually runs it.
This is NOT a shared-root state-contamination issue (only one check ran, in a clean root)
and NOT a "non-zero exit isn't treated as a failure" issue (`_run_acceptance_cmd` already
treats a non-zero exit honestly as not-passing) -- the acceptance path in this draw simply
never RAN the primary command at all. The two prior model-proposed checklist tiers
(`CHECKLIST_PROMPT` / `CHECKLIST_STRICT_PROMPT`) have the same structural gap whenever the
model chooses to `import` the built module and call its functions directly rather than
spawn the real CLI as a subprocess -- an in-process function call can silently bypass a
broken `__main__` dispatch branch a real invocation would hit.

#### Steps
1. In `harness/system_builder.py`, add a new prompt `SUBPROCESS_CHECKLIST_PROMPT` (near
   `CHECKLIST_STRICT_PROMPT`/`HTTP_CHECKLIST_PROMPT`) asking the model for 2-3 concrete
   acceptance checks that invoke the built system's own declared entrypoint as a REAL
   SUBPROCESS (`subprocess.run([sys.executable, "<entry file>", ...], capture_output=True,
   text=True)`), matching the exact command-line usage the SPEC itself describes, instead
   of importing the built modules in-process, and asserting on the real stdout/exit code.
2. Add a deterministic filter `_is_subprocess_check(code) -> bool` (mirrors
   `_is_http_check`'s pattern from REQ-22): survives only if it is already a real
   executable check (`_is_executable_check` -- parses + contains a real `assert`) AND its
   AST actually contains a call to `subprocess.run` / `subprocess.check_output` /
   `subprocess.check_call` / `subprocess.Popen`. Never raises.
3. Add `_propose_subprocess_checklist(spec, api, llm) -> list[dict]` (mirrors
   `_derive_http_checklist`'s shape): one guarded model round-trip using
   `SUBPROCESS_CHECKLIST_PROMPT`, filtered by `_is_subprocess_check`; returns `[]` on any
   model/parse failure or when nothing survives (never a fabricated pass).
4. Wire it into `_derive_acceptance_checklist` as a NEW THIRD tier, inserted between the
   existing strict-retry tier and the `_smoke_checklist` fallback: `checks =
   _propose_checklist(..., CHECKLIST_PROMPT)` -> if empty, `_propose_checklist(...,
   CHECKLIST_STRICT_PROMPT)` -> if still empty, NEW `_propose_subprocess_checklist(spec,
   api, llm)` -> if still empty, `_smoke_checklist(mods)`. Update the function's docstring
   to describe the new tier. This never changes behavior for any build whose first two
   tiers already produce a usable checklist (no regression to a currently-passing build).
5. Wrap all new/changed lines with `# #EXT-036-REQ-2 Start` / `# #EXT-036-REQ-2 End`
   (nested inside the existing REQ-2 region in this file) per the links skill.
6. Tests, appended to `tests/test_ext036_acceptance.py` (OFFLINE, canned `llm`, no live
   model): (a) unit tests for `_is_subprocess_check` (accepts a real subprocess-based
   assert check, rejects an in-process import-based check, rejects unparseable/no-assert
   code); (b) a fixture module reproducing the notes-sqlite-cli bug CLASS (a tiny CLI whose
   `add` branch writes to a store without initializing it first) -- when the canned llm's
   first two checklist tiers yield nothing usable but the THIRD tier yields a real
   subprocess-based check (e.g. running `python main.py add x` and asserting `rc == 0`),
   `build_system` now correctly reports `done=False` for the broken CLI (closing the false
   positive) and `done=True` once the CLI is fixed (no new false negative); (c) confirm the
   three EXISTING smoke-fallback tests
   (`test_unparseable_first_and_strict_falls_back_to_deterministic_smoke`,
   `test_all_vague_on_both_attempts_falls_back_to_deterministic_smoke`,
   `test_smoke_fallback_passes_a_working_system`,
   `test_smoke_fallback_fails_a_broken_system_no_false_pass`) still pass UNCHANGED (the
   canned llm's catch-all `_Resp("")` response to the new prompt tier yields `[]`, so these
   cases still fall through to `_smoke_checklist` exactly as before -- no regression).
7. Run `python -m pytest tests/test_ext036_acceptance.py -q` then the FULL
   `python -m pytest tests/ -q` synchronously in the foreground and confirm both stay
   green.

#### Implements
- [REQ-2] Executable acceptance — the plan must emit a RUNNABLE system-level oracle, not
  prose (closes the measured gap where the smoke fallback, and an in-process
  import-based check, can both structurally miss a bug that only a real subprocess
  invocation of the declared CLI entrypoint would surface)

### [TASK-36] Deterministic plan-repair: dangling LOCAL import not listed as a module (REQ-1)

MEASURED live, 6/6 identical draws (2026-07-04, owner-diagnosed): for the notes-sqlite-cli
task, gemma DETERMINISTICALLY draws a 2-module plan (e.g. `cli.py` + `main.py`, entrypoint
`main.py`) where `cli.py` lists an import of a LOCAL module (e.g. `database`) that is NOT
among the plan's listed modules. `validate_plan` correctly flags `cli.py: imports unknown
'database'` and the whole plan is rejected — 0 modules build, 0 accept. Because this is
DETERMINISTIC (not model sampling variance), best-of-k cannot help; a deterministic
plan-repair (the same lever TASK-19 used for the mismatched-entrypoint defect) is the fix:
generate the missing module instead of rejecting a plan that is one module short of coherent.

#### Steps
1. In `harness/system_builder.py` (REQ-1 section, alongside `validate_plan`/
   `_repair_plan_entrypoint`), add a deterministic
   `_repair_plan_dangling_imports(plan: dict) -> tuple[dict, str | None]`: scan every
   planned module's `imports`; for each entry that is NEITHER already a listed module name
   NOR a standard-library top-level name (`sys.stdlib_module_names`, top-level split — the
   same exemption `validate_plan`'s TASK-34 fix applies, so stdlib imports are never
   touched), ADD a new module entry to `plan["modules"]` for that missing name (filename
   matching the `.py` convention the plan already uses for other modules — append `.py`
   when the bare import name lacks it) with a minimal non-empty `exports` entry (a single
   function named after the module stem, or `run` if the stem isn't a valid identifier) so
   it satisfies `validate_plan`'s export-shape checks, and point the referencing module's
   dangling `imports` entry at that exact new name so the reference resolves. Only ADD
   module entries — never remove or rename anything the model planned. Return
   `(plan, note)` — `note` is `None` when no repair was made (no dangling local imports;
   already coherent on this axis), else a short human-readable description. Pure/
   deterministic, no model call, idempotent (re-running on an already-repaired plan is a
   no-op), never raises.
2. In `build_system`, call `_repair_plan_dangling_imports(plan)` immediately AFTER
   `_repair_plan_entrypoint(plan)` (same call site, before the `validate_plan(plan)`
   coherence gate) — sequenced so BOTH measured defects in one plan get repaired (the
   datastore plan can trip both "imports unknown" and, sometimes, "entrypoint not
   listed"); running the entrypoint repair first preserves its own single-module
   conservatism (module count is still accurate before any modules get added). Combine
   both repair notes (joined, non-empty ones only) into the existing `plan_repair` field —
   no new field, no change to `_result()`'s shape.
3. Tests, extending `tests/test_ext036_system_builder.py` (OFFLINE — canned `llm`, no
   network): (a) a plan with a module importing an unlisted LOCAL module `database` — after
   repair, `database.py` is a listed module and `validate_plan` yields NO "imports unknown
   'database'" defect; (b) a plan importing `sqlite3`/`os` (stdlib) is UNCHANGED by the
   repair — no bogus module added, stdlib stays exempt; (c) a plan importing a genuinely-
   listed local module is unchanged (idempotent, no-op on coherent plans, including
   re-running the repair a second time); (d) the repaired plan actually passes
   `validate_plan`'s module-shape checks (exports present/well-formed) and is fully
   coherent; (e) never raises on malformed/edge-case plan shapes; (f) an end-to-end
   `build_system` run on the exact measured defect shape (2-module plan, one dangling
   local import) now SHIPS all three modules (including the newly-added one) instead of
   being rejected with "imports unknown". Run
   `python -m harness.run_with_heartbeat --label "ext036 plan-repair" -- python -m pytest
   tests/test_ext036_system_builder.py -q` then the FULL
   `python -m harness.run_with_heartbeat --label "full suite" -- python -m pytest tests/ -q`
   synchronously in the foreground and confirm both stay green.

#### Implements
- [REQ-1] Planner: sentence -> structured, coherence-validated plan (a deterministic
  plan-repair for the MEASURED dangling-LOCAL-import defect — fills another slice of the
  "plan-repair loop... feed back for a coherent re-plan" acceptance criterion, alongside
  TASK-19's entrypoint repair; a general re-plan-on-defect loop for OTHER defect classes
  remains open)

### [TASK-37] Deterministic minimum acceptance floor -- trustworthy done for best-of-k (REQ-26, task #118)

MEASURED PROBLEM (2026-07-05): `_derive_acceptance_checklist(spec, mods, llm)` (REQ-2)
proposes acceptance checks via the MODEL, so the checklist VARIES in completeness for the
IDENTICAL sentence — a single datastore build derived 3 checks, another draw of the SAME
sentence derived only 1. `build_system_best_of_k` (REQ-25) then EARLY-EXITS on whichever
draw derived the fewest/easiest self-checks and reports `done=True` on a sparse 1-check
bar — not real correctness. The model was also independently found to systematically MISS
a 'usage'/CLI-help check. The fix is a DETERMINISTIC MINIMUM checklist the model can only
ADD TO, never shrink below.

#### Steps
1. Added `_minimum_acceptance(spec, mods, plan)`, `_extract_command_tokens(spec)`,
   `_minimum_entry_filename(mods, plan)`, and `_no_crash_subprocess_check(name, entry,
   invocations)` to `harness/system_builder.py` under a NEW `# #EXT-036-REQ-26 Start`/`End`
   tag (placed right after the existing REQ-2 region): a DETERMINISTIC (no model call)
   minimum acceptance checklist derived from the spec sentence + built module API alone —
   always includes the existing `_smoke_checklist` as a floor, a usage/--help check
   (running the entrypoint with no args AND with `--help`, asserting neither crashes with
   an unhandled Python exception, fed empty stdin via `input=""` so a stdin-driven CLI sees
   an immediate EOF rather than hanging), and one subprocess check per conservatively-
   extracted command token (quoted tokens like `'add'`/`'list'` plus a small fixed
   allow-list of imperative verbs, capped at `MAX_MINIMUM_COMMANDS=6` — under-extracts
   rather than hallucinates a command the sentence doesn't name). Every minimum check
   asserts ONLY `'Traceback (most recent call last)' not in result.stderr` — never a
   specific stdout VALUE (no oracle leak: asserting a specific answer would require
   knowing it up front). DONE.
2. Added `_compose_acceptance_checklist(spec, mods, llm, plan)`: the FINAL checklist = the
   deterministic minimum UNIONED with `_derive_acceptance_checklist`'s own model-derived
   proposals, de-duplicated by `(name, code)` — the model's checks AUGMENT, never REPLACE,
   the minimum. Guarded: never raises; a model/derive failure or exception still leaves
   the deterministic minimum in place. DONE.
3. Wired `_compose_acceptance_checklist` into `build_system`'s own ACCEPTANCE step
   (replacing the direct `_derive_acceptance_checklist` call) and into
   `build_system_best_of_k`'s `_score_build_attempt` (REQ-25) so best-of-k selects/
   early-exits only against the full, minimum-inclusive bar — both functions' own
   signatures/other behavior are otherwise byte-identical. DONE.
4. Wrapped all new/changed lines with `# #EXT-036-REQ-26 Start` / `# #EXT-036-REQ-26 End`
   per the links skill. DONE.
5. Tests: new `tests/test_ext036_acceptance_completeness.py` (16 tests, canned/fake `llm`,
   no live model) — unit tests for `_extract_command_tokens`/`_minimum_entry_filename`/
   `_minimum_acceptance` (including never-raises on bad input, and stability/determinism
   across repeated calls on the same sentence); the composed checklist is never sparser
   than the minimum and the model's proposals genuinely augment it; an identical model
   proposal dedupes against a minimum check; the composed checklist survives a raising
   `llm`; an end-to-end build whose model self-derives only ONE trivial (always-passing)
   check still gets `done=False` on a genuinely broken CLI (caught by the minimum's own
   command check) and `done=True` once fixed (no new false negative); a best-of-k test
   proving it no longer early-exits on a sparse first-attempt pass and lands the
   genuinely-fixed second attempt. Extended `tests/test_ext036_acceptance.py`: updated the
   pre-existing empty-checklist test to monkeypatch BOTH `_minimum_acceptance` and
   `_derive_acceptance_checklist` to `[]` (a real, non-monkeypatched minimum is never empty
   for a non-empty module set, so this is now the only way to reach that degenerate case);
   added a new test proving the minimum floor still gates — and a genuinely working system
   still passes it — when the model itself derives nothing usable on any tier. Updated the
   pre-existing REQ-23 `MAIN_MISSING_MUL` governed-build fixture in
   `tests/test_ext036_system_builder.py` to still DEFINE the `mul` function (satisfying the
   new stricter existence-based smoke floor) while leaving it unwired from the CLI
   dispatch — preserving that file's "build_system's own checklist is fooled by a dropped
   BEHAVIOR, not a dropped SYMBOL" premise, HONESTLY updated for the stricter (correct) bar
   rather than weakened. DONE.
6. Ran `python -m harness.run_with_heartbeat --label "full suite" -- python -m pytest
   tests/ -q` synchronously in the foreground and confirmed green: 2275 passed, 2 skipped,
   exit code 0 (up from 2258/2). DONE.

#### Implements
- [REQ-26] Acceptance-completeness / done-honesty — a deterministic minimum acceptance
  floor (this task introduces AND fully implements REQ-26 for its offline scope; an
  explicit follow-up — a LIVE gemma re-measurement of accept-rates before/after this fix,
  and wiring `build_system_best_of_k` into the `/buildsystem` CLI command — remains open,
  per REQ-25's own pre-existing follow-up, and does not block this task)

### [TASK-38] Behavioral acceptance honesty: error-in-output detection + add/list round-trip (REQ-27, task #121)

MEASURED PROBLEM (2026-07-05), behavioral verification of a `done=True` build: REQ-26's
deterministic minimum per-command checks (`_no_crash_subprocess_check`) assert ONLY
`'Traceback (most recent call last)' not in result.stderr` — a datastore CLI that gracefully
CATCHES its own error and PRINTS it at exit-code 0 (`"An error occurred while listing notes:
... missing 1 required positional argument: 'db_path'"`) PASSES the no-crash check while
being behaviorally broken (LIVE-measured: `add` doesn't persist, `list` never shows an added
note) — `done=True` was HOLLOW, a new false-done class directly beneath REQ-26's own floor.

#### Steps
1. Added `harness/system_builder.py::_has_error_marker(text)` — a host-side (and thus
   directly unit-testable) marker check plus `_ERROR_MARKER_HELPER_SRC`, a generated-code
   mirror built from the SAME compiled regex pattern strings (single source of truth, no
   drift): a line starting with `Traceback`/`Exception`/`Error`, or a substring match
   (case-insensitive) for `an error occurred` / `missing ... required ... argument` / `not
   found`. Anchored conservatively (line-start for the class-name forms) so an argparse-
   style `"prog: error: ..."` usage line (prefixed by the program name, not bare at
   line-start) and normal output that legitimately contains the word "error" as data are
   never false-flagged. DONE.
2. Strengthened `_no_crash_subprocess_check` (REQ-26): every generated invocation now also
   embeds `_ERROR_MARKER_HELPER_SRC` and asserts `not _has_error_marker(result.stdout +
   result.stderr)` in addition to the pre-existing no-traceback assertion, for every
   minimum invocation including the usage/--help check. DONE.
3. Added `_derive_roundtrip_pair(spec)` (conservative whole-word match against a small
   fixed ADD-like set `add/create/save/insert/new` and LIST-like set
   `list/show/print/get/all`; returns `None` — no check emitted — unless the sentence
   clearly names one of each) and `_roundtrip_acceptance_check(entry, add_cmd, list_cmd)`
   (generates a deterministic check: run `<entry> <add_cmd> <sentinel>` — trying 1 then 2
   positional sentinel args — then `<entry> <list_cmd>`, asserting the fixed literal
   sentinel token appears in the list output for at least one arg-count that didn't itself
   error). Composed into `_minimum_acceptance` (only when an entry filename resolves and a
   pair is derived) so it flows through the existing `_compose_acceptance_checklist`
   union/de-dup unchanged. NO ORACLE LEAK: the sentinel is a fixed literal never derived
   from or leaked into the solving prompt; the check only asserts the system's OWN stated
   add/list contract. DONE.
4. Wrapped all new/changed lines with `# #EXT-036-REQ-27 Start` / `# #EXT-036-REQ-27 End`
   per the links skill (placed immediately after the existing `# #EXT-036-REQ-26 End`
   region so REQ-26's own tag boundaries are untouched). DONE.
5. Tests: extended `tests/test_ext036_acceptance_completeness.py` — unit tests for
   `_has_error_marker` (catches the measured graceful-error phrasing and a bare
   `Error:`-prefixed line; does NOT flag an argparse-style `"prog: error: ..."` usage line
   or a legitimate `"...error rate..."` data line) and `_derive_roundtrip_pair`
   (finds an add+list pair; conservative `None` when the sentence names only one side, or
   neither; never raises on bad input); an end-to-end `build_system` run against a fake CLI
   that gracefully prints an error at `rc=0` on its primary command now reports
   `done=False`; an end-to-end run against a fake CLI whose add+list genuinely round-trips
   (writes then reads back a real file) reports `done=True` (no new false negative). DONE.
6. Ran `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirmed
   green and recorded the exact pass/skip count + exit code. DONE.

#### Implements
- [REQ-27] Behavioral acceptance honesty — error-in-output detection + add/list round-trip
  (this task introduces AND fully implements REQ-27 for its stated scope)

### [TASK-39] Fix false-negative: per-command guessed-arity probe must not mis-grade usage/argument-validation as a runtime defect (REQ-28)

MEASURED FALSE-NEGATIVE (2026-07-05): a best-of-k (k=5) attempt built a GENUINELY WORKING
SQLite notes CLI (physically verified: `add "T" "BODY"` persists, `list` shows it, all
requirements met, `n_unmet=0`), but `build_system`'s acceptance still reported `done=false`
("best attempt passes 4/5 acceptance checks"). Root cause: `_minimum_acceptance`'s
per-command probe (`_no_crash_subprocess_check(..., [[cmd, "x"]])`) feeds exactly ONE
guessed positional arg per command; the winning app's `add` takes TWO args (title +
content), so `add x` correctly prints its own usage/argument-validation message
(`"Error: 'add' command requires a title and content."`) at rc=0 — REQ-27's
`_has_error_marker` correctly flags the bare `Error:`-prefixed line, so the per-command
check FAILS even though the app is genuinely working. Correct argument validation was
mis-classified as a runtime defect.

#### Steps
1. Add `harness/system_builder.py::_is_usage_validation_message(text)` plus a
   generated-code mirror `_USAGE_VALIDATION_HELPER_SRC` (built from the SAME compiled
   pattern strings — single source of truth): a conservative, DETERMINISTIC classifier for
   usage/argument-validation vocabulary (`usage:`, "the following arguments are required",
   "too few/many arguments", "expected ... argument(s)", "requires a/an/<N>", "provide
   a/an/the", "required argument", "missing argument/option/parameter") — every pattern
   chosen so it does NOT match REQ-27's genuine-defect fixture text (the graceful "An error
   occurred while listing notes: ... missing 1 required positional argument: 'db_path'"
   TypeError string, which has "1 required positional" between "missing" and "argument" and
   so never matches).
2. Add a new keyword-only parameter `allow_usage_validation=False` to
   `_no_crash_subprocess_check`. Default `False` leaves every EXISTING call site
   byte-identical. When `True`, the generated error-marker assertion becomes: fail only if
   `_has_error_marker(combined)` AND NOT `_is_usage_validation_message(combined)`. The
   pre-existing no-traceback assertion is left completely unconditional/unchanged.
3. In `_minimum_acceptance`, pass `allow_usage_validation=True` ONLY on the per-command
   `[[cmd, "x"]]` guessed-arity loop over `_extract_command_tokens(spec)`. The usage/`--help`
   check (`[[], ["--help"]]`) and `_roundtrip_acceptance_check` (REQ-27's arity-aware
   round-trip) are left completely untouched/strict.
4. Wrap all new/changed lines with `# #EXT-036-REQ-28 Start` / `# #EXT-036-REQ-28 End` per
   the links skill, placed immediately after the existing `# #EXT-036-REQ-27 End` region so
   REQ-26/REQ-27's own tag boundaries are untouched.
5. Add `tests/test_ext036_usage_validation_floor.py`: build two synthetic on-disk CLIs and
   run the ACTUAL `_minimum_acceptance` + `_run_check`/`_run_check_verbose` checklist against
   each. (a) TRUE-POSITIVE PRESERVED: a CLI whose `list` (invoked correctly) prints
   `"Error: no such table: notes"` at rc=0 — assert the per-command `list` check still fails
   and the full minimum-acceptance checklist is NOT all-pass. (b) FALSE-NEGATIVE FIXED: a
   CLI whose `add x` (one guessed arg) prints `"Error: 'add' command requires a title and
   content."` at rc=0 but whose real `add <title> <content>` genuinely persists to sqlite
   and is visible via `list` — assert the per-command `add` check passes AND the full
   composed minimum-acceptance checklist is all-pass (round-trip included).
6. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm green,
   and record the exact pass/skip count + exit code (no regression vs the pre-change count).

#### Implements
- [REQ-28] Per-command minimum-acceptance probes must not mis-grade usage/argument-validation
  as a runtime defect (this task introduces AND fully implements REQ-28)

### [TASK-40] Optional 7B-review of model-proposed acceptance checks (REQ-30, task #122)

VALIDATED FIX (owner's idea, pre-registered kill criterion probed and PASSED 2026-07-05,
`.jaros-data/sevenb_review_probe.py`): REQ-26's composed acceptance checklist is honest
about the deterministic FLOOR, but its model-PROPOSED portion is a mixed bag — some
HALLUCINATE (an invented API/import, an invented expected value), false-negativing
correct builds; others correctly catch real breakage. A STRONGER model
(qwen2.5-coder-7b) reviewing+correcting each model-proposed check from the VISIBLE
spec+code ONLY (no oracle leak) fixed 3/4 hallucinated checks and preserved 1/1
real-bug check in the probe. Build the production-grade, injectable mechanism the
probe validated.

#### Steps
1. Add `harness/acceptance_review.py` with `review_checks(spec, modules, proposed_checks,
   reviewer_llm) -> list[dict]`, reusing the EXACT `REVIEW_PROMPT` wording and
   fence-stripping/DROP-parse logic from `.jaros-data/sevenb_review_probe.py`
   (`REVIEW_PROMPT`, `_write_and_run`-equivalent parse, the review loop). Calls
   `reviewer_llm.complete(LlmRequest(prompt=..., params={"temperature": 0.0,
   "max_tokens": 1024})).text` per check; corrects a hallucinated API/import, recomputes
   or drops an asserted value per the spec's stated rules, or drops the whole check when
   unverifiable. NO ORACLE LEAK: the reviewer sees only spec + built module sources + the
   one proposed check, never any hidden/expected output. NEVER raises: a
   `reviewer_llm.complete` exception leaves that ONE check unchanged (conservative).
2. Wrap the new module's content with `# #EXT-036-REQ-30 Start` / `# #EXT-036-REQ-30 End`
   per the links skill.
3. In `harness/system_builder.py`, add a keyword-only `check_reviewer=None` parameter to
   `build_system`, `_score_build_attempt`, and `build_system_best_of_k` (default `None`
   leaves every one of these BYTE-IDENTICAL to before this task — no behavior change
   unless a caller explicitly passes `check_reviewer`). When supplied: recompute the
   deterministic minimum (`_minimum_acceptance`, no model call) to identify which entries
   of the already-composed checklist (`_compose_acceptance_checklist`, REQ-26) are
   MODEL-PROPOSED (i.e. not in the minimum); pass ONLY that subset to
   `harness.acceptance_review.review_checks` along with the attempt's own `built` module
   sources; replace the checklist with `minimum + reviewed` BEFORE it gates `done` (in
   `build_system`) / scoring (in `_score_build_attempt`). The deterministic minimum is
   NEVER sent to the reviewer and always gates as-is. `build_system_best_of_k` threads
   `check_reviewer` to both its per-attempt `build_system` call and
   `_score_build_attempt`. Wrap all new/changed lines with `# #EXT-036-REQ-30 Start` /
   `# #EXT-036-REQ-30 End`.
   IMPORTANT (scope boundary): do NOT perform any Jetson model-swap orchestration inside
   `build_system`/`build_system_best_of_k` — `check_reviewer` is just an injected llm
   object; which model actually serves as the reviewer (e.g. a live gemma<->7B swap) is a
   CALLER concern, kept out of scope so these functions stay fast, gemma-default, and
   offline-testable.
4. Add `tests/test_ext036_acceptance_review.py` (fake/canned `llm`/`reviewer_llm` stubs,
   no live model, no network): unit-test `review_checks` (corrects a hallucinated check,
   drops an unverifiable one, keeps a real-bug check UNCHANGED when the reviewer is "told
   to keep it", keeps the original unchanged when the reviewer raises, strips markdown
   fences, never raises on bad/empty input, no-oracle-leak prompt shape); end-to-end
   `build_system(..., check_reviewer=...)` tests (a hallucinated model-proposed check on a
   genuinely-working synthetic build flips `done` False->True once reviewed; a real-bug
   model-proposed check stays failing/`done=False` even when the reviewer is told to keep
   it; `check_reviewer=None` — both implicit default and explicit `None` — is
   byte-identical on `shipped`/`done`/`unmet`/`note`/`modules` on a fixed synthetic build;
   a reviewer that raises on every call never crashes `build_system`).
5. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change count).

#### Implements
- [REQ-30] Optional 7B-review of model-proposed acceptance checks (this task introduces
  AND fully implements REQ-30's offline mechanism; the live model-swap + false-done-gate
  measurement remain open follow-ups)

### [TASK-41] 7B-GENERATE acceptance checks from scratch (REQ-31, owner idea #122b)

Owner's EXTENSION of TASK-40/REQ-30: `review_checks` is bounded by Gemma's own proposed
checks (it can only correct/patch them). Build the GENERATE variant: prompt a stronger
model to WRITE acceptance checks from scratch, using ONLY the visible spec + built module
sources (no oracle leak) — unshackled from Gemma's hallucinations entirely. Standalone and
offline-testable; NOT wired into `build_system` in this task — it will be A/B-measured by
the parent against `review_checks` and the baseline via the live gate, like REQ-30 was.

#### Steps
1. Add `harness/acceptance_review.py::generate_checks(spec, modules, generator_llm,
   max_checks=4) -> list[dict]`, modeled on `REVIEW_PROMPT`'s honesty framing but "WRITE
   checks" instead of "correct this check". Calls `generator_llm.complete(LlmRequest(
   prompt=..., params={"temperature": 0.0, "max_tokens": 1024})).text` once with a new
   `GENERATE_PROMPT` built from ONLY `spec` + the built `modules` source — never any
   hidden/expected output (NO ORACLE LEAK). Returns `{"name": str, "code": str}` dicts
   (same shape `_compose_acceptance_checklist` entries / `_run_check_verbose` consume).
2. Parse the model's raw response conservatively: strip markdown fences (reuse
   `review_checks`'s `_clean_reviewed_code`), split multiple fenced Python blocks into
   separate checks, honor a whole-response `DROP`, and OMIT any block that doesn't parse
   as valid Python with a real `assert` (a check the model can't write → omit it, never
   fabricate). Bound the result to `max_checks`. NEVER raises: a `generator_llm.complete`
   exception or any unparseable/garbage response returns `[]`.
3. Do NOT modify `review_checks` or wire `generate_checks` into `build_system` in this
   task — standalone only. Wrap all new code with `# #EXT-036-REQ-31 Start` /
   `# #EXT-036-REQ-31 End` per the links skill.
4. Add `tests/test_ext036_generate_checks.py` (fake `generator_llm` stubs, no live model,
   no network): a well-formed multi-check response parses into the right number of
   runnable `{name, code}` dicts; the no-oracle-leak prompt shape (spec + code present,
   no oracle-only string); fenced-code stripping and multi-block splitting; a
   raising/garbage/DROP/syntax-error generator each yields `[]` without crashing;
   `max_checks` bounding.
5. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change baseline).

### [TASK-42] Deterministic plan-repair for MULTI-module entrypoint-not-listed (REQ-32, hard-tier diagnostic #86)

MEASURED (hard-tier capability diagnostic, `.jaros-data/hardtier_failure_diag.json`,
2026-07-06): `graph-bfs-shortest-path-cli` fails at the PLAN stage — `note = "plan
failed coherence validation: entrypoint not a listed module"` — a pure deterministic
plan-coherence rejection, not a reasoning failure. LIVE-REPRODUCED (3/3 identical draws
against served gemma-4-e2b): the plan lists 2 modules (`graph_builder.py`,
`bfs_solver.py`), both with `imports: []` (no module imports the other), `entrypoint:
"main.py"` not among them. `_repair_plan_entrypoint` (TASK-19) only repairs the
single-module case, deliberately leaving every multi-module case untouched. Build the
narrow, safe multi-module extension.

#### Steps
1. In `harness/system_builder.py`, add `_repair_plan_entrypoint_multi(plan) -> (plan,
   note)` right after `_repair_plan_entrypoint` (before `_repair_plan_dangling_imports`).
   Fires ONLY when: `plan["modules"]` has 2+ well-formed (named) entries; `entrypoint`
   is a non-empty string matching `^[A-Za-z_][A-Za-z0-9_]*\.py$` and not already among
   the listed module names; AND no listed module's `imports` references another listed
   module (a fully disconnected set — the exact measured graph-bfs shape). When it
   fires, ADD a new module entry named `entrypoint` whose `exports` is a minimal
   `def main():` and whose `imports` lists every currently-listed module name —
   additive only, mirroring `_repair_plan_dangling_imports`'s convention (never renames
   or removes an existing module). When ANY listed module already imports another
   (an existing wiring relationship — genuinely ambiguous which module, if any, should
   host the entrypoint), or the entrypoint/module shapes are malformed, make NO repair
   — return the plan unchanged so `validate_plan` still rejects it exactly as before.
   Never raises. Wrap the new function with `# #EXT-036-REQ-32 Start` / `# #EXT-036-REQ-32
   End`.
2. Wire it into `build_system`'s plan-repair sequence (~lines 1519-1531): call it right
   after `_repair_plan_entrypoint` and before `_repair_plan_dangling_imports`; fold its
   note into the existing `plan_repair` string alongside the other two notes. Wrap the
   changed lines with `# #EXT-036-REQ-32 Start` / `# #EXT-036-REQ-32 End`.
3. Confirm, against the LIVE served model, that `build_system(graph_bfs_sentence, ...,
   llm=build_llm())` no longer rejects at the plan stage (the coherence-rejection note is
   gone; the build proceeds to the BUILD phase) — this is the WIN this task unblocks; it
   does not require the build to fully oracle-pass (a separate reasoning question).
4. Add `tests/test_ext036_planrepair_multi.py` (no live model, offline `_extract_json`
   plan literals only): (a) the exact measured graph-bfs shape (2 disconnected modules,
   mismatched entrypoint) is repaired and `validate_plan(repaired) == []`, asserting the
   added module's name/imports; (b) the pre-existing `test_ext036_planrepair.py`
   multi-module case (`cli.py` imports `calculator.py`) is UNCHANGED by
   `_repair_plan_entrypoint_multi` (still rejected) — proving no regression to that
   pinned conservatism; (c) a 3-module chain (`a.py`->`b.py`->`c.py`) with a mismatched
   entrypoint is left untouched/still rejected (an existing wiring relationship makes it
   ambiguous); (d) a malformed-entrypoint variant (e.g. not ending in `.py`, containing a
   space, or empty) is left untouched/still rejected; (e) the function never raises on
   malformed/edge-case plan input (`None`, missing keys, non-list `modules`, non-dict
   module entries, non-string entrypoint); (f) the existing single-module repair test
   (`test_ext036_planrepair.py`) stays green, unaffected by this new function.
5. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change baseline, 2315 passed / 2 skipped).

#### Implements
- [REQ-32] Deterministic plan-repair for MULTI-module "entrypoint not a listed module"
  (this task introduces AND fully implements REQ-32's mechanism)

#### Implements
- [REQ-31] 7B-GENERATE acceptance checks (this task introduces AND fully implements
  REQ-31's offline mechanism; wiring into `build_system` + the live A/B gate measurement
  against `review_checks`/baseline remain open follow-ups, owned by the parent)

### [TASK-43] Robust `_extract_json`: balanced extraction + bounded repair (REQ-33, plan-coherence gap-hunt 2026-07-06)

MEASURED (plan-coherence gap-hunt, 40 builds = 20 CREATION tasks x2 draws): the ONLY
not-shipped failures were `todo-list-cli` on both draws, note "planner produced no
parseable JSON plan". Repro: the plan's `"acceptance"` field is a long prose string
that on some draws carries an UNESCAPED literal control character (a raw newline)
inside the JSON string value; `_extract_json` (`harness/system_builder.py:290-300`)
does one greedy `opener.*closer` regex + a single `json.loads` with no repair, so it
returns `None` and the build never ships. This function backs the PLAN step AND every
acceptance-checks/fix extraction call site, so the fix is a generic robustness lift.

#### Steps
1. In `harness/system_builder.py`, add two new private helpers right above
   `_extract_json`: `_balanced_span(text, opener, closer)` — find the first `opener`
   and return the substring up to its DEPTH-MATCHED `closer` via a string-literal-aware
   scan (tracks `in_string`/backslash-escape state so quote/escape handling — including
   a malformed literal control char inside a string — never perturbs the brace/bracket
   depth count); returns `None` if no balanced span is found. And
   `_repair_json_candidate(text)` — a single string-aware pass that (i) escapes any
   literal control character (`\n`/`\r`/`\t`/other byte < 0x20) found INSIDE a string
   literal to its proper JSON escape, and (ii) drops a comma immediately before a
   closing `}`/`]` (outside any string, skipping intervening whitespace). Never raises;
   returns the input unchanged on falsy input. Wrap both with `# #EXT-036-REQ-33 Start`
   / `# #EXT-036-REQ-33 End`.
2. Add `_strip_md_fences(raw)`: drop any line that is just a fence marker
   (```` ``` ````/```` ```json ````, regex `^\s*```` optionally followed by a lang tag),
   keep everything else — a no-op when no `` ``` `` is present. Wrap with the same
   markers.
3. Rewrite `_extract_json(raw, opener, closer)` so the EXISTING greedy
   `re.search(re.escape(opener) + r".*" + re.escape(closer), raw, re.DOTALL)` +
   `json.loads(m.group(0))` call is preserved VERBATIM as the FIRST thing tried and
   returned on success — this is the byte-identical-valid-path guarantee (★ CRITICAL):
   any input the OLD code already parsed takes this exact branch, unchanged. Only when
   that fails (no match, or `json.loads` raises) does it fall through to: (a) strip
   markdown fences via `_strip_md_fences`; (b) try `_balanced_span` on the
   fence-stripped text, then a second greedy match on the fence-stripped text (skip if
   identical to a candidate already tried), then the original (unstripped) greedy span
   if one existed — parsing each with `json.loads`, returning on first success; (c) if
   still unparsed, run `_repair_json_candidate` on each of those candidates (in the same
   order) and retry `json.loads`, returning on first success; (d) return `None`. Never
   raises at any step. Wrap the changed function body with `# #EXT-036-REQ-33 Start` /
   `# #EXT-036-REQ-33 End`. Same signature; no caller changes anywhere.
4. Add `tests/test_ext036_extract_json_repair.py` (no live model): (a) the MEASURED
   todo-list shape — a plan-shaped JSON object whose `"acceptance"` string contains a
   raw embedded newline — now returns the correct dict via
   `_extract_json(raw, "{", "}")` (was `None` before this task; assert by literally
   running the OLD single-greedy-regex-then-json.loads logic inline in the test and
   confirming it fails, to prove this is a genuine fix not a pre-existing pass); (b) a
   valid JSON object followed by trailing prose containing a stray `}` returns the
   correct object; (c) several already-valid JSON payloads (escaped `\n`, nested
   objects/arrays, a valid `[`,`]` checks-array) parse to the IDENTICAL object as the
   pre-change greedy-regex+`json.loads` reference implementation kept inline in the
   test as an oracle — the explicit regression guard; (d) genuinely non-JSON garbage
   input returns `None`, never raises; (e) a trailing-comma-only defect
   (`{"a": 1, "b": [1, 2,],}`-shaped) is repaired and parses; (f) `_balanced_span` and
   `_repair_json_candidate` never raise on `None`/empty/malformed input.
5. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change baseline, 2322 passed / 2 skipped).

### [TASK-44] Iterative REPLAN-AS-MODIFICATION build recovery (REQ-34, owner idea, roadmap 57e8341)

Today's `_repair_system` (REQ-5) only ever does a per-module, per-check PATCH on
acceptance failure. The owner's richer idea: step BACK and REPLAN — assess where the
project actually landed vs the spec's target, produce a MODIFICATION request bridging
the gap, apply it via the existing MODIFICATION plane (`modify_system`, REQ-14), re-check,
and ITERATE. Reuses proven machinery; no new apply mechanism.

#### Steps
1. In `harness/system_builder.py`, right after `_repair_system` (before `_result`), add
   `MAX_REPLAN_ROUNDS = 3`, `_build_replan_request(spec, root, built, checks, unmet)`
   (builds a plain modification request from the spec text + `_sources_blob(built)` +
   each failing check's NAME and its REAL run error via `_run_check_verbose` — never the
   check's own `code`), and `_replan_as_modification(spec, root, built, checks, unmet,
   llm, *, max_rounds=MAX_REPLAN_ROUNDS, runtime=None)`: a bounded loop that, per round,
   builds the request, calls `modify_system(dict(built), mod_request, root, llm=llm,
   runtime=runtime)`, re-runs the FULL `checks` list, and accepts the round ONLY when the
   unmet COUNT strictly decreases AND no check that passed before the round now fails (a
   SET comparison); on reject, revert every module `modify_system` touched back to its
   pre-round content (disk via `_jailed_write` + the returned dict) and stop. Never
   raises. Wrap with `# #EXT-036-REQ-34 Start` / `# #EXT-036-REQ-34 End`.
2. Add a keyword-only `replan_on_failure: bool = False` parameter to `build_system`'s
   signature + docstring. After the existing REQ-5 `_repair_system` call, when
   `replan_on_failure` is `True` and `unmet` is still non-empty, call
   `_replan_as_modification` and fold a diagnostic note ("replan-as-modification: N
   round(s), unmet X->Y") into the returned `note` only when at least one round was
   accepted. Default `False` must leave `build_system` byte-identical to before this
   task (the whole block is skipped; no note/behavior change). Wrap the changed lines
   with `# #EXT-036-REQ-34 Start` / `# #EXT-036-REQ-34 End`.
3. Add `tests/test_ext036_replan.py` (offline, canned `llm`/stubbed `modify_system`, no
   live model): (a) FIXES — a synthetic 2-check-failing build with a canned
   `modify_system` fix reaches `done=True` after 1 replan round through the full
   `build_system(..., replan_on_failure=True)` pipeline; (b) a canned `modify_system`
   that makes no improvement stops after round 1 (no infinite loop); (c) a canned
   `modify_system` that fixes one check but regresses a different, previously-passing
   one is REJECTED and reverted (disk + dict), never regressing the original passing
   check; (d) a canned `modify_system` that fixes exactly one more check per round
   across 4 starting-unmet checks is capped at exactly `MAX_REPLAN_ROUNDS` accepted
   rounds; (e) `replan_on_failure=False` (default, implicit and explicit) never invokes
   `modify_system` and produces a result identical to before this task on a fixed
   synthetic failing build; (f) the modification request built for the model never
   contains a hidden expected-output sentinel embedded only in a failing check's own
   assertion code (only its NAME + its REAL run error); (g) never raises when
   `modify_system` raises, and is a complete no-op when the build is already done.
4. Run `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change baseline, 2356 passed / 2 skipped).

#### Implements
- [REQ-34] Iterative REPLAN-AS-MODIFICATION build recovery (this task introduces AND
  fully implements REQ-34's offline mechanism; a LIVE measurement of whether it lifts
  any repair-failing hard-tier CREATION-suite task remains open, owned by the parent)

#### Implements
- [REQ-33] Robust `_extract_json`: balanced-bracket extraction + bounded repair for
  malformed model JSON (this task introduces AND fully implements REQ-33's mechanism)

### [TASK-45] `modify_system` can ADD new modules, not just regenerate existing ones (REQ-35, owner steer, roadmap 45508cf, task #128)

`modify_system` (REQ-14) pipeline: assemble current system -> BASELINE (record passing
checks + importable modules) -> `_identify_targets(modules, mod_sentence, llm)` returns
EXISTING module names only -> `_regenerate_module` each -> assemble -> REGRESSION GATE
(behavioral `baseline_passing` + `import_regressed`) -> on any regression REVERT
changed modules to `pre_mod`. It can NEVER add a new module a modification genuinely
needs (e.g. "add rate-limiting" to a system with no rate-limiter module yet).

#### Steps
1. In `harness/system_builder.py`, add `_identify_new_modules(modules, mod_sentence,
   llm, *, max_new=MAX_NEW_MODULES=3) -> list`: a small model judgment (a new
   `IDENTIFY_NEW_MODULE_PROMPT`) asking whether the change needs a module that does NOT
   already exist. AMBIGUITY-GUARDED: an empty/falsy response or the literal `NONE`
   (case-insensitive) yields `[]`; otherwise parse a JSON list (`_extract_json`) and
   keep only entries that are strings, NOT already in `modules`, match a plausible bare
   `*.py` filename (`^[A-Za-z_][A-Za-z0-9_]*\.py$`), de-duplicated, bounded to
   `max_new`. Never raises (an `llm.complete` exception -> `[]`). Wrap with
   `# #EXT-036-REQ-35 Start` / `# #EXT-036-REQ-35 End`.
2. Add `_build_new_module(name, mod_sentence, modules, llm, *,
   max_repair=MAX_REPAIR_ATTEMPTS) -> tuple`: builds ONE brand-new module from scratch
   (a new `NEW_MODULE_PROMPT` given the existing modules' sources for import context),
   then the SAME bounded syntax-gate/repair loop `_regenerate_module`/`_build_module`
   use (`syntax_ok`/`REPAIR_PROMPT`, reused verbatim — no module-building logic
   duplicated). Wrap with the same markers. Choose prompt wording for both new prompts
   that shares NO substring with any existing routed prompt-key used across the
   `tests/test_ext036_*.py` canned-llm stubs (`"MODIFICATION TARGET"`, `"APPLY
   MODIFICATION"`, `"SYNTAX ERROR"`, `"RUNNABLE PYTHON CODE"`, `"ACCEPTANCE CHECKS"`,
   `"COMPLETE Python module"`, `"build PLAN"`, etc.) so every pre-existing stub's
   default/fallback branch (not this task's new step) keeps routing every pre-existing
   test's prompts exactly as before.
3. In `modify_system`, right after `targets = _identify_targets(...)`, call
   `new_module_names = _identify_new_modules(...)` (ALWAYS runs, so "no new module" is
   itself a genuine judgment, not a skipped step). Change the early-return guard to
   `if not targets and not new_module_names: return ...` (unchanged message). Build each
   named new module via `_build_new_module` (skip on exception/non-syntax-ok, mirroring
   the existing per-target loop) into a new `added_names` list; change the "no
   syntactically valid change" guard to `if not changed_names and not added_names`.
   Assemble each added module via `_jailed_write(root, name, code, runtime)` (Tenet 1)
   AFTER the existing regenerated-module assembly loop, folding any assembly failure
   into the SAME revert path (added modules removed from disk + dict too, never a
   half-written system). Extend BOTH the assembly-failure revert AND the REGRESSION-GATE
   revert (behavioral `regressed` OR `import_regressed`) to additionally, on that same
   path, `modules.pop(name, None)` and best-effort `(root / name).unlink()` for every
   name in `added_names` — never leaving an orphan file or a half-wired system. Fold
   added-module names into the returned `note` on both the success and failure paths.
   Wrap every changed/added line with `# #EXT-036-REQ-35 Start` / `# #EXT-036-REQ-35
   End`. BYTE-IDENTICAL when `new_module_names`/`added_names` end up empty (the
   injectable-idiom: every new loop is then a 0-iteration no-op) — every pre-existing
   `tests/test_ext036_modify.py` / `tests/test_ext037_buildsystem_jaros_write.py` /
   `tests/test_ext037_root_enforcement.py` test must pass completely unmodified.
4. NEVER raises (Tenet 3): matches `modify_system`'s existing never-raise contract at
   every new step; `applied=False` + a diagnostic `note` on any failure. NO ORACLE LEAK:
   the identify/build prompts see only the existing module sources + the modification
   sentence, never a hidden/expected output.
5. Add `tests/test_ext036_modify_add.py` (OFFLINE, canned llm mirroring
   `tests/test_ext036_modify.py`'s `_CannedModifyLlm` fixture style, no live model, no
   Jetson): (a) a purely-additive modification (no existing target) adds a new module
   and keeps it when nothing regresses (file genuinely on disk + in the returned dict);
   (b) BYTE-IDENTICAL when the llm names no new module (a clean regenerate-only
   modification behaves exactly as before, no stray new-module file); (c) a regression
   (a changed existing module breaks a previously-passing baseline check) REVERTS the
   regenerated module(s) AND REMOVES the added module (file gone + dropped from the
   returned dict); (d) bounded to at most 3 new modules even when the model names 5;
   (e) ambiguity-guarded — a vague/empty/`NONE` answer (and malformed/duplicate/existing
   names) adds nothing; (f) never raises when the model raises at either the identify or
   the build step; (g) `runtime` is genuinely threaded to the added module's write (a
   fake recording runtime, mirroring `tests/test_ext037_buildsystem_jaros_write.py`'s
   `_FakeApplyRuntime`, proves the write goes through a real `code.write_file` Decision).
   Also re-run the pre-existing `tests/test_ext036_modify.py`,
   `tests/test_ext037_buildsystem_jaros_write.py`, and
   `tests/test_ext037_root_enforcement.py` to confirm byte-identical behavior. Run the
   FULL `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q`, confirm
   green, and record the exact pass/skip count + exit code (no regression vs the
   pre-change baseline).

#### Implements
- [REQ-35] `modify_system` can ADD a new module, not just regenerate existing ones
  (this task introduces AND fully implements REQ-35's mechanism)

### [TASK-46] A spec-DERIVED behavioral PROPERTY check for build_system acceptance (REQ-37, PGS-style, arXiv 2506.18315, task #130)

The crash-based REQ-26 minimum acceptance floor (+ REQ-27's error-marker/round-trip
strengthening) catches a system that crashes or gracefully prints its own error, but
nothing in the composed checklist catches a system that never crashes yet behaves
semantically WRONG (e.g. a priority queue that dequeues in the wrong order, a codec whose
`decode(encode(x)) != x`). A PGS-style, spec-DERIVED behavioral PROPERTY check closes that
class. SACRED-SAFE BY CONSTRUCTION: this only ever ADDS a check to the composed acceptance
checklist — it can flip `done` True->False (catching a genuine semantic bug), never the
reverse, so it cannot manufacture a false-done; the only risk is an over-strict
false-negative, minimized by the tri-state grading rule below.

#### Steps
1. In `harness/system_builder.py`, add `_derive_spec_properties(spec, llm) -> list[dict]`:
   ONE model judgment given the SPEC STRING ONLY (never the built code — no leak, no
   self-deception cycle) asking for 0-2 ABSTRACT behavioral properties the system must
   satisfy (e.g. a priority queue -- "an item added with higher priority is dequeued
   before a lower-priority item"; a counter/notes system -- "the reported count increases
   by exactly 1 after each add"; a codec -- "decoding the encoding of X returns X"). If
   none is clearly derivable, `[]` — never invent one. Bounded to
   `MAX_SPEC_PROPERTIES = 2`; guarded (any model/parse failure -> `[]`); never raises.
   Wrap with `# #EXT-036-REQ-37 Start` / `# #EXT-036-REQ-37 End`.
2. Add `_build_property_check(prop, mods, llm, *, plan=None) -> dict | None`: converts one
   property into a runnable acceptance check that exercises the BUILT CLI through a REAL
   subprocess invocation, reusing `_minimum_entry_filename` (entrypoint resolution) and the
   SAME `_is_subprocess_check` filter (`_propose_subprocess_checklist`'s convention) already
   proven elsewhere in this module — no duplicated CLI-exercising logic. Any unusable
   property, no resolvable entrypoint, a model/parse failure, or code that fails the
   subprocess-check filter returns `None` (fewer checks, never a fabricated one). Wrap with
   the same markers.
3. Add `_wrap_property_check(code) -> str`: a DETERMINISTIC (no model) wrapper enforcing the
   TRI-STATE grading rule regardless of what the model wrote — the property-check body runs
   inside a function; only a genuine `AssertionError` from it is graded a definitive
   VIOLATION (non-zero exit, the check FAILS); ANY other exception (the CLI couldn't be
   invoked as the check assumed, a bad invocation, ...) is INCONCLUSIVE and exits 0 (a PASS,
   never manufacturing a false-negative); a clean run (SATISFIED) also exits 0. `_run_check`/
   `_run_check_verbose` (REQ-4/REQ-5) are reused UNMODIFIED to actually run the wrapped
   check — no new execution path.
4. In `build_system`, add an injectable keyword parameter `spec_properties: bool = False`
   (default is a complete no-op, keeping `build_system` BYTE-IDENTICAL to before this task
   for every existing caller/test). When `True`, immediately after the optional
   `check_reviewer` step (REQ-30) and before the `if not checks:` empty-checklist guard,
   call `_derive_spec_properties(spec, llm)`, and for each returned property call
   `_build_property_check(prop, mods, llm, plan=plan)`; any non-`None` result is APPENDED to
   `checks` (purely additive to the union — never removes/replaces an existing check).
   Guarded (`try`/`except Exception: pass`) so a property-derivation failure never raises and
   never reduces the checklist below what it would otherwise have been. Wrap every
   changed/added line with `# #EXT-036-REQ-37 Start` / `# #EXT-036-REQ-37 End`.
5. NO ORACLE LEAK: `_derive_spec_properties`'s prompt is formatted from the SPEC STRING
   alone — never the built module sources, the acceptance checklist, or any expected output.
6. Add `tests/test_ext036_property_check.py` (OFFLINE, canned llm, no live model, no
   Jetson): (a) a wrong-ordering priority-queue build -> property VIOLATED -> the check
   FAILS -> `build_system(..., spec_properties=True)` reports `done=False` (the SAME wrong
   build reports `done=True` with the flag off, isolating the property check as the cause);
   (b) a correct priority-queue build -> SATISFIED -> `done=True` (no new false-negative);
   (c) an inconclusive/broken property test (a `subprocess.check_call` against a
   nonexistent script, raising `CalledProcessError` before its own `assert` is ever reached)
   is treated as a PASS, plus a mirror-image control (a genuine `AssertionError` with no
   exotic exception) still FAILS; (d) a task with no derivable property (`"[]"`) adds no
   check, behavior unchanged (incl. bounding to `MAX_SPEC_PROPERTIES` and `None` returns on
   an unusable property/no entrypoint/malformed output/an in-process-only check); (e) never
   raises when the model raises at either the derivation or the build-check step, at both
   the helper-function level and through the full `build_system` call; (f) no-oracle-leak —
   the derivation prompt is asserted BYTE-EQUAL to `PROPERTY_DERIVATION_PROMPT.format(spec=spec)`,
   and none of the built module's source/plan JSON ever appears in it; (g) the flag off (by
   omission, and explicitly `False`) never calls `_derive_spec_properties` at all
   (monkeypatched to raise if called) and matches the explicit-`False` result exactly. Run
   the FULL `python -m harness.run_with_heartbeat -- python -m pytest tests/ -q` and confirm
   it stays green at the new count, with no regression vs. the pre-change baseline. Do NOT
   commit — a 20-task trustbar gate + the architect handle promotion/commit.

#### Implements
- [REQ-37] A spec-DERIVED behavioral PROPERTY check for build_system acceptance (this task
  introduces AND fully implements REQ-37's offline mechanism; the 20-task trustbar
  measurement gating opt-in->default-on promotion remains open)

### [TASK-47] Generalize the multi-module entrypoint plan-repair to any acyclic wired DAG (REQ-32 generalization, MEASURED 2026-07-07 on `todo-list-cli`)

MEASURED (per-class creation-scoreboard run, 2026-07-07): `todo-list-cli` still builds 0
files. `_repair_plan_entrypoint_multi` (TASK-42) only fires for a FULLY DISCONNECTED
module set; the model's plan for this task is a coherent WIRED DAG —
`data_manager.py` + `cli_handler.py` where `cli_handler` imports `data_manager` — with
`entrypoint: "main.py"` unlisted. TASK-42's "any sibling import -> decline" guard trips
on the existing `cli_handler -> data_manager` edge and the whole plan is rejected.
Because the repair only ever ADDS a brand-new entrypoint module (never renames/chooses an
existing one), the "which module hosts the entrypoint" ambiguity TASK-42 was guarding
against never actually applies — the only open question is what the new module should
import, and the DAG-correct, unambiguous answer is the ROOT modules (in-degree 0 within
the listed set).

#### Steps
1. In `harness/system_builder.py::_repair_plan_entrypoint_multi` (`# #EXT-036-REQ-32`
   block), replace the "decline if any listed module imports a sibling" guard with a
   root-modules computation: collect every module name that is imported by another
   listed module (`imported_by_sibling`), then `roots = [n for n in names if n not in
   imported_by_sibling]`. If `roots` is empty (every module is imported by another — a
   cycle), decline exactly as before (`validate_plan`'s own cycle check keeps a cyclic
   plan rejected). Otherwise add the new entrypoint module importing `roots` (not all
   `names`) and fold `roots` into the returned note ("...importing roots
   {roots}"). A fully disconnected set has every module as a root, so `roots == names`
   and behavior reduces EXACTLY to TASK-42 (strict superset, no regression). Update the
   function's own docstring/SAFETY list to describe the new roots-based condition instead
   of the old "any sibling import -> decline" one, and drop the stale reference to the
   now-renamed `test_multi_module_mismatched_entrypoint_still_rejected` test.
2. Update `tests/test_ext036_planrepair_multi.py`: the graph-bfs disconnected-shape
   assertion now expects the note phrased "importing roots [...]"; convert the two
   previously-"left untouched" wired/chain fixtures
   (`EXISTING_WIRING_AMBIGUOUS_PLAN`/`CHAIN_AMBIGUOUS_PLAN`) into repaired-and-coherent
   assertions (`validate_plan(repaired) == []`, added module imports exactly the single
   root); update the module docstring and fixture comments to describe the
   generalization.
3. Update `tests/test_ext036_planrepair.py`:
   `test_multi_module_mismatched_entrypoint_still_rejected` (pinned `cli.py` imports
   `calculator.py`, entrypoint `main.py`) is now REPAIRED, not rejected — rename it to
   `test_multi_module_wired_dag_mismatched_entrypoint_now_builds` and assert
   `shipped=True`, the `plan_repair` note importing root `['cli.py']`, and `main.py`
   written to disk through the full `build_system` pipeline.
4. Run `python -m pytest tests/test_ext036_planrepair_multi.py
   tests/test_ext036_planrepair.py -q` (targeted) then the broader
   `python -m pytest tests/test_ext036*.py -q` (no regression). Live re-measurement of
   `todo-list-cli` on the served Jetson model remains open, owned by the parent loop —
   this task's mechanism is proven OFFLINE only.

#### Implements
- [REQ-32] Deterministic plan-repair for MULTI-module "entrypoint not a listed module"
  (this task GENERALIZES REQ-32's TASK-42 mechanism from the fully-disconnected special
  case to any acyclic wired DAG; a live re-measurement of `todo-list-cli` on the served
  model remains an open follow-up, owned by the parent)

### [TASK-48] Structural-bracket recovery stage for `_extract_json` — missing `}` before `]` (REQ-33 extension)

MEASURED (repro artifact `.jaros-data/artifacts/todo_rawplan.log`): gemma's `todo-list-cli`
plan embeds a whole multi-line Python class body as an export "signature" JSON string, and
DROPS the `}` that closes the export object before the `]` ending `exports` — e.g.
`"signature": "...return self.items"\n      ],` where a `}` was owed before that `]`.
`_extract_json`'s existing greedy-match / `_balanced_span` / `_repair_json_candidate`
stages (TASK-43, REQ-33) only escape control characters and drop trailing commas — none of
them can insert an OMITTED structural closer — so `json.loads` fails ("Expecting ','
delimiter"), `_extract_json` returns `None`, `plan=None`, and 0 files build (class scores
0/3). The SAME defect class (a dropped internal structural closer) also kills
`kv-store-ttl` on qwen. This task adds one more, FINAL, string-literal-aware structural
recovery stage — additive, reached only after every existing path has already failed.

#### Steps
1. In `harness/system_builder.py`, add a new private helper `_recover_missing_braces(text:
   str) -> str` near `_repair_json_candidate` (inside the `# #EXT-036-REQ-33` marker
   block): walk `text` left-to-right keeping a stack of open `{`/`[` characters, tracking
   JSON string-literal state (`in_string` + backslash-escape awareness, mirroring
   `_balanced_span`'s scan) so brackets appearing INSIDE a string value (e.g. the embedded
   Python class body's own `{`/`}`/`[`/`]`) never perturb the stack. When a closer (`}` or
   `]`) is reached whose required opener is NOT the innermost entry on the stack but IS
   present deeper in the stack, first emit the closers for every unclosed entry above that
   depth (converting each to its matching closer, innermost first), then emit the actual
   closer, and pop the stack down to (and including) the matched entry — this is exactly
   the "insert the omitted `}`" recovery. When a closer's required opener is not found
   anywhere in the stack, pass it through unchanged (an unmatched extra closer is a
   different malformation, not this task's concern). Track a `changed` flag; if nothing
   was ever inserted, return the input `text` object unchanged (byte-identical, no
   reconstruction) — never fabricate keys/values/commas, only structural closers. Do NOT
   attempt to close anything at end-of-string (a stack still open when the input simply
   ends is END-OF-INPUT TRUNCATION, a different class — leave it to fail honestly, exactly
   as today). Pure stdlib, never raises on `None`/empty/malformed input.
2. Wire `_recover_missing_braces` into `_extract_json` as the LAST resort, after the
   existing greedy `json.loads`, `_balanced_span`, and `_repair_json_candidate` loops have
   all failed to return: for each candidate span already gathered in `candidates`, compute
   `recovered = _recover_missing_braces(candidate)`; if `recovered == candidate` (no
   structural insertion was possible) skip to the next candidate; otherwise try
   `json.loads(recovered)` and, if that still fails, `json.loads(_repair_json_candidate(recovered))`
   (composing with the existing control-char/trailing-comma repair); return the first
   candidate that parses. Only after every candidate has been tried through this new stage
   does the function fall through to the existing final `return None`. No change to the
   function's signature or to any code path preceding this new stage (the byte-identical
   valid-path guarantee and the TASK-43 balanced/repair paths are untouched and still tried
   first). Wrap the added/changed lines with `# #EXT-036-REQ-33 Start` / `# #EXT-036-REQ-33
   End` (extending the existing marked block).
3. Tests `tests/test_ext036_plan_brace_recovery.py` (new, OFFLINE — no live model, no
   network): (a) the captured plan bytes in `.jaros-data/artifacts/todo_rawplan.log`
   (the fenced JSON body) now parse via `_extract_json(raw, "{", "}")` into a plan dict with
   `modules` present and the export's `signature` string intact (assert it still contains
   the embedded class body's literal text, proving no content was fabricated or
   truncated); confirm the OLD (pre-recovery) code path genuinely fails on this input first
   (a regression oracle, mirroring `test_ext036_extract_json_repair.py`'s
   `_old_extract_json`), so this is a proven genuine fix, not a pre-existing pass. (b) At
   least 6 already-VALID JSON samples — including one with nested arrays-of-objects and at
   least one whose string VALUES literally contain the characters `{`, `}`, `[`, `]`, and
   `,` — each pass through `_recover_missing_braces` and come back BYTE-IDENTICAL
   (`recovered is text or recovered == text` with `changed` never true), and
   `_extract_json` returns the exact SAME parsed result as it did before this task (call
   the existing `_old_extract_json`/direct pre-TASK-43 style oracle or simply assert
   `json.loads(sample) == _extract_json(sample, opener, closer)` for each). (c) A payload
   truncated at end-of-input (e.g. an object that simply stops mid-value with no closing
   brackets at all) is left UNCHANGED by `_recover_missing_braces` (no fabricated closers)
   and `_extract_json` still returns `None` for it, exactly as before. (d)
   `_recover_missing_braces` never raises on `None`/empty/malformed input.
4. Run `python -m pytest tests/test_ext036_plan_brace_recovery.py -q` and the existing
   plan-parse/repair unit test file (`tests/test_ext036_extract_json_repair.py`) `-q` only —
   confirm both green with no change to the existing file's pass count (the
   byte-identical-valid-path + TASK-43 regression guards must still hold). Do NOT run the
   broader `tests/test_ext036*.py` glob or any `-k` sweep in this task (a live-model test
   elsewhere in that glob triggers a Jetson model-swap that must not run here); the full
   suite re-run remains the parent/architect's responsibility at integration time.

#### Implements
- [REQ-33] Robust `_extract_json`: balanced-bracket extraction + bounded repair for
  malformed model JSON (extends TASK-43's mechanism with a further, FINAL structural
  bracket-recovery stage for the MEASURED "dropped structural closer inside a nested
  container" defect class; additive, reached only after every existing parse path has
  already failed, so every previously-parseable plan is unaffected)

### [TASK-49] Deterministic module-body repair: length-guard / constant-index contradiction (REQ-39)

MEASURED (repro `.jaros-data/artifacts/kv_diag.log`, `cli.py`): the `kv-store-ttl` `set`
handler gemma writes is `if command == "set": if len(parts) == 3: key = parts[1]; value =
parts[2]; ttl = int(parts[3]); ...` — but `set <key> <value> <ttl>` splits into 4 tokens, so
`len(parts) == 3` is always False and every `set` SILENTLY NO-OPS (all 3 Get/Delete
behavioral checks fail 0/3). The guard is internally self-contradictory with its own body: it
requires `len(parts) == 3` yet indexes `parts[3]` (needs `len(parts) >= 4`). `build_system`'s
bounded acceptance-driven repair loop (REQ-5) already fed this failure back for 2 rounds live
and gemma could not fix it — a deterministic tool is the lever, mirroring
`harness/import_wiring.py::resolve_imports` (EXT-035 REQ-3): a pure, AST-only, never-raising,
purely-additive/corrective repair over generated module code, wired at the same spot in
`build_system`'s assemble path.

#### Steps
1. In `harness/system_builder.py`, right after `_build_module`/`syntax_ok` (the per-module
   code-gate section), add a new `# #EXT-036-REQ-39` block implementing
   `repair_guard_index_mismatch(code: str) -> str`: parse `code` with `ast.parse` (any
   exception → return `code` unchanged); walk every `ast.If` node; for each whose `test` is a
   SIMPLE, single (non-chained, non-boolean) comparison `len(<Name>) OP <int constant>`
   (either operand order — normalize reversed forms by flipping the operator), where `OP` is
   one of `{==, !=, <, <=, >, >=}`: only the CLOSED/bounded-above ops (`==`, `<`, `<=`) can
   ever be a PROVABLE, guard-wide contradiction (the guard admits a bounded set of lengths,
   so every admitted length can fail a fixed index); `!=`/`>`/`>=` are open-ended (some
   admitted length always leaves the index reachable) and are NEVER repaired. For a
   closed-op guard on name `seq`, scan the `If`'s own true-branch `body` (recursing into
   nested control flow — `if`/`for`/`while`/`try` — but NOT into a nested
   `def`/`class`/`lambda`, a different execution scope) for every `ast.Subscript` on the
   SAME name `seq` whose index is a non-negative int `ast.Constant` (never a slice/variable/
   negative index) and take the MAXIMUM such index `M`. If the guard's own bounded cap (the
   largest length value the guard admits: `N` for `==`/`<=`, `N-1` for `<`) is `<= M` (a
   provable contradiction — every admitted length is too small for index `M`), compute the
   MINIMAL replacement constant that fixes it (`M+1` for `==`/`<=`, `M+2` for `<`) and record
   a text-level edit at that literal's own AST span (`lineno`/`col_offset`/`end_lineno`/
   `end_col_offset`) — never at any other span. Apply all recorded edits (rightmost-first, by
   absolute offset, so multiple edits in one module never invalidate each other's positions)
   and return the result; return `code` UNCHANGED (same object/byte-identical) when no edits
   were made. Never raises on `None`/empty/malformed input.
2. In `build_system`, immediately after the existing deterministic import-resolver wiring
   (the `#EXT-035-REQ-3` block that runs `resolve_imports` over every module in `built`,
   right before `# 3. ASSEMBLE`), add a new `# #EXT-036-REQ-39` block that calls
   `built[name] = repair_guard_index_mismatch(built[name])` for every module in `built`.
   Purely additive: does not touch `build_system_escalating`/`build_system_governed`/
   `build_system_best_of_k`/`modify_system`, any plan-repair function, any acceptance
   oracle, or `validate_plan` — a no-op for any module without this exact defect shape.
3. Tests `tests/test_ext036_guard_index_repair.py` (new, OFFLINE — no model, no network):
   (a) the EXACT captured buggy `set` handler from `.jaros-data/artifacts/kv_diag.log` is
   repaired to a consistent `len(parts) == 4` guard; the repaired module still compiles
   (`py_compile`/`compile()`); a REAL subprocess run of the repaired module (paired with the
   captured `store.py`), fed a `set foo bar 100` + `get foo` stdin sequence, prints the
   stored value (not `"none"`) — proving `set` no longer no-ops; a control run of the
   ORIGINAL (unrepaired) module through the SAME real-subprocess harness independently
   confirms it genuinely DOES no-op first (a regression oracle, not a coincidental pass).
   (b) At least 8 valid/ambiguous fixtures are returned BYTE-IDENTICAL: a correct
   `len(parts)==4` guard over `parts[3]`; a guard on a different name than the one indexed;
   `x[-1]`; `x[i]`; `x[1:3]`; no length guard at all; an index confined to an `else` branch;
   a compound boolean guard (`len(x)==3 and flag`); and an open-ended `>`/`>=` guard whose
   body indexes past the guaranteed minimum. (c) `<`/`<=`/`!=` guards and their REVERSED
   operand forms (`N OP len(seq)`) are each covered: a genuine `<` contradiction repairs to
   its own minimal constant, a genuine `<=` contradiction repairs to its own minimal
   constant, both in REVERSED form too (`N > len(seq)`/`N >= len(seq)`), and a `!=` guard
   (plain and reversed) is NEVER touched regardless of its body's index. (d)
   `repair_guard_index_mismatch` never raises on `None`, `""`, or syntactically malformed
   Python.
4. Run `python -m pytest tests/test_ext036_guard_index_repair.py -q` and the existing
   targeted code-repair/import-resolver unit test file(s) (e.g. whichever file already covers
   `resolve_imports`/`_repair_plan_dangling_imports`/similar deterministic repairs) `-q` only
   to confirm no regression. Do NOT run the broader `tests/test_ext036*.py` glob, the full
   `tests/test_ext036_system_builder.py`, or any `-k` sweep in this task (a live-model test
   elsewhere in that glob triggers a Jetson model-swap that must not run here); the full
   suite re-run remains the parent/architect's responsibility at integration time.

#### Implements
- [REQ-39] Deterministic module-body repair: length-guard / constant-index contradiction
  (the MEASURED kv-store-ttl `set`-handler no-op defect and its general class — a guard
  self-contradicting its own body's constant-index access on the same sequence)

### [TASK-50] Ratchet the creation-suite frontier — 4 real-system HARDER_SLICE classes (REQ-20)

MEASURED (docs/GAP-MAP.md, 2026-07-08): the toy-CLI tier is now ~92% mastered (all 20
`ALL_CREATION_TASKS` classes buildable), so it no longer DISCRIMINATES — it stopped being an
honest frontier instrument (PRIME-001 difficulty ratchet). TASK-24 already pushed `HARDER_SLICE`
into a `"highly-complex"` tier with `lru-cache-cli`; this task adds 4 MORE `"highly-complex"`
classes drawn from the real-systems frontier (PRIME-001's reframe: build REAL systems — real
persistence, real parsing, real state — not just harder toy logic), so the tier has enough mass
to be a genuine next rung rather than one lone task.

#### Steps
1. In `harness/system_suite.py`, inside the existing `HARDER_SLICE` list (append after the
   current 8 entries, keeping them byte-for-byte unchanged), add 4 new contract-precise
   `CreationTask`s, all tier `"highly-complex"`, each requiring materially more logic/state than
   the existing tier: `sqlite-persistent-kv-cli` (a real `sqlite3`-backed key-value store whose
   `set`/`get` values must survive a completely separate later process invocation against the
   same `store.db` — genuine cross-process persistence, not in-memory state); `sql-mini-query-cli`
   (an in-memory `CREATE TABLE` / `INSERT INTO ... VALUES` / `SELECT * FROM ... WHERE` engine —
   real multi-command state + filtering, not a database library); `infix-expr-eval-cli` (an
   arithmetic expression evaluator for INFIX notation with standard operator precedence,
   left-to-right associativity, and parentheses — a real recursive/shunting-yard-style parser,
   harder than the suite's existing RPN calculator); `json-path-query-cli` (parses a JSON document
   from stdin via the standard `json` module and resolves a dotted/indexed path against it,
   printing `null` on any missing key/out-of-range index/invalid JSON). Each sentence pins the
   `main.py` entrypoint, the exact invocation (argv and/or a precise stdin protocol), and the
   exact stdout format — the same contract-precise convention TASK-15/17/24 proved — and each gets
   3+ deterministic checks (no wall-clock dependence) covering the core behavior plus at least one
   edge case (missing key, no-match `WHERE`, left-to-right subtraction associativity, a path
   segment past a scalar). Do NOT modify `run_creation_suite`/`_run_cli`/`_resolve_entry`/
   `_run_single_check`, `FIRST_SLICE`, or the existing 8 `HARDER_SLICE` tasks.
2. Update `tests/test_ext036_suite.py` minimally so it stays consistent with the grown list: bump
   `test_harder_slice_registry_shape`'s expected `len(HARDER_SLICE)` to 12; in
   `test_harder_slice_tasks_are_internally_coherent`, scope the `_HARDER_SLICE_REFERENCE_CODE` set
   -equality assertion to the ORIGINAL 8 task names only (mirroring how
   `test_grown_suite_tasks_are_internally_coherent` already excludes `FIRST_SLICE`'s original 6 by
   name) and change its loop to `.get()` + `continue` so it skips tasks without a reference entry
   in that dict — no new reference implementations duplicated into that file.
3. Add a NEW offline test file `tests/test_ext036_harder_creation_classes.py` (no live model, no
   network) that (a) asserts STRUCTURE for each of the 4 new tasks: non-empty `sentence`, `"main.py"`
   pinned in the sentence, `len(checks) >= 3`, and every check is either callable or a well-formed
   3-tuple; (b) writes a hand-written, genuinely-correct reference implementation for EACH of the 4
   new tasks and runs it through the real `run_creation_suite` oracle, asserting `accepted=True` and
   `n_checks_passed == n_checks` — proving every new check is satisfiable by (and thus actually
   determined by) its stated contract, not trivially-always-true or accidentally unsatisfiable
   (Tenet 3, no oracle leak — checks are independent black-box CLI checks derived only from the
   sentence, never from the reference implementation's internals).
4. Run ONLY `python -m pytest tests/test_ext036_harder_creation_classes.py -q` and
   `python -c "from harness.system_suite import FIRST_SLICE, HARDER_SLICE; print(len(FIRST_SLICE), len(HARDER_SLICE))"`
   — do NOT run `tests/test_ext036_system_builder.py`, a broad `test_ext036*`/`test_ext056*` glob,
   or any `-k` sweep (triggers a live Jetson model-swap); confirm the Jetson still serves the
   expected default model afterward. Update `.jarify/EXT-036/index.json`'s `REQ-20` range to the
   grown file's `#EXT-036-REQ-20` markers.

#### Implements
- [REQ-20] Parity instrument: a broad, DIVERSE, held-out suite of sentence->system CREATION
  classes (grows `HARDER_SLICE` from 8 to 12 — a genuine highly-complex tier of real-system
  classes: cross-process SQLite persistence, an in-memory SQL-ish query engine, an infix
  expression parser with precedence, and a JSON-path resolver — pushing the suite's difficulty
  frontier past the now-~92%-mastered toy-CLI tier; live gemma-vs-escalating measurement against
  the grown suite remains an open follow-up)

### [TASK-51] Ratchet the MODIFICATION suite's difficulty — a genuinely-hard `HARDER_SLICE` (REQ-21)

MEASURED (docs/GAP-MAP.md, 2026-07-08): gemma aces the current modification suite ~35/36
including the multi-file tier (`FIRST_SLICE` + `MULTIFILE_SLICE`) — it is SATURATED and no
longer DISCRIMINATES (PRIME-001's difficulty ratchet, exactly the pattern that already pushed
the creation suite's frontier via TASK-24/TASK-50). This task adds a `HARDER_SLICE` of 4
genuinely-hard modification tasks, each starting from a COMPLEX, already-non-trivial
`start_system` (not a toy CLI), requiring the model to comprehend intricate EXISTING logic and
extend it precisely without breaking it.

#### Steps
1. In `harness/modification_suite.py`, after the existing `MULTIFILE_SLICE` list (leaving
   `FIRST_SLICE`/`MULTIFILE_SLICE`/`ALL_TASKS` byte-for-byte unchanged — `ALL_TASKS` stays
   `FIRST_SLICE + MULTIFILE_SLICE` for backward compatibility with existing callers/tests), add
   a new `HARDER_SLICE: list[ModificationTask]` of 4 tasks, all tier `"highly-complex"`: (1) a
   correct single-file INFIX expression evaluator (integers, `+ - * /`, parens, precedence) gains
   support for `%` at the same precedence as `*`/`/`; (2) a correct in-memory `CREATE
   TABLE`/`INSERT INTO`/`SELECT * FROM ... WHERE` SQL-like engine gains single-column projection
   (`SELECT <col> FROM <t> WHERE <c>=<v>` prints only that column's value per matching row); (3) a
   correct dotted-path JSON resolver (stdin JSON, argv path) gains Python-style NEGATIVE array
   indices (`a.-1` = last element), preserving key/positive-index/`null`-on-missing behavior; (4)
   a correct 2-file stats system (`statlib.py` mean+median, `main.py` CLI dispatch) gains a `mode`
   subcommand (most frequent value, smallest wins ties), requiring a coordinated edit across both
   files. Each `start_system` must independently pass its own `regression_checks` UNMODIFIED
   (Tenet-3 known-good precondition).
2. Add a NEW offline test file `tests/test_ext036_harder_modification_classes.py` (no live model,
   no network) that: (a) asserts registry shape (4 tasks, tier `"highly-complex"`, unique names,
   `main.py` present with `if __name__ == "__main__"`, at least one `new_check`/`regression_check`
   each); (b) for EVERY task, writes the unmodified `start_system` to a temp root and asserts every
   `regression_check` passes via `harness.system_suite._run_single_check` (the known-good
   precondition); (c) for EVERY task, hand-writes a genuinely-correct REFERENCE MODIFICATION (the
   `start_system` with the change applied) and drives it through the REAL
   `run_modification_suite` oracle, asserting `new_behavior_ok`, `no_regression`, and `accepted`
   are all `True`; (d) drives a NO-OP `modify_fn` (never touches `root`) through
   `run_modification_suite` across all 4 tasks and asserts `new_behavior_ok`/`accepted` are `False`
   for every one — proving the checks genuinely test the requested change, not trivially or
   accidentally satisfiable by the pre-modification system (no leak, Tenet 3).
3. Run ONLY `python -m pytest tests/test_ext036_harder_modification_classes.py -q` (must pass) and
   `python -m pytest tests/test_ext036_modsuite.py -q` (must stay green — confirms `ALL_TASKS`/
   `FIRST_SLICE`/`MULTIFILE_SLICE` are unchanged). Do NOT run a live-model test, a broad
   `test_ext036*` glob, or any `-k` sweep (a Jetson measurement may be running). Update
   `.jarify/EXT-036/index.json`'s `REQ-21` range to the grown file's `#EXT-036-REQ-21` markers.

#### Implements
- [REQ-21] Parity instrument: matching sentence->system MODIFICATION classes (adds `HARDER_SLICE`
  — 4 genuinely-hard tasks extending a COMPLEX existing system: an infix evaluator gains modulo,
  a mini-SQL engine gains column projection, a JSON-path resolver gains negative indices, a
  multi-file stats CLI gains a `mode` subcommand — pushing the suite's difficulty frontier past
  the now-saturated `FIRST_SLICE`/`MULTIFILE_SLICE` tiers; a live gemma-vs-escalating measurement
  against the grown suite remains an open follow-up)

### [TASK-52] KEY-VALUE-aware persistence round-trip — fixes a false-negative on set/get datastores (REQ-40)

MEASURED + CONFIRMED OFFLINE (2026-07-08): the VERIFIED-CORRECT SQLite-kv leaf
(`graph_dsl.SQLITE_KV_LEAF`, passes all 5 of `sqlite-persistent-kv-cli`'s independent oracle
checks incl. genuine cross-process persistence) FAILS `build_system`'s `_minimum_acceptance`
on exactly one check — `minimum: 'create'+'get' round-trip persists`. This is the real
blocker keeping `sqlite-persistent-kv-cli` from greening, NOT a reasoning issue. Two root
causes in the existing add/list round-trip derivation (REQ-27): (1) `_ADD_LIKE_WORDS =
("add","create","save","insert","new")` has no "set"/"put"/"store", so the sqlite spec's real
write verb ("set") is never matched and the prose word "create" (from "create the database
file") is mis-picked instead; (2) `_roundtrip_acceptance_check` is ADD/LIST-shaped — it runs
`<entry> <add> <sentinel>` then a BARE `<entry> <list>` with no key, which structurally cannot
verify a `set <key> <value>`/`get <key>` contract (a bare `get` returns nothing).

#### Steps
1. In `harness/system_builder.py`, add `_derive_kv_roundtrip(spec) -> (set_cmd, get_cmd) |
   None`: detects a key-value SET/GET contract — the spec names a store verb (`set`/`put`/
   `store`) AND a `get` retrieve verb, both as whole words (reuse `_first_word_match`).
   Conservatively EXCLUDE a spec describing a stdin-driven multi-command SESSION protocol
   (matching "standard input"/"stdin") — a per-command subprocess invocation is the WRONG
   shape for that contract, and existing suite specs like `kv-store-ttl-cli`/`lru-cache-cli`
   also name `set`/`put`+`get` as whole words but are in-memory, single-session stores that
   never claim cross-process persistence (verify via a sweep of all 24 `ALL_CREATION_TASKS`
   specs that the new detector fires ONLY for `sqlite-persistent-kv-cli`). Never raises.
2. Add `_roundtrip_kv_acceptance_check(entry, set_cmd, get_cmd) -> dict`: from a FRESH
   invocation, run `<entry> <set_cmd> <SENTINEL_KEY> <SENTINEL_VAL>` as one subprocess, then a
   SEPARATE `<entry> <get_cmd> <SENTINEL_KEY>` subprocess, and assert the fixed literal
   `SENTINEL_VAL` appears in the get output — reading back BY THE SAME KEY it was just written
   under. Use FIXED literal sentinel key+value (`_KV_ROUNDTRIP_SENTINEL_KEY`/
   `_KV_ROUNDTRIP_SENTINEL_VAL`), never derived from `task.checks`/`system_suite` (no leak,
   Tenet 3). Two INDEPENDENT subprocess invocations make this a genuine CROSS-PROCESS
   persistence check — a non-persistent (in-memory-only) store must still FAIL it.
3. Wire into `_minimum_acceptance`: when `_derive_kv_roundtrip` detects the KV contract, emit
   the KV round-trip INSTEAD OF the add/list round-trip (precedence, never double-counted) —
   closes the exact `'create'+'get'` mis-pairing. A spec that only names add/list (e.g.
   `todo-list-cli`) is UNCHANGED — still gets exactly the pre-existing add/list round-trip.
4. Tests, extending `tests/test_ext036_acceptance_completeness.py` (OFFLINE, no live model):
   (a) `_derive_kv_roundtrip` unit behavior — finds set+get, conservative when only one side
   present, excludes the stdin-session protocol shape, a 24-task sweep across
   `ALL_CREATION_TASKS` confirming no-over-trigger, never raises on bad input; (b)
   `_minimum_acceptance` prefers the KV round-trip over add/list for a KV spec, and an
   add/list-only spec (`todo-list-cli`-style) is unaffected; (c) the real
   `graph_dsl.SQLITE_KV_LEAF` now passes `_minimum_acceptance` 8/8 (was 7/8) for the real
   `sqlite-persistent-kv-cli` spec (a dedicated regression test running every check via
   `_run_check`); (d) an end-to-end `build_system` run against a genuinely-persistent
   (disk-backed) kv CLI reports `done=True`; (e) an end-to-end `build_system` run against a
   genuinely non-persistent (in-memory-only, module-level dict) kv CLI reports `done=False`
   with the KV round-trip listed in `unmet` — a REAL, physically-verified failure, not
   mocked. Run `python -m pytest tests/test_ext036_system_builder.py -k "roundtrip or
   persist or minimum or acceptance" -q` plus the extended
   `tests/test_ext036_acceptance_completeness.py` — both offline, stay green. Do NOT run the
   broad suite or any live-model test (a Jetson re-measure may be running).

#### Implements
- [REQ-40] KEY-VALUE-aware persistence round-trip — fixes a false-negative on set/get
  datastores (closes the MEASURED `sqlite-persistent-kv-cli` blocker: the committed SQLite-kv
  leaf now passes `_minimum_acceptance` 8/8, was 7/8)

### [TASK-53] Interface ledger + AST seam check — the #1 generic fix for cross-module compositional coherence (REQ-41)

MEASURED (design review, compositional-failure diagnosis): `_build_module` injects the FULL
SOURCE of a sibling module into a build prompt only for that module's DIRECT imports (REQ-3)
-- for a 2B model, once a system grows past ~3 modules, a cross-module call can still come
out the WRONG SHAPE (e.g. `db.add(title)` when the built `db` module actually exports
`add(title, done)`) because the exact `def` line is buried in a full dependency body and the
model never sees a COMPACT, whole-system view of every contract at once. This is the top
generic mechanism from the design review: a PREVENTIVE half (a compact interface ledger,
always in context) plus a DETECTIVE half (a deterministic post-assemble AST check that
catches a mismatch that slips through anyway and routes it into the existing repair loop).
Generic -- lifts EVERY multi-module class, not one; no leaves.

#### Steps
1. In `harness/system_builder.py`, add `_build_interface_ledger(plan: dict | None) -> str`:
   deterministically assemble, from `plan["modules"]`, a compact ledger line per module (its
   name + responsibility + its exported names WITH signatures from `exports[].signature`).
   Degrades to `""` (never raises) on a missing/malformed plan or a module with no exports.
2. Add a `plan: dict | None = None` keyword parameter to `_build_module`; when given, compute
   `_build_interface_ledger(plan)` and inject it into `BUILD_PROMPT` (a new `{ledger}` slot)
   alongside the module's own direct-imports' FULL SOURCE (`deps`, UNCHANGED — still scoped to
   `m.get("imports")` only, never all siblings). `plan=None` (every pre-existing caller) is a
   byte-identical no-op. Wire `build_system`'s BUILD loop (the one `_build_module` call site)
   to pass `plan=plan`.
3. Add a deterministic, POST-ASSEMBLE AST seam check: `_module_top_level_defs(code)` (a
   symbol table of a module's top-level function/class/other names + positional arity,
   returning `None` on a parse failure or an UNCERTAIN surface -- a wildcard `from x import *`,
   a module-level `__getattr__`, or a `globals`/`setattr`/`exec`/`eval` call anywhere);
   `_module_import_aliases(code, sibling_stems)` (alias -> sibling-module-stem for a plain
   `import <sibling>`, never `from <sibling> import X`); `check_interface_seams(built: dict) ->
   list[dict]` walks every module's AST for `alias.method(...)` calls into a sibling module and
   flags a CONFIDENT positional-arity mismatch (never a name-mismatch, never a call using
   keywords/`*args`/`**kwargs`, never a call into an uncertain-surface module) with a concrete
   `{caller, callee, alias, method, n_args, min_args, max_args, message}` finding. Never raises.
4. Add `_seam_check_code(finding) -> str`: renders a SELF-CONTAINED, stdlib-only (`ast`) Python
   script that RE-DERIVES the same arity check fresh from the files on disk each run -- a
   genuinely DYNAMIC check (not a static always-fail marker), so a later repair round that
   fixes either side of the mismatch makes it pass for real.
5. In `build_system`, right after the composed acceptance checklist is assembled (after the
   optional 7B-review and spec-properties blocks, before the empty-checklist guard), call
   `check_interface_seams(built)` and append one synthetic check per finding
   (`{"name": f"seam: {caller} -> {alias}.{method}", "code": _seam_check_code(finding)}`) to
   `checks` -- purely ADDITIVE, guarded (never raises), so it feeds the SAME `unmet`/
   `_repair_system` (REQ-5) repair loop as any other check, peer to the deterministic minimum
   (never subject to the optional reviewer, which only touches model-proposed checks).
6. Tests `tests/test_ext036_interface_seam.py` (OFFLINE -- no live model, no network): ledger
   assembly contains every module's exported signatures and degrades gracefully; a module's
   build prompt carries the WHOLE ledger but full source only for its direct imports (a
   non-imported sibling's signature appears in the ledger, never its full source); the seam
   check catches the measured arity-mismatch shape with the concrete message, does not flag a
   correct-arity call, correctly handles class-constructor arity and defaults/`*args`;
   conservative-by-construction coverage (same-module calls, stdlib calls, keyword/starred
   calls, and calls into a dynamic/uncertain module are never flagged, and an unresolved
   symbol is never treated as a name-mismatch); the generated seam-check script is proven
   genuinely DYNAMIC via a real subprocess run (fails while mismatched, passes once fixed); and
   an end-to-end `build_system` run with a canned 2-module arity-mismatch draw shows the seam
   finding enters `unmet` and the existing repair loop resolves it to `done=True`, while a
   correct-arity draw is never flagged. Run `tests/test_ext036_system_builder.py`,
   `tests/test_ext036_system_repair.py`, and the new file (all offline) -- stay green. Do NOT
   run the broad suite or any live-model test (a Jetson re-measure may be running); do NOT
   touch `harness/secure_exec.py` or `harness/graph_dsl.py`.

#### Implements
- [REQ-41] Interface ledger + AST seam check — the #1 generic fix for cross-module
  compositional coherence (the deterministic mechanism + offline correctness tests; the true
  LIFT — does the small model now build bigger, correctly-wired multi-module systems — is an
  on-Jetson re-measure that follows this commit, out of scope here)

### [TASK-54] Enrich repair feedback with the built system's actual observed output (REQ-42)

Give the acceptance-driven repair loop the concrete observed-vs-expected signal for wrong-value
failures, so the model can localize a "runs but prints wrong" defect (measured: csv-column-aggregator
prints 0.00, repair blind to it).

#### Steps
1. In `harness/system_builder.py`, trace the failing-check feedback path (`_run_check_verbose` →
   `_repair_module_for_check` → `REPAIR_MODULE_PROMPT`) and make the `error` string carry the built
   system's ACTUAL stdout/stderr for the failing scenario (not just the AssertionError). Cleanest
   generic route: make the deterministic acceptance-check scripts capture the built entrypoint's real
   stdout and, on assertion failure, surface it (`assert expected in out, f"expected {expected!r}, got
   {out!r}"`) — so the captured run output already contains "got '0.00'"; OR enrich the feedback
   assembly to append the observed output. No per-class special-casing.
2. Keep it honest/leak-free: surface only the built system's own output + the expected already encoded
   in the check; never the hidden suite oracle or a reference implementation.
3. Add an offline test in `tests/test_ext036_system_repair.py`: a built stub whose entrypoint prints a
   wrong value produces repair feedback (the string passed to the repair prompt) that CONTAINS the
   actual observed output; a bare-AssertionError-only feedback is the failing baseline. No model call.
4. Run `tests/test_ext036_system_repair.py` + `tests/test_ext036_system_builder.py`; confirm green +
   the REQ-23 non-degrading guarantee holds. Update `.jarify/EXT-036/index.json` (REQ-42 ranges).

#### Implements
- [REQ-42] Execution-feedback enrichment — repair sees the ACTUAL wrong output, not a bare AssertionError

### [TASK-55] Single-file retry fallback for over-decomposed builds (REQ-43)

When a multi-module build fails acceptance, try the whole system as one file and keep the better result —
the generic fix for the measured over-decomposition failure (csv-column-aggregator).

#### Steps
1. In `harness/system_builder.py` `build_system`, after `_repair_system` returns, add a gated retry:
   if the result is NOT done AND the plan had >1 module, construct a single-module plan (entrypoint
   `main.py`, all logic in one file) and build it from the same spec via the existing module-build path
   (reuse `_build_module`/assemble/acceptance; a build prompt instructing "implement the ENTIRE system in
   this one file main.py, no other modules").
2. Grade the single-file build against the SAME composed acceptance checklist; pick the better of the two
   results by the existing ranking (done > shipped > fewer unmet). Record the choice in `build_path`
   (e.g. `single-file-retry`). Never retry an already-done build; never regress (keep multi-module if it
   ranks >= the retry).
3. Keep it honest/leak-free (spec only, never the suite oracle/independent checks) and bounded (ONE retry).
4. Add tests to `tests/test_ext036_system_builder.py`: a not-done multi-module build triggers the retry
   and keeps the better single-file result; an already-done build is not retried (byte-identical path).
   Mock the model/build calls where possible so tests stay offline. Run
   `tests/test_ext036_system_builder.py` + `tests/test_ext036_system_repair.py`; confirm green.
   Update `.jarify/EXT-036/index.json` (REQ-43 ranges).

#### Implements
- [REQ-43] Single-file retry fallback — recover from OVER-DECOMPOSITION of a simple spec

### [TASK-57] Bounded regression-gated new-behavior repair loop in modify_system (REQ-44)

Give the modify path the repair loop the build path already has, so a regression-safe-but-wrong edit
(measured: sql-mini-add-projection) gets fixed instead of shipped broken.

#### Steps
1. In `harness/system_builder.py` `modify_system` (~line 3910), after the regression-gated apply +
   the best-effort new-behavior evaluation (step 5), add a BOUNDED (≤2 round) repair loop that fires
   ONLY when the edit is applied, regression is preserved, but the new-behavior checks (derived from
   `mod_sentence`) do not all pass.
2. Each round: re-regenerate the target module(s) via the existing `_regenerate_module` path, giving
   the model the change request + the CONCRETE failing new-behavior output (reuse the REQ-42 enriched
   `_run_check_verbose` so the feedback carries "expected X, got Y"). Re-assemble onto `root`
   (jailed writes), then re-run BOTH the baseline/regression checks and the new-behavior checks.
3. Keep the re-regeneration ONLY if it passes ALL regression checks AND strictly more new-behavior
   checks than the current best; otherwise revert that round (disk + dict) — mirror the existing
   regression-gate revert/atomicity. Update `new_behavior_ok`/`note` to reflect the repaired result.
4. Leak-free (only the built system's own output + `mod_sentence`); `applied` still never strictly
   requires new behavior; bounded.
5. Tests in `tests/test_ext036_system_repair.py` (offline, injected llm): regression-safe-but-new-broken
   edit → repaired + kept; a retry that would regress → reverted; already-working edit → not repaired
   (byte-identical). Run `tests/test_ext036_system_repair.py` + `tests/test_ext036_system_builder.py`;
   confirm green. Update `.jarify/EXT-036/index.json` (REQ-44 ranges).

#### Implements
- [REQ-44] Modify path — bounded, regression-gated NEW-BEHAVIOR repair loop
