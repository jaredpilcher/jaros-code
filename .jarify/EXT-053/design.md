# EXT-053 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #25 names Claude Code's install + health story:
a one-command install, and a `/doctor` command that deterministically checks the environment
(auth/network reachable, dependencies present, config sane) so a user sees actionable diagnosis
instead of a confusing mid-task failure. Today jaros-code has no packaging (only
`python -m harness.cli` / `scripts/serve.*` / `scripts/jcode.*`, all repo-local) and no
self-diagnosis command at all.

The fix must not invent a new reasoning mechanism or touch the two-plane discipline: every
`/doctor` check is a plain deterministic fact-check (a file exists, a binary is on PATH, a
subprocess/socket call returns before a short bound elapses) — never a model judgement, and never
a host write (read-only diagnostics, mirroring `harness/product_parity.py`'s pure-bookkeeping
posture). The one genuinely external call (the Jetson/LLM endpoint reachability probe) MUST be
bounded and MUST degrade to an honest `warn`, never hang and never raise, so `/doctor` stays
useful when the Jetson is off, moved, or unreachable — this is the same "never hang" discipline
`harness/llamacpp_client.py`'s hard wall-clock timeout already established for the model-call path.

## Mechanism

```text
  /doctor (REPL) ----+                jcode doctor / jcode --doctor (headless) ----+
                      |                                                            |
                      v                                                            v
              JcodeCli.cmd_doctor(_arg)                          _dispatch_doctor_subcommand(argv)
                      |                                            (mirrors EXT-052's
                      |                                             _dispatch_bg_subcommand:
                      |                                             leading-token match,
                      |                                             recognized in main()
                      |                                             BEFORE other parsing)
                      +--------------------+-----------------------+
                                           |
                                           v
                          harness/doctor.py  (NEW module -- pure execution plane,
                                              no model call anywhere)
      ┌───────────────────────────────────────────────────────────────────────────────┐
      │ @dataclass(frozen=True) DoctorCheck(name, status, detail, remedy)              │
      │   status ∈ {"pass", "warn", "fail"}                                            │
      │                                                                                 │
      │ _check_python_version()        -- sys.version_info vs. a floor (stdlib only)   │
      │ _check_git(root)               -- shutil.which + bounded `git rev-parse        │
      │                                    --is-inside-work-tree` (subprocess.run,     │
      │                                    timeout=5s, never raises)                   │
      │ _check_docker()                -- shutil.which + bounded `docker --version`;   │
      │                                    ABSENT -> "warn" (only needed for some eval  │
      │                                    paths), never "fail"                        │
      │ _check_data_dir_writable(root) -- os.access(.jaros-data, W_OK) -- A CHECK, not  │
      │                                    a write (Tenet 1 placement: read-only)      │
      │ _check_dirs_present(root)      -- .jaros-data/{tools,agents} exist             │
      │ _check_config(root)            -- JCODE_LLM_BACKEND is a recognized value      │
      │ _check_llm_endpoint(timeout)   -- reuses harness.llamacpp_client.health(host,  │
      │                                    timeout) -- ALREADY a bounded urllib GET    │
      │                                    against /v1/models; produces TWO checks     │
      │                                    ("llm_endpoint" reachability + "model       │
      │                                    served") from the ONE probe (no double      │
      │                                    network round-trip); unreachable -> "warn"  │
      │                                    on BOTH (never "fail", never a raise)       │
      │                                                                                 │
      │ run_doctor(root=".") -> {"checks": [DoctorCheck, ...], "overall": status}       │
      │   each check call wrapped in its own try/except inside run_doctor -- one        │
      │   broken check can never blank out the rest of the report (mirrors             │
      │   product_parity.score's degrade-not-raise discipline)                          │
      │   overall = "fail" if any check fails, else "warn" if any warns, else "pass"    │
      │                                                                                 │
      │ render(report=None) -> str   -- human-readable table for /doctor's return value │
      └───────────────────────────────────────────────────────────────────────────────┘

  pyproject.toml (NEW, minimal)
      [project.scripts]
      jcode = "harness.cli:main"          <- same main() `python -m harness.cli` already calls;
                                              `pipx install .` / `pip install -e .` exposes it as
                                              a bare `jcode` command, additively -- the existing
                                              `python -m harness.cli` / serve.sh|.ps1 / jcode.sh|.ps1
                                              paths are completely unchanged.
```

- **No second reasoning mechanism, no model call.** Every function in `harness/doctor.py` is
  plain deterministic Python (stdlib `os`/`shutil`/`subprocess`/`sys` + the one reused
  `harness.llamacpp_client.health` helper) — Tenet 1's two-plane discipline is trivially satisfied
  because there is only one plane here (execution), never an agent/Decision in the loop.
- **Bounded, never-hanging network probe.** The endpoint check calls the EXISTING
  `harness.llamacpp_client.health(host, timeout)` helper (already used to verify the Jetson before
  switching the harness onto it) with a SHORT timeout (default 2s) — an unreachable/slow endpoint
  degrades to `"warn"` with an honest remedy hint, never a raised exception and never a `"fail"`,
  so `/doctor` remains fully usable with the Jetson powered off.
- **Bounded subprocess probes.** `git`/`docker` presence + the git-work-tree check use
  `subprocess.run(..., timeout=...)`, mirroring `.jaros-data/tools/_gittools.py`'s `run_git`
  choke-point discipline (a short timeout kills the immediate process; any exception, including a
  missing binary, degrades to a structured result rather than propagating).
- **Read-only.** No check in this module writes to the host filesystem — writability is assessed
  via `os.access(path, os.W_OK)` (a permission query, not an actual write), and every other check
  is a pure read (`shutil.which`, `Path.is_dir`, an env var lookup, a bounded subprocess/HTTP GET).
- **Never raises, anywhere.** `run_doctor` wraps every individual check call in its own
  `try/except` so one broken/unexpected check can never blank out the whole report — the same
  degrade-not-raise posture `harness/product_parity.py`'s `score()` already established for
  observability code (EXT-040 precedent: "observability must never break the thing it observes").
- **Additive CLI wiring.** `cmd_doctor` is a new `cmd_*` method (no existing method touched);
  `_dispatch_doctor_subcommand` is recognized in `main()` in the SAME leading-token style as
  EXT-052's `_dispatch_bg_subcommand` — a bare `python -m harness.cli "check my doctor visit"`-style
  plain request is unaffected because the match is an exact `args == ["doctor"]` / `args[0] ==
  "--doctor"`, not a fuzzy prefix.

## Two-plane / honesty

`harness/doctor.py` is 100% execution-plane (Tenet 1) — there is no agent, no Decision, no model
call anywhere in this spec; the ROUTING decision (`/doctor` vs. any other `cmd_*`, or a headless
`doctor`/`--doctor` token vs. any other argv) is a plain dictionary/list lookup, exactly like
EXT-046/EXT-052's dispatch fallbacks. Per Tenet 3, `harness/product_parity.py` row #25 is flipped
to `"works"` only for what is genuinely delivered and test-covered; if the packaging half does not
land cleanly in this pass, the row stays `"partial"` and `current_state` says exactly what shipped
(the `/doctor` half) versus what remains (the packaging half) — no inflation either way.

## Backward compatibility (no regression)

- `harness/doctor.py` is an entirely NEW module — no existing file is touched by its creation.
- `JcodeCli.cmd_doctor` is a new method; no existing `cmd_*` method, `dispatch()` branch, or
  constructor parameter changes shape.
- `_dispatch_doctor_subcommand` is inserted into `main()` as an ADDITIVE check, in the same style
  and position as `_dispatch_bg_subcommand` (a `None` return falls through to today's existing
  parsing byte-identically) — an ordinary one-shot/piped/session-flagged invocation that doesn't
  start with the literal `doctor`/`--doctor` token is completely unaffected.
- `pyproject.toml` is a NEW file; it does not modify `python -m harness.cli`, `scripts/serve.*`, or
  `scripts/jcode.*` in any way — all three remain exactly as they are today. Declaring
  `packages = ["harness"]` does not change how any test or script imports `harness.*` (it is a flat
  package with no subpackages), so there is no packaging-induced import-path change.

## Out of scope (this task)

Auto-update; a signed/versioned release artifact; a `pipx`/PyPI publish step (only local
`pip install -e .` / `pipx install .` from a checkout is proven here); richer Jetson-side
diagnostics (verifying the exact on-device CUDA/JetPack/llama.cpp build — out of scope for a
HOST-side `/doctor`); an interactive auto-remediation mode (`/doctor --fix`). These remain honestly
named in `docs/GAP-MAP.md` row #25's "Next lever" as the residual gap, per Tenet 3.
