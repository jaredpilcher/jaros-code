# EXT-001 — Deterministic Execution-Plane Tool Primitives

These five tools are the entire surface through which `jaros-code` touches the host.
Each is a Jaros custom tool: a class exposing `NAME` (the Decision `type` it
handles), a pure `validate()` run at the gate, and an `execute()` that performs the
effect and returns inert JSON.

```text
  Decision.type            tool class            effect       replay-safe?
  ───────────────────────  ────────────────────  ──────────   ────────────
  fs.read                  FsReadTool            read only    yes
  fs.list                  FsListTool            read only    yes
  fs.grep                  FsGrepTool            read only    yes
  code.apply_patch         ApplyPatchTool        write        recorded → re-applied
  shell.exec               ShellExecTool         execute      recorded → re-run
```

## Dispatch

```text
  agent emits Decision{type:"fs.read", payload:{path}}
        │
        ▼
  gate: FsReadTool.validate(d)  ── reject → job to failed/
        │ accept
        ▼
  executor: FsReadTool.execute(d) → {content, lines, bytes}
        │
        ▼
  outbox/<job>.json
```

The daemon imports every `*.py` in `.jaros-data/tools/` on its next tick and wires
`NAME → execute` into the executor and `validate` into the gate — no restart.

## Determinism boundary

Read-only tools (`fs.read`, `fs.list`, `fs.grep`) are pure functions of the host
file system at apply time: replay reconstructs identical output. `code.apply_patch`
and `shell.exec` are effectful; Jaros records the Decision that drove them *before*
they run, so the run stays attributable and re-executable. We keep effectful tools
exact and bounded (single unique edit; timed, captured command) to minimize replay
divergence — the model's nondeterminism is recorded, the tool's behavior is fixed.

## Safety bounds

Every tool caps its work so a single decision stays inert and bounded: a read byte
cap, a grep match cap, an exact single-occurrence edit, and a command timeout with
truncated output. A bad tool load is fault-isolated by Jaros and never crashes the
node.
