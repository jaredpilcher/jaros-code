# Intent

This spec exists to compose the single-purpose agents (EXT-002) and deterministic tools
(EXT-001) — individually incomplete — into the bounded edit→test→judge loop that actually
fixes code, serving Tenets 1, 3 and 5 of PRIME-001. Every step routes through the real
Jaros gate and executor so each Decision is validated, executed, and recorded in the
decision log, keeping the run replay-faithful, while the streaming transcript gives the
operator a transparent, Claude-Code-like view of exactly what the harness is doing. The
loop embodies the deeper half of the decomposition mandate: when a bug turns on a single
operator a 2B genuinely cannot reason about, the fix moves into the deterministic plane as
mechanical mutation-and-test rather than being sliced into ever-thinner judgements the
model still cannot make. It also recognizes that cold synthesis is best served not by one
strategy but by a test-gated cascade of complementary strategies whose union strictly
beats any single one, and that a fault may live in a different file than the one under
test — so locating the file is deterministic plane work and only the fix is the model's.
The whole point is to extract genuine coding capability from a small local model through
sharper scaffolding, never by escalating the model, and to prove it on real, external
benchmarks.
