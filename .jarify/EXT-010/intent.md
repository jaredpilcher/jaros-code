# EXT-010 — Real-world robustness (hardening for real repos + real input)

## Why

The authored evals (HumanEval/MBPP/build/agentic) exercise the harness on **tiny test suites and
well-formed inputs**. That structurally cannot surface the failures a real developer hits: a repo
whose suite is slower than a hard timeout, a fat-fingered or multi-word command argument, an
unhandled exception that dumps a traceback, or a benchmark task whose function name collides with
pytest's collection rules. A harness that aims to be "Claude Code for tiny models" (Tenet 5,
Claude-Code-like UX) must be **usable and non-crashing on real input**, not only green on the
authored bar.

This spec captures the **real-world robustness** requirement and the hardening done to meet it.
The defects were found by **dogfooding** — running the harness's own tools against jaros-code's
real (nested, 161-test) repository and against deliberately malformed input — exactly the gap
Tenet 3 (honest measurement) implies: if the authored evals can't catch a class of failure, go
find it where it actually lives.

## Scope

Reactive hardening of existing tools/flows so they survive real repos and real input. NOT new
capabilities — every fix preserves existing behavior on the authored evals (all suites unchanged;
161-test CI green) and only changes failure/edge behavior. Each requirement traces to the commit
that fixed it.

## Non-goals

- Lifting the 2B reasoning ceiling (that is the project's accepted constraint, Tenet 2).
- New language toolchains or capabilities (separate specs).
