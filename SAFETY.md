# Safety contract (unattended operation)

`jaros-code` is designed to build and monitor itself **unattended**. These bounds are
non-negotiable and are enforced deterministically where possible (two-plane safety:
the model only proposes; deterministic gates/tools decide).

## What is guaranteed

1. **No internet writes / no exfiltration.** All inference is **local** — Ollama
   `gemma2:2b` on `localhost:11434`. No cloud model, no paid API. The `shell.exec`
   tool's gate (EXT-001 / REQ-7) **refuses** any network command: `curl`, `wget`,
   `ssh`/`scp`, `git push/pull/clone/fetch`, `pip/npm/conda/apt install`, raw
   `http(s)://`, `Invoke-WebRequest`, etc. A refused command never executes.

2. **Safe to execute on this system.** The same gate refuses destructive and
   privilege-escalating commands: `rm -rf`, `del /`, `Remove-Item -Recurse`,
   `format`, `mkfs`, `dd`, `shutdown`/`reboot`, `sudo`/`runas`. Ordinary build/test
   commands (e.g. `python -m pytest -q`) are allowed. Evals run in throwaway temp
   dirs; the demo writes only under the gitignored `.jaros-data/artifacts/`.

3. **Capability-safety by construction.** Reasoning agents hold no host handles;
   every effect is a deterministic tool. Bugs cannot reach capabilities not granted.

## Autonomous build-loop rules (what the loop may and may not do)

The self-paced build/monitor loop is bounded to **safe, local, reversible** work:

| MAY                                                  | MUST NOT                                  |
| ---------------------------------------------------- | ----------------------------------------- |
| Run the eval suite (local, temp dirs, pytest)        | Push to any remote / open PRs             |
| Edit agents, tools, specs, tests in **this repo**    | Install packages or hit the network       |
| Run the local test suite                             | Delete or modify files outside this repo  |
| Commit **locally** with descriptive messages         | Run model-generated shell commands ungated|
| Add harder eval tasks (the ratchet)                  | Weaken the `shell.exec` denylist          |

If a needed step would cross any "MUST NOT" line, the loop **stops and flags it**
for the owner instead of proceeding (PRIME-001: conflicts are surfaced, not resolved
silently).
