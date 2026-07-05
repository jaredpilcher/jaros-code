# Implementation Tasks

### [TASK-1] Thin headless output layer over the existing one-shot path

Add stdin piping, `--output-format text|json`, `--max-turns` capping, and deterministic exit codes
around `harness/cli.py`'s existing one-shot `JcodeCli.handle()` invocation, without changing the
orchestrator/agents or the interactive REPL.

#### Steps
1. In `harness/cli.py`, add `_parse_headless_args(args)`: a linear scan of `argv[1:]` that recognizes
   `--resume <id>` (existing behavior, now folded into this one parser), `--output-format text|json`
   (unrecognized values fall back to `"text"`), and `--max-turns N` (non-integer values fall back to
   `None`, meaning "no cap") wherever they occur; every other token is left, in original order, in a
   `rest` list. Returns `(session_id, output_format, max_turns, rest)`.
2. Add `_stdin_is_tty()` (wraps `sys.stdin.isatty()`, defaulting to `True` — i.e. "assume interactive"
   — if the check itself raises) and `_read_stdin_request()` (reads + strips `sys.stdin`, returning
   `""` on any read failure) as small deterministic helpers.
3. Add `_run_one_shot(request, session_id, output_format, max_turns)`: if `max_turns is not None and
   max_turns < 1`, return a failure tuple `(text_or_json, 1)` WITHOUT constructing `JcodeCli`. Else
   construct `JcodeCli(session_id=session_id)`, call `.handle(request)`, and on success return
   `(response, 0)` for `text` format or `(json.dumps({"request":..., "response":..., "ok": True,
   "model": cli.model}), 0)` for `json` format. On any exception from construction or `.handle()`,
   return `(f"\033[31merror:\033[0m {exc}", 1)` for `text` format or
   `(json.dumps({"request":..., "response": None, "ok": False, "model": None, "error": str(exc)}), 1)`
   for `json` format.
4. Rewrite `main()`: call `_parse_headless_args(sys.argv[1:])`; determine `request` as `None` (falls
   through to `repl(session_id=session_id)`, unchanged) unless: `rest == ["-"]` (read stdin
   unconditionally), `rest` is non-empty (`request = " ".join(rest)`, identical to today when no new
   flags were used), or `rest` is empty and `not _stdin_is_tty()` (read stdin). When `request is not
   None`, call `_run_one_shot(...)`, `print()` its text, and `return` its exit code. Update the
   module-level `main()` docstring with the new invocation forms (piped stdin, `--output-format`,
   `--max-turns`).
5. Write `tests/test_ext043_headless.py`: stub `harness.cli.JcodeCli` (monkeypatched class) so no
   live gemma/network call is needed; cover a stdin-piped request being routed to the stubbed
   `handle()`, `--output-format json` producing `json.loads`-parseable output with the required keys,
   exit code `0` on success and non-zero on a simulated `handle()`/`__init__` exception (both output
   formats), `--max-turns 0` refusing without invoking `JcodeCli` at all, and a default/no-flags
   one-shot call producing output byte-identical to the pre-EXT-043 path (backward-compat regression
   check).
6. Update `harness/product_parity.py` row #13 (`id=13`) honestly: flip `state` to `"partial"` (already
   partial) or `"works"` only if genuinely fully delivered per this task's scope, update
   `current_state` to describe what now exists (stdin pipe, JSON output, exit codes, max-turns cap)
   and `next_lever` to name the honestly-deferred `stream-json` (and any other remaining gap), without
   inflating beyond what ships in this task.

#### Implements
- [REQ-1] Read the request from stdin when piped
- [REQ-2] `--output-format text|json`
- [REQ-3] Deterministic exit codes
- [REQ-4] `--max-turns N` cap
