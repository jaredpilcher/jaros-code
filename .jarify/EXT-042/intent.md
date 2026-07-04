# Intent

Claude Code's `CLAUDE.md` is the mechanism by which a developer steers every session of the
product with durable, auto-loaded project instructions — conventions, architecture notes,
how-to-run commands — without having to restate them each time. `docs/GAP-MAP.md`'s
Product-surface parity row #14 names this gap explicitly: jaros-code has `.jcode/memory.md` +
`/remember` + an episodic store, but nothing that is *auto-loaded into the reasoning context every
session* the way `CLAUDE.md` is, no user-level tier, and no `/init` generator to bootstrap one from
repo comprehension.

This spec closes that gap with a `JCODE.md` convention: a project-root file (mirroring
`CLAUDE.md`) plus a user-level file (`~/.jcode/JCODE.md`, mirroring Claude Code's user memory
tier), both loaded deterministically (no model call — Tenet 1: the loading is execution-plane file
I/O, not a judgement) and injected as a clearly-labeled preamble into the context the
orchestrator/planner sees on every turn. An `/init` command (mirroring Claude Code's `/init`)
writes a starter `JCODE.md` from repo comprehension (reusing `harness/repo_map.py`'s structural
scan), so a new repo gets a useful instruction file with a single command rather than a blank page.

This converges PRIME-001 in two ways. First, it directly advances the "in ALL ways" whole-product
parity bar the Prime Directive names — instruction memory is called out by name alongside
sessions, headless mode, and the other product-surface rows, and the Product-Parity Checklist
(EXT-041) is the instrument that must move honestly when this ships. Second, and more materially,
it advances Tenet 4 (spec-first) and Tenet 5 (Claude-Code-like experience) at the same time: an
auto-loaded project-instruction file is exactly the kind of standing, low-cost context a small
local model benefits from most — it is a durable statement of intent the orchestrator can lean on
every turn instead of re-deriving project conventions from scratch, which is precisely the
decomposition/plane-placement discipline PRIME-001 asks for (a deterministic fact injected into
the reasoning plane, never a judgement the plane must re-make). It must remain strictly additive:
a repo with no `JCODE.md` behaves byte-identically to today (Tenet 3 — no regression to existing
JAROS.md/EXT-036 behavior, which this spec does not touch or replace).
