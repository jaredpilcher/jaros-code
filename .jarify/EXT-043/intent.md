# Intent

Claude Code is scriptable from a shell or a CI pipeline: `claude -p "..."` accepts a piped prompt,
emits structured (`--output-format json`/`stream-json`) or plain text output, honors a turn cap, and
reports success/failure through its process exit code so a calling script can branch on the result
without scraping human-readable prose. `docs/GAP-MAP.md`'s Product-surface parity row #13 names this
gap explicitly: jaros-code already has a one-shot invocation (`python -m harness.cli "request"`) but
nothing that pipes, nothing machine-parseable, no turn cap, and no deterministic exit-code contract
— so `jcode` cannot yet be composed into a Unix pipeline or a CI job the way `claude` can.

This spec closes that gap with a thin, deterministic **execution-plane** layer wrapped around the
existing one-shot path: read the request from stdin when no argument is given (or when the request is
literally `-`), emit either the current human text or a single structured JSON object
(`--output-format json`), cap the (already single) turn count with `--max-turns`, and return a
non-zero process exit code on failure so `jcode | some-other-tool` and `jcode ... ; echo $?` behave
predictably. No orchestrator reasoning changes — the model still emits the same inert Decision for the
same request; only how that result is packaged for a non-interactive caller changes.

This converges PRIME-001 in two ways. First, it directly advances the "in ALL ways" whole-product
parity bar the Prime Directive names — headless/piping is called out by name in the Product-Parity
Checklist (EXT-041) alongside sessions and instruction memory, and that instrument must move honestly
once this ships. Second, it reinforces Tenet 1 (two-plane discipline) in its purest form: everything
this spec adds — reading stdin, formatting JSON, counting turns, choosing an exit code — is pure,
deterministic execution-plane bookkeeping around a judgement the model already makes; no new model
call, no new agent, is introduced. It must remain strictly additive (Tenet 3): a caller that uses
neither the new flags nor stdin piping sees byte-identical output and exit codes to today, and the
interactive REPL is untouched.
