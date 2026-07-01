
## REQ-6 (#9) locate-accuracy measurement (2026-06-30, honest — criterion 4)
Measured the built locate agent (LocateBoundary + gemma-4-e2b, temp=0) on 5 SWE-bench instances: given the
ISSUE as intent + the buggy file's functions as candidates, does it pick the function the gold fix belongs
in? RESULT: ~1/5 (NOISY — 2 of the 5 golds change CLASS-LEVEL code with no enclosing def, so those targets
are ill-defined; on the 3 clean def-targets it was 1/3). Also measured: the FULL-FILE def menu (django
files ~100 defs) OVERFLOWS the 3B context (HTTP 400) — the general locate REQUIRES candidate-narrowing
first, not a raw dump. HONEST CONCLUSION (forward-only, no net-negative): the locate agent MECHANISM is
sound (two-plane, degeneracy-guarded, 988 tests) but MODEL-driven localization-from-intent is WEAK for the
3B — do NOT integrate as-is, so REQ-6 criterion 4 stays UNCHECKED. This is precisely WHY SWE-bench
localization worked: it used the GOLD to content-match the KNOWN buggy line (a strong deterministic
signal), NOT the model guessing from the issue. Improvement directions: (a) candidate-narrowing (retrieve
a small relevant set before the judgement); (b) a STRONGER localization signal (a traceback/test-failure
line, not just issue prose); (c) fix the measurement to handle class-level-change targets.
