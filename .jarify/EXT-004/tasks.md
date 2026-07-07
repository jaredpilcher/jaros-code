# Implementation Tasks

### [TASK-1] Slash-command REPL loop

An interactive prompt loop modelled on Claude Code: dispatches `/`-prefixed commands,
prints a Claude-Code-like banner naming the local model, and handles `/help`/`/quit`/`/clear`
and unrecognized input gracefully.

#### Steps
1. Implement `cmd_help` in `harness/cli.py` (lines 621-623) listing every available slash
   command.
2. Implement `dispatch()` (lines 2326-2346) — the central `/`-prefix router that maps a typed
   command to its handler, falling back to natural-language routing (TASK-3) for non-slash
   input.
3. Implement `repl()` (lines 2414-2480) — the interactive loop: print the model-naming banner,
   read a line, hand it to `dispatch()`, print the result, loop until `/quit`.
4. Cover the REPL surface in `tests/test_ext004_cli.py` (lines 17-21).

#### Implements
- [REQ-1] Slash-command REPL

### [TASK-2] Fleet-wiring commands

Commands that make the CLI a real wiring surface: each one drives a single-purpose agent
or deterministic tool through the Runtime, so the agents/tools are actually used, not
orphaned. Covers `/find`, `/run`, `/grep`, `/ls`, `/read`, `/symbols`, `/status`, `/report`,
`/fix`, plus the navigation suite (`/map`, `/usages`, `/about`, `/callers`, `/defn`,
`/deadcode`).

#### Steps
1. Implement `cmd_find`/`cmd_run` (`harness/cli.py` lines 624-646, 730-750) — `/find` drives
   the `navigator_agent` then runs `fs.grep`; `/run` drives the `commander_agent` then runs
   `shell.exec` through the safety gate.
2. Implement the read-only tool commands `/grep`/`/ls`/`/read`/`/symbols` (line 752-754 and
   surrounding handlers) invoking their tools directly through the Runtime.
3. Implement `/status`/`/report` surfacing live metrics, and `/fix` driving the coding loop
   (`fix_loop`).
4. Implement the navigation-suite commands (`/map`, `/usages`, `/about`, `/callers`, `/defn`,
   `/deadcode`), backed by `harness/navigate.py` and `harness/repo_map.py`.
5. Cover with `tests/test_ext004_navigate.py` and `tests/test_ext004_repomap.py`.

#### Implements
- [REQ-2] Commands that wire the fleet

### [TASK-3] Natural-language routing

Non-slash input is classified by the `orchestrator_agent` (Gemma 4 2B `e2b`) into one of a
fixed action set, then dispatched to the matching specialist command — the model decides
WHAT the user wants, the deterministic CLI decides HOW, transparently showing the routing
decision to the user.

#### Steps
1. Implement `_is_multistep`/`_route_intent`/`_route_plain`/`handle()` in `harness/cli.py`
   (lines 2119-2321): classify non-slash input via `orchestrator_agent`, print the routing
   decision (`"[orchestrator → …]"`), and dispatch to the chosen command.
2. Fall back to a safe default (help) when the classification is unclear.

#### Implements
- [REQ-4] Natural-language routing (the system decides which agents/tools)

### [TASK-4] Multi-step planning via `/plan`

The `planner_agent` turns a natural-language request into an inert ordered JSON plan over a
fixed verb set (find/read/fix/run); a deterministic executor grounds vague args per-verb and
runs each step in order — the model plans, tools/agents act.

#### Steps
1. Implement `planner_agent.parse_plan` keeping only well-formed steps with a known verb.
2. Implement `cmd_plan` (`harness/cli.py` lines 1551-1590) — the deterministic executor that
   grounds each planned step (`fix` → `multi_file_fix`, `run` → the test suite, `find`/`read`
   → navigator/reader) and runs them in sequence.
3. Verify end-to-end on gemma-4-e2b via `harness/plan_eval.py`'s 3-scenario eval
   (cross-file fix, from-stub implementation, single-file fix).
4. Cover with `tests/test_ext004_planner.py`.

#### Implements
- [REQ-5] Multi-step planning (toward "give it a request and it works")

### [TASK-5] Continual Claude-Code parity (ongoing, not a discrete build)

REQ-3 is a standing tracking commitment ("study Claude Code, adopt what fits the two
planes"), not a one-time discrete implementation — it is satisfied by the cumulative body
of product-surface parity work landed across many later specs (EXT-041 through EXT-055:
JCODE.md, headless mode, sessions, terminal UX, custom skills, hooks, permissions,
checkpoint/rewind, MCP client, subagent authoring, context management, background runs,
interrupt/steer — all tracked against the official Product-Parity Checklist). No dedicated
`harness/cli.py` line range is claimed here beyond what TASK-1/2/3/4 already cover; this
entry exists so REQ-3 is traceable to its actual satisfying mechanism (the standing
product-parity program) rather than left silently unimplemented.

#### Implements
- [REQ-3] Continual Claude-Code parity
