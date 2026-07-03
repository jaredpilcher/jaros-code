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
