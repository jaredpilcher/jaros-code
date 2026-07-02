# EXT-035 — The Foundry (design)

The Foundry builds real software BY jaros-code and grades it binary ship/no-ship by RUNNING it.
Two-plane structured build (the measured multi-file lever): the MODEL fills per-module logic
bodies (build_from_intent, oracle-verified); the DETERMINISTIC plane synthesizes the mechanical
cross-module wiring (imports/arg-marshalling/entry-call) the small model botches free-form.

```text
  project intent
     │
     ▼
  [build_from_intent]  per module  → logic bodies (MODEL plane, oracle-verified)
     │
     ▼
  synthesize_cli(module, entry)     → wiring (DETERMINISTIC plane, AST-derived)   ← REQ-1
     │
     ▼
  assemble in sandbox → RUN as a program → ship/no-ship  (ship-log #8)
```

Safety envelope (PURSUIT §5G, non-negotiable): dedicated sandbox workspace, localhost-only, no
external egress, no destructive ops, no secrets; per-project owner-approved manifest for any exception.
REQ-1 is the first productionized piece (the deterministic wiring synthesizer); the assemble+ship-gate
loop and the ship-log follow.
