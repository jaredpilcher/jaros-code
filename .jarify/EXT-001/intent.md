# Intent

This spec exists to give jaros-code the deterministic execution plane that Tenet 1 of
PRIME-001 demands: every host effect the harness performs — reading a file, listing a
directory, searching, applying an edit, running a command, validating syntax — is a
sharp, single-purpose Jaros tool with `validate()` + `execute()`, never an action the
reasoning model takes directly. The model only ever emits inert `Decision` data; these
tools are the verbs that actually touch the host, so the two planes stay cleanly
separated and every effect is attributable. Read-only tools must be purely replay-safe
so re-running reconstructs identical output, and effectful tools (write, shell) are
recorded as Decisions before they run, keeping every run honest and byte-identically
reproducible (Tenet 3). Because the harness runs unattended, the effectful gates must
deterministically refuse dangerous content and commands — network egress, destructive or
privilege-escalating operations, unsafe dynamic code — so a small model's output can
never make the system unsafe. These primitives are deliberately tiny and reliable so the
single-purpose coding agents can compose them into capability, which is where the
intelligence lives — in the multitude and the wiring, not in any one big action.
