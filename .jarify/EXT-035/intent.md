# Intent

This spec exists to make the Foundry real: the standing capability to build actual software
end-to-end and grade it binary ship/no-ship by RUNNING it, measuring what benchmarks and the
single-function suite cannot — bootstrap, multi-file coordination, and "did it actually run." It
productionizes the measured lever for the multi-file gap: the mechanical cross-module
coordination a small model botches (correct import lines, arg marshalling, calling the entry
function, printing) is produced by the DETERMINISTIC plane, freeing the model to fill only the
logic bodies it is good at. It provides deterministic CLI-wrapper synthesis from a module's AST,
an assemble-and-ship-gate loop that runs the tool as a program and grades by exact stdout, a
deterministic import-resolver that injects the imports the model omits, and a completeness check
so an incomplete module cannot ship just because the run-cases never exercised the missing part.

It converges toward the Prime Directive's two-plane discipline (Tenet 1) — every host effect a
deterministic tool, the model confined to inert logic — and toward the honest scoreboard: the
ship-gate is gated on the RUN, never on a flaky build oracle, and appends each verdict to the
ship-log so progress on real systems is measured, not asserted. It operates inside the Foundry
safety envelope (sandboxed, localhost-only, no egress, no destructive ops).
