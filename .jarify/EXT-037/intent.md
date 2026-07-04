# Intent

This spec exists because Claude-Code parity requires the product to actually DO development on the
host — run commands, manage files, set up environments, use git, investigate with throwaway
probes — not merely emit source. It is the execution-plane toolbelt that makes that real: it
hardens the existing filesystem/shell primitives (root-jailing every create/write/update to the
project folder, gating shell execution with a timeout + process-tree kill and a
destructive/egress denylist) and adds the missing capabilities — Python/venv/dependency tools, a
full git toolset with a secret-and-history guard, a scratch research-script investigation loop,
and a secure sandboxed runner (scrubbed environment, resource caps, gated egress, AST security
scan) for executing model-generated code plus an advisory code-quality signal.

It converges toward the Prime Directive by realizing capabilities (b), (e), and the "DO
development" end goal of the intent while staying strictly inside two-plane discipline (Tenet 1):
the model emits inert Decisions, and every host effect is a deterministic Jaros tool with
`validate()` gating `execute()`, hash-chain logged. The owner's exact safeguard — writes confined
to the root folder, no external egress, no destructive ops outside root, never a secret committed
— is the Foundry safety envelope, and egress is GATED (default-deny allow-list) rather than
blanket-killed so real web research and dependency install remain possible. The spec is honest
about its partial edges (which write paths are actually jailed, that egress enforcement is static
today).
