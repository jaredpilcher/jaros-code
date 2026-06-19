---
id: EXT-004
title: Claude-Code-like Operator CLI
status: partial
priority: high
implementation:
  - file: harness/cli.py
    ranges:
      - - 1
        - 220
---

This spec serves **Tenet 5** of PRIME-001: a familiar, transparent terminal experience
with the same look and feel as Claude Code. We continually study Claude Code's CLI and
move ours toward parity. The CLI is also a real WIRING surface: its commands invoke the
single-purpose agents and tools (navigator, commander, fs.grep/list/read, py.symbols),
so they are used, not orphaned. Every command routes a Decision through the same
gate + executor — the CLI never bypasses the two planes.

### [REQ-1] Slash-command REPL

An interactive prompt loop, modelled on Claude Code, dispatches `/`-prefixed commands
and prints results, with a status line naming the local model.

#### Acceptance Criteria
- [ ] No-arg `jcode` launches the REPL; `/quit` exits; `/clear` clears the screen
- [ ] `/help` lists commands; unknown commands and non-slash input are handled gracefully
- [ ] A banner/status line names the model (gemma2:2b, local)

### [REQ-2] Commands that wire the fleet

Commands invoke the agents/tools so they actually fire: `/find` (navigator→fs.grep),
`/run` (commander→shell.exec, gated), `/grep`, `/ls`, `/read`, `/symbols`, plus
`/status`, `/agents`, `/tools`, `/report`, and `/fix` (the edit→test→judge loop).

#### Acceptance Criteria
- [ ] `/find` drives the navigator agent then runs fs.grep on its term
- [ ] `/run` drives the commander agent then runs shell.exec (safety-gated)
- [ ] `/grep` `/ls` `/read` `/symbols` invoke their read-only tools through the Runtime
- [ ] `/status` and `/report` surface the live metrics; `/fix` runs the coding loop

### [REQ-4] Natural-language routing (the system decides which agents/tools)

The user types a plain request (no slash); an `orchestrator` agent classifies it into an
action and the CLI dispatches to the matching specialist/tool. The model decides *what*
the user wants; the deterministic CLI decides *how* — the user never has to know which
agent/tool to invoke.

#### Acceptance Criteria
- [ ] Non-slash input is routed by the `orchestrator` agent (gemma2:2b) to one action
- [ ] The chosen action dispatches to the matching command (fix/find/run/read/list/symbols)
- [ ] A safe default (help) is used when the request is unclear
- [ ] The routing decision is shown to the user ("[orchestrator → …]") for transparency

### [REQ-3] Continual Claude-Code parity

The CLI is iterated toward Claude Code's UX (slash commands, status line, transcript,
custom commands) based on ongoing study of Claude Code.

#### Acceptance Criteria
- [ ] New Claude-Code CLI features are tracked and adopted where they fit the two planes
- [ ] The transcript/status mirror Claude Code's look and feel
