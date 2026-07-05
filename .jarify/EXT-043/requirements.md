---
id: EXT-043
title: Headless / Unix-composable CLI
status: covered
priority: high
implementation:
  - file: harness/cli.py
    ranges:
      - - 1349
        - 1499
  - file: harness/product_parity.py
    ranges:
      - - 74
        - 92
  - file: tests/test_ext043_headless.py
    ranges:
      - - 1
        - 277
---

# EXT-043 — Headless / Unix-composable CLI

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #13 — the Claude Code
headless/`-p`/piping surface. jcode already has a one-shot invocation
(`python -m harness.cli "request"`); this spec adds stdin piping, `--output-format text|json`,
`--max-turns`, and deterministic exit codes as a thin deterministic layer over that existing path —
no change to orchestrator reasoning.

### [REQ-1] Read the request from stdin when piped

`python -m harness.cli` (no request argument) reads the request from stdin when stdin is not a TTY
(a genuine Unix pipe, e.g. `echo "fix foo.py" | python -m harness.cli`); `python -m harness.cli -`
reads from stdin unconditionally, regardless of TTY state. Both route the piped text through the
exact same `JcodeCli.handle()` call the existing one-shot path uses.

#### Acceptance Criteria
- [x] No request argument given AND stdin is not a TTY: the request is read from stdin, stripped, and passed to `JcodeCli.handle()`.
- [x] The literal request argument `-` reads from stdin unconditionally (even if stdin happens to be a TTY).
- [x] No request argument given AND stdin IS a TTY: behavior is unchanged — the interactive REPL starts, byte-identical to today.
- [x] A plain-argument one-shot request (`python -m harness.cli "request"`, no new flags) is unaffected — request text and routing are byte-identical to today.

### [REQ-2] `--output-format text|json`

Add an `--output-format` flag accepted anywhere in `argv` (default `text`, i.e. today's human
output, unchanged). `--output-format json` emits exactly one machine-parseable JSON object to stdout
containing at least `request`, `response`, `ok`, and `model` keys (plus `error` when `ok` is false).
`stream-json` is explicitly deferred (recorded honestly in `design.md`, not silently omitted) — this
requirement covers `text` and `json` only.

#### Acceptance Criteria
- [x] `--output-format json` prints a single line that `json.loads` parses without error.
- [x] The parsed JSON object contains `request`, `response`, `ok`, and `model` keys on a successful run.
- [x] `--output-format text` (or the flag omitted entirely) produces output byte-identical to the pre-EXT-043 one-shot path when no other new flag is used.
- [x] An unrecognized `--output-format` value falls back to `text` rather than raising.

### [REQ-3] Deterministic exit codes

The one-shot/headless path returns process exit code `0` when `JcodeCli.handle()` returns a response
normally, and a non-zero code when constructing `JcodeCli` or calling `handle()` raises (including a
safety-gate refusal or a `--max-turns < 1` refusal) — so a calling script or CI job can branch on
`$?` without parsing human-readable text.

#### Acceptance Criteria
- [x] A successful one-shot run (mocked `handle()` returns normally) exits `0` in both `text` and `json` output formats.
- [x] A failing one-shot run (mocked `handle()`/`JcodeCli.__init__` raises) exits non-zero (`1`) in both `text` and `json` output formats, and (for `json`) the emitted object has `ok: false` plus an `error` string.
- [x] This exit-code contract matches (is not a regression of) today's existing one-shot `try/except` behavior when no new flags are used.

### [REQ-4] `--max-turns N` cap

Add a `--max-turns N` flag for the one-shot/headless path. Because the one-shot path already
performs exactly one turn, `N >= 1` is accepted with no further effect (documented honestly as a
no-op above the existing single-turn ceiling); `N < 1` is enforced as a genuine refusal — the request
is never dispatched to `JcodeCli`/`handle()` at all, and the caller sees a clear failure (non-zero
exit, `ok: false` for JSON) rather than a silently-ignored flag.

#### Acceptance Criteria
- [x] `--max-turns 0` (or any value `< 1`) refuses to run the request — `JcodeCli`/`handle()` is never invoked — and exits non-zero.
- [x] `--max-turns` with a value `>= 1` runs the request normally (exit code and output depend only on whether `handle()` succeeds), and this is documented as a no-op ceiling above the one-shot path's existing single-turn behavior.
- [x] A non-integer `--max-turns` value falls back to "no cap" rather than raising.
- [x] Omitting `--max-turns` entirely behaves exactly as today (no cap, unchanged output).
