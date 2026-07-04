# Intent

This spec exists because the Prime Directive's real-systems ratchet includes systems backed by
real datastores, and a capability only counts when the persisted state is HONESTLY verified — a
generated CLI can print "Saved!" on every command and never touch a database, or keep state in an
in-process dict that vanishes when the process exits, and stdout-based acceptance can catch
neither. This spec closes that hollow-persistence-done class, exactly analogous to the server
oracle's fix for hollow web-service passes. It starts at the one datastore stdlib already ships
(`sqlite3` — fully deterministic, no running service, honestly testable offline): an acceptance
oracle that INDEPENDENTLY opens the resulting `.db` file and asserts real rows/values (never
trusting the CLI's own stdout), and proves persistence survives a second, fresh CLI invocation
across a process boundary — which an in-memory fake cannot fake. It also names, but deliberately
does not build, the extension seam for a future real-service provisioner (Postgres/Redis/Qdrant/
Cassandra) that would plug into the same verify contract.

It converges toward the Prime Directive's honest-verification commitment (Tenet 3): the oracle
never coerces a pass, always reports an honest ok=False with a diagnostic note, and establishes
the acceptance PATTERN — verify real state independently, never trust the artifact's self-report —
that the harder real-service rung will reuse unchanged. It is deterministic execution-plane code
with no model call, and honest about its scope: sqlite first, real services named as the next rung.
