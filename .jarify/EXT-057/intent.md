# Intent

This spec exists to make the jaros-code CLI **feel like Claude Code** — an interactive, responsive
agent you collaborate with — instead of the silent command-runner it is today. The owner used it
(2026-07-07) and reported it plainly: *"it's just awful. you can only use commands to run things…
it doesn't give you feedback while it's running things… we are not anywhere near Claude Code product
quality at all… have it much more interactive."* That is the ground truth, and it overrides the
Product-Parity Checklist's earlier "~84%" (which measured *feature presence*, not *felt quality* — a
Tenet-3 gap this spec also corrects by adding a felt-quality dimension to the instrument).

The diagnosis is concrete: (1) the REPL is bannered and shaped as a *slash-command* surface, so plain
natural language never feels like the point; (2) `harness/llamacpp_client.py` hard-codes
`"stream": False`, so every model call is a blocking black box — the user waits in silence with no
feedback, then a wall of text appears; (3) the interactive loop is `out = handle(line)` then
`print(out)` — the entire command runs silently and dumps one block at the end, with no live tool
feedback, no progress, no working indicator. The owner's directive is to **rebuild the REPL
end-to-end** to a Claude-Code-grade interactive shell.

The rebuild delivers, on jaros-code's constraints (local Gemma on the Jetson, two-plane, Jaros-native):
**streaming** (model tokens appear as generated; tool events render live as they fire; a working
indicator so the cursor is never dead), **natural-language-first** (talking to it is the default path
to the orchestrator; slash-commands are the `/`-prefixed escape hatch), and a **conversational,
interactive feel** (progressive turn-taking, mid-task clarifying questions and interrupt-and-steer
surfaced well — the plumbing already exists in EXT-036/EXT-055 but isn't *felt*).

It converges toward the Prime Directive's Tenet 5 (Claude-Code-like experience — familiar, transparent
terminal feel) — which the directive says is the *whole product*, not just the model's task-solving —
while never overriding the tenets above it: streaming is pure presentation over the existing hash-chain
Decision log (Tenet 1 two-plane preserved — no new side-effect path), every reasoning call still runs
on the local Jetson model at $0 (Tenet 2), and the streamed transcript remains the same replayable
hash-chain truth (Tenet 3).
