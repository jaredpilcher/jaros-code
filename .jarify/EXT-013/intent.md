# Intent

This spec exists to make the proven behavioral solve run truly native in Jaros, because the
owner is proving out Jaros at the same time as building the tool — co-equal and
non-negotiable. The EXT-012 behavioral solve works and beats its baseline on held-out
commits, but it currently runs as plain harness Python: it uses the model client only, with
no inert `Decision` objects, no `validate()`/`execute()` tools, no submit/watch, no hash-chain
log, no replay. This spec migrates it so the two-plane discipline (Tenet 1) is *enforced by
the runtime rather than by convention* — every model-judgement grain becomes a single-purpose
Jaros agent emitting an inert `code.write_file` Decision, every host effect becomes a Jaros
tool driven through the Runtime's gate, executor, and decision log, and the orchestrator
becomes a grounded judge-agent emitting next-action Decisions over a constrained set of proven
layers so a weak 2B cannot degenerate. The whole solve thereby becomes hash-chain logged and
byte-identically replayable (Tenet 3). This is a change of form, not of capability: the
Jaros-native solve must match the Python solve's held-out number within noise, with no
regression versus the baseline, reported honestly with its confidence interval. EXT-012 remains
the capability spec; this is its runtime-native, replayable form.
