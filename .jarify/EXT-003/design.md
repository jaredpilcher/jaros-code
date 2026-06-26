# EXT-003 — Bounded Coding Loop Orchestration

The orchestrator is the "outer driver" of PRIME-001's design: it composes
single-purpose agents and deterministic tools into a multi-step coding loop while
keeping every step individually replayable. It routes Decisions through the **real**
Jaros gate + executor + decision log — it does not call tools behind their backs.

```text
  Runtime (faithful jaros execution path)
  ────────────────────────────────────────
   validate_decision(d)  ──reject──►  raise (honest stop)
        │ accept
        ▼
   executor.apply(d, on_accept=record→DecisionLog, log=TransitionLog)
        │
        ▼
   tool output (inert dict)
```

## The loop

```text
  fix_loop(target, instruction, test_cmd, max_iters)
  ──────────────────────────────────────────────────
   round r = 1..max_iters:
     content   = fs.read(target)                         # operator read
     d_edit    = editor.decide({target, content, instr}) # Gemma 4 2B (e2b) — reasoning
     Runtime.apply(d_edit)        → code.apply_patch      # deterministic tool edits file
     d_test    = shell.exec(test_cmd)                     # operator-issued command Decision
     out       = Runtime.apply(d_test)                    # deterministic tool runs tests
     d_verdict = test-reader.decide({output: out})        # Gemma 4 2B (e2b) — reasoning
     Runtime.apply(d_verdict)     → advance (DONE|FAILED)
     if verdict == PASS: stop(success)
   stop(exhausted)
```

Reasoning steps (editor, test-reader) are the only Gemma 4 2B (`e2b`) calls; everything
else is deterministic. The model decides *what* edit and *whether* tests passed;
the executor and tools decide *how*. The decision log records every step so
`jaros replay` can reconstruct the run.

## Look and feel

The transcript mirrors Claude Code: a banner naming the model, per-round sections
showing the agent's Decision and the tool's real output, and a clear final verdict.
Authority stays with the deterministic harness; the UX never bypasses the planes.
