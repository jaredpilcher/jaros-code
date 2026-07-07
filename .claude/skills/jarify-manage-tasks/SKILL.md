---
name: jarify-manage-tasks
description: Create and manage step-by-step implementation tasks based on Jarify requirements. Use this skill when asked to define tasks for requirements or update tasks.md in a Jarify project.
---

# Jarify: Manage Tasks

This skill provides the strict formatting rules for defining and managing implementation tasks for Jarify specifications.

## Core Rules

Tasks represent the step-by-step implementation plan for the requirements defined in a specification. Tasks must be "not too big and not too small".

Tasks are stored in a `tasks.md` file within the respective specification folder (e.g., `.jarify/EXT-001/tasks.md`).

**Do not automatically create tasks without user approval.** You can propose creating tasks when discussing requirements, but only modify `tasks.md` upon explicit request.

## Formatting `tasks.md`

The `tasks.md` file should begin with a high-level title.

Every single task MUST adhere to this exact Markdown hierarchy and naming convention:

```markdown
# Implementation Tasks

### [TASK-1] Implement API Endpoint

Detailed description of what this task accomplishes.

#### Steps
1. Create the router in `src/routes.ts`
2. Implement the controller logic
3. Add input validation using Zod

#### Implements
- [REQ-1] API Export
- [REQ-2] Component Initialization
```

**Crucial Formatting Restrictions:**
- The task ID MUST be in brackets: `[TASK-X]`
- The task header MUST be an H3: `###`
- Every task MUST contain a `#### Steps` heading followed by an ordered list (`1.`, `2.`, etc.). **These steps MUST describe the exact, specific code changes that will happen** (e.g., "Add `fetchData()` method to `src/api.ts` to execute a GET request"). Do not be vague.
- Every task MUST contain a `#### Implements` heading followed by a bulleted list (`- `) of the Requirement IDs and Titles that it fulfills. The Requirement ID must exactly match the `[REQ-X]` format from `requirements.md`.

## Task Granularity

Tasks must be "not too big and not too small." If a task feels like it contains too many sweeping changes across too many files, you MUST break it up into smaller, cohesive tasks.

- **Too Big**: "Implement the entire backend." (Too many systems involved)
- **Too Small**: "Define the `id` variable." (Not a complete unit of work)
- **Just Right**: "Implement the user authentication endpoint and password hashing in `src/auth.ts`."

Each task should cover a cohesive unit of work that can be implemented and tested together, fulfilling specific acceptance criteria from the linked requirements.
