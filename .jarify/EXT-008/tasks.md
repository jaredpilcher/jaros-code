# Implementation Tasks — EXT-008 From-Intent Build Loop

### [TASK-1] Multi-module dependency support in build + oracle env (REQ-4)

Thread caller-supplied dependency modules into both temp dirs `build_from_intent` uses, so a module
can import an already-built sibling and pass its held-out oracle — unblocking multi-component (Foundry)
builds. Additive + backward-compatible (`deps=None` default).

#### Steps
1. `harness/intent_loop.py`: add `deps: dict | None = None` param to `build_from_intent`. Inside the
   `tempfile.TemporaryDirectory()` build dir, after seeding the stub, write each `deps` item
   (`filename → source`) into that dir. Pass `deps` through to `_run_oracle`.
2. `_run_oracle(module, target, impl, oracle_test, test_cmd, deps=None)`: write each `deps` file into
   its oracle temp dir (`od`) before running the oracle, so an implementation that imports a dep does
   not `ImportError`. Keep the oracle test itself hidden as before.
3. `tests/` (offline, prefer no model — construct the pieces directly or use a canned/monkeypatched
   build path): a target module whose ORACLE imports a supplied dep module PASSES when `deps={dep.py:src}`
   is provided, and FAILS (ImportError) when `deps=None` — proving the dep is the cause. If a fully
   offline path isn't available, add a focused unit test of `_run_oracle` with a dep + an oracle that
   imports it. Tag `# #EXT-008-REQ-4`.
4. Run `python -m pytest -q` — full suite green (existing single-module builds unchanged, deps=None).
5. Add the REQ-4 traceability entry to `.jarify/EXT-008/index.json`. Do NOT touch sibling specs.

#### Implements
- [REQ-4] Multi-module builds — dependency modules present in the build + oracle env
