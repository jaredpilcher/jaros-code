# Intent

This spec exists to provide a bounded test-feedback repair scaffold — generate, run the visible
test, and if it fails, re-generate with the deterministic failure text fed back into the context
("your previous attempt … the test FAILED with … fix it") for a small number of retries. The
refined insight it targets is that a scaffold does not lift from-scratch synthesis (settled by
EXT-031) but it can multiply capability WITHIN its class; the one promising untested cell is
this repair loop paired with a stronger slow-reasoning base (qwen3-4b-thinking) on the hard-repo
class — the cheapest fitting scaffold for a reasoner that benefits from seeing its own error.
The core loop is model-agnostic and fully injectable so it is offline-testable without a Jetson.

It converges toward the Prime Directive by exercising the L1/L6 rungs — a deterministic repair
control-flow wrapped around a fitting model — and by keeping the two planes clean (Tenet 1):
`test_fn` is the sole arbiter and the model only regenerates. It holds Tenet 3 as a hard line:
the repair loop sees only the VISIBLE failing test's output (the spec the developer is given),
while the hidden grading oracle is called once at the end and never shown to the model, so no
expected output leaks into generation and the result is reported honestly against the qwen3-bare
1/4 baseline.
