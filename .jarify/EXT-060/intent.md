# Intent

EXT-060 is **THE canonical real-systems scoreboard** — the ONE tracked pass@1 number for whether the
model+harness can genuinely build AND modify real systems, superseding the drift of several
overlapping "real-systems-ish" suites that had accumulated (each claiming a piece of the North-Star
story, none of them the whole story, none of them growing in lockstep).

It has **two halves, never one**: a **CREATE half** (a real system built from a bare sentence, via
`harness.system_builder.build_system`) and a **MODIFY half** (an already-working real system changed
from a one-sentence change request, via `harness.system_builder.modify_system`) — because "can it
build" and "can it change something that already works without breaking it" are two different, both
load-bearing, capabilities, and a scoreboard that only measures one is silently blind to the other.
The task roster is **fixed and only ever GROWS** (new tasks are appended; existing tasks are never
swapped out, watered down, or renamed away) — so the number is comparable release over release, never
gamed by task churn.

Every single task, in both halves, is graded by an **INDEPENDENT execution-plane oracle** — a
filesystem re-read (`fs_oracle`), a sandboxed import-and-call (`import_driver`), or an exact-stdout
CLI check (`cli-exact`) — never by the model's own self-acceptance checklist, never by a hand-written
leaf template silently substituting for genuine capability. The suite explicitly asserts the LEAF path
stayed OFF for every task (Tenet 3: a leaf-produced green proves nothing about the model's own
capability, and is scored a failure, not a pass). The **one reported number** is a single unified
pass@1 — `(create passes + modify passes) / (total create + modify tasks)` — tracked over time as the
headline; per-half and per-class breakdowns are diagnostic detail underneath it, never a second
headline competing with the first.

**This spec formally DEMOTES the suites that used to compete for "the number":** `harness/
system_suite.py`'s toy-CLI creation suite, `harness/modification_suite.py`'s modify board, and
`harness/daily_driver.py`'s North-Star instrument are now REGRESSION CHECKS and task-shape FEEDERS
only — useful for catching a local regression fast, and for donating well-shaped task ideas upward —
but NONE of them is the tracked capability number anymore. Reporting a pass rate from any of those
suites as "the real-systems number" going forward is a spec violation; EXT-060's combined pass@1 is
the only number that answers "can the harness build/modify real systems," and it is the one to quote,
trend, and steer from.

**How it converges toward the Prime Directive:** the independent oracles are pure execution-plane code
(Tenet 1) — the model never grades its own work. Every oracle is deterministic and reproducible byte
for byte (Tenet 3), and the suite is honest by construction: a leak-free sentence-derived oracle, a
leaves-OFF guardrail, and a "never raises, never fabricates a pass" runner on both halves. The suite
runs exclusively on the small local model (`gemma-4-e2b` via llama.cpp on the Jetson — Tenet 2); it
never escalates to a paid/cloud model even to get a better score. And it is itself governed spec-first
through the Jarify workflow (Tenet 4) — the roster's growth, like every other change to this repo,
flows through `jarify-manage-specs`/`-tasks`/`-links`, never an ad-hoc edit. Growing this one number,
honestly, is how jaros-code measures its own progress toward Claude-Code-class real-systems capability
on Jetson-tier hardware.
