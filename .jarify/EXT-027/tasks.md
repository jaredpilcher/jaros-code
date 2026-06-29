# EXT-027 Tasks

## TASK-1: Build solution_memory.py scaffold + tests (DONE)

#### Implements
REQ-1

#### Steps
1. Create `harness/solution_memory.py` with `record_verified`, `recall_similar`, `inject_verified_example`.
2. Reuse `new_class_log._build_signature` + `_normalise` for the deterministic signature.
3. Create `tests/test_solution_memory.py` (OFFLINE, temp path) covering all acceptance criteria.
4. Run `python -m pytest tests/test_solution_memory.py tests/ -q` -- all green.
5. Add traceability comments (`#EXT-027-REQ-1 Start/End`) and update `.jarify/EXT-027/index.json`.

**Status: DONE** (implemented in this session)

---

## TASK-2: Kill-test -- measure WITH vs WITHOUT inject (ACTIVE HOURS ONLY)

#### Implements
REQ-2

#### Steps
1. Seed the store: run `pass1_eval` or any passing-solve path to accumulate records in
   `.jaros-data/artifacts/solution_memory.jsonl`.
2. Run the honest bar WITHOUT memory injection (baseline).  Record result in
   `.jarify/EXT-027/requirements.md` under REQ-2.
3. Wire `inject_verified_example` into the `pass1_eval` solve prompt temporarily.
4. Re-run on the SAME problems; compare WITH vs WITHOUT honestly.
5. If confirmed lift (>= +2pp, outside Wilson overlap, held-out): adopt into default solve;
   mark REQ-2 [x] in requirements.md and status -> covered.
   If non-result: record faithfully; leave inject unwired; note the negative in REQ-2.

**Status: NOT STARTED** (requires active hours + Jetson running)
