# Intent

EXT-015 exists to lift the small local model's coding capability by decomposing *generation itself* —
the research-derived **plan-then-code** mechanism — rather than asking the 2B for a monolithic, single-pass
solution it often cannot produce. The model first emits a concise natural-language **implementation
strategy** (steps + edge cases); a **deterministic** strategy-filter then cleans that plan (stripping
few-shot contamination and boilerplate, keeping the concrete actionable steps); and the code grain finally
implements *from the filtered plan*. This directly serves PRIME-001's design principles: the planning
judgement is the model's (an inert Decision), while the filtering is a deterministic execution-plane tool
with `validate()`/`execute()` (two-plane discipline, Tenet 1) — and, crucially, the filter is deterministic
precisely because a small model cannot reliably improve its own scaffold, so the harness must.

The mechanism is **additive and opt-in** (a `--plan` flag; the default solve is byte-identical when it is
off) and every claim about it is held to honest measurement (Tenet 3): plan-then-code is integrated into
the default path only if it shows a real, reproducible lift on a trustworthy bar, never on noise. It was
measured at parity on the noisy 37-task suite and is retained as an available mechanism, not the default —
an honest non-win recorded faithfully. EXT-015 builds on EXT-012/EXT-013 (the behavioral solve) and serves
PRIME-001; it never overrides it.
