---
name: jarify-manage-roadmap
description: Manage the Jarify ROADMAP — the single official, LIVING forward-plan artifact for a Jarify-governed repo (`.jarify/ROADMAP.md`). Use this skill whenever you add/re-prioritize/advance/land/park roadmap items, or when the convergence loop needs to maintain or regenerate the roadmap. It holds the high-level plan tasks can't: which specs/requirements we intend to CREATE and IMPLEMENT next, organized by horizon, before tasks exist for them.
---

# Jarify: Manage the Roadmap

The **Roadmap** is a first-class Jarify governance artifact — one per repo, at `.jarify/ROADMAP.md`.
It fills the gap between the **Prime Directive** (the fixed north-star intent) and **tasks** (per-spec
implementation units): it is the **living forward plan** across specs — *which specs/requirements we
intend to create and implement next*, organized by horizon, with priority and rationale, **before**
tasks (or even the specs) exist. It uses and extends the **gap-map paradigm**.

## Core principles (the gap-map paradigm)

1. **Impact × tractability ranks everything.** The top of `NOW` is always the highest-leverage,
   most-tractable next move toward the Prime Directive's intent.
2. **Progress is the scoreboard TREND, never activity or commit count.** Every item ties to a
   scoreboard number, a measured gap, or a Prime-Directive capability — not "we did a thing."
3. **Honest.** Never inflate status. An item is `LANDED` only when it is actually shipped + verified.
   Park model-bound / net-negative work honestly (with a reason + a revisit trigger), never as "done."
4. **LIVING + UNBOUNDED.** The roadmap is **never finished**. When `NOW` empties, you MUST pull the
   next item(s) from `NEXT`, and when the whole plan thins, **regenerate** the next horizon from the
   Prime Directive intent + the measured gaps (see "Regeneration"). An empty roadmap is a signal to
   look harder, never to stop.

## Structure of `.jarify/ROADMAP.md` (keep these sections, in this order)

- **North Star** — a short restatement of the Prime Directive's intent (the target this plan serves).
- **Scoreboard (brief)** — the few honest headline numbers; link to `docs/GAP-MAP.md` for detail.
- **NOW** — in flight: the 1–3 items actively being worked this cycle (the top of the loop).
- **NEXT** — planned soon (this week): specs/requirements to create + implement next.
- **LATER** — planned later (weeks+): larger bets, roster/flywheel, capstones.
- **PARKED** — deferred with an explicit REASON + a revisit trigger (model-bound, banked-negative, blocked).
- **GAPS** — measured gaps (impact × tractability), each linking to the GAP-MAP evidence.
- **LANDED** — a recent trail (newest first) of shipped items with commit hashes.

## Item format

```
- **[<id|tag>]** <one line describing the spec/requirement/gap/milestone> — <priority> · <rationale, links to spec·REQ·GAP·#task·commit>
```
- `<id|tag>`: a spec id (`EXT-041`), a spec+req (`EXT-039 REQ-2`), a `(new spec)` marker for a
  spec that does not exist yet, or a short kebab tag for a cross-cutting bet (`best-of-k-select`).
- `<priority>`: `high` | `med` | `low`.
- Rationale must tie to the intent / a scoreboard number / a measured gap. Link specs, REQs, GAP-MAP
  entries, task numbers, or commit hashes so the item is traceable.

## Operations (what this skill does)

- **Add a planned item:** insert a bullet into the correct horizon (`NEXT`/`LATER`) with a `(new spec)`
  tag if the spec doesn't exist yet. Placing a *future spec/requirement* here is the whole point —
  you do NOT need the spec to exist first (that's the gap tasks couldn't fill).
- **Advance an item:** move it up a horizon as it becomes the next move (`LATER`→`NEXT`→`NOW`). When it
  reaches `NOW` and work starts, create its spec via `jarify-manage-specs` and its tasks via
  `jarify-manage-tasks`, then implement through the builder→architect workflow.
- **Land an item:** when it ships + is verified/committed, move it to `LANDED` (newest first) with the
  commit hash, and remove it from `NOW`.
- **Park an item:** move to `PARKED` with an explicit REASON and a REVISIT TRIGGER (e.g. "model-bound;
  revisit on a stronger base"). Parking is honest deferral, never silent dropping.
- **Re-prioritize:** reorder within/`across horizons by impact × tractability when new evidence lands.
- **Record a gap:** add measured gaps to `GAPS` with a link to the GAP-MAP evidence.

## Regeneration (the living contract — REQUIRED, not optional)

The convergence loop maintains the roadmap **every tick**:
1. Reconcile with reality: mark shipped items `LANDED`; move blocked items to `PARKED` with a reason.
2. Ensure `NOW` is non-empty: if it emptied, promote the top `NEXT` item(s) into `NOW`.
3. If the whole plan has thinned (few/no credible `NEXT`/`LATER` items), **REGENERATE**: re-read the
   Prime Directive `intent.md` + `docs/GAP-MAP.md` + the scoreboard, and author the next horizon of
   specs/requirements/bets that move the north-star number — the pursuit is unbounded, so there is
   ALWAYS a next horizon. Never leave the roadmap empty and never conclude "done."
4. Keep it honest and lean: prune stale/duplicate items; every remaining item must still tie to the intent.

## Roadmap vs. tasks (two complementary layers — do not conflate)

- The **Roadmap is LONGER-HORIZON** — the forward-seeking plan of which specs/requirements are coming,
  across horizons (weeks). The **task list is SHORT-TERM** — the immediate work, executed exactly as it
  always has been (TaskCreate/TaskUpdate → jarify-builder → jarify-architect).
- The roadmap **FEEDS** the tasks: a `NOW` item, when it becomes the immediate work, is decomposed into
  concrete tasks and executed the normal way. The roadmap does NOT replace, subordinate, or bypass the
  task list — it is the longer-range steering above it. Both are maintained every tick.

## Guardrails

- **One roadmap per repo** (`.jarify/ROADMAP.md`); never fork competing plans.
- **Spec-first still holds:** the roadmap PLANS specs/requirements; actually creating/implementing them
  still flows through `jarify-manage-specs` / `jarify-manage-tasks` → **jarify-builder** → **jarify-architect**,
  spec + code in the same commit. The roadmap is the layer ABOVE that, not a bypass of it.
- **Prime Directive supreme:** a roadmap item must never plan something that contradicts the Prime
  Directive. If it would, STOP and flag the conflict.
- Roadmap edits are governance-doc edits (safe anytime); they don't need a builder/architect, but the
  convergence loop should keep them consistent with specs/tasks/GAP-MAP.
