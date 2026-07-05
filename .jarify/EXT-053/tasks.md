# Implementation Tasks

### [TASK-1] `/doctor` deterministic health check + minimal install story

Add a new `harness/doctor.py` module that runs a fixed battery of deterministic health checks
(Python version, git, docker, `.jaros-data/` writability + dirs, `JCODE_LLM_BACKEND` config
sanity, and a bounded Jetson/LLM endpoint + model-served probe) and returns a structured
pass/warn/fail report; wire it into `harness/cli.py` as `/doctor` (REPL) and `jcode doctor` /
`jcode --doctor` (headless); add a minimal `pyproject.toml` exposing a `jcode` console-script
entry point; honestly update the Product-Parity Checklist (row #25) and its test pin.

#### Steps
1. Create `harness/doctor.py`: `@dataclass(frozen=True) DoctorCheck(name, status, detail,
   remedy="")` with `status` constrained to `"pass"|"warn"|"fail"`. Add
   `_check_python_version(minimum=(3, 10))`, `_check_git(root=".")` (via `shutil.which("git")` +
   a bounded `subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
   timeout=5.0)`, mirroring `.jaros-data/tools/_gittools.py`'s `run_git` timeout discipline),
   `_check_docker()` (via `shutil.which("docker")` + a bounded `subprocess.run(["docker",
   "--version"], timeout=5.0)`; ABSENT is `"warn"`, never `"fail"`), `_check_data_dir_writable
   (root=".")` (uses `os.access(path, os.W_OK)` — a permission query, never an actual write),
   `_check_dirs_present(root=".")` (`.jaros-data/tools` and `.jaros-data/agents` exist),
   `_check_config(root=".")` (`JCODE_LLM_BACKEND` env value is `llamacpp`-prefixed or `ollama`),
   and `_check_llm_endpoint(timeout=2.0)` (calls the EXISTING `harness.llamacpp_client.health(host,
   timeout)` once, deriving BOTH an `"llm_endpoint"` reachability check and an `"llm_model_served"`
   check from the single result — reachable-with-models is `"pass"`/`"pass"`, reachable-with-no-
   models is `"pass"`/`"warn"`, unreachable or any exception is `"warn"`/`"warn"` (never `"fail"`,
   never raised, never a hang beyond `timeout`)). Add `run_doctor(root=".") -> dict` that calls
   every check, wraps each call in its own `try/except` (one broken check degrades to a `"warn"`
   entry rather than blanking the report), and returns `{"checks": [DoctorCheck, ...], "overall":
   "fail" if any check failed else "warn" if any warned else "pass"}`. Add `render(report=None)
   -> str` that runs `run_doctor()` when no report is passed and formats a human-readable table
   (status glyph + name + detail, plus an indented remedy line for anything not `"pass"`, plus an
   `overall:` line) — never raises (falls back to an honest one-line message on any failure).
2. In `harness/cli.py`: add `JcodeCli.cmd_doctor(self, _arg: str) -> str` (near `cmd_parity`) that
   lazily imports `harness.doctor.run_doctor`/`render` and returns `render(run_doctor())`, wrapped
   in `try/except` returning an honest `"/doctor: (unavailable -- ...)"` message on failure. Add
   `_dispatch_doctor_subcommand(args: list[str]) -> int | None` (near `_dispatch_bg_subcommand`)
   that returns `None` for anything except `args == ["doctor"]` or `args and args[0] ==
   "--doctor"`, in which case it lazily imports and calls `run_doctor()`/`render()`, prints the
   rendered report, and returns `0` unless `report["overall"] == "fail"` (then `1`). Wire it into
   `main()` immediately after the existing `_dispatch_bg_subcommand(args)` call, in the same
   "non-`None` short-circuits, `None` falls through unchanged" style. Add a `/doctor` line to the
   module docstring's `Commands (Claude-Code-style):` list and a `jcode doctor` / `jcode --doctor`
   line to `main()`'s own docstring, alongside the existing EXT-052 command-line-only examples.
3. Create `pyproject.toml` at the repo root: a `[build-system]` table (`setuptools>=68`,
   `build-backend = "setuptools.build_meta"`), a `[project]` table (`name = "jaros-code"`, a
   version, `requires-python = ">=3.10"`, `dependencies = ["jaros>=0.4.0"]` — matching
   `requirements.txt`'s actual runtime dependency, nothing else), a `[project.scripts]` table
   (`jcode = "harness.cli:main"`), and a `[tool.setuptools]` table declaring `packages =
   ["harness"]` (the existing flat package layout — no subpackages to declare).
4. Update `harness/product_parity.py` row `id=25` (Install + health story): set `state` to
   `"works"` (this task delivers `/doctor` + CLI wiring + packaging together); `current_state`
   names what is genuinely delivered (the `harness/doctor.py` check battery, `/doctor` +
   `jcode doctor`/`--doctor` wiring, and the minimal `pyproject.toml` console-script) and what
   remains deferred (auto-update, a signed/versioned release artifact, a PyPI publish step);
   `next_lever` names only that residual gap. Mirror the same honest update into
   `docs/GAP-MAP.md` row #25's `State`/`Current honest state`/`Next lever` columns.
5. Update `tests/test_ext041_product_parity.py`: add `25` to the `works == [...]` pin (kept
   sorted) and its explanatory docstring, and update
   `test_score_default_rows_reflects_honest_current_baseline`'s `n_total`/`n_works` (and the
   derived `n_partial + n_missing`) assertions to match the new works-count.
6. Write `tests/test_ext053_doctor.py` (fully hermetic — no real network calls, no real
   subprocess/docker spawns): monkeypatch `harness.llamacpp_client.health` (imported lazily inside
   `_check_llm_endpoint`, so patching the `harness.llamacpp_client` module attribute is picked up)
   to return both a reachable-with-models result and an unreachable/error result, asserting the
   endpoint + model-served checks come back `"pass"`/`"pass"` and `"warn"`/`"warn"` respectively
   (never `"fail"`, never a raised exception) in each case; monkeypatch `subprocess.run` (or
   `shutil.which`) to simulate git/docker present vs. absent vs. present-but-failing, asserting the
   documented status for each; use `tmp_path` for `_check_data_dir_writable`/`_check_dirs_present`
   to cover writable, missing-dir, and missing-subdirs cases without touching the real repo's
   `.jaros-data/`; assert `run_doctor()`'s `"overall"` is `"fail"` when any check is mocked to
   `"fail"`, `"warn"` when any is `"warn"` and none `"fail"`, and `"pass"` when all are `"pass"`;
   assert one check function raising (monkeypatched to throw) still yields a full report (that
   check downgraded to `"warn"`, others unaffected); test `JcodeCli.cmd_doctor` renders
   `run_doctor()`'s report (with `run_doctor` monkeypatched, so the test never touches the network/
   subprocess for real); test `_dispatch_doctor_subcommand(["doctor"])` and
   `(["--doctor", ...])` print the rendered report and return the documented exit code for both an
   `"overall": "pass"`/`"warn"` and an `"overall": "fail"` mocked report, and that it returns
   `None` for an ordinary plain-language request (e.g. `["fix", "the", "bug"]`) and for `[]`.

#### Implements
- [REQ-1] `harness/doctor.py` — deterministic check battery
- [REQ-2] CLI wiring — `/doctor` (REPL) and `jcode doctor` / `jcode --doctor` (headless)
- [REQ-3] Minimal install story — `pyproject.toml` console script
- [REQ-4] Honest Product-Parity Checklist update
