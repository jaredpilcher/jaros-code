# Intent

This spec exists to give the harness a deterministic map of a function's dependency structure
so that decomposition of a hard multi-step-repo change is *guided* rather than guessed. Before
the model tries to change a function `f`, this tool answers — purely from the module's AST —
"what else must change, and in what order?": which helpers `f` calls, which functions call
`f`, which module-level state it touches, and which sibling functions share that state and so
likely need coordinated edits. It then renders that structure as a concise decomposition brief
the solve prompt can consume. The hard part of a multi-step change is knowing the blast radius;
that knowledge is a computation, not a judgement, so it belongs in the deterministic plane.

It converges toward the Prime Directive by deepening plane-placement (Tenet 1): the
brittle judgement "what is connected to what" is moved entirely to a deterministic AST tool,
leaving the model only the reasoning it can do. It advances the directive's requirement to form
complex, correct plans for changes of any size (intent point (d)) and supplies the structural
fact-source that the L1 decomposition rung needs to be accurate rather than hallucinated.
