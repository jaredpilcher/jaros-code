# Design — Claude-Code-like Operator CLI

## Overview

`harness/cli.py` is the operator-facing terminal harness — the Tenet-5 surface. It is both a
Claude-Code-style experience (a slash-command REPL with a model-naming status line and a
transcript) AND a real wiring layer: its commands drive the single-purpose agents and
deterministic tools so they actually fire instead of sitting orphaned. Every command — whether
typed as an explicit `/`-command or issued as a plain natural-language request — resolves to a
`Decision` that flows through the same gate → executor path; the CLI never performs a side
effect directly.

Three routes reach a command: an explicit slash command, a natural-language request the
`orchestrator` agent classifies into one action, and a multi-step request the `planner` agent
turns into an inert ordered plan that a deterministic executor walks step by step. The model
decides *what* the user wants; the deterministic CLI decides *how*.

## Component flow

```text
                         operator input at the REPL
                                    │
              ┌─────────────────────┼───────────────────────┐
              │                     │                        │
        "/command …"       plain request (no slash)   multi-step request
              │                     │                        │
              │            ┌────────▼────────┐      ┌─────────▼─────────┐
              │            │ orchestrator ag.│      │  planner agent    │
              │            │ (gemma-4-e2b)   │      │  (gemma-4-e2b)    │
              │            │ classify → 1    │      │ parse → inert     │
              │            │ action Decision │      │ ordered plan JSON │
              │            └────────┬────────┘      │ (find/read/fix/run)│
              │                     │               └─────────┬─────────┘
              │       [orchestrator → action] shown            │ /plan executor
              │                     │                walks each step, grounds args
              └─────────────────────┼────────────────────────┘
                                    ▼
                        cli.handle()  (guarded — never a traceback)
                                    │
                    dispatch to matching command
                                    │
        ┌──────────┬──────────┬─────────────┬──────────┬───────────┐
        ▼          ▼          ▼             ▼          ▼           ▼
     /find      /run       /grep /ls      /symbols   /fix       /status
   navigator  commander    /read          py.symbols edit→test  /report
      │          │        (read-only        │        →judge     /agents
      ▼          ▼         tools via         ▼        loop       /tools
   fs.grep   shell.exec    Runtime)      py symbols              │
             (safety-gated)                                      ▼
        │          │          │             │          │   live metrics
        └──────────┴──────────┴─────────────┴──────────┴───────────┘
                                    │
                    Runtime: validate() gate → execute()
                       → hash-chain log → replayable
```

## Key design points

- **Two-plane enforcement.** Agents (navigator, commander, orchestrator, planner) emit inert
  Decisions only; every host effect (grep, list, read, shell exec, symbol scan, edit) is a
  deterministic tool run by the Runtime behind its `validate()` gate. `/run`'s shell.exec is
  safety-gated.
- **Never crash the operator.** `cli.handle()` is guarded in both the REPL (survives to the next
  command) and the one-shot entry (clean `error:` line, exit 1) so a bad command never dumps a
  traceback — a Tenet-5 obligation hardened further in EXT-010.
- **Transparency.** The natural-language route prints its routing decision (`[orchestrator → …]`)
  so the operator sees which specialist was chosen; the status line names the local model.
- **Continual parity.** New Claude Code CLI features (slash commands, status line, transcript,
  custom commands) are tracked and adopted where they fit the two planes — UX never overrides the
  higher tenets.
- **Multi-step planning.** The `planner` keeps only well-formed steps over a fixed verb set
  (find/read/fix/run); the `/plan` executor grounds vague args (`fix` → multi_file_fix,
  `run` → the test suite) and is tracked by a 3-scenario plan eval.
