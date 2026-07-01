
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

## REQ-6 (#9) resolution — deterministic-signal-FIRST localization (2026-07-01)
The measurement (model-locate ~1/5, weak) drove the honest design: WHERE-to-act must NOT rely on the 3B
guessing from prose. Built a tested localization TOOLKIT in harness/swebench_live.py — locate_target_line
(content-match + ambiguous-anchor disambiguation by hint, the proven 2/8->5/8 lever), locate_from_patch
(from a gold diff), locate_from_traceback (from a FAILURE SIGNAL = the exact failing line) — plus
locate_where in locate_agent.py: deterministic-signal-FIRST, preferring locate_from_traceback (STRONG)
over the grounded LocateBoundary model judgement (weak), inert when neither. 36 tests, all offline. So #9's
WHERE-to-act is STRONG when a run/test failure exists (the realistic repo-solve case) and degrades
gracefully to the bounded model guess otherwise — no net-negative. REMAINING (active-hours, needs Docker):
wire locate_where into a general GOLD-FREE repo-solve (run the failing test -> traceback -> locate_where ->
solve) — the realistic SWE-bench path without the gold. All localization LOGIC is offline + test-gated;
only the run-the-test step needs Docker.

## REQ-6 (#9) locate_where tiers — MEASURED (2026-07-01, honest, incl. a correction)
locate_where is 3-tier: traceback (strong) -> failing-test-name deterministic token-match (medium?) ->
model (weak, ~1/5). MEASURED the test-name tier OFFLINE on 5 easy-slice instances (deterministic, no
model): **0/5** — WEAK. NOISY measurement (some enclosing-def targets ill-computed; the astropy
FAIL_TO_PASS is a file PATH not a test-method name so it didn't extract), but the django cases are clear:
test names describe the SCENARIO (test_callable_path, test_str, test_invalid_string), NOT the function, so
token-overlap doesn't localize. HONEST CORRECTION: I shipped the tier on a hypothesis (test-name->function)
then measured — should have measured first. The tier stays (backward-compatible, deterministic, no worse
than the equally-weak model tier) but is NOT a validated strong signal. NET FINDING: gold-free localization
for WRONG-OUTPUT bugs is genuinely HARD — traceback localizes only CRASH bugs; test-name and the model are
both weak. That is precisely why the SWE-bench solve used the GOLD to content-match the known buggy line.
The one strong deterministic gold-free signal is the traceback (crash class); wrong-output localization
remains the open problem (candidate directions: retrieval by the issue's named symbols; the test BODY's
called symbols, not its name).

## gold-free wrong-output localization — EXPLORATION CLOSED (2026-07-01, honest)
Measured 4 deterministic signals for localizing WRONG-OUTPUT bugs without the gold: traceback (STRONG but
crash-class only — the failing frame is in the buggy file), failing-test-NAME token-match (0/5, weak),
failing-test-BODY called-symbols (1/5, weak), model-from-prose (~1/5, weak). The name/body measurements are
CONFOUNDED by noisy target computation (enclosing-def of the gold anchor is unreliable when the fix is
class-level or in a large method), but the direction is clear: NO strong deterministic gold-free signal for
wrong-output bugs. Contrast: gold-BASED localization (content-match the KNOWN buggy line) is proven at 5/8.
CONCLUSION: solve_from_failure is a genuine gold-free path for the CRASH class (traceback signal); general
gold-free wrong-output localization stays OPEN (would need richer repo retrieval / symbol-graph, not a
one-line heuristic). This bounds the gold-free capability honestly. Localization exploration CLOSED here.

### RE-MEASURED with CLEAN targets (2026-07-01) — confound removed, finding FIRMED
The name/body measurements above were confounded by noisy target computation. Redid them using the PROVEN
localizer for ground truth: locate_from_patch(file, gold) -> the true buggy line -> its enclosing def =
clean target. Clean result: test-name 0/5, test-body-call 1/5 (unchanged verdict, now UNconfounded). The
clean targets reveal WHY: the true fix sites are DurationField / Choices (class-level) and _scale_back_ascii
/ _cstack (internal helpers) — the failing test exercises the PUBLIC behaviour, but the fix is DEEP
(class-level or internal), so no surface signal (test name or called-symbol) points at it. A general
gold-free wrong-output localizer must REASON from a public-behaviour failure to a deep internal site — a
reasoning task, not a heuristic. CONSEQUENCE: the failing-test-NAME tier that had been added to locate_where
measured 0/5 and was REMOVED (forward-only: don't ship an unvalidated signal); locate_where is now
traceback (validated, crash-class) -> model (weak fallback). Exploration FIRMLY closed.
