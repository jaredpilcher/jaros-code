---
name: jarify-manage-specs
description: Manage Jarify specification folders and documents. Use this skill when you need to add, modify, or remove specifications (requirements.md, design.md, tasks.md) in a Jarify project (the `.jarify` directory).
---

# Jarify: Manage Specifications

This skill provides the strict formatting rules for managing Jarify specification documents. Use these instructions when adding or removing requirements in the `.jarify` directory.

## Core Rules

1. **Folder Structure**: Every specification lives in its own isolated folder under `.jarify/`. The folder name MUST match the specification ID exactly (e.g., `.jarify/EXT-001/`).
2. **Required Files (EVERY spec MUST have all of these — owner directive 2026-07-04):**
   - `intent.md`: **The spec's own INTENT** — a concise statement of *why this spec exists* (the local purpose/capability it serves) and *how it converges toward the Prime Directive*. Every spec MUST have one. (This is the spec's LOCAL intent, distinct from the Prime Directive's system-wide intent — see below.)
   - `design.md`: Architectural documentation and ASCII diagrams. Every spec MUST have one.
   - `requirements.md`: The core requirements definition (the `### [REQ-x]` blocks that serve this spec's intent).
   - `tasks.md`: Step-by-step implementation tasks (managed by the `jarify-manage-tasks` skill).
   - `index.json`: The generated line-number mapping file (managed by the `jarify-manage-links` skill).

   When CREATING a spec, author `intent.md` and `design.md` alongside `requirements.md` from the start. When you find an existing spec MISSING either, backfill it (read the requirements to state the intent it clearly serves, consistent with the Prime Directive).

## The Prime Directive (System Intent)

A Jarify project SHOULD define a single **Prime Directive** — the top-level statement of intent for the *entire* system. It is the "north star" that every other specification must serve and must never contradict.

The Prime Directive is **special — it is NOT a normal specification** and must never be treated like one. It is distinguished from ordinary feature specs by three things:

1. **Reserved ID**: Its folder name uses the reserved prefix `PRIME` (e.g., `.jarify/PRIME-001/`). There is exactly ONE prime directive per project.
2. **Only two files, never requirements**: The Prime Directive folder contains ONLY `intent.md` and `design.md`. It MUST NEVER contain `requirements.md`, `tasks.md`, or `index.json`. The Prime Directive is never decomposed into requirements, tasks, or code-traceability links — it is the pure intent that all of those things ultimately serve. (Note: ordinary specs ALSO have their own `intent.md` now — what makes the Prime Directive special is that it has ONLY intent+design and no requirements/tasks/index; it is the SUPREME, system-wide intent, whereas a spec's intent is LOCAL and must converge toward it.)
3. **Authority**: It expresses the non-negotiable architectural intent and purpose of the whole system. When adding or modifying ANY other specification, you MUST ensure it is consistent with the Prime Directive. Every spec's own `intent.md` must converge toward — and never contradict — the Prime Directive. If a new requirement or spec intent would contradict it, STOP and flag the conflict to the user before proceeding.

### Formatting a spec's `intent.md` (every ordinary spec)

Under an `# Intent` heading, a concise prose statement of (a) **why this spec exists** — the specific
capability, gap, or product need it serves — and (b) **how it converges toward the Prime Directive**
(which tenet/goal it advances). Keep it to the essential local purpose: no requirement IDs, no
acceptance criteria, no task lists (those live in `requirements.md`/`tasks.md`). It is the "north star
for THIS spec" that its requirements serve and that the whole spec must not drift from. A few sentences
is right; it should read as the durable reason the spec is worth having.

### Formatting the Prime Directive's `intent.md`

`intent.md` holds the directive itself: a concise prose statement of the system's ultimate intention, under an `# Intent` heading. Keep it to the essential, non-negotiable intent — no requirement IDs, no acceptance criteria, no task lists.

### Formatting the Prime Directive's `design.md`

This follows the same rules as any other `design.md` (see "Formatting `design.md`" below): high-level architecture plus meaningful ASCII diagrams. For the Prime Directive it should map out the system-wide architecture that the intent demands.

## Formatting `requirements.md`

### 1. YAML Frontmatter

Every `requirements.md` file MUST start with the following YAML frontmatter:

```yaml
---
id: EXT-001               # Must match folder name
title: Feature Name       # Human readable title
status: covered           # Valid values: 'covered', 'partial', 'uncovered'
priority: high            # Valid values: 'high', 'medium', 'low'
implementation:           # High-level file ranges covered by this spec
  - file: src/feature.ts
    ranges:
      - - 1               # Start line
        - 150             # End line
---
```

### 2. Requirements Definition

The body of `requirements.md` contains the specific requirements. Every single requirement MUST adhere to this exact Markdown hierarchy and naming convention:

```markdown
### [REQ-1] Name of the Requirement

Detailed description of what the requirement entails.

#### Acceptance Criteria
- [ ] Implement X
- [ ] Verify Y handles Z properly
```

**Crucial Formatting Restrictions:**
- The requirement ID MUST be in brackets: `[REQ-X]`
- The requirement header MUST be an H3: `###`
- Every requirement MUST be followed by an H4 `#### Acceptance Criteria` heading.
- The criteria MUST be a Markdown task list: `- [ ]`

## Formatting `design.md`

The `design.md` document should provide architectural context for the specification.

1. It should include high-level descriptions of the system design.
2. It MUST include meaningful ASCII diagrams to map out the structure or flow of the components discussed in the requirements. Use ```text blocks for diagrams.

## Creating and Maintaining Tasks

Tasks describe how the requirements will be implemented.
- Tasks are created and maintained in `tasks.md`.
- See the `jarify-manage-tasks` skill for detailed rules on generating and formatting tasks.
- You may propose creating tasks to implement requirements when discussing them with the user, but you should only create or modify `tasks.md` when explicitly requested by the user.

## Host-project side effects MUST go through a Jaros Decision (Tenet 1)

Any new product-surface feature that performs a HOST-PROJECT side effect (file write/patch/shell)
MUST do so through a Jaros Decision via `Runtime.apply`, never raw `open()`/`write_text()`. Config
READS + REPL/CLI glue + internal state (e.g. `.jaros-data/`) may stay plain Python.

## Modifying Existing Specifications

When modifying existing specs:
- **Do not rewrite unaffected requirements.** Only surgically add or remove the necessary `### [REQ-X]` blocks.
- **Maintain ID continuity.** If you add a new requirement, use the next available ID number (e.g., if REQ-3 exists, use REQ-4).
- **Update statuses.** If you add a brand new, unimplemented requirement, update the YAML frontmatter `status` to `partial` or `uncovered`.
