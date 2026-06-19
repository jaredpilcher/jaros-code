# jaros-code

A software-development harness built on **Jaros** that aims to match or exceed
Claude Code at real coding work, while every reasoning call is served by a single
small local model — **Ollama `gemma2:2b`** — at zero inference cost.

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

## Design rules

- **Agents are single-purpose.** Each agent makes ONE narrow judgement and emits
  inert Decisions. Capability comes from composing many small agents, not one big
  one or a bigger model.
- **Tools are deterministic.** Every host effect (read, write, shell, patch) is a
  Jaros custom tool with `validate()` + `execute()`. Agents never touch the host.

## Running

```
pwsh scripts/serve.ps1        # boot the node pinned to gemma2:2b (Windows)
bash scripts/serve.sh         # same, POSIX
```

- Agents live in `.jaros-data/agents/`, tools in `.jaros-data/tools/`, model
  selection in `.jaros-data/config/llm.json` (mirrored by the serve scripts).
- Submit work: `jaros submit <agent> --input '{...}'`; observe: `jaros watch`;
  prove determinism: `jaros replay`.

## Commit discipline

Commit often: after each verified logical unit, commit code + spec together with a
descriptive message. Never commit `.env`, secrets, logs, or runtime state
(`.gitignore` covers `.jaros-data` runtime dirs). Footer:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
