# EXT-037 — Host Development Toolbelt: Architecture

The toolbelt is the execution-plane library the orchestrator wields to DO development on the host.
Every capability is a Jaros custom tool: the model emits an inert `Decision`, the tool's `validate()`
gate deterministically checks safety (path containment, command policy, secret guard) BEFORE `execute()`
runs the host effect, and every accepted/rejected Decision is hash-chain logged and replayable. This is
PRIME-001 Tenet 1 (two-plane) applied to real development, inside the Foundry safety envelope.

```text
  orchestrator (model)  ──emits──▶  Decision {tool: write_file|shell_exec|venv_create|git_commit|…, args}
                                          │
                                          ▼
             ┌──────────────── DECISION GATE — validate() ────────────────┐
             │  path_jail(root,target)  ·  command policy (no egress/       │
             │  destructive)  ·  secret/ignored guard  ·  timeout config    │
             │        REJECT (logged) ◀── escapes root / blocked            │
             └───────────────────────────────┬─────────────────────────────┘
                                     accept   ▼
             ┌──────────────── EXECUTE — the host effect ─────────────────┐
             │  fs read (broad) │ fs write/update (ROOT-JAILED)            │
             │  shell_exec (timeout + tree-kill, cwd=root, no egress)      │
             │  venv/python/deps (root-scoped)  │  git init/commit/log     │
             └───────────────────────────────┬─────────────────────────────┘
                                              ▼
             ┌──────── hash-chain decision log + observation back to model ┐
             │  stdout/stderr/exit as inert observation; replayable state   │
             └──────────────────────────────────────────────────────────────┘

  SAFETY ENVELOPE (invariant): read freely · write/update ONLY within the project ROOT ·
  no external network egress · no destructive ops outside root · never commit secrets.
```

## Path-jail (REQ-1 core)

```text
  path_jail(root, target):
     p = realpath(join(root, target))        # resolves .. AND symlinks
     if not is_within(root_realpath, p): REJECT
     return p                                 # every writer routes through this
```

The path-jail is ONE deterministic helper reused by `write_file`, `apply_patch`, `search_replace`, and every
future writer — the single choke point that enforces "limited to the root folder of the project." Reads are not
jailed (broad read is safe + needed for repo understanding); only create/write/update are confined.

## Relationship to existing tools

Foundational tools exist (`.jaros-data/tools/`: `fs_read`, `fs_list`, `fs_find`, `fs_grep`, `write_file`,
`apply_patch`, `search_replace`, `shell_exec`, `_codesafety.py`). EXT-037 HARDENS the writers/exec (REQ-1/REQ-2)
and ADDS environments (REQ-3) + git (REQ-4), all under the same Jaros two-plane + Foundry-safety pattern (REQ-5).
