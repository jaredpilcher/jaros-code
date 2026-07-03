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
