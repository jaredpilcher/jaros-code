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
2. **Small-model-only** — all reasoning is local `gemma2:2b` via Ollama. No paid
   or cloud model, ever, not even as a fallback. Decompose instead of escalating.
3. **Reproducible & honest** — hash-chain logged, byte-identically replayable;
   never hide or fabricate a result.
4. **Spec-first** — code traces to `.jarify` requirements; spec + code change in
   the same commit; stale specs are defects.
5. **Claude-Code-like UX** — familiar, transparent terminal feel, but UX never
   overrides the tenets above it.

When a change would violate a tenet, **STOP and flag the conflict** — do not
silently resolve it.

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
  cascade tuning hit the 2B ceiling — two reverts), STOP and switch AXES — don't grind the same
  failing experiment. Vary the KIND of work (capability builds vs evals vs research) so the loop
  never spins on one dead end. The single-function pass rate is near the 2B ceiling; the productive
  axis is NEW capability classes (multi-file → multi-step → refactoring → navigation), each
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
  `gemma2:2b` can reliably make? If yes (classify, pick, transform-by-example, read a
  result) → a tiny agent. If no (count, arithmetic, operator semantics, exhaustive
  search) → a deterministic tool, usually generate-and-test. When a model-side
  pipeline keeps failing, run a raw single-call probe to see what the 2B actually
  emits *before* building more agents; if it's genuine incomprehension, move that
  grain to the execution plane rather than slicing it smaller. Prove generalization
  with a second eval of the same class. Never ship a net-negative fallback.

## Running

```
pwsh scripts/serve.ps1        # boot the node pinned to gemma2:2b (Windows)
bash scripts/serve.sh         # same, POSIX
```

Try the Claude-Code-like CLI yourself (needs Ollama running with `gemma2:2b`):

```
pwsh scripts/jcode.ps1                 # interactive REPL (Windows; powershell -File also works)
bash scripts/jcode.sh                  # interactive REPL (POSIX)
python -m harness.cli /status          # or run one command and exit
python -m harness.cli "fix foo.py"     # or one plain-language request (orchestrator routes it)
```

In the REPL, type `/help` for slash commands, or just type a plain request — the
`orchestrator` agent (gemma2:2b) decides which agent/tool serves it. `/quit` exits.

- Agents live in `.jaros-data/agents/`, tools in `.jaros-data/tools/`, model
  selection in `.jaros-data/config/llm.json` (mirrored by the serve scripts).
- Submit work: `jaros submit <agent> --input '{...}'`; observe: `jaros watch`;
  prove determinism: `jaros replay`.

## Commit discipline

Commit often: after each verified logical unit, commit code + spec together with a
descriptive message. Never commit `.env`, secrets, logs, or runtime state
(`.gitignore` covers `.jaros-data` runtime dirs). Footer:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
