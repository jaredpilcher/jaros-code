# Intent

This spec stands up the **real-systems capability suite** — a leaves-OFF, honestly-graded instrument that
measures whether the model+harness can build GENUINE small real systems (not toy stdin/stdout CLIs) on
the verification substrate landed in EXT-059 (`fs_oracle`, `import_driver`, exact-eq/rc check variants).

Why it exists: the 2026-07-08 Python-breadth taxonomy established that covering ~90% of common Python is
gated by the VERIFICATION SUBSTRATE (now partly built), and that the honest capability frontier is real
systems verified by INDEPENDENT behavioral oracles — never by hand-written leaves (a leaf-green proves
coverage, not capability, and is a Tenet-3 violation for this tier). This suite is the North-Star
instrument that replaces the saturated toy suites at the top of the difficulty curve: each task is a
real system graded by a real behavioral oracle, run **pass@1, leaves-OFF (asserted), on a frozen
held-out** the harness is never tuned against.

How it converges toward the Prime Directive: it makes real-system breadth HONESTLY MEASURABLE (Tenet 3),
so the small-local-only model+harness (Tenet 2) can be driven to genuinely build more real systems —
each graded by a deterministic independent oracle (Tenet 1, execution plane), reproducibly and without
oracle leak.
