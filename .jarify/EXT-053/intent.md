# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #25 names a gap Claude Code closes but jcode does
not: an **install + health story**. Claude Code ships a one-command install and a `/doctor`
command that tells a user, in seconds, whether their environment is set up correctly (auth,
network, dependencies) before they hit a confusing failure mid-task. Today jaros-code has
`serve.sh`/`.ps1` (boot the Jetson llama.cpp node) and `jcode.sh`/`.ps1` (launch the REPL), both
repo-local scripts — there is no packaging (`pip install` doesn't expose a `jcode` command from
outside the repo) and no self-diagnosis command a confused user (or CI job) can run to see what's
wrong.

This spec closes that gap the same deterministic way EXT-041/EXT-046/EXT-047 closed their rows: a
small, pure execution-plane module (`harness/doctor.py`) that runs a fixed battery of DETERMINISTIC
checks — nothing here is a model judgement — and reports an honest pass/warn/fail verdict per
check plus an overall verdict, wired as both `/doctor` (REPL) and `jcode doctor` / `jcode --doctor`
(headless, mirroring the EXT-043 headless entry family). A minimal `pyproject.toml` adds a `jcode`
console-script entry point so `pipx install .` / `pip install -e .` exposes the same command Claude
Code users expect, without touching the existing `python -m harness.cli` / serve/jcode-script paths.

This converges PRIME-001 on two tenets. **Tenet 1 (two-plane discipline):** every `/doctor` check
is pure deterministic execution-plane code — file/env inspection, a bounded subprocess probe for
git/docker, a bounded network probe of the configured LLM endpoint that degrades to an honest WARN
(never a hang, never a raise) when the Jetson is unreachable, so `/doctor` remains genuinely useful
offline. No check is a model call, and no check performs a host write (read-only diagnostics only).
**Tenet 5 (Claude-Code-like UX):** this is direct product-surface parity — a new or confused user
gets the same "run `/doctor`, see what's wrong, fix it" workflow Claude Code offers, and can install
the tool the way any other Python CLI is installed. Per Tenet 3 (honesty), the Product-Parity
Checklist (EXT-041) row #25 is flipped to `"works"` only once `/doctor`'s checks, its CLI wiring, and
(if it lands cleanly) the packaging are genuinely built and test-covered — any deferred piece (e.g.
auto-update, a signed release artifact) is named honestly in `next_lever`, not hidden.
