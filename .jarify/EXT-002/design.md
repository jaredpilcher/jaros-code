# EXT-002 — Single-Purpose Coding Agent Fleet

Each agent is a `ReasoningBoundary` (`build(llm) -> obj` with `decide(context) ->
[Decision]`). It calls Gemma 4 2B (`e2b`) once with a tiny prompt and emits exactly one
inert Decision targeting an EXT-001 tool. No agent holds a host handle.

```text
  agent          input                       model decides         emits Decision.type
  ─────────────  ──────────────────────────  ───────────────────   ────────────────────
  editor         {path, content, instruction} one exact old→new    code.apply_patch
  commander      {task, cwd?}                 one shell command    shell.exec
  test-reader    {output}                     PASS / FAIL          advance (complete|fail)
```

## Why delimited blocks, not JSON (editor)

A 2B model reliably emits literal text between sentinels but frequently breaks JSON
(unescaped quotes/newlines). The editor's contract is therefore:

```text
  <<<OLD
  exact snippet copied verbatim from the file (unique)
  OLD>>>
  <<<NEW
  replacement text
  NEW>>>
```

parsed with a tolerant regex. The parsed `old`/`new` go straight into a
`code.apply_patch` Decision; the deterministic tool enforces single-occurrence
uniqueness, so a sloppy edit is rejected at execution, not silently misapplied.

## Honesty on failure

When the model's output cannot be parsed into the agent's contract, the agent does
not crash and does not invent an action: it emits an `advance` Decision with events
`[start, fail]` and a note explaining why. The failure is recorded in the decision
log (PRIME-001 Tenet 3) and the orchestrator (EXT-003) sees a FAILED job.

## Composition

These agents are intentionally incomplete alone — they are composed by the
orchestrator (EXT-003) into a bounded edit→test→judge loop, and later mirror the
jarify roles (spec, task, builder, architect) described in PRIME-001's design.
```text
  fs.read ─→ editor ─→ code.apply_patch ─→ commander ─→ shell.exec ─→ test-reader ─→ advance
                                                                          │ fail
                                                                          └─ loop (bounded)
```
