# Intent

This spec exists to build the **deterministic verification toolset** — the plane of tools that
makes a hard-class failure **visible, localized, and fed back** so the small local Gemma 4 2B can
reason on it. It is the direct execution of the owner re-directive (2026-07-07): *refuse to believe
there is a cap on a model's reasoning when it is coupled with a sufficient set of deterministic
tools; find the complete set.* Every measured hard-class "0" (best-of-k net-negative on
semantic-ordering classes; the hard multi-step-repo residual) is treated here not as a model
ceiling but as a **missing deterministic tool** whose absence left the failure mode invisible to
both the model and the acceptance signal.

The first requirement is the **ADT differential oracle** — a two-plane tool that classifies a built
system against a canonical abstract-data-type reference (LRU / priority-queue / TTL-store /
FIFO / ring-buffer), drives seeded boundary-stressing operation sequences through both the textbook
reference and the built CLI in lockstep, and reports the **first diverging operation** as a
concrete, localized witness. This makes the semantic-ordering blind spot (the exact spot best-of-k
amplified) *visible* — the signal the acceptance oracle and the execution-feedback repair loop were
missing. Later requirements extend the toolset toward the complete set (structural-invariant
harness, fault localization, delta-debugging minimizer, dynamic-invariant differ).

It converges toward the Prime Directive on three tenets at once: **Tenet 1 (two-plane)** — the tool
does all deterministic work (classify, model, drive, compare, localize) and the model makes only the
narrow now-visible fix judgment; **Tenet 3 (honest)** — the oracle's reference models are built from
the *visible* spec's declared operations (never from the eval's hidden tests), it is seeded and
byte-replayable, and it composes into acceptance by **union only**, so it can only ever flip a
build's `done` from True→False (the 0-false-done invariant is preserved by construction); and the
**Founding Assumption** — it is the concrete harness mechanism that lifts the hard class rather than
conceding it.
