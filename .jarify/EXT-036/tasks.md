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
