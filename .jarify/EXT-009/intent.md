# Intent

This spec exists to build the agent that wields the tools, serving Tenets 1, 4 and 5 of
PRIME-001. The earlier specs gave the system its verbs — fix, find, run, navigate, locate,
build — but a human will not invoke each by hand; the missing piece is the master loop that,
from ONE natural-language request, plans a sequence of tool calls, executes them, observes
each result, and replans when reality diverges from the plan. This is Claude Code's
single-threaded loop and its working-memory todo, reconstructed on the small local model. The
honest framing (Tenet 3) is that planning and replanning *quality* are capped by the 2B — it
is not Opus — and the two-plane discipline is exactly what makes the loop usable anyway: the
model emits only an inert plan and inert replans, while the deterministic, test-gated tools do
every side effect, so each step stays reliable even when the sequencing is imperfect. Because
single-function benchmarks cannot measure planning, the honest metric is a multi-step eval that
scores whether the loop drives the tools to green from a high-level request. The spec also gives
the harness long-term project memory it can read to anchor conventions and append durable
learnings (only through the tool plane), a plan mode that shows the plan before acting, and
whole-run checkpoints to undo an entire run — mapping the remaining Claude-Code features to
jaros-code's local-only, two-plane constraints.
