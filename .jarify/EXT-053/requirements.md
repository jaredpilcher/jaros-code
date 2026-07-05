---
id: EXT-053
title: Install + health story
status: covered
priority: medium
---

# EXT-053 — Install + health story

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #25 — a Claude-Code-like
`/doctor` deterministic health check, plus a minimal install story (`pip install -e .` / `pipx
install .` exposing a `jcode` console command) — without touching the existing
`python -m harness.cli` / `scripts/serve.*` / `scripts/jcode.*` paths.

### [REQ-1] `harness/doctor.py` — deterministic check battery

A new, pure execution-plane module `harness/doctor.py` runs a fixed battery of DETERMINISTIC
checks (no model call anywhere) and returns a structured report: `run_doctor(root=".") ->
{"checks": [DoctorCheck, ...], "overall": "pass"|"warn"|"fail"}`, where `DoctorCheck` carries
`name`, `status` (`"pass"|"warn"|"fail"`), `detail`, and `remedy` (a hint, possibly empty). The
checks cover: Python version; git present + this directory is inside a git work tree; docker
present (WARN, not fail, if absent — only needed for some eval paths); `.jaros-data/` writability
and the `tools`/`agents` subdirectories being present; `JCODE_LLM_BACKEND` config sanity; and a
BOUNDED probe of the configured LLM (Jetson llama.cpp) endpoint's reachability and whether a model
is served. Every check degrades honestly (to `"warn"`, or `"fail"` only for a genuine local
capability gap like a missing required binary) rather than raising, and the endpoint/model-served
probe in particular never hangs and never fails purely because the Jetson is offline.

#### Acceptance Criteria
- [x] `run_doctor(root=".")` returns a dict with a `"checks"` list of `DoctorCheck` (or
      equivalent structured) entries and an `"overall"` status computed from them (`"fail"` if any
      check is `"fail"`, else `"warn"` if any check is `"warn"`, else `"pass"`).
- [x] The Jetson/LLM endpoint reachability check performs a BOUNDED probe (a short, explicit
      timeout) of `LLAMACPP_HOST` (default the repo's documented Jetson endpoint); an unreachable
      endpoint yields `"warn"` (never `"fail"`, never a raised exception, never a hang) so
      `/doctor` remains usable fully offline.
- [x] A "model served" check is derived from the SAME endpoint probe (no second network round
      trip) when the endpoint is reachable; when the endpoint is unreachable, the model-served
      check honestly reports itself as skipped/unknown rather than fabricating a result.
- [x] git presence + "inside a work tree" is checked via a BOUNDED subprocess call (a short
      explicit timeout); a missing `git` binary is `"fail"`; git present but this directory not a
      work tree is `"warn"`.
- [x] docker presence is checked via a BOUNDED subprocess call; ABSENT docker is `"warn"`, never
      `"fail"` (docker is only needed for some eval paths, not the core CLI).
- [x] Python version is checked against a stated minimum; below the minimum is `"fail"`, at or
      above is `"pass"`.
- [x] `.jaros-data/` writability is checked via a permission query (e.g. `os.access(path,
      os.W_OK)`) — NOT by performing an actual write (read-only diagnostics, per design.md's
      placement note); a missing/unwritable directory is `"fail"` or `"warn"` as appropriate, and
      a separate check confirms the `tools`/`agents` subdirectories are present (missing is
      `"warn"`, since the harness creates them on first use).
- [x] `JCODE_LLM_BACKEND` config sanity: a recognized value (`llamacpp` default, `ollama` legacy)
      is `"pass"`; an unrecognized value is `"warn"` with a remedy hint, never `"fail"`.
- [x] Every check function is individually defensive AND `run_doctor` wraps each call so one
      broken/unexpected check can never blank out or crash the rest of the report.

### [REQ-2] CLI wiring — `/doctor` (REPL) and `jcode doctor` / `jcode --doctor` (headless)

`JcodeCli.cmd_doctor` renders `run_doctor()`'s report as a human-readable table (status + detail +
remedy hint for anything not `"pass"`, plus an honest overall verdict) for the interactive REPL.
A headless entry point recognizes the leading token `doctor` (bare) or `--doctor` (anywhere `jcode`
is invoked without other flags consuming it) and prints the same rendered report, exiting `0`
unless the overall verdict is `"fail"` (then a non-zero exit), mirroring the EXT-043 headless
exit-code discipline and the EXT-052 `_dispatch_bg_subcommand` leading-token pattern. `/help`
documents `/doctor`.

#### Acceptance Criteria
- [x] `JcodeCli.cmd_doctor(_arg)` returns a human-readable rendering of `run_doctor()`'s report
      (never raises — degrades to an honest "(unavailable)" message on any failure).
- [x] A headless `python -m harness.cli doctor` (or `... --doctor`) invocation prints the same
      rendered report to stdout and exits `0` when the overall verdict is `"pass"` or `"warn"`,
      non-zero when it is `"fail"` — recognized as a LEADING token, mirroring
      `_dispatch_bg_subcommand`'s exact-match discipline so an ordinary plain-language request is
      never misrouted.
- [x] `/help`'s command list documents `/doctor`.
- [x] This wiring is purely additive: an invocation that does not match the `doctor`/`--doctor`
      leading token, and a REPL session that never types `/doctor`, are byte-identical to before
      this spec.

### [REQ-3] Minimal install story — `pyproject.toml` console script

A minimal `pyproject.toml` declares the `harness` package and a `jcode` console-script entry point
(`jcode = "harness.cli:main"`), so `pip install -e .` or `pipx install .` from a checkout exposes a
bare `jcode` command equivalent to `python -m harness.cli`. This does not replace or modify
`python -m harness.cli`, `scripts/serve.sh`/`.ps1`, or `scripts/jcode.sh`/`.ps1` — all three remain
exactly as they are today.

#### Acceptance Criteria
- [x] `pyproject.toml` exists at the repo root with a `[project]` table (name, version,
      `requires-python`), a real dependency list containing only what the harness actually imports
      at runtime (the `jaros` runtime package), and a `[project.scripts]` entry mapping `jcode` to
      `harness.cli:main`.
- [x] `pip install -e .` (or an equivalent local, offline-safe build check) succeeds and the
      installed package exposes `harness` importable exactly as it is today (no import-path
      change — the package is declared flat, matching `harness/`'s existing flat module layout).
- [x] `python -m harness.cli`, `scripts/serve.sh`/`.ps1`, and `scripts/jcode.sh`/`.ps1` are
      unmodified and behave exactly as before this spec.

### [REQ-4] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=25` (Install + health story) is flipped to `"works"` ONLY
because `/doctor`'s check battery, its CLI wiring, and (if it lands cleanly) the packaging are
genuinely delivered and test-covered; if only the `/doctor` half lands, the row stays `"partial"`
and `current_state` says exactly what shipped versus what remains. `docs/GAP-MAP.md` row #25 and
`tests/test_ext041_product_parity.py`'s honesty-pin are updated to match, mirroring how
EXT-042/EXT-043/.../EXT-052 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=25` `state` honestly reflects what this pass actually
      delivered (`"works"` only if `/doctor` + CLI wiring + packaging are ALL genuinely delivered
      and test-covered; otherwise stays `"partial"` with an accurate `current_state`), and
      `next_lever` names only the residual gap (e.g. auto-update, a signed release artifact).
- [x] `docs/GAP-MAP.md` row #25's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] If row #25 is flipped to `"works"`, `tests/test_ext041_product_parity.py`'s `works ==
      [...]` pin and the `n_works` aggregate-bound assertions include `25`.
