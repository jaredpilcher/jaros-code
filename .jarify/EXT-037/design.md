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

## Optional-runtime idiom for deterministic fast-paths (REQ-9)

Some product surfaces (`system_builder.py`'s plan-assembly, `refactor.py`'s `/rename`/`/move`) are
DETERMINISTIC edit paths that write directly to disk rather than being dispatched through a
model-emitted Decision — and the SAME function is shared between real host use (a live CLI command,
root = the repo) and throwaway eval-sandbox use (tests/eval harnesses against a temp dir with no
meaningful "project root"). Forcing every caller through a `Runtime`/root-jail would break the
sandbox callers. The idiom (first landed as EXT-042 REQ-5, reused here for REQ-9): the writer function
takes an OPTIONAL `runtime=None` parameter.

```text
  caller supplies runtime? ──yes──▶ build code.write_file Decision {path, content, root}
        │                              │
        no                             ▼
        │                    runtime.apply(decision)  — gate (REQ-1 root-jail) → execute → hash-chain log
        ▼                              │
  raw Path.write_text(...)        gate rejects? ──▶ honest error string, no crash, snapshot/restore
  (byte-identical fallback,            │
   used by eval/test callers)     accepted ──▶ file written, logged, replayable
```

The real-host CLI command handler (`harness/cli.py`) constructs a root-anchored `Runtime` (the same
`_write_runtime()` helper `/init`/`/remember`/`/rewind` already use) and passes it in; every
eval/test/sandbox caller passes nothing and keeps the exact pre-existing raw-write behavior.
