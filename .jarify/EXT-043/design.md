# EXT-043 — Design

## Problem

`harness/cli.py::main()` already has a one-shot path (`python -m harness.cli "request"` runs one
request through `JcodeCli.handle()` and exits) alongside the interactive REPL. GAP-MAP row #13 names
four concrete missing pieces on top of that one-shot path: (1) reading the request from a Unix pipe
(stdin) instead of only `argv`, (2) a machine-parseable `--output-format json` alternative to the
current human text, (3) a `--max-turns` cap for scripted/CI safety, and (4) a deterministic
success/failure process exit code. All four are pure execution-plane packaging around the SAME
`JcodeCli.handle()` call that already exists — this spec does not touch the orchestrator, any agent,
or any tool.

## Mechanism

```
 argv / stdin                              headless argument parsing (deterministic, no model call)
 ┌────────────────────────┐                ┌───────────────────────────────────────────────┐
 │ sys.argv[1:]            │──────────────▶│ harness/cli.py :: _parse_headless_args(args)    │
 │  --resume <id>          │                │   strips --resume/--output-format/--max-turns   │
 │  --output-format json   │                │   wherever they occur; everything else stays    │
 │  --max-turns N          │                │   IN ORDER as the plain-request tokens (`rest`) │
 │  "plain request words"  │                │   -> (session_id, output_format, max_turns, rest)│
 │  "-"  (explicit stdin)  │                └───────────────────────────────────────────────┘
 └────────────────────────┘                                     │
                                                                  ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────┐
 │ harness/cli.py :: main()                                                                    │
 │                                                                                              │
 │   rest == ["-"]                -> request = stdin.read().strip()   (explicit pipe request)  │
 │   rest non-empty               -> request = " ".join(rest)          (existing one-shot path) │
 │   rest empty + stdin NOT a tty -> request = stdin.read().strip()   (new: `echo x | jcode`)   │
 │   rest empty + stdin IS a tty  -> request = None -> repl(session_id)  (UNCHANGED)            │
 │                                                                                              │
 │   request is None -> repl()  (byte-identical interactive REPL path)                          │
 │   request given   -> _run_one_shot(request, session_id, output_format, max_turns)            │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
                                                                  │
                                                                  ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────┐
 │ harness/cli.py :: _run_one_shot(...)                                                         │
 │                                                                                              │
 │   max_turns is not None and max_turns < 1                                                    │
 │        -> refuse WITHOUT constructing JcodeCli / calling handle()  -- the honest cap          │
 │                                                                                              │
 │   otherwise: cli = JcodeCli(session_id=...); response = cli.handle(request)                  │
 │        text  format -> print(response)                       exit 0                          │
 │        json  format -> print(json.dumps({request, response, ok, model}))   exit 0             │
 │        (any exception raised by handle()/__init__)                                           │
 │             text format -> print("\033[31merror:\033[0m {exc}")            exit 1             │
 │             json format -> print(json.dumps({..., ok: False, error: str(exc)}))  exit 1       │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **`_parse_headless_args(args)`** is the sole new parsing routine: a linear scan of `argv[1:]` that
  recognizes exactly three flag forms (`--resume <id>`, `--output-format text|json`, `--max-turns N`)
  wherever they appear and leaves every other token untouched, in its original relative order, in
  `rest`. When none of the three flags are present, `rest == args` (minus nothing) — the input to the
  existing one-shot join is unchanged byte-for-byte, which is what makes the "no new flags -> no
  behavior change" backward-compat guarantee mechanical rather than merely intentional.
- **stdin detection** is a single `sys.stdin.isatty()` check (wrapped so any detection failure
  conservatively assumes "yes, a tty" and falls through to the existing REPL, never silently
  swallowing a live terminal session into a stdin read). The explicit `-` request token bypasses the
  tty check entirely (mirrors `claude -p -` / common Unix-tool convention for "read this argument from
  stdin no matter what").
- **`--output-format`** supports `text` (default, current human string, byte-identical) and `json`
  (single structured object: `request`, `response`, `ok`, `model`, and `error` when `ok` is false).
  `stream-json` (line-delimited per-event output) is explicitly **deferred** — the existing one-shot
  path only ever produces ONE final response (there is no intermediate per-tool event stream exposed
  at this seam today; EXT-040's heartbeat/activity log is the closest existing "stream" and is a
  separate, already-shipped observability surface). Building a genuine multi-line NDJSON event stream
  would mean threading heartbeat/tool-level events through `handle()` — a materially bigger, riskier
  change than "a thin layer over the existing one-shot path" calls for. This is recorded here plainly
  (Tenet 3 — no silent scope inflation) rather than half-built.
- **`--max-turns N`** is honored as a real, enforced cap, honestly matched to what the one-shot path
  actually does: `JcodeCli.handle()` performs exactly ONE turn (one call into the orchestrator/agent/
  slash dispatch, no internal replanning loop today). So `--max-turns N` for `N >= 1` is accepted with
  no further effect (the path never exceeds 1 turn regardless), and `N < 1` is enforced as a genuine
  refusal — `_run_one_shot` returns a failure (`ok: false`, exit 1) WITHOUT ever constructing
  `JcodeCli` or calling `handle()`, so a caller that deliberately caps at zero turns gets an honest,
  observable no-op rather than a silently-ignored flag. `/agent`'s internal replan loop (EXT-009) is a
  separate, already-bounded mechanism and is not re-wired here (out of scope, see below).
- **Exit codes**: `0` on any successful `handle()` return (a response was produced, whatever its
  content), `1` on any exception escaping `JcodeCli(...)`/`handle()` — including safety-gate refusals,
  the max-turns-before-any-work refusal above, and any tool/agent error. This mirrors the existing
  one-shot `try/except` contract exactly (today's `main()` already returns 1 on exception) rather than
  attempting to parse arbitrary response *text* for "did it really solve it" (which would be an
  unreliable, command-specific heuristic across dozens of different `cmd_*` response shapes — not a
  deterministic contract worth codifying).

## Two-plane / honesty

Every function this spec adds (`_parse_headless_args`, `_read_stdin_request`, `_run_one_shot`) is
pure deterministic execution-plane code (Tenet 1): argv scanning, a stdin read, a `try/except`, and a
`json.dumps` call. None of it calls the LLM or changes what the orchestrator/agents decide — it only
changes how the SAME decision's result is packaged and reported to a non-interactive caller.

## Backward compatibility (no regression)

- `rest` is unchanged when none of the three flags are used, so the plain one-shot invocation
  (`python -m harness.cli "request"`) produces the identical printed text and identical exit codes
  (0 success / 1 exception) as before this spec, by construction — `_run_one_shot`'s `text`-format,
  no-`max-turns` branch performs the exact same `try: print(handle(...)) except: print(error); return
  1` sequence the old `main()` body did, merely factored into a helper.
- The interactive REPL (`repl()`) is untouched — it is reached only when `rest` is empty AND stdin
  is a real tty, exactly as `args` being empty triggered it before.
- `harness/product_parity.py` row #13's `state` only flips from `"partial"` if stdin piping, JSON
  output, and exit codes are ALL genuinely wired and test-covered; `stream-json`'s deferral is recorded
  honestly in `current_state`/`next_lever` rather than silently omitted.

## Out of scope (this task)

`stream-json` (line-delimited event streaming) — see above, deferred pending a genuine per-tool event
stream at the `handle()` seam. `--json-schema` (a caller-supplied output schema) and `-p`/`--print`
as an explicit alias flag (the bare one-shot invocation already serves that role for `jcode`) are not
built here; GAP-MAP can track them as a future increment on this same row if the owner wants the exact
`claude -p` flag surface mirrored 1:1. Re-wiring `/agent`'s own internal replanning loop (EXT-009) to
respect `--max-turns` is also out of scope — this spec caps the *one-shot invocation's* turn count,
not `/agent`'s separate, already-bounded plan/act/observe loop.
