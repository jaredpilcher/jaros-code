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
