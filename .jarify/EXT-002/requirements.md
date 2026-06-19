---
id: EXT-002
title: Single-Purpose Coding Agent Fleet
status: partial
priority: high
implementation:
  - file: .jaros-data/agents/editor_agent.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/agents/commander_agent.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/agents/test_reader_agent.py
    ranges:
      - - 1
        - 200
---

This spec serves **Tenets 1 & 2** of PRIME-001: capability comes from many small,
single-purpose `gemma2:2b` reasoning boundaries, each making ONE narrow judgement
and emitting only inert `Decision` data that a deterministic EXT-001 tool executes.
Each agent has a tiny prompt and a tiny output contract — the regime where a 2B
model is reliable — and never escalates to a larger model.

### [REQ-1] editor — propose one exact edit

An agent named `editor` is given a file's content and an instruction and proposes a
single exact `old`→`new` edit, emitting a `code.apply_patch` Decision. It uses a
delimited block contract (not JSON) because a 2B model produces it reliably.

#### Acceptance Criteria
- [ ] Build a focused prompt from `{path, content, instruction}` with bounded content
- [ ] Parse `<<<OLD ... OLD>>>` / `<<<NEW ... NEW>>>` blocks from the model output
- [ ] On success emit a `code.apply_patch` Decision with the parsed `old`/`new`
- [ ] On unparseable output emit an honest `advance` Decision (events start, fail) — never crash

### [REQ-2] commander — propose one shell command

An agent named `commander` is given a task and proposes exactly one shell command to
accomplish it, emitting a `shell.exec` Decision. Used to run builds and tests.

#### Acceptance Criteria
- [ ] Build a focused prompt from `{task}` (and optional `cwd`)
- [ ] Extract a single command line from the model output (strip fences/backticks)
- [ ] Emit a `shell.exec` Decision carrying that command and optional `cwd`
- [ ] On empty output emit an honest `advance` Decision (events start, fail)

### [REQ-6] config-editor — specialist for config files

A specialist agent `config-editor` (split from the broad rewriter per EXT-007/REQ-6)
edits CONFIG files (JSON/YAML/INI/TOML) with a config-focused prompt, emitting a
`code.write_file` Decision. The loop's dispatcher routes config-extension targets to
it (so it fires); `json.check` guards its JSON edits.

#### Acceptance Criteria
- [ ] Build a config-focused prompt from `{path, content, instruction}` (+ feedback)
- [ ] Parse the `<<<FILE ... FILE>>>` block (or code fence) and emit `code.write_file`
- [ ] On unparseable output emit an honest `advance` Decision (events start, fail)
- [ ] The loop dispatches config-extension targets to this specialist (it appears in wiringUsage)

### [REQ-7] dockerfile-editor — specialist for Dockerfiles

A specialist agent `dockerfile-editor` (EXT-007/REQ-6 split) edits Dockerfiles with a
Docker-focused prompt, emitting `code.write_file`. The dispatcher routes Dockerfile
targets to it (so it fires).

#### Acceptance Criteria
- [ ] Build a Docker-focused prompt from `{path, content, instruction}` (+ feedback)
- [ ] Parse the `<<<FILE ... FILE>>>` block (or code fence) and emit `code.write_file`
- [ ] On unparseable output emit an honest `advance` Decision (events start, fail)
- [ ] The loop dispatches Dockerfile targets to this specialist (appears in wiringUsage)

### [REQ-5] navigator — locate code via a tool

An agent named `navigator` decides ONE search term for a task and emits an `fs.grep`
Decision — a genuine agent→tool wiring where the agent reasons about *what* to find
and the deterministic tool does the search. Used to locate where to change code.

#### Acceptance Criteria
- [ ] Build a focused prompt from `{task}` and extract a single search term
- [ ] Emit an `fs.grep` Decision carrying that term and the search root
- [ ] On empty output emit an honest `advance` Decision (events start, fail)

### [REQ-3] test-reader — judge a test run

An agent named `test-reader` reads captured test/command output and judges
PASS/FAIL, emitting an `advance` Decision whose events drive the job to DONE or
FAILED. The model's verdict drives the outcome; the executor performs the transition.

#### Acceptance Criteria
- [ ] Build a focused prompt from `{output}` (bounded)
- [ ] Parse a one-word PASS/FAIL verdict, defaulting safely to FAIL when ambiguous
- [ ] Emit an `advance` Decision: events [start, complete] on PASS, [start, fail] on FAIL
- [ ] Record the verdict and a short note in the Decision payload
