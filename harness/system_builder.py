"""EXT-036 TASK-4/TASK-5: productionize the sentence-to-system pipeline (REQ-1/REQ-3/REQ-4),
plus system-level acceptance-driven repair (REQ-5, TASK-5).

The end-to-end pipeline was PROVEN in probes:
  - ``.jaros-data/s2s_planner_probe.py`` — sentence -> JSON build plan, deterministic
    coherence validation (``validate()``).
  - ``.jaros-data/s2s_build_probe.py`` — topological (leaves-first) module build, a
    per-module ``py_compile`` SYNTAX GATE + bounded (max 2) repair loop before assembly
    (the two gaps discovered there: token-budget truncation, and no syntax gate).
  - ``.jaros-data/s2s_doneness_probe.py`` — an executable acceptance CHECKLIST derived
    contract-first from the spec + module API, run against the assembled system for an
    honest DONE/NOT-DONE verdict (Tenet 3 — a real gate, not prose).

This module composes those PROVEN pieces into one tested harness entry point,
``build_system(spec, root, *, llm=None) -> dict``.

Two-plane split:
  - model: the JSON build plan, each module's body (+ syntax-repair attempts), and the
    acceptance checklist.
  - deterministic: plan coherence validation (DAG/exports/imports/entrypoint), topological
    ordering, the ``py_compile`` syntax gate, assembly into `root`, and RUNNING every
    acceptance check.

``build_system`` NEVER raises: any stage failure returns ``shipped``/``done`` False with a
diagnostic ``note``, never a traceback. ``done`` is only True when every derived acceptance
check actually PASSES (Tenet 3 — the checklist is executed, not eyeballed).

TASK-5 (REQ-5) adds a bounded SYSTEM-LEVEL repair loop: when the acceptance checklist has
unmet checks, each unmet check's code + run error + the current module sources are fed to
the model for a TARGETED fix (which module + its corrected complete content); the fix is
syntax-gated (reusing the same ``syntax_ok``/repair-prompt machinery as the per-module
build), applied, and the FULL checklist is re-run. Repeats up to ``max_repair`` rounds
(default 2), stopping early on done or on a round that reduces no unmet checks. Non-
degrading is ENFORCED, not incidental: because the repair prompt asks for a module's
COMPLETE corrected content, a fix targeted at one failing check can incidentally break a
DIFFERENT, previously-passing check (same unmet COUNT, different unmet SET). Each round
snapshots the pre-round module sources + unmet SET; if any previously-passing check now
fails, the round's module write(s) are REVERTED and the loop stops, rejecting that round.
Best-seen ``(built, unmet)`` is tracked and returned — repair only ever improves or leaves
``unmet`` unchanged, never regresses a previously-passing check — and an already-done build
skips repair entirely. The result dict gains a ``repairs`` field recording every repair
attempt (round, check, module, whether it was applied, and — for a rejected/reverted round
— why).

TASK-6 (REQ-2 refinement) makes acceptance-checklist DERIVATION robust: systems were
observed to ship (build+assemble fine) but report ``done=False`` because the model's
proposed checks were vague/"conceptual" prose (not real assertions) or the checklist
didn't parse at all. ``_derive_acceptance_checklist`` now DETERMINISTICALLY FILTERS the
model's proposed checks to ones that actually parse and contain a real ``assert``
statement; when nothing survives it RETRIES ONCE with a stricter prompt; when nothing
survives that either it falls back to a deterministic SMOKE checklist (every module
imports, its exported names are present). The smoke check is still a REAL executable
check (genuine import + assert) — it fails for real on a broken system, so filtering and
the fallback can only relieve spurious pessimism, never manufacture a false pass (Tenet
3). An empty checklist (only possible when there are no modules to check at all) still
never counts as done.

TASK-7 (REQ-14) adds ``modify_system(modules, mod_sentence, root, *, llm=None)`` — MODIFYING
an already-built system from a sentence, not just creating one. It composes the same PROVEN
pieces (``syntax_ok``, ``_derive_acceptance_checklist``, ``_run_check``) with TASK-5's
non-degrading revert pattern: a BASELINE acceptance checklist records the system's currently-
passing behavior, the model identifies + regenerates the targeted module(s) with the change
(syntax-gated + repaired), and a REGRESSION GATE re-runs the baseline-passing checks — any
regression REVERTS the modified module(s) (disk + dict) and reports ``applied=False``. Honest
(Tenet 3): a modification is ``applied`` only when nothing that used to work broke.

TASK-13 (REQ-13) adds ``build_system_escalating(spec, root, *, primary_llm, fallback_llm=None,
swap_fn=None, fallback_model_id=None, primary_model_id=None)`` — an OFFLINE, test-gated
ESCALATE-ONLY-ON-FAILURE core for the hard tier. MEASURED (2026-07-03): on complex builds
gemma-4-e2b ships 2/3 (fully-completes 1) while Qwen2.5-Coder-7B ships 3/3 but never fully
completes and costs ~3x latency — so routing everything to the 7B is a bad trade. The honest
lever is to run the default (primary) model first and only pay for the stronger fallback when
the primary actually failed acceptance (2026-07-07, task #142: ``not done``, not merely
``not shipped`` — a primary that SHIPPED a broken system must still escalate), capturing the
marginal coverage without losing the primary's done-ness or latency on the common (done) case.
Two-plane: the model does the build; the deterministic wrapper decides WHETHER to escalate,
performs the serving swap via an injectable ``swap_fn`` (mirrors
``harness.collaborative_solve._http_swap``'s ``(model_id: str) -> None`` convention), restores
the primary model afterward, and picks the better of the two results by a fixed rule
(done > shipped > fewer unmet requirements). Never raises: a ``swap_fn``/fallback-build failure
gracefully falls back to the primary-only result. Live
CLI/Jetson wiring of ``swap_fn`` is an explicit out-of-scope follow-up — this task only builds
the offline-testable core.

TASK-25 (REQ-22) wires ``harness/server_oracle.py`` (built standalone in TASK-23) into
``build_system``'s acceptance step. MEASURED gap: a FastAPI/Flask service has no stdout, so
its model-proposed checks get filtered out by the stdout-based executable-check gate and the
build silently fell back to the import-only ``_smoke_checklist`` — a Tenet-3 hollow pass that
reports ``done=True`` without ever hitting an endpoint. Fix: immediately after ASSEMBLE,
``detect_web_service(built)`` is called; when it finds a service, the model proposes HTTP
endpoint checks from the spec (``_derive_http_checklist``, deterministically filtered by
``_is_http_check`` to well-formed, actually-assertive dicts), and ``done`` is GATED on a real
``serve_and_check`` run — never on the stdout checklist/smoke fallback. If no valid
``http_checks`` can be derived, ``done=False`` with an honest "not HTTP-verified" note
(``shipped`` may still be True). Non-web-service builds are completely unaffected — the
stdout/smoke acceptance path below is reached only when no web service is detected.

TASK-27 (REQ-23) adds ``build_system_governed(spec, root, *, llm=None, max_repair=3)`` — the
GOVERNED build path that LIFTS long-horizon build coherence (``harness/coherence_suite.py``),
realizing PRIME-001 intent capability (g). MEASURED gap: ``build_system`` on an 11-requirement
interdependent kvdb-cli SHIPPED but silently dropped one requirement (``incr``) AND reported
``done=True`` anyway, because its self-derived acceptance checklist is generated from the SAME
prompt as the code — sharing the same blind spot. ``build_system_governed`` fixes this with an
explicit, INDEPENDENTLY-decomposed requirement list (a separate model call, made BEFORE any
code exists) that is the SPEC OF RECORD: it builds via the unmodified ``build_system`` pipeline,
then verifies EVERY enumerated requirement's own executable check against the assembled system
— never trusting ``build_system``'s own checklist for `done`. Unmet requirements trigger a
RE-GROUND repair call that feeds the model the FULL requirement list (not just the failing one)
so a fix can't silently re-drop a different requirement; if it does anyway, the round is
REVERTED (mirrors TASK-5's ``_repair_system`` non-degrading guard) so ``requirements_met`` never
regresses across repair rounds. Never modifies ``build_system`` itself.

TASK-28 (REQ-23) fixes THREE defects a LIVE gemma diagnostic caught in TASK-27's mechanism
(``.jaros-data/diag_decompose.py``, confirmed before fixing): (A) PARSE BUG — live gemma emits
the decompose list as ONE JSON ARRAY PER LINE (``[{"req_id":"R1",...}]`` then
``[{"req_id":"R2",...}]`` on separate lines), not one combined array; the old single-outermost
``[..]`` extractor's greedy match spans every line at once, which isn't valid JSON, so it
silently returned ZERO requirements. ``_extract_requirements_json`` now tries the single
combined-array case first (back-compat), then falls back to a line-by-line scan collecting
every parseable JSON array/object — handling one-array-per-line, multiple arrays, or bare
JSONL objects alike. (B) CHECK-INTERFACE MISMATCH — gemma's ``check`` field assumed an
imagined import-and-assert-class API (``import main; main.KeyValueStore().set(...)``) that
never matches the ACTUAL built system (a stdin-driven CLI, ``python main.py``), so even a
parsed check errored against the real interface and every requirement was falsely "unmet".
Requirements are now decomposed as BLACK-BOX CLI checks (``argv``/``stdin``/``expect``, in the
system's own ``python main.py``-reads-stdin terms) and verified via
``harness.system_suite._run_cli``/``_resolve_entry`` — the SAME proven black-box oracle
REQ-20/21 already built — never an imagined class API. (C) NO-REGRESS FLOOR —
``build_system_governed`` now ALWAYS runs the underlying ``build_system`` pipeline (even when
decompose yields zero requirements), so a decompose failure degrades to build_system's own
shipped/done result rather than a hollow 0-requirement/0-module regression; a defensive final
check also ensures the returned module set is never smaller than build_system's own.

TASK-29 (REQ-23) makes the NO-REGRESS FLOOR from TASK-28's defect (C) actually HOLD end to end.
A LIVE measurement (an 11-requirement kvdb-cli) caught the gap: ``build_system`` (single-pass)
satisfied 10/11 behavioral requirements, but ``build_system_governed``'s re-ground REPAIR
LOOP — chasing its own unmet requirements — DAMAGED previously-working behavior, ending at
8/11 on an independent behavioral check: a genuine regression below single-pass, one the prior
(count-only, in-memory) tracking did not actually guarantee against end to end — e.g. an
exception aborting a repair round mid-way (after some of its module write(s) already landed on
disk, before that round's own end-of-round regression check ever ran) left stale bookkeeping
that could report the pre-round unmet set unchanged while a genuinely-worse system shipped on
disk. The fix: capture build_system's INITIAL output as an explicit BASELINE (its modules,
verified against the SAME independently-decomposed requirement checks, computed BEFORE any
governed repair runs) and, after the repair loop, independently RE-VERIFY the actual
CURRENT on-disk state from scratch (never trust the loop's own bookkeeping). If that final
verified count is worse than the baseline's (or the final state fails to re-verify at all),
REVERT — re-assemble the baseline's modules back onto ``root`` and return the baseline's own
modules/shipped/done/``requirements_met``, with an honest note that governed repair did not
improve on ``build_system`` so the single-pass result was kept. This GUARANTEES
``build_system_governed`` is always ``max(baseline, governed)`` on the independently-decomposed
requirement set — never worse than a plain ``build_system`` call. Honest scope (no fabricated
lift): this floor does NOT claim to fix decompose-completeness blind spots (a requirement the
decompose call never enumerates at all is invisible to this check set, same as before) — it
only guarantees governed never regresses BELOW build_system on the requirements it does check.

TASK-33 (REQ-25) adds ``build_system_best_of_k(spec, root, *, llm=None, k=3)`` — a BEST-OF-K
build-RELIABILITY wrapper, a different lever from ``build_system_governed`` above. MEASURED
(a median-of-3 coherence run on ``harness/coherence_suite.py::HARD_SLICE``): single-pass
``build_system`` scores median coherence 1.0 with ZERO dropped requirements when it succeeds —
so REQ-23's decompose->repair capstone is the WRONG lever here (there is nothing partial to
repair) — but suffers an occasional TOTAL BUILD FAILURE (~17% measured: 1/6 builds produced
nothing runnable, scoring 0). Best-of-k masks that failure rate deterministically: build the
same spec up to ``k`` times, each into its OWN fresh temp subdirectory (attempts never
contaminate each other), independently SCORE each attempt with a freshly-derived acceptance
checklist run for real (never trusting the attempt's own self-reported ``done``), and ASSEMBLE
only the best-scoring attempt's modules onto the caller's ``root``. Two-plane, like every other
function in this module: selection (score, early-exit, tie-break, assembly) is 100%
deterministic; only generation (``build_system`` itself) is model-driven. Never raises: a
failing attempt scores 0 and is skipped over; if every attempt fails, the least-bad attempt is
returned with ``done=False`` and an honest note (never a manufactured pass). Does not modify
``build_system``/``build_system_governed``/``build_system_escalating`` in any way — wiring this
into the ``/buildsystem`` CLI command is an explicit follow-up (REQ-25).

TASK-46 (REQ-37) adds an OPTIONAL, opt-in (``spec_properties=False`` default, byte-identical
when off) spec-DERIVED behavioral PROPERTY check for ``build_system``'s acceptance step
(PGS-style, arXiv 2506.18315): 0-2 ABSTRACT properties (e.g. "higher priority dequeues
first", "decode(encode(x)) == x") are derived from the SPEC STRING ALONE (never the built
code — no leak) and, when a runnable subprocess-driven check can be built for one, it is
ADDED to the composed acceptance checklist. SAFE BY CONSTRUCTION: purely additive to the
checklist union, so it can only flip ``done`` True->False (catching a semantic/ordering bug
the crash-based REQ-26 floor misses), never False->True — it cannot manufacture a
false-done. A DETERMINISTIC wrapper (``_wrap_property_check``) enforces a tri-state grading
rule regardless of what the model wrote: a genuine ``AssertionError`` from the property test
is the only definitive VIOLATION (fails); any other exception is INCONCLUSIVE (a pass, never
a manufactured false-negative); a clean run is SATISFIED (a pass).
"""

from __future__ import annotations

import ast
import json
import os
import py_compile
import re
import shutil
# #EXT-036-REQ-14 Start
import subprocess  # TASK-21: deterministic import smoke-gate (modify_system regression hardening)
# #EXT-036-REQ-14 End
import sys
import tempfile
# #EXT-036-REQ-37 Start
import textwrap  # TASK-46: deterministic indent-wrap of a model-authored property check
# #EXT-036-REQ-37 End
# #EXT-037-REQ-11 Start
import uuid  # TASK-15: Decision ids for the optional Jaros-native write path
# #EXT-037-REQ-11 End
from pathlib import Path

# #EXT-037-REQ-7 Start
# TASK-10: wire the standalone sandbox module (REQ-7's foundation) into build_system's own
# acceptance execution -- the live gap named by the owner (2026-07-04): model-generated code
# was run as a plain subprocess with the FULL host environment and no static scan.
from harness.secure_exec import EgressPolicy, run_sandboxed, scan_code
# #EXT-037-REQ-7 End

# #EXT-037-REQ-8 Start
# TASK-12: deterministic, stdlib-only ADVISORY code-quality signal (REQ-8) -- answers "are we
# checking the actual code it's writing for quality?" (previously honestly NO). ADDITIVE only:
# never gates `done`, never refuses a build. See harness/code_quality.py for the full module.
import dataclasses

from harness.code_quality import assess_quality
# #EXT-037-REQ-8 End

# #EXT-056-REQ-1 Start
# TASK-2: wire the ADT differential oracle (EXT-056/REQ-1) into the deterministic acceptance
# minimum -- see `_minimum_acceptance` below for the actual conservative classify+append.
from harness import adt_oracle
# #EXT-056-REQ-1 End

# #EXT-037-REQ-1 Start
# TASK-2: root-jail every module write this module performs directly (bypassing the
# Decision/tool layer entirely -- `build_system`/`modify_system` write files straight to
# disk by a model-chosen module NAME, so this is the product path's own choke point).
_TOOLS_DIR = str(Path(__file__).resolve().parents[1] / ".jaros-data" / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
try:
    from _pathjail import PathEscapeError, path_jail  # root-jail helper (EXT-037 / REQ-1)
except Exception:  # pragma: no cover - fail safe if helper missing
    class PathEscapeError(Exception):  # type: ignore
        pass

    def path_jail(root, target):  # type: ignore
        return os.path.join(root, target) if not os.path.isabs(target) else target


def _jailed_write(root: Path, name: str, content: str,
                   runtime: "object | None" = None) -> "str | None":
    """Write ``content`` to module ``name`` under ``root`` iff it stays contained.

    Returns ``None`` on a successful write, or a human rejection reason (NO write
    performed) when ``name`` resolves outside ``root`` -- e.g. a model-authored plan or
    modification naming a module ``"../../evil.py"``. Never raises.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional -- any object exposing
    ``.apply(decision)``, e.g. ``harness.coding_loop.Runtime``. The local ``path_jail``
    pre-check above ALWAYS runs first, unconditionally -- this preserves the exact current
    rejection messages/behavior whether or not a runtime is supplied. Once the target is
    confirmed in-root, ``runtime=None`` (the default -- used by every existing eval/test/suite
    caller against a throwaway sandbox directory) performs the write via the pre-existing raw
    ``Path.write_text`` call, byte-for-byte unchanged. A supplied ``runtime`` instead performs
    the write as a real ``code.write_file`` Decision applied through it, so it gets the SAME
    gate + hash-chain log every other Jaros write Decision goes through; a gate rejection or
    executor failure degrades to an honest error string here, never a crash."""
    try:
        resolved = path_jail(str(root), name)
    except PathEscapeError as exc:
        return str(exc)
    # #EXT-037-REQ-11 Start
    if runtime is None:
        # #EXT-037-REQ-11 End
        try:
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            Path(resolved).write_text(content, encoding="utf-8", newline="\n")
        except OSError as exc:
            return str(exc)
        return None
    # #EXT-037-REQ-11 Start
    try:
        from jaros.core import create_decision
        decision = create_decision(
            id=f"system-builder-write-{uuid.uuid4().hex}", source="system_builder",
            type="code.write_file",
            payload={"path": resolved, "content": content, "root": str(root)},
        )
        runtime.apply(decision)
    except Exception as exc:
        return f"failed to write {name}: {exc}"
    return None
    # #EXT-037-REQ-11 End
# #EXT-037-REQ-1 End

# #EXT-036-REQ-1 Start
PLAN_PROMPT = """You are a software architect. Turn this one-sentence spec into a concrete build PLAN for a small Python system.

SPEC: {spec}

Output ONLY a JSON object (no prose) with this exact shape:
{{
  "modules": [
    {{"name": "<module>.py",
      "responsibility": "<one line>",
      "exports": [{{"name": "<fn_or_Class>", "signature": "<def foo(a, b): / class Bar:>"}}],
      "imports": ["<other_module>.py"]}}
  ],
  "entrypoint": "<module>.py",
  "acceptance": "<one concrete runnable check that proves the system works>"
}}
Rules: each module does ONE thing; imports must reference modules you list; put the CLI/entrypoint last; keep it minimal but complete."""


# #EXT-036-REQ-33 Start
def _strip_md_fences(raw: str) -> str:
    """Drop markdown code-fence marker lines (``` or ```json) from `raw`, keeping every
    other line untouched. A no-op when no fence marker is present. Purely a normalization
    step for the repair fallback below -- never used on the byte-identical valid-JSON path."""
    if not raw or "```" not in raw:
        return raw
    lines = raw.split("\n")
    kept = [ln for ln in lines if not re.match(r"^\s*```", ln)]
    return "\n".join(kept)


def _balanced_span(text: str, opener: str, closer: str):
    """Find the first `opener` in `text` and return the substring up to its DEPTH-MATCHED
    `closer`, tracking JSON string-literal state (quotes + backslash-escapes) so that an
    opener/closer character that appears INSIDE a string value -- including a malformed
    literal control character embedded in that string -- never perturbs the depth count.
    Returns None if no balanced span is found. Never raises."""
    if not text:
        return None
    start = text.find(opener)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _repair_json_candidate(text: str) -> str:
    """Best-effort, minimal, string-aware repair of a JSON-ish span that failed to parse:
    (1) escape literal control characters (newline/tab/carriage-return and any other byte
    < 0x20) found INSIDE a JSON string literal to their proper JSON escape -- the MEASURED
    defect (a model emits a raw newline inside a JSON string instead of the escaped `\\n`);
    (2) drop a comma that appears immediately before a closing '}'/']' (outside any
    string, skipping intervening whitespace) -- a trailing-comma defect. Never raises;
    returns falsy input unchanged."""
    if not text:
        return text
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    escapes = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                out.append(ch)
                escape = False
            elif ch == "\\":
                out.append(ch)
                escape = True
            elif ch == '"':
                in_string = False
                out.append(ch)
            elif ch in escapes:
                out.append(escapes[ch])
            elif ord(ch) < 0x20:
                out.append("\\u%04x" % ord(ch))
            else:
                out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _recover_missing_braces(text: str) -> str:
    """TASK-48 (REQ-33 extension): recover a DROPPED structural closer (`}`/`]`) inside a
    nested container -- a defect class `_repair_json_candidate` cannot fix (it only
    escapes control characters and drops trailing commas, never inserts a missing
    bracket).

    MEASURED (`.jaros-data/artifacts/todo_rawplan.log`): gemma's `todo-list-cli` plan
    embeds a whole multi-line Python class body as an export "signature" JSON string and
    drops the `}` that closes the export object before the `]` ending `exports` --
    ``"signature": "...return self.items"\\n      ],`` where a `}` was owed before that
    `]`. `json.loads` fails ("Expecting ',' delimiter") on this shape.

    Walks `text` left-to-right keeping a stack of open `{`/`[` characters, tracking JSON
    string-literal state (quote + backslash-escape awareness, mirroring
    `_balanced_span`'s scan) so brackets appearing INSIDE a string value -- including the
    embedded class body's own `{`/`}`/`[`/`]` -- never perturb the stack. When a closer's
    matching opener is not the innermost stack entry but IS present deeper in the stack,
    the closers for every unclosed entry above that depth are emitted first (innermost
    first), then the real closer -- inserting ONLY omitted STRUCTURAL closers, never
    fabricating keys/values/commas. An unmatched closer with no corresponding opener
    anywhere in the stack is passed through unchanged (a different malformation, not this
    helper's concern).

    Does NOT recover END-OF-INPUT truncation: a stack still open when the input simply
    ends is left untouched (no closers are ever appended at end-of-string) -- that is a
    different defect class, left to fail honestly exactly as before this task.

    Byte-identical when nothing needed recovery: returns the input `text` object itself
    (no reconstruction) whenever no insertion was made. Pure stdlib; never raises on
    None/empty/malformed input."""
    if not text:
        return text
    openers = {"{": "}", "[": "]"}
    closers_to_openers = {"}": "{", "]": "["}
    stack: list[str] = []
    out: list[str] = []
    in_string = False
    escape = False
    changed = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            continue
        if ch in openers:
            stack.append(ch)
            out.append(ch)
            continue
        if ch in closers_to_openers:
            wanted = closers_to_openers[ch]
            if stack and stack[-1] == wanted:
                stack.pop()
                out.append(ch)
                continue
            depth_index = None
            for idx in range(len(stack) - 1, -1, -1):
                if stack[idx] == wanted:
                    depth_index = idx
                    break
            if depth_index is None:
                # No matching opener anywhere on the stack -- an unmatched extra
                # closer is a different malformation; leave it untouched.
                out.append(ch)
                continue
            for idx in range(len(stack) - 1, depth_index, -1):
                out.append(openers[stack[idx]])
            changed = True
            del stack[depth_index:]
            out.append(ch)
            continue
        out.append(ch)
    if not changed:
        return text
    return "".join(out)


def _extract_json(raw: str, opener: str, closer: str):
    """Best-effort JSON extraction: the model output may carry prose or markdown fences
    around the JSON payload; pull the outermost {..}/[..] span and parse it. Returns None
    (never raises) when no parseable payload is found.

    ★ Byte-identical valid path: the ORIGINAL greedy first-opener-to-LAST-closer match +
    `json.loads` is preserved verbatim as the first thing tried; any input the old code
    already parsed takes that exact branch, unchanged. Only on failure does this fall
    through to a balanced-bracket extraction (string-literal aware, avoids over-spanning
    into trailing prose that contains a stray closer), then a bounded, string-aware
    repair (escaping unescaped control characters inside string values; dropping trailing
    commas), and finally (TASK-48) a structural-bracket RECOVERY stage that inserts an
    OMITTED closer the model dropped inside a nested container, before giving up."""
    raw = raw or ""
    m = re.search(re.escape(opener) + r".*" + re.escape(closer), raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    # ROBUSTNESS FALLBACK -- the plain greedy match above failed (missing, malformed, or
    # over-spanning into trailing prose). Gather candidate spans, preferring a balanced
    # extraction, then attempt each with a bounded repair.
    candidates: list[str] = []
    text = _strip_md_fences(raw)
    balanced = _balanced_span(text, opener, closer)
    if balanced is not None:
        # Only trust the balanced span when what follows it is NOT itself another
        # apparent top-level JSON value of the same bracket type (e.g. several
        # `[...]\n[...]` arrays concatenated, one per line) -- that shape is a
        # multi-value payload some callers deliberately handle themselves when
        # `_extract_json` returns None (e.g. `_extract_requirements_json`'s
        # line-by-line fallback), and must keep seeing None here, unchanged.
        start_idx = text.find(opener)
        tail = text[start_idx + len(balanced):].strip() if start_idx != -1 else ""
        if not tail or not tail.startswith(opener):
            candidates.append(balanced)
    if text != raw:
        m2 = re.search(re.escape(opener) + r".*" + re.escape(closer), text, re.DOTALL)
        if m2 and m2.group(0) not in candidates:
            candidates.append(m2.group(0))
    if m and m.group(0) not in candidates:
        candidates.append(m.group(0))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

    for candidate in candidates:
        repaired = _repair_json_candidate(candidate)
        if repaired == candidate:
            continue
        try:
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            continue

    # TASK-48: FINAL structural-bracket recovery -- only reached when every path above
    # (greedy match, balanced span, and control-char/trailing-comma repair) has already
    # failed to return. Inserts an OMITTED closer the model dropped inside a nested
    # container (e.g. a missing '}' before a ']'); never fabricates content.
    for candidate in candidates:
        recovered = _recover_missing_braces(candidate)
        if recovered == candidate:
            continue
        try:
            return json.loads(recovered)
        except (json.JSONDecodeError, ValueError):
            pass
        repaired = _repair_json_candidate(recovered)
        try:
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            continue

    return None
# #EXT-036-REQ-33 End


def validate_plan(plan: dict) -> list[str]:
    """Deterministic coherence checks on a build plan -> list of defects (empty = coherent).
    Ported unchanged from ``.jaros-data/s2s_planner_probe.py::validate`` (parseable modules,
    well-formed exports, imports reference listed modules, entrypoint listed, an acceptance
    line, and no import cycle)."""
    d: list[str] = []
    mods = plan.get("modules") if isinstance(plan, dict) else None
    if not isinstance(mods, list) or not mods:
        return ["no modules"]
    names = [m.get("name") for m in mods]
    for m in mods:
        if not isinstance(m, dict):
            d.append("malformed module entry")
            continue
        if not m.get("name"):
            d.append("module missing name")
        if not m.get("exports"):
            d.append(f"{m.get('name')}: no exports")
        for e in m.get("exports", []) or []:
            sig = str(e.get("signature", "")) if isinstance(e, dict) else ""
            if not sig or ("(" not in sig and "class" not in sig):
                d.append(f"{m.get('name')}: export '{e.get('name') if isinstance(e, dict) else e}' bad signature")
        # #EXT-036-REQ-1 Start (TASK-34: stdlib imports are not dangling local references)
        for imp in m.get("imports", []) or []:
            if imp in names:
                continue
            top_level = str(imp).split(".")[0] if imp else ""
            if top_level in sys.stdlib_module_names:
                continue
            d.append(f"{m.get('name')}: imports unknown '{imp}'")
        # #EXT-036-REQ-1 End
    if plan.get("entrypoint") not in names:
        d.append("entrypoint not a listed module")
    if not plan.get("acceptance"):
        d.append("no acceptance check")
    # cycle check (simple DFS, mirrors the probe)
    graph = {m.get("name"): [i for i in (m.get("imports", []) or []) if i in names]
             for m in mods if isinstance(m, dict)}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def dfs(n):
        color[n] = GREY
        for nb in graph.get(n, []):
            if color.get(nb) == GREY:
                return True
            if color.get(nb) == WHITE and dfs(nb):
                return True
        color[n] = BLACK
        return False

    if any(color[n] == WHITE and dfs(n) for n in graph):
        d.append("import cycle")
    return d


def _topo_order(mods: list[dict], names: list[str]) -> list[str]:
    """Leaves-first build order (ported from the probe's DFS visit). Safe against cycles
    (a defect the planner would already have rejected, but this must never hang)."""
    order: list[str] = []
    seen: set[str] = set()

    def visit(n: str) -> None:
        if n in seen:
            return
        seen.add(n)
        m = next((x for x in mods if x.get("name") == n), None)
        if m:
            for imp in m.get("imports", []) or []:
                if imp in names:
                    visit(imp)
        order.append(n)

    for n in names:
        visit(n)
    return order


def _repair_plan_entrypoint(plan: dict) -> "tuple[dict, str | None]":
    """Deterministic plan-repair (TASK-19, REQ-1): fixes the single MEASURED coherence
    defect (`.jaros-data/diag_residuals.py`) where the model's plan lists exactly ONE
    module (named descriptively, e.g. ``calculator.py``) but sets ``entrypoint`` to a
    DIFFERENT filename (e.g. ``main.py``, matching the sentence's pinned entrypoint
    convention) — the model clearly INTENDS that file as the entrypoint, it just named its
    lone module descriptively rather than matching it. When there is exactly one module and
    the entrypoint is a non-empty string that isn't that module's name, rename the sole
    module (and any self-referencing import) to the entrypoint filename, so it BECOMES the
    entrypoint the sentence asked for. Returns ``(plan, note)`` — ``note`` is ``None`` when
    no repair was made (already coherent, or nothing safe to repair), else a short
    human-readable description for traceability/honesty. Never raises. Multi-module plans
    with a mismatched entrypoint are left UNTOUCHED — ambiguous which module should host the
    entrypoint, so a genuinely incoherent multi-module plan is still rejected by
    ``validate_plan`` exactly as before (no silent, possibly-wrong guess)."""
    if not isinstance(plan, dict):
        return plan, None
    mods = plan.get("modules")
    entrypoint = plan.get("entrypoint")
    if not isinstance(mods, list) or len(mods) != 1 or not isinstance(entrypoint, str) or not entrypoint:
        return plan, None
    sole = mods[0]
    if not isinstance(sole, dict):
        return plan, None
    old_name = sole.get("name")
    if not old_name or old_name == entrypoint:
        return plan, None
    sole["name"] = entrypoint
    imports = sole.get("imports")
    if isinstance(imports, list):
        sole["imports"] = [entrypoint if i == old_name else i for i in imports]
    return plan, f"plan-repair: renamed sole module {old_name} -> {entrypoint}"
# #EXT-036-REQ-1 End


# #EXT-036-REQ-32 Start (TASK-42: deterministic plan-repair for MULTI-module
# "entrypoint not a listed module")
_ENTRYPOINT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.py$")


def _repair_plan_entrypoint_multi(plan: dict) -> "tuple[dict, str | None]":
    """Deterministic plan-repair (TASK-42/TASK-47, REQ-32): fixes the MEASURED
    MULTI-module "entrypoint not a listed module" coherence defect
    (`graph-bfs-shortest-path-cli`, `.jaros-data/hardtier_failure_diag.json`; and the
    wired-DAG shape `todo-list-cli`) -- the model plans >=2 logic modules (e.g.
    `graph_builder.py`, `bfs_solver.py`, or `data_manager.py` + `cli_handler.py`) but
    sets `entrypoint` to a DIFFERENT filename (e.g. `main.py`, the sentence's pinned
    entrypoint convention, see TASK-15) that it never adds as a module --
    `validate_plan` correctly rejects the whole plan ("entrypoint not a listed module")
    and 0 modules build, even though the model clearly needs a CLI wrapper it just
    never listed.

    `_repair_plan_entrypoint` (TASK-19) already fills this gap for a SINGLE listed
    module (rename); that function's own docstring/tests deliberately leave EVERY
    multi-module case untouched ("ambiguous which module should host the entrypoint").
    This function fills that gap for ANY ACYCLIC multi-module plan. Because the repair
    only ever ADDS a brand-new entrypoint module (never renames/chooses an existing
    one), the "which module hosts the entrypoint" ambiguity never actually applies --
    the only open question is what the new module should import. The DAG-correct,
    unambiguous answer is the ROOT modules: those NO other listed module imports
    (in-degree 0 within the listed set -- the top of the dependency graph, from which
    every other module is transitively reachable). A fully disconnected set (TASK-42's
    original, narrower shape -- e.g. `graph-bfs-shortest-path-cli`) has every module as
    a root, so this reduces EXACTLY to the original behavior there (a strict superset,
    no regression).

    SAFETY (declines to repair -- plan stays rejected exactly as before -- whenever):
      - fewer than 2 modules (the single-module case is `_repair_plan_entrypoint`'s, and
        0 modules is already its own "no modules" defect);
      - `entrypoint` is missing/not a string/empty, or already a listed module name
        (nothing to repair);
      - any listed module entry is malformed/unnamed (nothing safe to reason about);
      - `entrypoint` isn't a well-formed `<identifier>.py` filename (ambiguous what to
        add);
      - the listed modules' import graph is CYCLIC (no module has in-degree 0, so
        `roots` is empty) -- there is no unambiguous top of the graph to import from,
        so this function makes NO guess and `validate_plan`'s own cycle check keeps the
        plan rejected exactly as before (see
        `tests/test_ext036_planrepair_multi.py::test_cyclic_plan_left_untouched` and
        similar coverage in `tests/test_ext036_planrepair.py`).

    Never raises. Returns ``(plan, note)`` -- ``note`` is ``None`` when no repair was
    made, else a short human-readable description for traceability/honesty."""
    if not isinstance(plan, dict):
        return plan, None
    mods = plan.get("modules")
    entrypoint = plan.get("entrypoint")
    if not isinstance(mods, list) or len(mods) < 2:
        return plan, None
    if not isinstance(entrypoint, str) or not entrypoint:
        return plan, None
    names = [m.get("name") for m in mods if isinstance(m, dict) and m.get("name")]
    if len(names) != len(mods):
        return plan, None  # a malformed/unnamed module entry -- nothing safe to guess
    if entrypoint in names:
        return plan, None  # already coherent
    if not _ENTRYPOINT_NAME_RE.match(entrypoint):
        return plan, None  # not a sane module filename -- ambiguous, don't guess
    # TASK-47 (REQ-32 generalization): the ORIGINAL repair fired only when the listed modules
    # were a FULLY DISCONNECTED set (no module imports a sibling). MEASURED 2026-07-07 that this
    # left the common wired-DAG shape rejected: the `todo-list-cli` CREATION task plans
    # `data_manager.py` + `cli_handler.py` where `cli_handler` imports `data_manager` and sets
    # `entrypoint: "main.py"` -- a perfectly coherent dependency DAG with a pinned entrypoint the
    # model just never listed. The old "any sibling import -> decline" guard tripped and 0 files
    # built. Because we ADD a brand-new entrypoint module (never rename/choose an existing one),
    # the "which module should host the entrypoint" ambiguity never applies -- the only question
    # is what the new entrypoint should import. The least-ambiguous, DAG-correct answer is the
    # ROOT modules: those NO other listed module imports (in-degree 0 within the listed set) --
    # the top of the dependency graph, from which every other module is transitively reachable.
    # For a fully disconnected set every module is a root, so `roots == names` and this reduces
    # EXACTLY to the prior behavior (a strict superset -- no regression). The added module is a
    # pure sink (nothing imports it) so it can never introduce a cycle; a genuinely CYCLIC plan
    # has no in-degree-0 module -> `roots` is empty -> we decline and `validate_plan`'s own cycle
    # check keeps it rejected, exactly as before.
    imported_by_sibling = set()
    for m in mods:
        imports = m.get("imports") if isinstance(m, dict) else None
        if isinstance(imports, list):
            imported_by_sibling.update(i for i in imports if i in names)
    roots = [n for n in names if n not in imported_by_sibling]
    if not roots:
        return plan, None  # every module is imported by another (a cycle) -- leave rejected
    new_module = {
        "name": entrypoint,
        "responsibility": "CLI entrypoint wiring the other modules together",
        "exports": [{"name": "main", "signature": "def main():"}],
        "imports": list(roots),
    }
    plan["modules"] = mods + [new_module]
    return plan, f"plan-repair: added missing entrypoint module {entrypoint} importing roots {roots}"
# #EXT-036-REQ-32 End


# #EXT-036-REQ-1 Start (TASK-36: deterministic plan-repair for dangling LOCAL imports)
def _repair_plan_dangling_imports(plan: dict) -> "tuple[dict, str | None]":
    """Deterministic plan-repair (TASK-36, REQ-1): fixes the MEASURED DANGLING-LOCAL-IMPORT
    coherence defect (owner-diagnosed live, 6/6 identical draws for the notes-sqlite-cli
    task) — a module's `imports` names a LOCAL module (e.g. ``database``) that the model
    never added to `plan["modules"]`, so ``validate_plan`` correctly rejects the whole plan
    with ``"imports unknown '<name>'"`` and 0 modules build. Because it is deterministic,
    best-of-k cannot help; this ADDITIVELY repairs it by generating the missing module entry
    instead of rejecting the plan.

    For every planned module's `imports`, any entry that is NEITHER already a listed module
    name NOR a standard-library top-level name (``sys.stdlib_module_names``, dotted-safe —
    the same exemption `validate_plan`'s TASK-34 fix applies) is a genuinely-dangling LOCAL
    reference. A new module entry is ADDED for it (never renaming/removing anything the
    model planned): its ``name`` matches the ``.py`` convention the plan already uses for
    other modules (appends ``.py`` when the bare import lacks it), with a minimal
    non-empty ``exports`` entry so it satisfies ``validate_plan``'s export-shape checks. The
    referencing module's own dangling `imports` entry is then pointed at that exact new
    name (unambiguous — nothing else could satisfy that reference) so the import resolves
    for ``validate_plan``'s "imports unknown" check without inventing/guessing behavior.

    Returns ``(plan, note)`` — ``note`` is ``None`` when no repair was made (already
    coherent, no dangling local imports, or nothing safe to repair), else a short
    human-readable description for traceability/honesty. Never raises. Only ADDS module
    entries for genuinely-dangling LOCAL imports — stdlib/third-party imports (already
    exempt in `validate_plan`) and imports that already resolve to a listed module are left
    completely untouched, so a coherent plan is a no-op (idempotent: re-running on an
    already-repaired plan changes nothing further)."""
    if not isinstance(plan, dict):
        return plan, None
    mods = plan.get("modules")
    if not isinstance(mods, list) or not mods:
        return plan, None
    names = [m.get("name") for m in mods if isinstance(m, dict)]
    added: list[dict] = []
    added_names: set[str] = set()
    notes: list[str] = []
    for m in mods:
        if not isinstance(m, dict):
            continue
        imports = m.get("imports")
        if not isinstance(imports, list):
            continue
        new_imports: list = []
        changed = False
        for imp in imports:
            if not isinstance(imp, str) or not imp or imp in names or imp in added_names:
                new_imports.append(imp)
                continue
            top_level = imp.split(".")[0]
            if top_level in sys.stdlib_module_names:
                new_imports.append(imp)
                continue
            # Genuinely-dangling LOCAL import -> add a module entry for it.
            new_name = imp if imp.endswith(".py") else f"{imp}.py"
            if new_name not in added_names and new_name not in names:
                stem = new_name[:-3] if new_name.endswith(".py") else new_name
                sym = stem if _IDENT_RE.match(stem) else "run"
                added.append({
                    "name": new_name,
                    "responsibility": f"provide '{imp}', used by other modules",
                    "exports": [{"name": sym, "signature": f"def {sym}():"}],
                    "imports": [],
                })
                added_names.add(new_name)
                notes.append(
                    f"plan-repair: added missing local module {new_name} "
                    f"(dangling import '{imp}' in {m.get('name')})"
                )
            new_imports.append(new_name)
            changed = True
        if changed:
            m["imports"] = new_imports
    if not added:
        return plan, None
    plan["modules"] = mods + added
    return plan, "; ".join(notes)
# #EXT-036-REQ-1 End


# #EXT-036-REQ-3 Start
BUILD_PROMPT = """Write the COMPLETE Python module `{name}` for this system.
System spec: {spec}
This module's responsibility: {resp}
It MUST define exactly these (matching signatures): {sigs}
{deps}
Output ONLY the Python code for {name} (no markdown fences, no prose)."""

REPAIR_PROMPT = ("This Python module `{name}` has a SYNTAX ERROR:\n{err}\n\nCODE:\n{code}\n\n"
                  "Return the COMPLETE corrected module, no prose.")

MAX_REPAIR_ATTEMPTS = 2       # bounded repair loop (the syntax-gate gap the probe fixed)
BUILD_MAX_TOKENS = 1400       # raised token budget (the truncation gap the probe fixed)
PLAN_MAX_TOKENS = 900
CHECKLIST_MAX_TOKENS = 900


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n", "", (text or "").strip())
    return re.sub(r"\n```$", "", text).strip()


def syntax_ok(code: str) -> tuple[bool, str]:
    """The deterministic per-module SYNTAX GATE (``py_compile``). Ported from the probe.
    Never raises — a filesystem error during the temp-file dance is treated as not-ok."""
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code or "")
            path = f.name
        py_compile.compile(path, doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)[:200]
    except OSError as exc:
        return False, str(exc)[:200]
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _build_module(spec: str, m: dict, built: dict, llm, *,
                   max_repair: int = MAX_REPAIR_ATTEMPTS) -> tuple[str, bool]:
    """Build one module's body: model writes it given responsibility+signature+already-built
    sibling code, then a bounded syntax-gate/repair loop (REQ-3 — the two probe-discovered
    gaps: token budget + syntax gate). Returns (code, syntax_ok)."""
    name = m.get("name", "")
    sigs = "; ".join(e.get("signature", e.get("name", "")) for e in (m.get("exports", []) or []))
    dep_srcs = [f"# already-written {imp}:\n{built[imp]}" for imp in (m.get("imports", []) or []) if imp in built]
    deps = ("You MUST import from these already-written modules (use their real names):\n"
            + "\n\n".join(dep_srcs)) if dep_srcs else ""
    code = _strip_fences(_call(llm, BUILD_PROMPT.format(
        name=name, spec=spec, resp=m.get("responsibility", ""), sigs=sigs, deps=deps),
        max_tokens=BUILD_MAX_TOKENS))
    ok, err = syntax_ok(code)
    for _ in range(max_repair):
        if ok:
            break
        code = _strip_fences(_call(llm, REPAIR_PROMPT.format(name=name, err=err, code=code),
                                    max_tokens=BUILD_MAX_TOKENS))
        ok, err = syntax_ok(code)
    return code, ok
# #EXT-036-REQ-3 End


# #EXT-036-REQ-4 Start
CHECKLIST_PROMPT = (
    "SPEC: {spec}\nThe system will expose this API: {api}\n\n"
    "Write 3-4 concrete ACCEPTANCE CHECKS proving the SPEC is satisfied. Each check is "
    "standalone Python that imports the built modules and asserts expected behavior. "
    "Output ONLY a JSON list: "
    '[{{"name": "<short label>", "code": "<standalone python asserting real behavior>"}}]. '
    "No prose."
)


def _call(llm, prompt: str, *, max_tokens: int = 900) -> str:
    """The one model-call convention shared by every stage (mirrors ``build_llm()``/
    ``LlmRequest`` as used by ``harness.daily_driver._generate_tests``)."""
    from jaros.llm import LlmRequest
    return llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": max_tokens})).text


def _module_api(mods: list[dict]) -> str:
    parts = []
    for m in mods:
        sigs = ", ".join(e.get("signature", e.get("name", "")) for e in (m.get("exports", []) or []))
        parts.append(f"{m.get('name')}: {sigs}")
    return "; ".join(parts)
# #EXT-036-REQ-4 End
# #EXT-036-REQ-2 Start
CHECKLIST_STRICT_PROMPT = (
    "SPEC: {spec}\nThe system will expose this API: {api}\n\n"
    "Your previous ACCEPTANCE CHECKS were not runnable. Write 3-4 ACCEPTANCE CHECKS as ONLY "
    'RUNNABLE PYTHON CODE — no prose, no "conceptual" descriptions. Each check\'s `code` MUST '
    "parse as valid Python and contain a real `assert` statement testing CONCRETE behavior "
    "against the module API (import the built modules, call them, assert on a real result). "
    "Output ONLY a JSON list: "
    '[{{"name": "<short label>", "code": "<standalone runnable python with a real assert>"}}]. '
    "No prose."
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_executable_check(code) -> bool:
    """The deterministic EXECUTABLE-check filter (REQ-2): a proposed check survives only
    if its ``code`` parses as valid Python (``ast.parse``) AND contains a real ``assert``
    statement. Drops prose/"conceptual"/non-assertion items that the model sometimes
    emits instead of a runnable check — those are never run as-is."""
    if not isinstance(code, str) or not code.strip():
        return False
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.Assert) for node in ast.walk(tree))


def _smoke_checklist(mods: list[dict]) -> list[dict]:
    """Deterministic FALLBACK (REQ-2) when the model cannot produce any executable
    acceptance check: a minimal SMOKE check asserting every module IMPORTS without error
    and each exported name is actually present on it. This is still a REAL executable
    check — a genuine import plus real ``assert`` statements — so it FAILS for real when a
    module is broken or missing an exported name; it never manufactures a false pass
    (Tenet 3). Returns [] only when there is nothing to check at all (no modules)."""
    lines: list[str] = []
    asserts: list[str] = []
    for m in mods or []:
        mod = m.get("name") if isinstance(m, dict) else None
        if not mod:
            continue
        modname = mod[:-3] if mod.endswith(".py") else mod
        if not _IDENT_RE.match(modname):
            continue
        lines.append(f"import {modname}")
        for e in (m.get("exports", []) or []):
            ename = e.get("name") if isinstance(e, dict) else None
            if ename and _IDENT_RE.match(ename):
                asserts.append(
                    f"assert hasattr({modname}, {ename!r}), \"{modname} missing {ename}\""
                )
    if not lines:
        return []
    if not asserts:
        asserts.append("assert True  # modules imported without error")
    code = "\n".join(lines + asserts) + "\n"
    return [{"name": "smoke: modules import and expose their API", "code": code}]


def _propose_checklist(spec: str, api: str, llm, prompt: str) -> list[dict]:
    """One model round-trip proposing acceptance checks, DETERMINISTICALLY FILTERED to
    executable ones (``_is_executable_check``). Guarded — returns [] on any model/parse
    failure or when nothing survives the filter (never a fabricated pass)."""
    try:
        raw = _call(llm, prompt.format(spec=spec, api=api), max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    checks = _extract_json(raw, "[", "]")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and _is_executable_check(c.get("code"))]


# TASK-35: a DETECTED-false-done Tenet-3 defect, MEASURED LIVE (2026-07-04) — building
# `notes-sqlite-cli` fell all the way through to the deterministic SMOKE checklist (below),
# which only asserts `import <module>` + `hasattr(<module>, <export>)` for each exported
# name. That is a REAL executable check, but it never calls any exported function and never
# drives the module's own `if __name__ == "__main__":` CLI dispatch — so a build whose CLI
# genuinely crashes on its primary command (e.g. `add` inserts into a table that was never
# created) still reports `done=True`. The SAME structural gap applies to the two prior
# model-proposed tiers above whenever the model chooses to `import` the built module and
# call its functions in-process rather than spawn the real CLI — an in-process call can
# silently bypass a broken `__main__` branch a genuine invocation would hit. This new tier
# closes the gap the SAME way REQ-22 closed it for detected web services (an honest,
# narrowly-filtered, model-proposed check that actually DRIVES the real thing) — here, a
# real subprocess invocation of the system's own declared entrypoint, matching the SPEC's
# own stated command-line usage, instead of a guessed/hardcoded invocation.
SUBPROCESS_CHECKLIST_PROMPT = (
    "SPEC: {spec}\nThe system will expose this API: {api}\n\n"
    "The checks you previously proposed were not usable. This system is a COMMAND-LINE "
    "PROGRAM (see the SPEC for its exact usage). Write 2-3 concrete checks that RUN IT AS A "
    "REAL SUBPROCESS using Python's `subprocess` module (e.g. "
    '`subprocess.run([sys.executable, "<entry file>", ...], capture_output=True, '
    "text=True)`), invoking it exactly as a user would from the command line per the SPEC's "
    "own usage, and asserting on its real stdout/exit code. Do NOT `import` the built "
    'modules. Output ONLY a JSON list: [{{"name": "<short label>", "code": "<standalone '
    'runnable python that spawns a real subprocess and asserts on its output>"}}]. No prose.'
)


def _is_subprocess_check(code) -> bool:
    """Deterministic filter (TASK-35) for a SUBPROCESS-based acceptance check: survives
    only if it is already a real executable check (``_is_executable_check`` — parses +
    contains a real ``assert``) AND its AST actually contains a call to
    ``subprocess.run``/``check_output``/``check_call``/``Popen`` — i.e. it genuinely spawns
    a fresh process rather than importing the built module in-process. Never raises."""
    if not _is_executable_check(code):
        return False
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in (
            "run", "check_output", "check_call", "Popen",
        ):
            value = node.value
            if isinstance(value, ast.Name) and value.id == "subprocess":
                return True
    return False


def _propose_subprocess_checklist(spec: str, api: str, llm) -> list[dict]:
    """One guarded model round-trip proposing SUBPROCESS-based acceptance checks (TASK-35),
    deterministically filtered to ``_is_subprocess_check``. Returns [] on any model/parse
    failure or when nothing survives (never a fabricated pass) — callers fall through to
    ``_smoke_checklist``."""
    try:
        raw = _call(llm, SUBPROCESS_CHECKLIST_PROMPT.format(spec=spec, api=api),
                     max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    checks = _extract_json(raw, "[", "]")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and _is_subprocess_check(c.get("code"))]


def _derive_acceptance_checklist(spec: str, mods: list[dict], llm) -> list[dict]:
    """Executable acceptance CHECKLIST (REQ-2/REQ-7 probe logic, hardened by TASK-6 and
    TASK-35), derived contract-first from the SPEC + the module API (not the built code).
    ROBUST derivation: (1) propose checks and keep only the ones that survive the
    deterministic executable-check filter; (2) if nothing survives (unparseable output or
    every check was vague/"conceptual"), RETRY ONCE with a stricter prompt demanding only
    runnable Python; (3) if STILL nothing survives, try ONE more tier asking for
    SUBPROCESS-based checks that actually drive the system's real CLI entrypoint (TASK-35 —
    closes the measured gap where an in-process import/call can silently bypass a broken
    ``__main__`` dispatch branch); (4) if that also yields nothing, fall back to a
    deterministic SMOKE checklist. Only stage (4)'s [] (no modules at all) yields an empty
    checklist — callers must treat an empty list as NOT done (Tenet 3), never as a vacuous
    pass."""
    api = _module_api(mods)
    checks = _propose_checklist(spec, api, llm, CHECKLIST_PROMPT)
    if not checks:
        checks = _propose_checklist(spec, api, llm, CHECKLIST_STRICT_PROMPT)
    if not checks:
        checks = _propose_subprocess_checklist(spec, api, llm)
    if not checks:
        checks = _smoke_checklist(mods)
    return checks
# #EXT-036-REQ-2 End
# #EXT-036-REQ-26 Start
# TASK-37 (REQ-26): DETERMINISTIC MINIMUM acceptance floor -- closes a measured Tenet-3
# honesty gap (task #118). MEASURED: `_derive_acceptance_checklist` proposes checks via the
# MODEL, so the checklist VARIES in completeness for the IDENTICAL sentence (one datastore
# build derived 3 checks, another draw of the same sentence derived only 1) -- `done`/
# best-of-k then compare builds against a bar that isn't even comparable ACROSS DRAWS, and
# the model was independently found to systematically MISS a usage/--help check. The fix: a
# DETERMINISTIC minimum checklist, derived from the SPEC + the built module API alone (no
# model call, so it is IDENTICAL for the same input every time), that the model's own
# proposals can only ADD TO, never shrink below (`_compose_acceptance_checklist`). NO ORACLE
# LEAK: every minimum check asserts only that the command runs WITHOUT AN UNHANDLED CRASH
# (no Python traceback) -- never a specific stdout VALUE, which would require knowing the
# answer up front.

_MINIMUM_COMMAND_VERBS = {
    "add", "list", "remove", "delete", "get", "set", "update", "create", "show",
    "done", "clear", "insert", "count", "search", "find", "put", "push", "pop",
    "enqueue", "dequeue", "subscribe", "publish", "start", "stop", "run",
}
_QUOTED_TOKEN_RE = re.compile(r"['\"]([a-zA-Z][a-zA-Z0-9_-]{0,20})['\"]")
_WORD_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]*")
MAX_MINIMUM_COMMANDS = 6


def _extract_command_tokens(spec: str) -> list[str]:
    """Conservative, DETERMINISTIC extraction of command/subcommand tokens a SPEC sentence
    names -- quoted short tokens (e.g. 'add'/'list') and a small FIXED allow-list of
    imperative verbs appearing as whole words in the sentence. No model call; better to
    under-extract than hallucinate a command the sentence doesn't really name. Order-
    preserving, de-duplicated, bounded to `MAX_MINIMUM_COMMANDS`. Never raises."""
    if not isinstance(spec, str) or not spec.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in _QUOTED_TOKEN_RE.finditer(spec):
        tok = m.group(1).lower()
        if tok not in seen:
            seen.add(tok)
            found.append(tok)
    for m in _WORD_TOKEN_RE.finditer(spec):
        tok = m.group(0).lower()
        if tok in _MINIMUM_COMMAND_VERBS and tok not in seen:
            seen.add(tok)
            found.append(tok)
    return found[:MAX_MINIMUM_COMMANDS]


def _minimum_entry_filename(mods: list[dict], plan: "dict | None" = None) -> "str | None":
    """Best-effort, DETERMINISTIC entrypoint filename for the minimum checklist -- prefers
    the plan's own declared `entrypoint` (mirrors `harness.system_suite._resolve_entry`),
    then a module literally named `main.py` (the pinned convention `FIRST_SLICE` sentences
    already use), then the last planned module. Never raises."""
    entry = plan.get("entrypoint") if isinstance(plan, dict) else None
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    names = [m.get("name") for m in (mods or []) if isinstance(m, dict) and m.get("name")]
    if "main.py" in names:
        return "main.py"
    return names[-1] if names else None


def _no_crash_subprocess_check(name: str, entry: str, invocations: "list[list[str]]", *,
                                # #EXT-036-REQ-28 Start
                                allow_usage_validation: bool = False,
                                # #EXT-036-REQ-28 End
                                ) -> dict:
    """One MINIMUM acceptance check: actually runs the built CLI's real entrypoint as a
    subprocess for each argv list in `invocations` and asserts NONE of them crash with an
    UNHANDLED Python exception (no traceback in stderr). Empty stdin (`input=""`) is fed so
    a stdin-driven CLI (REQ-23's convention) sees an immediate EOF rather than hanging.
    Deliberately does NOT assert on stdout CONTENT or an exact exit code -- asserting a
    specific expected VALUE would require knowing the answer up front (an oracle leak); this
    floor only asserts the command doesn't genuinely crash -- the systematically-missed bug
    class TASK-35 measured (a CLI branch that skips required setup and raises).
    STRENGTHENED (REQ-27, task #121): also asserts the run's combined stdout+stderr contains
    no standalone ERROR MARKER (`_has_error_marker`) -- closes the measured false-done class
    where a CLI gracefully CATCHES its own exception and PRINTS it at `rc=0` (no traceback at
    all), which the pre-existing no-traceback check alone could not see.
    STRENGTHENED AGAIN (REQ-28, task #86): `allow_usage_validation`, keyword-only and default
    `False` (every existing call site unchanged), lets a GUESSED-ARITY probe (one guessed
    positional arg, which may be the WRONG arity for the real command) excuse an error marker
    that is ITSELF classified as a usage/argument-validation message (`_is_usage_validation_message`)
    -- e.g. a 2-arg `add` command correctly printing "requires a title and content" when
    probed with only one arg is correct behavior, not a defect. A genuine runtime error (no
    usage vocabulary present) still fails exactly as before; the no-traceback assertion is
    completely unconditional/unchanged."""
    code = (
        # #EXT-036-REQ-27 Start
        _ERROR_MARKER_HELPER_SRC +
        # #EXT-036-REQ-27 End
        # #EXT-036-REQ-28 Start
        (_USAGE_VALIDATION_HELPER_SRC if allow_usage_validation else "") +
        # #EXT-036-REQ-28 End
        "import subprocess, sys\n"
        f"entry = {entry!r}\n"
        f"for argv in {invocations!r}:\n"
        "    result = subprocess.run([sys.executable, entry] + argv, capture_output=True,\n"
        "                            text=True, timeout=20, input='')\n"
        "    assert 'Traceback (most recent call last)' not in result.stderr, result.stderr\n"
        # #EXT-036-REQ-27 Start
        "    _combined = (result.stdout or '') + (result.stderr or '')\n"
        # #EXT-036-REQ-27 End
        # #EXT-036-REQ-28 Start
        + (
            "    assert not (_has_error_marker(_combined) "
            "and not _is_usage_validation_message(_combined)), _combined\n"
            if allow_usage_validation else
            "    assert not _has_error_marker(_combined), _combined\n"
        )
        # #EXT-036-REQ-28 End
    )
    return {"name": name, "code": code}


def _minimum_acceptance(spec: str, mods: list[dict], plan: "dict | None" = None) -> list[dict]:
    """The DETERMINISTIC MINIMUM acceptance checklist (REQ-26, task #118). Derived from the
    SPEC + the built module API alone -- NO model call, so it is IDENTICAL for the same
    input every time (fixing the measured cross-draw inconsistency). Always includes:
      - the existing `_smoke_checklist` (import + `hasattr`) as the floor beneath everything
      - a USAGE/HELP check: running the CLI with no args AND with `--help` must not crash
        with an unhandled exception (the systematically-MISSED check)
      - one subprocess check per conservatively-extracted command token the spec names
        (`_extract_command_tokens`), each invoking the system's real CLI entrypoint
    Composed by `_compose_acceptance_checklist` with the model's own proposals via UNION
    (never REPLACING them) -- see `build_system`/`_score_build_attempt`. Never raises; `[]`
    only when there are no modules to check at all (nothing built yet).
    STRENGTHENED (REQ-27, task #121): every check above additionally rejects a graceful
    error-marker in the run output (see `_no_crash_subprocess_check`), and -- when the spec
    clearly names an add+list command pair -- a BEHAVIORAL round-trip check is added too
    (`_roundtrip_acceptance_check`): real persistence, not just no-crash.
    STRENGTHENED AGAIN (REQ-28, task #86): the per-command loop's GUESSED-ARITY probe (one
    guessed arg, which may be the wrong arity for the real command) now excuses an error
    marker that is itself a usage/argument-validation message (see
    `_no_crash_subprocess_check`'s `allow_usage_validation`) -- correct argument validation
    is no longer mis-graded as a runtime defect. The usage/`--help` check and the
    arity-aware round-trip check are left strict/unchanged.
    STRENGTHENED AGAIN (EXT-056/REQ-1, TASK-2): when the spec CONSERVATIVELY, unambiguously
    names a supported ADT (`adt_oracle.classify_confident` -- a keyword hit is required, never
    method-token overlap alone), one more BEHAVIORAL check is added: a seeded differential
    drive of the built CLI against an independently-authored textbook reference model
    (`adt_oracle.acceptance_check`), catching semantic-ordering bugs (e.g. LRU eviction order)
    that no no-crash/substring check can see. Classification/emit failures are swallowed
    (append nothing) so this can never break checklist derivation."""
    if not mods:
        return []
    checks = list(_smoke_checklist(mods))
    entry = _minimum_entry_filename(mods, plan)
    if entry:
        checks.append(_no_crash_subprocess_check(
            "minimum: usage/--help runs without crashing", entry, [[], ["--help"]]))
        for cmd in _extract_command_tokens(spec):
            checks.append(_no_crash_subprocess_check(
                f"minimum: '{cmd}' command runs without crashing", entry, [[cmd, "x"]],
                # #EXT-036-REQ-28 Start
                allow_usage_validation=True,
                # #EXT-036-REQ-28 End
            ))
        # #EXT-036-REQ-27 Start
        pair = _derive_roundtrip_pair(spec)
        if pair:
            add_cmd, list_cmd = pair
            checks.append(_roundtrip_acceptance_check(entry, add_cmd, list_cmd))
        # #EXT-036-REQ-27 End
        # #EXT-056-REQ-1 Start
        # TASK-2: the ADT differential-oracle check (EXT-056/REQ-1) -- CONSERVATIVE by
        # construction: `classify_confident` only returns a class when the SPEC TEXT itself
        # names the ADT (a keyword hit), never on command-token overlap alone, so a plain
        # get/put store with no "lru"/"least recently used" wording is left un-classified
        # (no-op) rather than risk a false-not-done. Wrapped in try/except so a
        # classification/emit failure NEVER breaks checklist derivation -- on any error,
        # nothing is appended and the rest of the deterministic minimum is unaffected.
        try:
            command_mods = _extract_command_tokens(spec) + [
                m.get("name", "") for m in mods if isinstance(m, dict)
            ]
            adt_cls = adt_oracle.classify_confident(spec, command_mods)
            if adt_cls:
                # TASK-9: thread the visible spec text through so the drive uses whatever
                # synonym vocabulary (e.g. enqueue/dequeue) the spec actually declares, instead
                # of always the hard-coded canonical verbs (push/pop) -- see
                # `adt_oracle._resolve_verbs`. Falls back to the canonical vocabulary when the
                # spec names no synonym, so this is purely additive.
                adt_check = adt_oracle.acceptance_check(entry, adt_cls, spec=spec)
                if adt_check:
                    checks.append(adt_check)
        except Exception:
            pass
        # #EXT-056-REQ-1 End
    return checks


def _compose_acceptance_checklist(spec: str, mods: list[dict], llm,
                                   plan: "dict | None" = None) -> list[dict]:
    """The FINAL acceptance checklist (REQ-26): the DETERMINISTIC MINIMUM
    (`_minimum_acceptance`) UNIONED with the model's own proposals
    (`_derive_acceptance_checklist`) -- the model's checks AUGMENT, never REPLACE, the
    minimum, so the bar for a given sentence can never be SPARSER than the minimum. Closes
    the measured gap where an easy self-derived checklist (as few as ONE trivial check)
    let a build report a hollow `done=True`/win a best-of-k comparison on a sparse bar. A
    check proposed by the model that is byte-identical to one already in the minimum is
    de-duplicated (by `name` + `code`), never double-counted. Never raises: a model/derive
    failure still leaves the deterministic minimum in place, which is never a fabricated
    pass by itself (each minimum check is a real, run-for-real assertion)."""
    minimum = _minimum_acceptance(spec, mods, plan)
    try:
        proposed = _derive_acceptance_checklist(spec, mods, llm)
    except Exception:
        proposed = []
    combined = list(minimum)
    seen = {(c.get("name"), c.get("code")) for c in minimum}
    for c in proposed:
        key = (c.get("name"), c.get("code"))
        if key not in seen:
            seen.add(key)
            combined.append(c)
    return combined
# #EXT-036-REQ-26 End
# #EXT-036-REQ-27 Start
# TASK-38 (REQ-27): BEHAVIORAL acceptance honesty -- closes a MEASURED false-done class
# sitting directly beneath REQ-26's own floor (task #121). LIVE-measured: a built datastore
# CLI whose `list` command gracefully CATCHES its own exception and PRINTS it (e.g. "An
# error occurred while listing notes: DatabaseManager.__init__() missing 1 required
# positional argument: 'db_path'") at exit-code 0 PASSES `_no_crash_subprocess_check`'s
# no-traceback assertion while being genuinely broken -- `done=True` was reported even
# though `add` never actually persisted a note. "Runs without crashing" != "works". The fix
# has two independent, DETERMINISTIC parts: (1) a check now FAILS on a standalone ERROR
# MARKER in the run's combined stdout+stderr even at rc=0 (not just an unhandled traceback);
# (2) when the spec names a clear add+list command pair, a BEHAVIORAL round-trip check
# actually asserts real persistence (add a sentinel, then see it in list) -- not just
# no-crash. NO ORACLE LEAK: the sentinel is a fixed literal never derived from/leaked into
# the solving prompt; the round-trip only asserts the system's OWN stated add/list contract.

_ERR_LINE_PATTERN = r"(?im)^\s*(Traceback|Exception|Error)\b"
_ERR_SUBSTR_PATTERNS = (
    r"(?i)an error occurred",
    r"(?i)missing\b.{0,80}\brequired\b.{0,40}\bargument",
    r"(?i)\bnot found\b",
)
_ERR_LINE_RE = re.compile(_ERR_LINE_PATTERN)
_ERR_SUBSTR_RES = tuple(re.compile(p) for p in _ERR_SUBSTR_PATTERNS)


def _has_error_marker(text) -> bool:
    """Deterministic, CONSERVATIVELY-ANCHORED error-marker detector (REQ-27): True if `text`
    (a run's combined stdout+stderr) contains a standalone error marker -- a line starting
    with `Traceback`/`Exception`/`Error` (catches a graceful `print(f"Error: {e}")` that
    never raises a real exception, as well as the traceback's own header line), or a
    substring match (case-insensitive) for `an error occurred` / `missing ... required ...
    argument` / `not found`. Anchoring the class-name forms to LINE-START (rather than any
    substring) is what keeps this conservative: an argparse-style usage line like
    `"prog.py: error: the following arguments are required: cmd"` is prefixed by the program
    name so it never matches the line-start pattern, and ordinary output that legitimately
    contains the word "error" as DATA (e.g. `"Server error rate: 0.02"`) matches none of the
    fixed phrases above. Never raises on non-string/empty input."""
    if not isinstance(text, str) or not text:
        return False
    if _ERR_LINE_RE.search(text):
        return True
    return any(p.search(text) for p in _ERR_SUBSTR_RES)


# Generated-code MIRROR of `_has_error_marker` above, built from the SAME pattern strings
# (single source of truth -- no drift) so a subprocess-run acceptance check can call it
# without importing this harness module.
_ERROR_MARKER_HELPER_SRC = (
    "import re\n"
    f"_err_line_re = re.compile({_ERR_LINE_PATTERN!r})\n"
    f"_err_substr_res = [re.compile(p) for p in {list(_ERR_SUBSTR_PATTERNS)!r}]\n"
    "def _has_error_marker(text):\n"
    "    if not text:\n"
    "        return False\n"
    "    if _err_line_re.search(text):\n"
    "        return True\n"
    "    return any(p.search(text) for p in _err_substr_res)\n"
)

_ADD_LIKE_WORDS = ("add", "create", "save", "insert", "new")
_LIST_LIKE_WORDS = ("list", "show", "print", "get", "all")
_ROUNDTRIP_SENTINEL = "jarosrtsentinel471"


def _first_word_match(spec: str, words: "tuple[str, ...]") -> "str | None":
    """Conservative, DETERMINISTIC whole-word (case-insensitive) match of the first `words`
    entry literally present in `spec` -- e.g. matches `'add'`/quoted `'add'` but NOT `adding`
    or `adder` (word-boundary anchored). Never raises."""
    if not isinstance(spec, str) or not spec.strip():
        return None
    for w in words:
        try:
            if re.search(r"\b" + re.escape(w) + r"\b", spec, re.I):
                return w
        except re.error:
            continue
    return None


def _derive_roundtrip_pair(spec: str) -> "tuple[str, str] | None":
    """Conservative derivation (REQ-27): when the SPEC sentence clearly names BOTH an
    ADD-like command (`add`/`create`/`save`/`insert`/`new`) AND a LIST-like command
    (`list`/`show`/`print`/`get`/`all`) as whole words, returns `(add_cmd, list_cmd)`; else
    `None` (no round-trip check emitted -- under-assert rather than false-fail/hallucinate a
    command pair the sentence doesn't clearly name). Never raises."""
    try:
        add_cmd = _first_word_match(spec, _ADD_LIKE_WORDS)
        list_cmd = _first_word_match(spec, _LIST_LIKE_WORDS)
    except Exception:
        return None
    if add_cmd and list_cmd and add_cmd != list_cmd:
        return add_cmd, list_cmd
    return None


def _roundtrip_acceptance_check(entry: str, add_cmd: str, list_cmd: str) -> dict:
    """One BEHAVIORAL minimum acceptance check (REQ-27): from a fresh invocation, runs
    `<entry> <add_cmd> <sentinel...>` (trying 1 then 2 positional sentinel args -- covers
    both an `add <text>` and an `add <title> <content>` convention) followed by
    `<entry> <list_cmd>`, and asserts the FIXED LITERAL sentinel token actually appears in
    the list output for at least one arg-count whose add invocation itself produced no error
    marker. This is genuine PERSISTENCE verification, not just no-crash -- catches the
    measured bug class where `add` silently fails to persist. NO ORACLE LEAK: `sentinel` is
    a fixed literal never derived from/leaked into the solving prompt; the assertion is only
    that the system's OWN add/list contract holds."""
    code = (
        _ERROR_MARKER_HELPER_SRC +
        "import subprocess, sys\n"
        f"entry = {entry!r}\n"
        f"add_cmd = {add_cmd!r}\n"
        f"list_cmd = {list_cmd!r}\n"
        f"sentinel = {_ROUNDTRIP_SENTINEL!r}\n"
        "ok = False\n"
        "last_add = ''\n"
        "last_list = ''\n"
        "for nargs in (1, 2):\n"
        "    args = [sentinel] * nargs\n"
        "    add_result = subprocess.run([sys.executable, entry, add_cmd] + args,\n"
        "                                 capture_output=True, text=True, timeout=20, input='')\n"
        "    add_out = (add_result.stdout or '') + (add_result.stderr or '')\n"
        "    last_add = add_out\n"
        "    if _has_error_marker(add_out):\n"
        "        continue\n"
        "    list_result = subprocess.run([sys.executable, entry, list_cmd],\n"
        "                                  capture_output=True, text=True, timeout=20, input='')\n"
        "    list_out = (list_result.stdout or '') + (list_result.stderr or '')\n"
        "    last_list = list_out\n"
        "    if sentinel in list_out:\n"
        "        ok = True\n"
        "        break\n"
        "assert ok, 'round-trip failed: add=' + repr(last_add) + ' list=' + repr(last_list)\n"
    )
    return {"name": f"minimum: '{add_cmd}'+'{list_cmd}' round-trip persists", "code": code}
# #EXT-036-REQ-27 End
# #EXT-036-REQ-28 Start
# TASK-39 (REQ-28): fixes a MEASURED FALSE-NEGATIVE sitting directly beneath REQ-27's own
# floor. A best-of-k (k=5) attempt built a GENUINELY WORKING SQLite notes CLI (physically
# verified: add persists, list shows it, n_unmet=0), but `build_system`'s acceptance still
# reported `done=false` -- the per-command MINIMUM check (`_no_crash_subprocess_check`,
# fed exactly ONE guessed positional arg per command since it can't know a command's real
# arity) probed the winning app's two-arg `add` with only one arg; the app correctly
# printed its OWN usage/argument-validation message ("Error: 'add' command requires a
# title and content.") at rc=0, and REQ-27's `_has_error_marker` correctly flagged the bare
# "Error:"-prefixed line, failing the check even though the app genuinely works. The fix:
# a conservative usage/argument-validation vocabulary classifier that excuses an error
# marker ONLY when it is itself recognizable as usage/argument-validation feedback, applied
# ONLY to the per-command GUESSED-ARITY probe (never to the arity-aware round-trip check or
# the unconditional traceback assertion, which stay strict -- REQ-27's own genuine-defect
# catch, e.g. "list" gracefully printing "no such table" at rc=0, is untouched).

_USAGE_VALIDATION_PATTERNS = (
    r"(?i)\busage\s*:",
    r"(?i)\bthe following arguments are required\b",
    r"(?i)\btoo (few|many) arguments\b",
    r"(?i)\bexpected\b.{0,20}\bargument",
    r"(?i)\brequires?\s+(a|an|\d+)\b",
    r"(?i)\bprovide\s+(a|an|the)\b",
    r"(?i)\brequired\s+argument\b",
    r"(?i)\bmissing\s+(argument|option|parameter)\b",
)
_USAGE_VALIDATION_RES = tuple(re.compile(p) for p in _USAGE_VALIDATION_PATTERNS)


def _is_usage_validation_message(text) -> bool:
    """Deterministic, CONSERVATIVE classifier (REQ-28): True if `text` (a run's combined
    stdout+stderr) reads as USAGE/ARGUMENT-VALIDATION feedback about a mis-arity/missing-
    argument invocation, rather than a genuine runtime defect -- an argparse-style `usage:`
    line, "the following arguments are required", "too few/many arguments", "expected ...
    argument(s)", a self-descriptive "requires a/an/<N> ..." phrasing (the measured
    "'add' command requires a title and content" shape), "provide a/an/the ...", a bare
    "required argument" phrase, or "missing argument/option/parameter" immediately adjacent.
    Deliberately does NOT match the Python-runtime "missing N required positional argument"
    TypeError shape (REQ-27's own motivating genuine-defect text) -- there, "N required
    positional" sits between "missing" and "argument", and no "requires"/"required argument"/
    "missing argument" pattern above matches "required positional argument" or "missing 1
    required" as written. Never raises on non-string/empty input."""
    if not isinstance(text, str) or not text:
        return False
    return any(p.search(text) for p in _USAGE_VALIDATION_RES)


# Generated-code MIRROR of `_is_usage_validation_message` above, built from the SAME pattern
# strings (single source of truth -- no drift) so a subprocess-run acceptance check can call
# it without importing this harness module.
_USAGE_VALIDATION_HELPER_SRC = (
    "import re\n"
    f"_usage_validation_res = [re.compile(p) for p in {list(_USAGE_VALIDATION_PATTERNS)!r}]\n"
    "def _is_usage_validation_message(text):\n"
    "    if not text:\n"
    "        return False\n"
    "    return any(p.search(text) for p in _usage_validation_res)\n"
)
# #EXT-036-REQ-28 End
# #EXT-036-REQ-22 Start
# TASK-25: wiring `harness/server_oracle.py` into `build_system`'s acceptance so a DETECTED
# web service is HONESTLY HTTP-verified instead of falling back to the import-only
# `_smoke_checklist` (the measured hollow-pass gap, REQ-22). Deterministic filtering mirrors
# `_is_executable_check`/`_propose_checklist` above: the model proposes HTTP endpoint checks
# from the SPEC (which already describes the endpoints + expected responses), a deterministic
# gate keeps only well-formed http-check dicts, and — critical for honesty — a check must
# assert at least one of status/json_contains/body_contains to survive (an assertion-free
# check would be a vacuous pass, the HTTP analog of a prose/"conceptual" check).

HTTP_CHECKLIST_PROMPT = (
    "SPEC: {spec}\nThe system is a WEB SERVICE exposing this API: {api}\n\n"
    "Write 2-4 concrete HTTP ENDPOINT CHECKS proving the SPEC's endpoints behave as "
    "described. Each check is a JSON object describing ONE real HTTP request and the "
    "expected response. Output ONLY a JSON list: "
    '[{{"method": "GET"|"POST"|"PUT"|"PATCH"|"DELETE", "path": "/endpoint", '
    '"status": <optional expected int status code>, '
    '"json_contains": <optional dict subset the JSON response must contain>, '
    '"body_contains": <optional substring the response body must contain>}}]. '
    "Every check MUST specify at least one of status/json_contains/body_contains. No prose."
)

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _is_http_check(check) -> bool:
    """The deterministic HTTP-check filter (REQ-22): a proposed check survives only if it
    is a well-formed dict with a non-empty string `path`, an optional `method` that is a
    real HTTP verb, and at least one real assertion (`status` an int, `json_contains` a
    dict, or `body_contains` a string). A check asserting nothing is dropped — the HTTP
    analog of `_is_executable_check` rejecting a prose/non-assertion check. Never raises."""
    if not isinstance(check, dict):
        return False
    path = check.get("path")
    if not isinstance(path, str) or not path.strip():
        return False
    method = check.get("method")
    if method is not None and (not isinstance(method, str) or method.strip().upper() not in _HTTP_METHODS):
        return False
    status = check.get("status")
    if status is not None and (isinstance(status, bool) or not isinstance(status, int)):
        return False
    json_contains = check.get("json_contains")
    if json_contains is not None and not isinstance(json_contains, dict):
        return False
    body_contains = check.get("body_contains")
    if body_contains is not None and not isinstance(body_contains, str):
        return False
    return status is not None or json_contains is not None or body_contains is not None


def _derive_http_checklist(spec: str, mods: list[dict], llm) -> list[dict]:
    """One model round-trip proposing HTTP endpoint checks for a DETECTED web service,
    deterministically filtered to well-formed http-check dicts (`_is_http_check`). Guarded
    — returns [] on any model/parse failure or when nothing survives the filter; never a
    fabricated pass. The prompt already carries the spec (which describes the endpoints +
    expected responses), so no extra context beyond the module API is needed."""
    api = _module_api(mods)
    try:
        raw = _call(llm, HTTP_CHECKLIST_PROMPT.format(spec=spec, api=api), max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    checks = _extract_json(raw, "[", "]")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if _is_http_check(c)]


def _http_check_label(check: dict) -> str:
    method = str(check.get("method") or "GET").upper()
    path = check.get("path") or "/"
    return f"{method} {path}"
# #EXT-036-REQ-22 End
# #EXT-036-REQ-37 Start
# TASK-46 (REQ-37): a spec-DERIVED behavioral PROPERTY check (PGS-style, arXiv 2506.18315)
# for build_system acceptance -- catches SEMANTIC/ORDERING false-dones the crash-based
# REQ-26 minimum floor misses (e.g. a priority queue that dequeues in the WRONG order, or a
# codec whose decode(encode(x)) != x -- neither ever crashes, they just behave WRONG). SAFE
# BY CONSTRUCTION: this only ever ADDS a check to the composed acceptance checklist (REQ-26)
# -- it can flip a build's `done` from True->False (catching a genuine semantic bug the
# existing checks missed) but can NEVER flip False->True, so it cannot manufacture a
# false-done; the only risk is an over-strict FALSE-NEGATIVE, which the tri-state grading
# rule below is specifically designed to avoid.
#
# Two-plane split: `_derive_spec_properties` is ONE model judgment (0-2 abstract properties
# from the SPEC STRING ONLY -- NEVER the built code, so there is no leak/self-deception
# cycle: the model can't just read its own implementation and assert whatever it happens to
# do); `_build_property_check` is a second, narrow model call converting one property into a
# runnable subprocess-driven check (mirrors `_roundtrip_acceptance_check`/
# `_propose_subprocess_checklist`'s real-CLI convention, never `import`-ing the built
# modules); `_wrap_property_check` is a DETERMINISTIC (no model) wrapper enforcing the
# tri-state grading rule below regardless of what the model wrote.
#
# GRADING RULE (tri-state, critical -- minimizes false-negatives):
#   - VIOLATED     = the property test RAN and its assertion DEFINITIVELY failed (an
#                    `AssertionError`) -> the check FAILS (catches the semantic bug).
#   - INCONCLUSIVE = the CLI couldn't be invoked as the check assumed, or ANY other
#                    exception was raised -> treated as a PASS (never manufacture a
#                    false-negative from a broken/mismatched test).
#   - SATISFIED    = the property test ran to completion with no exception -> PASS.

MAX_SPEC_PROPERTIES = 2

PROPERTY_DERIVATION_PROMPT = (
    "SPEC: {spec}\n\n"
    "Identify 0 to 2 ABSTRACT BEHAVIORAL PROPERTIES this system must satisfy -- general "
    "rules about its behavior, not specific example commands or values. Examples of the "
    "KIND of property to name: a priority queue -- 'an item added with higher priority is "
    "dequeued before a lower-priority item'; a counter/notes system -- 'the reported count "
    "increases by exactly 1 after each add'; a codec -- 'decoding the encoding of X returns "
    "X'. If no such property is clearly implied by the spec, output an empty list -- do NOT "
    "invent one. Output ONLY a JSON list (no prose, no code): "
    '[{{"property": "<one-sentence abstract behavioral property>"}}]. Output [] if none apply.'
)

PROPERTY_CHECK_PROMPT = (
    "BEHAVIORAL PROPERTY CHECK: this system must satisfy the property below. Write ONE "
    "acceptance check that exercises the property through the system's REAL command-line "
    "interface, invoked as a genuine subprocess (never `import` the built modules).\n"
    "The system exposes this API: {api}\n"
    "The system's entrypoint file is: {entry}\n"
    "PROPERTY: {property}\n\n"
    "Write standalone Python using `subprocess.run` (or check_output/check_call/Popen) that "
    "invokes the entrypoint one or more times and asserts the property holds via a real "
    "`assert` statement. Do NOT assert one specific expected VALUE you would have to know in "
    "advance -- only assert the STRUCTURAL/RELATIVE property stated above (an ordering, an "
    "invariant, a round-trip). Output ONLY a JSON object (no prose, no markdown fences): "
    '{{"name": "<short label>", "code": "<standalone runnable python that spawns a real '
    'subprocess and asserts the property>"}}.'
)


def _derive_spec_properties(spec: str, llm) -> list[dict]:
    """Derive 0-2 ABSTRACT behavioral properties from the SPEC STRING ONLY (REQ-37). NEVER
    given the built code -- no leak, no self-deception cycle. Guarded: any model/parse
    failure, or a malformed/unparseable response, yields `[]` (no property derived -- keeps
    today's behavior exactly, never a spurious check). Bounded to `MAX_SPEC_PROPERTIES`.
    Never raises."""
    if not isinstance(spec, str) or not spec.strip():
        return []
    try:
        raw = _call(llm, PROPERTY_DERIVATION_PROMPT.format(spec=spec), max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    items = _extract_json(raw, "[", "]")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items:
        if isinstance(it, dict):
            desc = it.get("property")
        elif isinstance(it, str):
            desc = it
        else:
            desc = None
        if isinstance(desc, str) and desc.strip():
            out.append({"property": desc.strip()})
        if len(out) >= MAX_SPEC_PROPERTIES:
            break
    return out


def _wrap_property_check(code: str) -> str:
    """DETERMINISTIC wrapper (no model) enforcing REQ-37's tri-state grading rule
    regardless of what the model-authored property-check `code` does: it runs inside a
    function, and only an `AssertionError` raised from it is graded a definitive VIOLATION
    (non-zero exit); ANY other exception (the CLI didn't behave as the check assumed, a bad
    invocation, a timeout, ...) is INCONCLUSIVE and exits 0 -- a PASS, never manufacturing a
    false failure. A clean run (SATISFIED) also exits 0. `code` is assumed to already have
    passed `_is_subprocess_check` (parses + contains a real subprocess call + a real
    assert) before being wrapped."""
    body = textwrap.indent(code.rstrip("\n") + "\n", "    ")
    return (
        "def _property_test():\n"
        + body +
        "try:\n"
        "    _property_test()\n"
        "except AssertionError as _e:\n"
        "    print('PROPERTY_CHECK_RESULT: VIOLATED: ' + str(_e))\n"
        "    raise SystemExit(1)\n"
        "except Exception as _e:\n"
        "    print('PROPERTY_CHECK_RESULT: INCONCLUSIVE: ' + str(_e))\n"
        "    raise SystemExit(0)\n"
        "else:\n"
        "    print('PROPERTY_CHECK_RESULT: SATISFIED')\n"
        "    raise SystemExit(0)\n"
    )


def _build_property_check(prop: dict, mods: "list[dict]", llm, *,
                           plan: "dict | None" = None) -> "dict | None":
    """Convert ONE abstract behavioral property (REQ-37) into a runnable acceptance check
    exercising the BUILT CLI through a real subprocess invocation (mirrors
    `_roundtrip_acceptance_check`/`_propose_subprocess_checklist`'s subprocess-only, no
    in-process `import` convention). Guarded: an unusable `prop`, no resolvable entrypoint,
    any model/parse failure, or code that doesn't survive the SAME `_is_subprocess_check`
    filter used elsewhere in this module returns `None` -- no check is added (fewer checks,
    never a fabricated one). The surviving check's `code` is DETERMINISTICALLY wrapped
    (`_wrap_property_check`) so the tri-state grading rule holds regardless of what the
    model wrote. Never raises."""
    description = prop.get("property") if isinstance(prop, dict) else None
    if not isinstance(description, str) or not description.strip():
        return None
    entry = _minimum_entry_filename(mods, plan)
    if not entry:
        return None
    api = _module_api(mods or [])
    try:
        raw = _call(llm, PROPERTY_CHECK_PROMPT.format(api=api, entry=entry, property=description),
                    max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return None
    proposed = _extract_json(raw, "{", "}")
    if not isinstance(proposed, dict):
        return None
    name = proposed.get("name")
    code = proposed.get("code")
    if not isinstance(name, str) or not name.strip() or not _is_subprocess_check(code):
        return None
    wrapped = _wrap_property_check(code)
    ok, _err = syntax_ok(wrapped)
    if not ok:
        return None
    return {"name": f"property: {name.strip()}", "code": wrapped}
# #EXT-036-REQ-37 End
# #EXT-036-REQ-4 Start

# #EXT-037-REQ-7 Start
# TASK-10: the SANDBOXED replacement for the prior plain ``harness.multi_file._run`` call --
# defense in depth alongside the scan gate above. Every acceptance-check execution now goes
# through ``harness.secure_exec.run_sandboxed``: a SCRUBBED environment (no ambient host
# secrets -- API keys, LLAMACPP_*, tokens -- reach the model-generated check script or
# anything it in turn spawns, e.g. the check script's own ``python main.py`` subprocess),
# POSIX resource caps, and the same timeout + process-tree-kill discipline the prior plain
# subprocess path already had. Egress is DENY_ALL by default (a generated CLI/service
# acceptance run has no legitimate need for network access). Never raises.
def _run_acceptance_cmd(cwd: str, cmd: str) -> tuple[bool, str]:
    timeout = float(os.environ.get("JCODE_TEST_TIMEOUT_S", "120"))
    result = run_sandboxed(cmd, cwd=cwd, egress_policy=EgressPolicy.DENY_ALL, timeout=timeout)
    out = (result.get("stdout") or "") + (result.get("stderr") or "")
    if result.get("timed_out") and not out:
        out = f"acceptance check timed out after {timeout}s (treated as not-passing): {cmd}"
    return bool(result.get("ok")), out
# #EXT-037-REQ-7 End


def _run_check(root: Path, check: dict) -> bool:
    """RUN one acceptance check against the assembled system (the real Tenet-3 gate — not
    prose). Runs via ``_run_acceptance_cmd`` (REQ-7: scrubbed env, resource caps, timeout +
    tree-kill). A temp check-script name is used so it never collides with a planned
    module."""
    code = check.get("code", "")
    if not code:
        return False
    chk_path = root / "_s2s_acceptance_check.py"
    # #EXT-037-REQ-11 Start
    # TASK-15: deliberately left as a raw write -- this is INTERNAL BUILD-SCRATCH state, not
    # product output. `chk_path` is written immediately before running it and unconditionally
    # `unlink()`'d in the `finally` block a few lines below, within this SAME call -- it is
    # never part of the shipped system and never seen by the user, so routing it through a
    # Decision would gate/log a file that exists for microseconds and is deleted before this
    # function ever returns.
    # #EXT-037-REQ-11 End
    try:
        chk_path.write_text(code, encoding="utf-8", newline="\n")
        # #EXT-037-REQ-7 Start
        ok, _out = _run_acceptance_cmd(str(root), "python _s2s_acceptance_check.py")
        # #EXT-037-REQ-7 End
        return ok
    except Exception:
        return False
    finally:
        try:
            chk_path.unlink()
        except OSError:
            pass

# #EXT-036-REQ-4 End
# #EXT-036-REQ-5 Start
REPAIR_MODULE_PROMPT = (
    "SYSTEM ACCEPTANCE REPAIR: an acceptance check for this system is FAILING and the "
    "responsible module must be fixed.\n"
    "SPEC: {spec}\n"
    "FAILING CHECK: {check_name}\n"
    "CHECK CODE:\n{check_code}\n"
    "RUN ERROR:\n{error}\n\n"
    "CURRENT MODULE SOURCES:\n{sources}\n\n"
    "Identify which ONE module needs to change to fix this failure, and provide its COMPLETE "
    "corrected content. Output ONLY a JSON object (no prose, no markdown fences): "
    '{{"module": "<module_name>.py", "code": "<complete corrected module source>"}}'
)

MAX_SYSTEM_REPAIR_ROUNDS = 2   # bounded system-level (acceptance-driven) repair loop, REQ-5


def _run_check_verbose(root: Path, check: dict) -> tuple[bool, str]:
    """Like ``_run_check`` but also returns the run output (stdout+stderr) so a failing
    check can be fed back to the model as repair feedback (REQ-5). Runs via the same
    sandboxed execution path (``_run_acceptance_cmd``, REQ-7); never raises."""
    code = check.get("code", "")
    if not code:
        return False, "no check code"
    chk_path = root / "_s2s_acceptance_check.py"
    # #EXT-037-REQ-11 Start
    # TASK-15: same deliberate raw-write choice as `_run_check` above -- internal build-scratch,
    # written then unlinked within this same call, never shipped.
    # #EXT-037-REQ-11 End
    try:
        chk_path.write_text(code, encoding="utf-8", newline="\n")
        # #EXT-037-REQ-7 Start
        ok, out = _run_acceptance_cmd(str(root), "python _s2s_acceptance_check.py")
        # #EXT-037-REQ-7 End
        return ok, out
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            chk_path.unlink()
        except OSError:
            pass


def _sources_blob(built: dict[str, str]) -> str:
    return "\n\n".join(f"# {name}:\n{code}" for name, code in built.items())


def _repair_module_for_check(spec: str, check: dict, error: str, built: dict[str, str], llm) -> "dict | None":
    """Ask the model for a TARGETED fix for one failing acceptance check: which module +
    its corrected COMPLETE content, given the check's code + its run error + the CURRENT
    sources of every module (REQ-5). Returns ``{"module": name, "code": code}`` or ``None``
    on any model/parse failure or an out-of-range module name (never raises, never a
    fabricated fix)."""
    try:
        raw = _call(llm, REPAIR_MODULE_PROMPT.format(
            spec=spec, check_name=check.get("name", "?"), check_code=check.get("code", ""),
            error=(error or "")[:500], sources=_sources_blob(built)), max_tokens=BUILD_MAX_TOKENS)
    except Exception:
        return None
    fix = _extract_json(raw, "{", "}")
    if not isinstance(fix, dict):
        return None
    name, code = fix.get("module"), fix.get("code")
    if not name or name not in built or not code:
        return None
    return {"module": name, "code": code}


def _repair_system(spec: str, root: Path, built: dict[str, str], checks: list[dict],
                    unmet: list[str], llm, *, max_repair: int = MAX_SYSTEM_REPAIR_ROUNDS,
                    runtime: "object | None" = None
                    ) -> tuple[dict[str, str], list[str], list[dict]]:
    """Bounded system-level (acceptance-driven) repair loop, REQ-5 — the analog of the
    write-tests/syntax repair loops at the acceptance level. For each currently-unmet
    check: feed (check code + run error + current module sources) to the model for a
    TARGETED fix, syntax-gate + repair the fix (reusing ``syntax_ok``/``REPAIR_PROMPT``),
    apply it (deterministic write), then re-run the FULL checklist once per round.

    REAL (not incidental) non-degrading guarantee: the repair prompt asks the model for a
    module's COMPLETE corrected content, so a targeted fix for one failing check can
    incidentally break a DIFFERENT, previously-passing check (same unmet COUNT, different
    unmet SET — a silent swap the old count-only guard let through). Each round therefore
    snapshots the pre-round module sources + unmet SET; after the round's fix(es) and a
    full checklist re-run, if any check that PASSED before the round now FAILS (a
    set-based regression, not just a count comparison), the round's module write(s) are
    REVERTED to their pre-round content and the loop STOPS (that round is rejected, not
    accepted). Best-seen `(built, unmet)` — fewest unmet, never a state where a
    previously-passing check has regressed vs the pre-repair baseline — is tracked and
    returned. Also stops early when done, or when an accepted (non-regressing) round makes
    no further progress. Bounded, never raises.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional, threaded straight to every
    ``_jailed_write`` call below -- same contract as ``build_system``'s own ``runtime``
    parameter (``runtime=None`` is unchanged from before this parameter existed)."""
    repairs: list[dict] = []
    all_names = [c.get("name", "?") for c in checks]
    # Best-seen state: current (built, unmet) is only ever updated by an ACCEPTED
    # (non-regressing) round below, so it is always at least as good as the pre-repair
    # baseline captured here.
    best_built, best_unmet = dict(built), list(unmet)
    try:
        for round_no in range(1, max_repair + 1):
            if not unmet:
                break
            pre_round_built = dict(built)
            pre_round_unmet = set(unmet)
            round_repairs: list[dict] = []
            for check in [c for c in checks if c.get("name") in unmet]:
                ok, err = _run_check_verbose(root, check)
                if ok:
                    continue   # an earlier fix this round already resolved it
                record = {"round": round_no, "check": check.get("name", "?"), "applied": False, "module": None}
                fix = _repair_module_for_check(spec, check, err, built, llm)
                if fix:
                    name, code = fix["module"], fix["code"]
                    syn_ok, syn_err = syntax_ok(code)
                    for _ in range(MAX_REPAIR_ATTEMPTS):
                        if syn_ok:
                            break
                        code = _strip_fences(_call(llm, REPAIR_PROMPT.format(name=name, err=syn_err, code=code),
                                                    max_tokens=BUILD_MAX_TOKENS))
                        syn_ok, syn_err = syntax_ok(code)
                    if syn_ok:
                        # #EXT-037-REQ-1 Start
                        # #EXT-037-REQ-11 Start
                        if _jailed_write(root, name, code, runtime) is None:
                        # #EXT-037-REQ-11 End
                            built[name] = code
                            record["applied"] = True
                            record["module"] = name
                        # #EXT-037-REQ-1 End
                round_repairs.append(record)

            new_unmet_list = [c.get("name", "?") for c in checks if not _run_check(root, c)]
            new_unmet_set = set(new_unmet_list)
            passed_before_round = set(all_names) - pre_round_unmet
            regressed = passed_before_round & new_unmet_set
            if regressed:
                # SET-based regression (a swap, e.g. fix `sub` but break `add`): revert this
                # round's module write(s) to their pre-round content and reject the round.
                touched = {r["module"] for r in round_repairs if r["applied"] and r["module"]}
                for name in touched:
                    prev_code = pre_round_built.get(name)
                    if prev_code is None:
                        continue
                    # #EXT-037-REQ-1 Start
                    # #EXT-037-REQ-11 Start
                    _jailed_write(root, name, prev_code, runtime)
                    # #EXT-037-REQ-11 End
                    # #EXT-037-REQ-1 End
                    built[name] = prev_code
                for r in round_repairs:
                    if r["applied"]:
                        r["applied"] = False
                        r["reverted"] = "regressed a previously-passing check"
                repairs.extend(round_repairs)
                unmet = [n for n in all_names if n in pre_round_unmet]
                break   # reject-and-stop: never build on a regressing round

            repairs.extend(round_repairs)
            unmet = new_unmet_list
            if len(unmet) < len(best_unmet):
                best_built, best_unmet = dict(built), list(unmet)
            if len(unmet) >= len(pre_round_unmet):
                break   # an accepted round that reduced no unmet checks -> stop (no infinite loop)
    except Exception:
        pass   # never raise -- fall through with whatever progress was made

    # Final safety net: never return worse than the best-seen (non-regressing) state.
    if len(unmet) > len(best_unmet):
        built, unmet = best_built, best_unmet
    return built, unmet, repairs
# #EXT-036-REQ-5 End

# #EXT-036-REQ-34 Start
# TASK-44 (REQ-34, owner idea, roadmap 57e8341): OPT-IN iterative REPLAN-AS-MODIFICATION
# recovery. When the targeted per-check patch above (`_repair_system`) still leaves a build
# NOT DONE, step back and treat the remaining gap as a MODIFICATION: describe where the
# system actually landed vs the spec's target, apply the fix via the existing MODIFICATION
# plane (`modify_system`), re-check, and iterate. This can fix things a local per-check patch
# cannot (e.g. a whole missing module / a structural change), and reuses proven machinery
# rather than inventing a new apply mechanism.
MAX_REPLAN_ROUNDS = 3   # bounded iterative replan-as-modification recovery, REQ-34


def _build_replan_request(spec: str, root: Path, built: dict[str, str], checks: list[dict],
                           unmet: list[str]) -> str:
    """Build a plain MODIFICATION request describing the gap between the built system and the
    spec, for REQ-34's replan-as-modification recovery. Uses ONLY the spec text, the CURRENT
    built module sources, and each FAILING check's NAME + its REAL run ERROR (obtained by
    actually running the check, exactly like `_repair_module_for_check`'s existing feedback
    loop) -- NEVER the check's own assertion CODE (which can embed a hidden expected value)
    and never any other oracle-only sentinel. Never raises (a check-run failure just yields an
    empty error string for that name)."""
    lines = [
        "The following system was built for this spec but does not yet fully satisfy it. "
        "Assess where the project actually landed vs the spec's target, then modify it to "
        "bridge the gap.",
        "",
        f"SPEC: {spec}",
        "",
        "CURRENT MODULES:",
        _sources_blob(built)[:4000],
        "",
        "FAILING ACCEPTANCE CHECKS (name: real run error -- never the check's own code):",
    ]
    for name in unmet:
        check = next((c for c in (checks or []) if c.get("name") == name), None)
        err = ""
        if check is not None:
            try:
                _, err = _run_check_verbose(root, check)
            except Exception:
                err = ""
        lines.append(f"- {name}: {(err or '')[:300]}")
    return "\n".join(lines)


def _replan_as_modification(spec: str, root: Path, built: dict[str, str], checks: list[dict],
                             unmet: list[str], llm, *, max_rounds: int = MAX_REPLAN_ROUNDS,
                             runtime: "object | None" = None
                             ) -> "tuple[dict[str, str], list[str], int]":
    """Iterative REPLAN-AS-MODIFICATION recovery (REQ-34): builds a modification request from
    the gap (see `_build_replan_request`), applies it via `modify_system` (the existing
    MODIFICATION plane), re-runs the FULL acceptance checklist, and repeats up to
    `max_rounds` times.

    CONVERGENCE GATE (mirrors `_repair_system`'s non-degrading floor, made STRICTER here per
    REQ-34): a round is ACCEPTED only when it STRICTLY REDUCES the unmet-check COUNT AND
    regresses no check that was passing before the round (a SET comparison, so a swap-in
    regression on a different check can never slip through as a same-count coincidence);
    otherwise the round is REJECTED -- every module `modify_system` touched this round is
    restored to its pre-round content (disk + the returned dict) and the loop STOPS. Bounded
    to `max_rounds`; stops early once `done` (0 unmet). Never raises -- any `modify_system`
    failure just stops the loop and returns the best-seen state so far.

    0-FALSE-DONE (Tenet 3): the caller recomputes `done` from a FRESH run of the real
    acceptance checks after this returns -- this function can only ever produce a genuinely
    fresh passing state on disk, never fabricate one.

    Returns `(built, unmet, rounds_run)` where `rounds_run` counts only ACCEPTED rounds."""
    all_names = [c.get("name", "?") for c in (checks or [])]
    best_built, best_unmet = dict(built), list(unmet)
    rounds_run = 0
    try:
        for round_no in range(1, max_rounds + 1):
            if not unmet:
                break
            pre_round_built = dict(built)
            pre_round_unmet_set = set(unmet)

            mod_request = _build_replan_request(spec, root, built, checks, unmet)
            try:
                result = modify_system(dict(built), mod_request, root, llm=llm, runtime=runtime)
            except Exception:
                break
            candidate_built = dict(result.get("modules") or built)

            new_unmet_list = [c.get("name", "?") for c in (checks or []) if not _run_check(root, c)]
            new_unmet_set = set(new_unmet_list)
            passed_before_round = set(all_names) - pre_round_unmet_set
            regressed = passed_before_round & new_unmet_set
            improved = len(new_unmet_set) < len(pre_round_unmet_set)

            if regressed or not improved:
                # REJECT this round: restore any module `modify_system` touched back to its
                # pre-round content (disk + dict) and stop -- never worse than best-seen.
                for name, code in pre_round_built.items():
                    if candidate_built.get(name) != code:
                        # #EXT-037-REQ-11 Start
                        _jailed_write(root, name, code, runtime)
                        # #EXT-037-REQ-11 End
                built = pre_round_built
                break

            rounds_run = round_no
            built = candidate_built
            unmet = new_unmet_list
            best_built, best_unmet = dict(built), list(unmet)
    except Exception:
        pass   # never raise -- fall through with the best progress made

    # Final safety net: never return worse than the best-seen (non-regressing, improving) state.
    if len(unmet) > len(best_unmet):
        built, unmet = best_built, best_unmet
    return built, unmet, rounds_run
# #EXT-036-REQ-34 End

# #EXT-036-REQ-4 Start
def _result(*, modules=None, shipped: bool, done: bool, unmet=None, plan=None, note: str = "",
            repairs=None, plan_repair: str = "", security=None, quality=None,
            # #EXT-058-REQ-3 Start
            build_path: str = "free-form",
            # #EXT-058-REQ-3 End
            ) -> dict:
    # #EXT-037-REQ-7 Start
    # TASK-10: `security` is an additive, backward-compatible field (default None) -- only
    # populated when the REQ-7 scan gate actually refuses a build; every other call site is
    # unchanged.
    # #EXT-037-REQ-7 End
    # #EXT-037-REQ-8 Start
    # TASK-12: `quality` is likewise additive/backward-compatible (default None) -- ADVISORY
    # only, populated on the relevant build_system return paths once modules exist and the
    # security scan has passed; omitting it (every pre-existing caller/test) leaves the
    # returned dict byte-compatible with before this task.
    # #EXT-058-REQ-3 Start
    # TASK-6: `build_path` is likewise additive/backward-compatible (default "free-form") --
    # honest for every pre-existing return path (the leaf-repair branch never ran on any of
    # them); only the single return path in `build_system` where a leaf candidate actually
    # WON overrides it to "leaf:<class>".
    # #EXT-058-REQ-3 End
    return {"modules": modules or {}, "shipped": shipped, "done": done,
            "unmet": unmet or [], "plan": plan, "note": note, "repairs": repairs or [],
            "plan_repair": plan_repair, "security": security, "quality": quality,
            "build_path": build_path}
    # #EXT-037-REQ-8 End


# #EXT-036-REQ-30 Start
# TASK-40: `check_reviewer` keyword param (default None -- byte-identical no-op) added to
# the signature + docstring below; the actual review step lives further down in the
# ACCEPTANCE stage (see the SECOND `#EXT-036-REQ-30` region in this function).
def build_system(spec: str, root: "str | Path", *, llm=None,
                  runtime: "object | None" = None,
                  check_reviewer=None,
                  replan_on_failure: bool = False,
                  # #EXT-036-REQ-37 Start
                  spec_properties: bool = False,
                  # #EXT-036-REQ-37 End
                  # #EXT-038-REQ-4 Start
                  enable_research: bool = False,
                  # #EXT-038-REQ-4 End
                  ) -> dict:
    """PLAN -> topological BUILD (syntax-gated + repair) -> ASSEMBLE -> ACCEPTANCE.

    Returns ``{modules: {name: code}, shipped: bool, done: bool, unmet: [names], plan: {...}}``
    (plus a diagnostic ``note``). NEVER raises: any stage failure returns
    ``shipped``/``done`` False with a `note` explaining why. `done` requires the derived
    acceptance checklist to actually PASS (Tenet 3), not just parse.

    Uses ``harness.coding_loop.build_llm()`` when `llm` is None (mirrors the convention in
    ``harness.daily_driver._generate_tests``); an injected `llm` (any object exposing
    ``.complete(LlmRequest) -> .text``) drives fully offline testing.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional -- any object exposing ``.apply(decision)``,
    e.g. ``harness.coding_loop.Runtime``. When given, every module write this function performs
    (ASSEMBLE, and the REQ-5 acceptance-repair loop via ``_repair_system``) is routed through a
    real ``code.write_file`` Decision (gated, hash-chain logged) instead of a raw
    ``Path.write_text``. ``runtime=None`` (the default) is unchanged from before this parameter
    existed -- every existing eval/test/suite caller against a throwaway sandbox directory is
    unaffected.

    ``check_reviewer`` (EXT-036 REQ-30, task #122): OPTIONAL -- any object exposing
    ``.complete(LlmRequest) -> .text``, injected via ``harness.acceptance_review.review_checks``.
    Default ``None`` leaves this function BYTE-IDENTICAL to before this parameter existed (no
    behavior change, proven by a dedicated regression test). When given, the MODEL-PROPOSED
    portion of the composed acceptance checklist (REQ-26) -- never the deterministic minimum,
    which always gates as-is -- is reviewed+corrected by `check_reviewer` against the visible
    spec + built module sources ONLY (no oracle leak) before the checklist gates `done`. This
    function never performs any model swap itself -- `check_reviewer` is just an injected llm;
    orchestrating which model actually serves as the reviewer (e.g. a Jetson gemma<->7B swap)
    is a CALLER concern, out of scope here.

    ``replan_on_failure`` (EXT-036 REQ-34, task #57e8341): OPTIONAL, default `False` -- a
    complete no-op, leaving this function BYTE-IDENTICAL to before this parameter existed (no
    behavior change, proven by a dedicated regression test). When `True` AND the build is
    still NOT DONE after the normal acceptance + `_repair_system` targeted patch, an iterative
    REPLAN-AS-MODIFICATION recovery (`_replan_as_modification`) runs: it reframes the
    remaining gap as a MODIFICATION request and applies it via `modify_system` (the existing
    MODIFICATION plane), re-checks, and iterates up to `MAX_REPLAN_ROUNDS` times,
    convergence-gated so it never regresses a previously-passing check and never fabricates
    `done` -- `done` is always the real acceptance checklist passing.

    ``spec_properties`` (EXT-036 REQ-37, task #130): OPTIONAL, default ``False`` -- a
    complete no-op, leaving this function BYTE-IDENTICAL to before this parameter existed
    (no behavior change, proven by a dedicated regression test). When ``True``, 0-2
    ABSTRACT behavioral properties are derived from the SPEC ALONE (``_derive_spec_properties``
    -- never the built code, no oracle leak) and, when a runnable subprocess check can be
    built for a property (``_build_property_check``), it is ADDED to the composed
    acceptance checklist so ``done`` requires it too. SAFE BY CONSTRUCTION: this is purely
    ADDITIVE to the checklist union -- it can only flip a build's ``done`` from True to
    False (catching a genuine semantic/ordering bug the crash-only floor misses), never the
    reverse, so it cannot manufacture a false-done.

    ``enable_research`` (EXT-038 REQ-4, task #TASK-4): OPTIONAL, default ``False`` -- a complete
    no-op, leaving this function BYTE-IDENTICAL to before this parameter existed. When ``True``,
    ``harness.web_research.research_context(spec)`` is called ONCE before the PLAN prompt is
    built: a deterministic (never model-judged) scan for a known library name in `spec`, guarded
    fetch of that library's docs on a match. An empty result (no library match, or ANY fetch
    failure -- an active eval-lock, egress refusal, network failure) changes nothing; the exact
    same ``PLAN_PROMPT.format(spec=spec)`` is sent as when this parameter is left at its default.
    A non-empty result is prepended to that prompt. Research can only ADD context to the plan
    prompt -- it never touches `validate_plan`, the build/repair/acceptance pipeline, or any other
    stage, so a research failure of any kind degrades to the `enable_research=False` behavior for
    that build, never turning an otherwise-successful build into a failure.

    Leaf-repair (EXT-058 REQ-3, task #TASK-6): ALWAYS ON, no parameter -- a strict superset of
    every prior stage. Only tried once every stage above still leaves the build NOT DONE:
    ``harness.graph_dsl.leaf_for_spec(spec)`` fingerprints the visible spec text against the
    verified leaf-library's earned members (REQ-1); on a match, that leaf's template is emitted
    into a throwaway candidate directory and re-graded by the SAME deterministic
    `_minimum_acceptance` floor a free-form build must pass. It is adopted -- written into
    `root` through the same gated write path (Tenet 1), `done` flipped True -- ONLY when it
    genuinely passes; the returned dict's `build_path` records which path won
    (`"free-form"` or `"leaf:<class>"`). A spec with no matching leaf, or a free-form build that
    already passed, never reaches this stage at all -- byte-identical to before this task."""
    # #EXT-036-REQ-30 End
    root = Path(root)
    # #EXT-040-REQ-3 Start
    # TASK-4: observability phase beats -- /status shows the LIVE build phase (PLAN/ASSEMBLE/
    # SCAN/ACCEPTANCE/REPAIR/DONE) instead of "idle", so a wedged build is visible. Additive
    # and never-raises (harness.heartbeat.beat swallows its own errors) -- it can neither
    # change build_system's control flow/return values nor break a build.
    import time as _time

    from harness.heartbeat import beat as _hb_beat
    _hb_start = _time.time()
    _hb_run = f"build_system-{int(_hb_start)}"

    def _beat(_phase: str) -> None:
        _hb_beat("build_system", _phase, run_id=_hb_run, started_at=_hb_start)

    _beat("START")
    # #EXT-040-REQ-3 End
    if llm is None:
        try:
            from harness.coding_loop import build_llm
            llm = build_llm()
        except Exception as exc:
            return _result(shipped=False, done=False, note=f"llm unavailable: {exc}")

    # 1. PLAN (REQ-1)
    _beat("PLAN")  # #EXT-040-REQ-3
    plan_prompt = PLAN_PROMPT.format(spec=spec)
    # #EXT-038-REQ-4 Start
    # TASK-4: an empty research_context() result changes nothing -- byte-identical to the
    # enable_research=False path below, which never even imports/calls this function.
    if enable_research:
        from harness.web_research import research_context
        ctx = research_context(spec)
        if ctx:
            plan_prompt = ctx + plan_prompt
    # #EXT-038-REQ-4 End
    try:
        raw = _call(llm, plan_prompt, max_tokens=PLAN_MAX_TOKENS)
    except Exception as exc:
        return _result(shipped=False, done=False, note=f"planning call failed: {exc}")
    plan = _extract_json(raw, "{", "}")
    if not isinstance(plan, dict):
        return _result(shipped=False, done=False, note="planner produced no parseable JSON plan")
    # #EXT-036-REQ-1 Start
    # TASK-19: deterministic plan-repair BEFORE the coherence gate — fixes the MEASURED
    # single-module/mismatched-entrypoint defect so a genuinely coherent (just misnamed)
    # plan isn't rejected. Never weakens validate_plan's other checks (see
    # _repair_plan_entrypoint's own multi-module conservatism).
    plan, plan_repair_note = _repair_plan_entrypoint(plan)
    # #EXT-036-REQ-32 Start
    # TASK-42: runs SECOND (right after the single-module entrypoint repair, before the
    # dangling-import repair) -- fills the analogous MULTI-module "entrypoint not listed"
    # gap that TASK-19 deliberately left untouched, but only for the one unambiguous
    # shape (a fully disconnected module set); see the function's own docstring for the
    # safety conditions. A no-op on the plan `_repair_plan_entrypoint` already fixed
    # (single-module) or that has no such defect.
    plan, plan_repair_multi_note = _repair_plan_entrypoint_multi(plan)
    # #EXT-036-REQ-32 End
    # TASK-36: runs THIRD (after both entrypoint repairs, while any module-count-dependent
    # conservatism above has already had its say) so ALL measured defects in one plan get
    # repaired — the datastore plan trips both "imports unknown" and (sometimes)
    # "entrypoint not listed". Additive-only; never touches a plan with no dangling local
    # imports.
    plan, dangling_import_note = _repair_plan_dangling_imports(plan)
    plan_repair = "; ".join(
        n for n in (plan_repair_note, plan_repair_multi_note, dangling_import_note) if n
    )
    # #EXT-036-REQ-1 End
    defects = validate_plan(plan)
    if defects:
        return _result(shipped=False, done=False, plan=plan, plan_repair=plan_repair,
                        note="plan failed coherence validation: " + "; ".join(defects[:6]))

    mods = plan.get("modules", [])
    names = [m.get("name") for m in mods]
    order = _topo_order(mods, names)

    # 2. BUILD, leaves-first (REQ-3: syntax gate + bounded repair per module)
    built: dict[str, str] = {}
    for name in order:
        m = next((x for x in mods if x.get("name") == name), None)
        if m is None:
            continue
        try:
            code, ok = _build_module(spec, m, built, llm)
        except Exception as exc:
            return _result(modules=built, shipped=False, done=False, plan=plan, plan_repair=plan_repair,
                            note=f"build failed for {name}: {exc}")
        if not ok:
            return _result(modules=built, shipped=False, done=False, plan=plan, plan_repair=plan_repair,
                            note=f"module {name} failed the syntax gate after {MAX_REPAIR_ATTEMPTS} repair attempt(s)")
        built[name] = code

    # #EXT-035-REQ-3 Start
    # TASK-5: wire the deterministic import-resolver into build_system's OWN multi-module
    # BUILD output. MEASURED gap 2026-07-08: a module generated by THIS build that
    # references a SIBLING module's exported symbol (e.g. a base class) without importing
    # it shipped a NameError at import time -- resolve_imports (harness/import_wiring.py)
    # already handles this shape and is wired into build_from_intent's externally-supplied
    # `deps` path (REQ-3 TASK-3), but was never run over build_system's own generated
    # `built` modules. dep_exports is derived from ALL sibling modules' own top-level
    # def/class names by reusing harness.intent_loop._derive_dep_exports unchanged
    # (`built`'s {name.py: code} shape already matches its expected `deps` input),
    # excluding each module's own stem so a module is never offered an import of itself.
    # Purely mechanical / additive: only ever PREPENDS a missing import line to a module's
    # own code -- never touches any oracle, gate, or acceptance logic below, and is a
    # no-op for single-module builds.
    from harness.import_wiring import resolve_imports
    from harness.intent_loop import _derive_dep_exports
    _sibling_exports = _derive_dep_exports(built)
    for _mod_name in list(built.keys()):
        _others = {stem: exp for stem, exp in _sibling_exports.items()
                   if stem != Path(_mod_name).stem}
        if _others:
            built[_mod_name] = resolve_imports(built[_mod_name], _others)
    # #EXT-035-REQ-3 End

    # 3. ASSEMBLE
    _beat("ASSEMBLE")  # #EXT-040-REQ-3
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _result(modules=built, shipped=False, done=False, plan=plan, plan_repair=plan_repair,
                        note=f"assembly failed: {exc}")
    # #EXT-037-REQ-1 Start
    for name, code in built.items():
        # #EXT-037-REQ-11 Start
        escape = _jailed_write(root, name, code, runtime)
        # #EXT-037-REQ-11 End
        if escape is not None:
            return _result(modules=built, shipped=False, done=False, plan=plan, plan_repair=plan_repair,
                            note=f"assembly failed: module {name!r} refused: {escape}")
    # #EXT-037-REQ-1 End

    # #EXT-037-REQ-7 Start
    # 3b. SECURITY SCAN GATE (TASK-10/REQ-7) — refuse to EXECUTE any acceptance path (HTTP
    # or plain checklist) when the assembled modules trip scan_code's dangerous-operation
    # classifier: SUBPROCESS/SHELL, DYNAMIC-EXEC, DESTRUCTIVE/FS-OUTSIDE-ROOT, or an
    # un-permitted NETWORK/EGRESS call. A generated CLI/service has no legitimate business
    # doing any of these; refusing here means dangerous model-generated code NEVER RUNS on
    # the host. Assembly (the files already written to `root`) is preserved (`shipped=True`
    # so a caller can still inspect what was refused) -- only EXECUTION is withheld.
    # DENY_ALL egress by default: a generated CLI/service acceptance run has no legitimate
    # need for network access (the owner's egress-is-gated-not-blocked design applies to a
    # future caller that explicitly supplies a looser EgressPolicy, not to this default).
    _beat("SCAN")  # #EXT-040-REQ-3
    security_report = scan_code(built, egress_policy=EgressPolicy.DENY_ALL)
    if not security_report.ok:
        categories = sorted({v.get("category", "?") for v in security_report.violations})
        detail = "; ".join(
            f"{v.get('category')}: {v.get('detail')} (line {v.get('lineno')}, {v.get('file')})"
            for v in security_report.violations[:5]
        )
        return _result(
            modules=built, shipped=True, done=False, plan=plan, plan_repair=plan_repair,
            unmet=["build refused on security scan: " + ", ".join(categories)],
            note="SECURITY: build refused — " + detail,
            security={"ok": False, "violations": security_report.violations,
                      "egress_ops": security_report.egress_ops, "notes": security_report.notes},
        )
    # #EXT-037-REQ-7 End

    # #EXT-037-REQ-8 Start
    # 3c. CODE-QUALITY SIGNAL (TASK-12/REQ-8) — computed AFTER the security scan gate has
    # already passed (built modules exist and are cleared to run). ADVISORY ONLY: this NEVER
    # changes `done`, never refuses the build -- a working-but-smelly build still ships/passes
    # exactly as before this task. Computed once here and attached to every RELEVANT return
    # path below that has `built` (both done=True and done=False paths).
    quality = dataclasses.asdict(assess_quality(built))
    # #EXT-037-REQ-8 End

    # 4. ACCEPTANCE (REQ-2/REQ-7 probe logic) — the real DONE gate, not prose
    _beat("ACCEPTANCE")  # #EXT-040-REQ-3
    # #EXT-036-REQ-22 Start
    # TASK-25: a DETECTED web service is HONESTLY HTTP-verified — never allowed to fall
    # through to the stdout-based checklist / import-only `_smoke_checklist` below, which
    # would hollow-pass the instant the module imports without ever hitting an endpoint.
    try:
        from harness.server_oracle import detect_web_service, serve_and_check
        service = detect_web_service(built)
    except Exception:
        service = None
    if service:
        http_checks = _derive_http_checklist(spec, mods, llm)
        if not http_checks:
            return _result(
                modules=built, shipped=True, done=False, plan=plan, plan_repair=plan_repair,
                unmet=["web service present but not HTTP-verified"],
                note="shipped, but a web service was detected and no derivable HTTP "
                     "acceptance checks were found — not HTTP-verified",
                # #EXT-037-REQ-8 Start
                quality=quality,
                # #EXT-037-REQ-8 End
            )
        try:
            http_result = serve_and_check(root, service, http_checks)
        except Exception as exc:
            http_result = {"ok": False, "results": [], "note": f"serve_and_check failed: {exc}"}
        done = bool(http_result.get("ok"))
        unmet = [] if done else [
            _http_check_label(r.get("check") or {})
            for r in (http_result.get("results") or []) if not r.get("passed")
        ]
        if done:
            note = "DONE (web service HTTP-verified: " + ", ".join(
                _http_check_label(c) for c in http_checks) + ")"
        else:
            note = "NOT DONE — web service HTTP checks failed: " + \
                (", ".join(unmet) if unmet else (http_result.get("note") or "unknown failure"))
        # #EXT-037-REQ-8 Start
        return _result(modules=built, shipped=True, done=done, plan=plan, unmet=unmet,
                        note=note, plan_repair=plan_repair, quality=quality)
        # #EXT-037-REQ-8 End
    # #EXT-036-REQ-22 End
    # #EXT-036-REQ-26 Start
    # TASK-37: COMPOSED checklist -- the deterministic minimum UNIONED with the model's own
    # proposals, never sparser than the minimum (task #118, done-honesty).
    checks = _compose_acceptance_checklist(spec, mods, llm, plan)
    # #EXT-036-REQ-26 End
    # #EXT-036-REQ-30 Start
    # TASK-40: OPTIONAL 7B-review of the MODEL-PROPOSED checks only -- default
    # `check_reviewer=None` is a complete no-op (this whole block is skipped), keeping
    # `build_system` byte-identical to before this task. The deterministic minimum is NEVER
    # sent to the reviewer and always gates as-is; only the non-minimum, model-proposed
    # subset of `checks` is replaced by `review_checks`'s corrected/dropped output.
    if check_reviewer is not None:
        try:
            _minimum_now = _minimum_acceptance(spec, mods, plan)
            _minimum_keys = {(c.get("name"), c.get("code")) for c in _minimum_now}
            _proposed_now = [c for c in checks if (c.get("name"), c.get("code")) not in _minimum_keys]
            if _proposed_now:
                from harness.acceptance_review import review_checks
                _reviewed_now = review_checks(spec, built, _proposed_now, check_reviewer)
                checks = list(_minimum_now) + _reviewed_now
        except Exception:
            pass  # never raises -- keep the composed checklist as-is on any reviewer failure
    # #EXT-036-REQ-30 End
    # #EXT-036-REQ-37 Start
    # TASK-46: OPTIONAL spec-derived behavioral PROPERTY checks -- default
    # `spec_properties=False` is a complete no-op (this whole block is skipped), keeping
    # `build_system` byte-identical to before this task. When enabled, this is PURELY
    # ADDITIVE to the composed checklist (never removes/weakens an existing check) -- see
    # the REQ-37 block above for the full safety argument + tri-state grading rule.
    if spec_properties:
        try:
            for _prop in _derive_spec_properties(spec, llm):
                _pcheck = _build_property_check(_prop, mods, llm, plan=plan)
                if _pcheck is not None:
                    checks.append(_pcheck)
        except Exception:
            pass  # never raises -- a property-check failure just means fewer checks, never more
    # #EXT-036-REQ-37 End
    if not checks:
        # #EXT-037-REQ-8 Start
        return _result(modules=built, shipped=True, done=False, plan=plan, plan_repair=plan_repair,
                        unmet=["no acceptance checklist derived"],
                        note="shipped, but no executable acceptance checklist could be derived",
                        quality=quality)
        # #EXT-037-REQ-8 End
    unmet = [c.get("name", "?") for c in checks if not _run_check(root, c)]
    # #EXT-036-REQ-4 End
    # #EXT-036-REQ-5 Start
    # 5. SYSTEM-LEVEL REPAIR (REQ-5): drive shipped -> DONE from the acceptance-check
    # feedback. Skipped entirely when already done (non-degrading, no wasted calls).
    repairs: list[dict] = []
    if unmet:
        _beat("REPAIR")  # #EXT-040-REQ-3
        # #EXT-037-REQ-11 Start
        built, unmet, repairs = _repair_system(spec, root, built, checks, unmet, llm, runtime=runtime)
        # #EXT-037-REQ-11 End
    # #EXT-036-REQ-5 End
    # #EXT-036-REQ-34 Start
    # TASK-44 (REQ-34): OPT-IN iterative replan-as-modification recovery -- default
    # `replan_on_failure=False` is a complete no-op (this whole block never runs), keeping
    # `build_system` BYTE-IDENTICAL to before this task for every existing caller/test. When
    # `True` and the targeted per-check repair above still leaves the build NOT DONE, step
    # back and REPLAN the remaining gap as a MODIFICATION (reusing `modify_system`),
    # convergence-gated, bounded to `MAX_REPLAN_ROUNDS`.
    replan_note = ""
    if replan_on_failure and unmet:
        _beat("REPLAN")  # #EXT-040-REQ-3
        pre_replan_unmet_count = len(unmet)
        built, unmet, replan_rounds = _replan_as_modification(
            spec, root, built, checks, unmet, llm, runtime=runtime)
        if replan_rounds:
            replan_note = (f" (replan-as-modification: {replan_rounds} round(s), "
                            f"unmet {pre_replan_unmet_count}->{len(unmet)})")
    # #EXT-036-REQ-34 End
    # #EXT-058-REQ-3 Start
    # TASK-6: deterministic REPAIR candidate -- the verified leaf-library's single-leaf
    # DSL->system path (TASK-5, `harness.graph_dsl`) made LIVE. ONLY tried when the free-form
    # build (plus every repair stage above: targeted per-check repair, and the optional
    # replan-as-modification loop) STILL has an unmet check -- so a spec with no matching leaf,
    # or a free-form build that already passed, never reaches this block at all (byte-identical
    # to before this task, `unmet` empty short-circuits the `if unmet:` guard immediately).
    #
    # ADDITIVE + HONEST by construction: `leaf_for_spec` returns a class only when the VISIBLE
    # spec text fingerprints that leaf's contract (reusing `adt_oracle`'s conservative,
    # spec-keyword-gated classifier -- never a benchmark/task id, see `graph_dsl.leaf_for_spec`).
    # The candidate is emitted into a FRESH throwaway directory (never touching `root` until it
    # proves itself) and graded by the SAME deterministic `_minimum_acceptance` floor a
    # free-form build must pass. It is adopted -- written into `root` through the SAME gated
    # `_jailed_write`/`code.write_file` chokepoint `build_system` already uses (Tenet 1),
    # `unmet` cleared, `done` flipped True -- ONLY when it actually passes every one of those
    # checks. It can NEVER flip a broken build to done: any exception, a declined
    # `dsl_to_system` (multi-node/unknown-class), an empty checklist, or a still-unmet check
    # leaves `unmet`/`built` completely untouched.
    build_path = "free-form"
    if unmet:
        from harness import graph_dsl
        leaf_cls = graph_dsl.leaf_for_spec(spec)
        if leaf_cls:
            _beat("LEAF-REPAIR")  # #EXT-040-REQ-3
            try:
                leaf_graph = {"nodes": [{"id": "leaf", "class": leaf_cls, "params": {}}],
                               "edges": []}
                with tempfile.TemporaryDirectory(prefix="ext058_leaf_") as _cand_dir:
                    cand_root = Path(_cand_dir)
                    if graph_dsl.dsl_to_system(leaf_graph, cand_root):
                        leaf_mods = [{"name": "main.py"}]
                        leaf_checks = _minimum_acceptance(spec, leaf_mods, plan=None)
                        leaf_unmet = [c.get("name", "?") for c in leaf_checks
                                      if not _run_check(cand_root, c)]
                        if leaf_checks and not leaf_unmet:
                            leaf_code = (cand_root / "main.py").read_text(encoding="utf-8")
                            escape = _jailed_write(root, "main.py", leaf_code, runtime)
                            if escape is None:
                                built = {"main.py": leaf_code}
                                unmet = []
                                build_path = f"leaf:{leaf_cls}"
                                # quality is ADVISORY (never gates `done`); recompute so it
                                # honestly reflects the adopted leaf module, not the stale
                                # free-form modules it replaced.
                                quality = dataclasses.asdict(assess_quality(built))
            except Exception:
                pass
    # #EXT-058-REQ-3 End
    # #EXT-036-REQ-4 Start
    done = not unmet
    _beat("DONE" if done else "NOT-DONE")  # #EXT-040-REQ-3
    note = "DONE (all acceptance checks pass)" if done else "NOT DONE — unmet: " + ", ".join(unmet)
    if repairs:
        rounds = len({r["round"] for r in repairs})
        note += f" (after {rounds} repair round(s))"
    # #EXT-036-REQ-34 Start
    note += replan_note
    # #EXT-036-REQ-34 End
    # #EXT-058-REQ-3 Start
    if build_path != "free-form":
        note += f" (build_path={build_path})"
    # #EXT-058-REQ-3 End
    # #EXT-037-REQ-8 Start
    return _result(modules=built, shipped=True, done=done, plan=plan, unmet=unmet, note=note,
                    repairs=repairs, plan_repair=plan_repair, quality=quality,
                    # #EXT-058-REQ-3 Start
                    build_path=build_path,
                    # #EXT-058-REQ-3 End
                    )
    # #EXT-037-REQ-8 End
# #EXT-036-REQ-4 End


# #EXT-036-REQ-14 Start
# TASK-7 (REQ-14): modify an EXISTING system from a sentence ("add median to the CSV CLI").
# Composes the CREATE pipeline's PROVEN pieces (``syntax_ok``, ``_derive_acceptance_checklist``,
# ``_run_check``, ``REPAIR_PROMPT``) with the non-degrading revert pattern from TASK-5's
# ``_repair_system``. Two-plane: the model judges WHICH module(s) the sentence targets and
# writes their regenerated body; every baseline/regression/revert/assembly step is
# deterministic. The HONESTY core (Tenet 3): a modification is only ``applied`` when the
# system's PRE-EXISTING passing behavior survives it — a modification that breaks something
# that used to work is REVERTED (disk + in-memory dict), never accepted.

IDENTIFY_TARGET_PROMPT = (
    "MODIFICATION TARGET: given the existing system's modules and a modification sentence, "
    "identify which module(s) must change.\n\n"
    "EXISTING MODULES:\n{sources}\n\n"
    "MODIFICATION: {sentence}\n\n"
    "Output ONLY a JSON list of the module name(s) to change, taken from the list above "
    '(e.g. ["name.py"]). No prose.'
)

MODIFY_MODULE_PROMPT = (
    "APPLY MODIFICATION to module `{name}`: change it to satisfy the MODIFICATION below "
    "while preserving its existing behavior for anything the sentence does not touch.\n"
    "MODIFICATION: {sentence}\n\n"
    "CURRENT `{name}`:\n{code}\n\n"
    "Output ONLY the COMPLETE modified module (no markdown fences, no prose)."
)


def _mods_from_code(modules: dict) -> list:
    """Derive a plan-shaped module list (name + best-effort exports) from raw source code, so
    the existing plan-oriented helpers (``_module_api``, ``_derive_acceptance_checklist``,
    ``_smoke_checklist``) can be REUSED for a system that has no plan at all — an
    already-built or externally-supplied system, as ``modify_system`` receives. Exports are
    the module's top-level functions/classes (name only — no signature is fabricated). Never
    raises: a module whose source fails to parse simply contributes no exports."""
    mods = []
    for name, code in (modules or {}).items():
        exports = []
        try:
            tree = ast.parse(code or "")
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    exports.append({"name": node.name, "signature": f"def {node.name}(...):"})
                elif isinstance(node, ast.ClassDef):
                    exports.append({"name": node.name, "signature": f"class {node.name}:"})
        except (SyntaxError, ValueError):
            pass
        mods.append({"name": name, "exports": exports, "imports": []})
    return mods


def _identify_targets(modules: dict, mod_sentence: str, llm) -> list:
    """Model judgment (REQ-14): which existing module(s) does the modification sentence
    target? Guarded — an unreachable model, unparseable JSON, or a name outside the known
    module set yields ``[]`` (no target identified, no change attempted; never raises, never
    guesses at a module that doesn't exist)."""
    sources = "\n\n".join(f"# {name}:\n{code}" for name, code in (modules or {}).items())
    try:
        raw = _call(llm, IDENTIFY_TARGET_PROMPT.format(sources=sources, sentence=mod_sentence),
                    max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    names = _extract_json(raw, "[", "]")
    if not isinstance(names, list):
        return []
    return [n for n in names if isinstance(n, str) and n in modules]


def _regenerate_module(name: str, code: str, mod_sentence: str, llm, *,
                        max_repair: int = MAX_REPAIR_ATTEMPTS) -> tuple:
    """Regenerate one existing module WITH the requested change (REQ-14), given its CURRENT
    source + the modification sentence, then the SAME bounded syntax-gate/repair loop
    ``_build_module`` uses for a freshly-planned module (reusing ``syntax_ok``/
    ``REPAIR_PROMPT`` verbatim). Returns ``(code, syntax_ok)``."""
    new_code = _strip_fences(_call(llm, MODIFY_MODULE_PROMPT.format(
        name=name, sentence=mod_sentence, code=code), max_tokens=BUILD_MAX_TOKENS))
    ok, err = syntax_ok(new_code)
    for _ in range(max_repair):
        if ok:
            break
        new_code = _strip_fences(_call(llm, REPAIR_PROMPT.format(name=name, err=err, code=new_code),
                                        max_tokens=BUILD_MAX_TOKENS))
        ok, err = syntax_ok(new_code)
    return new_code, ok


# #EXT-036-REQ-35 Start
# TASK-45 (REQ-35): a modification is not always a change to an EXISTING module — it may
# genuinely require a NEW module (e.g. "add rate-limiting" to a system with no rate-limiter
# module yet). `_identify_targets` above only ever names EXISTING modules; this adds the
# analogous NEW-module judgment + the deterministic build path for it, reusing the SAME
# syntax-gate/repair loop `_regenerate_module` uses (`syntax_ok`/`REPAIR_PROMPT` verbatim) so
# no module-building logic is duplicated.
IDENTIFY_NEW_MODULE_PROMPT = (
    "NEW-MODULE CHECK: given the existing system's modules and a change request, does "
    "satisfying the change require an ENTIRELY NEW module that does not already exist?\n\n"
    "EXISTING MODULES: {names}\n\n"
    "CHANGE REQUEST: {sentence}\n\n"
    "If the change can be done by only editing the existing modules above, output exactly: "
    "NONE\n"
    "Otherwise output ONLY a JSON list of the new module filename(s) needed (e.g. "
    '["ratelimiter.py"]) -- each a NEW filename not already in the existing list above. '
    "No prose."
)

NEW_MODULE_PROMPT = (
    "WRITE NEW MODULE `{name}` needed to satisfy this change to an existing system: "
    "{sentence}\n\n"
    "EXISTING MODULES (for context/imports):\n{sources}\n\n"
    "Output ONLY the full source of the new module `{name}` (no markdown fences, no prose)."
)

MAX_NEW_MODULES = 3   # bounded — never fabricate an unbounded number of new files


def _identify_new_modules(modules: dict, mod_sentence: str, llm, *,
                           max_new: int = MAX_NEW_MODULES) -> list:
    """Model judgment (REQ-35): does the modification require an entirely NEW module that does
    not already exist? AMBIGUITY-GUARDED (Tenet 3): any vague/empty/unparseable output
    (including the literal ``NONE``, or a name that isn't a plausible new bare-filename, or one
    that duplicates an existing module) yields ``[]`` — no new module is added, and the
    pre-existing regenerate-only flow is unaffected. Bounded to at most ``max_new`` new module
    names, de-duplicated, in the order named. Never raises (an unreachable model degrades to
    ``[]``, exactly like ``_identify_targets``)."""
    names_list = ", ".join(sorted(modules or {}))
    try:
        raw = _call(llm, IDENTIFY_NEW_MODULE_PROMPT.format(names=names_list, sentence=mod_sentence),
                    max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    raw = (raw or "").strip()
    if not raw or raw.upper().startswith("NONE"):
        return []
    parsed = _extract_json(raw, "[", "]")
    if not isinstance(parsed, list):
        return []
    new_names: list = []
    for n in parsed:
        if not isinstance(n, str):
            continue
        n = n.strip()
        if not n or n in modules or n in new_names:
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.py$", n):
            continue
        new_names.append(n)
        if len(new_names) >= max_new:
            break
    return new_names


def _build_new_module(name: str, mod_sentence: str, modules: dict, llm, *,
                       max_repair: int = MAX_REPAIR_ATTEMPTS) -> tuple:
    """Build one brand-NEW module ``name`` the modification requires (REQ-35), given the
    existing modules' sources for import context, then the SAME bounded syntax-gate/repair
    loop ``_regenerate_module``/``_build_module`` use (``syntax_ok``/``REPAIR_PROMPT``,
    verbatim — no module-building logic duplicated). Returns ``(code, syntax_ok)``."""
    sources = "\n\n".join(f"# {n}:\n{c}" for n, c in (modules or {}).items())
    new_code = _strip_fences(_call(llm, NEW_MODULE_PROMPT.format(
        name=name, sentence=mod_sentence, sources=sources), max_tokens=BUILD_MAX_TOKENS))
    ok, err = syntax_ok(new_code)
    for _ in range(max_repair):
        if ok:
            break
        new_code = _strip_fences(_call(llm, REPAIR_PROMPT.format(name=name, err=err, code=new_code),
                                        max_tokens=BUILD_MAX_TOKENS))
        ok, err = syntax_ok(new_code)
    return new_code, ok
# #EXT-036-REQ-35 End


def _modify_result(*, modules, applied: bool, regressed=None, new_behavior_ok: bool = False,
                    note: str = "") -> dict:
    return {"modules": modules, "applied": applied, "regressed": regressed or [],
            "new_behavior_ok": new_behavior_ok, "note": note}


# TASK-21 (REQ-14 hardening): MEASURED BUG — the model-derived ``baseline_passing`` regression
# gate above can miss a modification that breaks a module's IMPORT entirely, if every surviving
# baseline check happens to exercise only a subset of modules (e.g. only the library, never the
# entrypoint that imports it). Add a DETERMINISTIC, model-independent import smoke-gate: a
# module is "importable" iff ``python -c "import <stem>"`` exits 0 in ``root``. This is additive
# to (never a replacement for) the existing behavioral regression gate.
def _importable_modules(modules: dict, root: Path, python_exe: "str | None" = None) -> set:
    """Return the subset of ``modules`` (by name, e.g. ``"statlib.py"``) that import cleanly
    from ``root`` right now. Deterministic, no model call. Never raises — any subprocess
    failure (missing interpreter, timeout, OSError) conservatively counts that module as NOT
    importable, so it can never later cause a spurious revert."""
    exe = python_exe or sys.executable or "python"
    importable = set()
    for name in (modules or {}):
        stem = Path(name).stem
        if not stem:
            continue
        try:
            proc = subprocess.run(
                [exe, "-c", f"import {stem}"],
                cwd=str(root), capture_output=True, timeout=15,
            )
            if proc.returncode == 0:
                importable.add(name)
        except Exception:
            pass  # not importable — never raises
    return importable


def modify_system(modules: dict, mod_sentence: str, root: "str | Path", *, llm=None,
                   runtime: "object | None" = None) -> dict:
    """Modify an EXISTING system (``modules``: ``{name: code}``) from a one-sentence change
    request, regression-gated (REQ-14). NEVER raises — any stage failure or a modification
    that regresses existing behavior returns ``applied=False`` with a diagnostic ``note``.

    Pipeline:
      1. BASELINE — assemble the current ``modules`` onto ``root``, derive + run the
         acceptance checklist (reusing ``_derive_acceptance_checklist``/``_run_check``) on
         the CURRENT system, and record the SET of checks that currently PASS — the existing
         behavior this modification must preserve.
      2. The model IDENTIFIES which module(s) ``mod_sentence`` targets (``_identify_targets``)
         and REGENERATES each one with the change, given its current source (
         ``_regenerate_module``), syntax-gated + bounded-repaired (reusing ``syntax_ok``/
         ``REPAIR_PROMPT``, TASK-4's per-module gate). The model is ALSO asked (REQ-35,
         ``_identify_new_modules``) whether the change needs an entirely NEW module that
         doesn't already exist; any clearly-named new module(s) (bounded, ambiguity-guarded)
         are built from scratch (``_build_new_module``, the SAME syntax-gate/repair loop).
      3. ASSEMBLE the modified module(s) AND any newly-added module(s) onto ``root``.
      4. REGRESSION GATE (the honesty core, mirrors TASK-5's ``_repair_system`` revert): the
         baseline-passing checks are re-run; if ANY of them now fails (or the deterministic
         import smoke-gate below regresses), the modified module(s) are REVERTED to their
         pre-modification content (disk + the returned dict), ``applied`` is False, and any
         newly-ADDED module(s) are REMOVED entirely (disk + dict) — never leaving an orphan
         file or a half-wired system (REQ-35). Non-degrading — a modification is only
         accepted when it does not break anything that used to work.
      5. Best-effort: a NEW-behavior checklist is derived from ``mod_sentence`` itself and run
         against the (accepted) modified system; ``new_behavior_ok`` reports whether it passed
         (advisory — ``applied`` never depends on it, since the model-authored new-behavior
         check could itself be wrong, and REQ-14 only REQUIRES existing behavior preserved).

    Returns ``{modules, applied, regressed: [names], new_behavior_ok, note}``. Uses
    ``harness.coding_loop.build_llm()`` when ``llm`` is None (mirrors ``build_system``); an
    injected ``llm`` (``.complete(LlmRequest) -> .text``) drives fully offline testing.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional, same contract as ``build_system``'s own
    ``runtime`` -- threaded to every module write below (the current-system assembly, the
    modified-module assembly and its half-written revert, the regression-gate revert, and any
    newly-added module's write, REQ-35). ``runtime=None`` (the default) is unchanged from
    before this parameter existed.
    """
    root = Path(root)
    modules = dict(modules or {})
    if llm is None:
        try:
            from harness.coding_loop import build_llm
            llm = build_llm()
        except Exception as exc:
            return _modify_result(modules=modules, applied=False, note=f"llm unavailable: {exc}")

    # 0. Assemble the CURRENT system onto disk before baselining — `modules` is the source of
    # truth (a caller may pass a dict without `root` yet reflecting it).
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _modify_result(modules=modules, applied=False, note=f"could not assemble current system: {exc}")
    # #EXT-037-REQ-1 Start
    for name, code in modules.items():
        # #EXT-037-REQ-11 Start
        escape = _jailed_write(root, name, code, runtime)
        # #EXT-037-REQ-11 End
        if escape is not None:
            return _modify_result(modules=modules, applied=False,
                                   note=f"could not assemble current system: module {name!r} refused: {escape}")
    # #EXT-037-REQ-1 End

    mods = _mods_from_code(modules)

    # 1. BASELINE — derive + run the acceptance checklist on the CURRENT system; the set of
    # checks that PASS now is the existing behavior this modification must preserve.
    try:
        baseline_checks = _derive_acceptance_checklist("existing system", mods, llm)
    except Exception:
        baseline_checks = []
    baseline_passing = {c.get("name", "?") for c in baseline_checks if _run_check(root, c)}
    # TASK-21 (REQ-14 hardening): a DETERMINISTIC, model-independent baseline of which modules
    # import cleanly right now — complements the (possibly narrow) model-derived checks above,
    # since the surviving baseline_passing checks may never happen to import every module.
    baseline_importable = _importable_modules(modules, root)

    # 2. IDENTIFY + REGENERATE the targeted module(s) WITH the change.
    targets = _identify_targets(modules, mod_sentence, llm)
    # #EXT-036-REQ-35 Start
    # TASK-45: the modification may ALSO (or INSTEAD) require an entirely NEW module. This
    # call always runs so the "no new module" case is itself a genuine judgment, not a skipped
    # step -- but when it returns [] (the vast majority of modifications, and every existing
    # regenerate-only test in this file), every line below behaves BYTE-IDENTICALLY to before
    # this task (each `new_module_names`/`added_names` loop is simply a no-op 0-iteration pass).
    new_module_names = _identify_new_modules(modules, mod_sentence, llm)
    # #EXT-036-REQ-35 End
    if not targets and not new_module_names:
        return _modify_result(modules=modules, applied=False,
                               note="could not identify a target module for the modification — no change made")

    pre_mod = {name: modules[name] for name in targets}
    changed_names = []
    for name in targets:
        try:
            new_code, ok = _regenerate_module(name, modules[name], mod_sentence, llm)
        except Exception:
            continue
        if not ok:
            continue
        modules[name] = new_code
        changed_names.append(name)

    # #EXT-036-REQ-35 Start
    added_names = []
    for name in new_module_names:
        try:
            new_code, ok = _build_new_module(name, mod_sentence, modules, llm)
        except Exception:
            continue
        if not ok:
            continue
        modules[name] = new_code
        added_names.append(name)
    # #EXT-036-REQ-35 End

    if not changed_names and not added_names:
        return _modify_result(modules=modules, applied=False,
                               note="modification produced no syntactically valid change — no change made")

    # 3. ASSEMBLE the modified module(s) and any newly-ADDED module(s).
    # #EXT-037-REQ-1 Start
    _assembly_error: "str | None" = None
    for name in changed_names:
        # #EXT-037-REQ-11 Start
        escape = _jailed_write(root, name, modules[name], runtime)
        # #EXT-037-REQ-11 End
        if escape is not None:
            _assembly_error = escape
            break
    # #EXT-036-REQ-35 Start
    if _assembly_error is None:
        for name in added_names:
            escape = _jailed_write(root, name, modules[name], runtime)
            if escape is not None:
                _assembly_error = escape
                break
    # #EXT-036-REQ-35 End
    if _assembly_error is not None:
        for name in changed_names:                # never leave a half-written system
            modules[name] = pre_mod[name]
            # #EXT-037-REQ-11 Start
            _jailed_write(root, name, pre_mod[name], runtime)
            # #EXT-037-REQ-11 End
        # #EXT-036-REQ-35 Start
        for name in added_names:                  # never leave an orphaned new-module file
            modules.pop(name, None)
            try:
                (root / name).unlink()
            except OSError:
                pass
        # #EXT-036-REQ-35 End
        return _modify_result(modules=modules, applied=False, note=f"assembly failed: {_assembly_error}")
    # #EXT-037-REQ-1 End

    # 4. REGRESSION GATE — re-run the baseline-passing checks; ANY regression -> REVERT.
    regressed = [c.get("name", "?") for c in baseline_checks
                 if c.get("name", "?") in baseline_passing and not _run_check(root, c)]
    # TASK-21 (REQ-14 hardening): DETERMINISTIC import smoke-gate, additive to the behavioral
    # regression gate above — a module that imported cleanly at baseline but no longer imports
    # after the change is an honest regression even when no surviving model-derived check
    # happened to exercise it (the MEASURED false-honesty-signal bug: a broken `main.py` import
    # slipped past a checklist that only ever imported the library module).
    post_mod_importable = _importable_modules(modules, root)
    import_regressed = sorted(baseline_importable - post_mod_importable)
    if regressed or import_regressed:
        for name in changed_names:
            modules[name] = pre_mod[name]
            # #EXT-037-REQ-1 Start
            # #EXT-037-REQ-11 Start
            _jailed_write(root, name, pre_mod[name], runtime)
            # #EXT-037-REQ-11 End
            # #EXT-037-REQ-1 End
        # #EXT-036-REQ-35 Start
        for name in added_names:   # a regression reverts the WHOLE modification, incl. new files
            modules.pop(name, None)
            try:
                (root / name).unlink()
            except OSError:
                pass
        # #EXT-036-REQ-35 End
        all_regressed = regressed + [n for n in import_regressed if n not in regressed]
        note = "modification regressed existing behavior — reverted: " + ", ".join(regressed) if regressed else \
            "modification reverted"
        if import_regressed:
            note += ("; " if regressed else " — ") + "import-broken: " + ", ".join(import_regressed)
        # #EXT-036-REQ-35 Start
        if added_names:
            note += ("; " if (regressed or import_regressed) else " — ") + \
                "removed added module(s): " + ", ".join(added_names)
        # #EXT-036-REQ-35 End
        return _modify_result(modules=modules, applied=False, regressed=all_regressed, note=note)

    # 5. Best-effort NEW-behavior check, derived from the mod_sentence itself.
    try:
        new_checks = _derive_acceptance_checklist(mod_sentence, _mods_from_code(modules), llm)
    except Exception:
        new_checks = []
    new_behavior_ok = bool(new_checks) and all(_run_check(root, c) for c in new_checks)

    note = "applied — existing behavior preserved"
    if new_checks:
        note += "; new behavior " + ("confirmed" if new_behavior_ok else "not confirmed")
    # #EXT-036-REQ-35 Start
    if added_names:
        note += "; added module(s): " + ", ".join(added_names)
    # #EXT-036-REQ-35 End
    return _modify_result(modules=modules, applied=True, new_behavior_ok=new_behavior_ok, note=note)
# #EXT-036-REQ-14 End


# #EXT-036-REQ-13 Start
# TASK-13 (REQ-13): hard-tier ESCALATION core — run the default (primary) model first; only pay
# for the stronger fallback (measured: Qwen2.5-Coder-7B) when the primary actually failed to
# ship. OFFLINE, test-gated. Live CLI/Jetson wiring of a real `swap_fn` (e.g.
# `harness.collaborative_solve._http_swap(manager_url)`) is an explicit OUT-OF-SCOPE follow-up.
#
# 2026-07-07 MEASURED FIX (task #142): a live Jetson hard-tier LRU build shipped a BROKEN system
# (`shipped=True, done=False` — it failed the deterministic acceptance floor) and escalation did
# NOT fire, because the trigger only checked `not shipped`. Since the primary almost always
# ships *something*, the 7B fallback was barely ever invoked. The meaningful success signal is
# `done` (passed acceptance), not `shipped` — the trigger below now escalates on `not done`, and
# `_better_result`'s tie-break now ranks `done` above `shipped` to match (done always implies
# shipped in `build_system`'s own result shape, so this never contradicts a shipped-only result).

def _better_result(fallback: dict, primary: dict) -> dict:
    """Deterministic tie-break rule (REQ-13, amended 2026-07-07): prefer done over not-done,
    then shipped over not-shipped, then fewer unmet requirements. The PRIMARY wins an exact tie
    — the fallback must be STRICTLY better to be worth the extra latency/cost it already paid.
    Never raises — a malformed dict is treated as the worst possible result."""
    def _score(r: dict) -> tuple:
        r = r if isinstance(r, dict) else {}
        return (
            1 if r.get("done") else 0,
            1 if r.get("shipped") else 0,
            -len(r.get("unmet") or []),
        )
    return fallback if _score(fallback) > _score(primary) else primary


def build_system_escalating(spec: str, root: "str | Path", *, primary_llm, fallback_llm=None,
                             swap_fn=None, fallback_model_id: "str | None" = None,
                             primary_model_id: "str | None" = None,
                             runtime: "object | None" = None) -> dict:
    """ESCALATE-ONLY-ON-FAILURE wrapper around ``build_system`` (REQ-13). Runs the default
    (``primary_llm``) build first; if it is DONE (passed the deterministic acceptance floor),
    returns it AS-IS — ``fallback_llm``/``swap_fn`` are NEVER invoked, so the common case pays no
    extra latency. Only when the primary is NOT done (2026-07-07: this includes a primary that
    SHIPPED a broken system, not only one that failed to ship at all), and a ``fallback_llm`` is
    supplied, does it swap to the stronger fallback model (via ``swap_fn(fallback_model_id)``
    when a ``swap_fn`` is given — the two-plane serving swap) and retry with
    ``build_system(spec, root, llm=fallback_llm)``, returning whichever result is BETTER by
    ``_better_result``'s deterministic rule (done > shipped > fewer unmet requirements).
    Restores the primary model afterward (``swap_fn(primary_model_id)`` in a ``finally`` block)
    whenever a swap to the fallback was made and both ``swap_fn``/``primary_model_id`` are
    available.

    Adds two metadata keys to every returned dict (including primary-only returns, for a
    consistent shape): ``escalated`` (bool — whether a fallback attempt was actually made) and
    ``model`` (``"primary"`` or ``"fallback"`` — which model's result was returned).

    NEVER raises (mirrors ``build_system``): a ``swap_fn`` failure or an exception from the
    fallback ``build_system`` call is caught and the PRIMARY result is returned unchanged (with
    the metadata keys added) — escalation never leaves the caller worse off than primary-only.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional, threaded straight through to BOTH internal
    ``build_system`` calls below (same target ``root`` either way). ``runtime=None`` (the
    default) is unchanged from before this parameter existed.
    """
    primary_result = build_system(spec, root, llm=primary_llm, runtime=runtime)
    # 2026-07-07 (task #142): escalate on NOT-DONE, not merely not-shipped -- a primary that
    # SHIPPED a broken system (shipped=True, done=False) must still trigger the fallback; `done`
    # is the meaningful acceptance signal, `shipped` alone is not.
    if primary_result.get("done"):
        return {**primary_result, "escalated": False, "model": "primary"}

    if fallback_llm is None:
        return {**primary_result, "escalated": False, "model": "primary"}

    swapped_to_fallback = False
    try:
        if swap_fn is not None and fallback_model_id is not None:
            swap_fn(fallback_model_id)
            swapped_to_fallback = True
        fallback_result = build_system(spec, root, llm=fallback_llm, runtime=runtime)
    except Exception:
        return {**primary_result, "escalated": False, "model": "primary"}
    finally:
        if swapped_to_fallback and swap_fn is not None and primary_model_id is not None:
            try:
                swap_fn(primary_model_id)
            except Exception:
                pass   # never let a restore failure raise out of the wrapper

    winner = _better_result(fallback_result, primary_result)
    model_tag = "fallback" if winner is fallback_result else "primary"
    return {**winner, "escalated": True, "model": model_tag}
# #EXT-036-REQ-13 End


# #EXT-036-REQ-23 Start
# TASK-27 (REQ-23): the GOVERNED build path -- an explicit, INDEPENDENTLY-verified requirement
# list so no requirement is silently dropped from code OR acceptance. MEASURED gap
# (`harness/coherence_suite.py`): `build_system` on an 11-requirement interdependent kvdb-cli
# SHIPPED but reported `done=True` while silently dropping ONE requirement (`incr`) -- because
# both the code AND its own self-derived acceptance checklist are generated from the SAME
# prompt, sharing the same blind spot. `build_system_governed` fixes this with a SPEC-OF-RECORD:
# an independently DECOMPOSED requirement list (a separate model call, before any code exists),
# each with its own executable check; `done` is judged ONLY against that list, never against
# `build_system`'s own checklist. When a requirement is unmet, a RE-GROUND repair call feeds the
# model the FULL requirement list (not just the failing one) so a fix can't blindly re-drop a
# different requirement -- and if it does anyway, the round is REVERTED (mirrors TASK-5's
# `_repair_system` non-degrading guard) so `requirements_met` never regresses across rounds.
#
# TASK-28 (REQ-23): LIVE gemma diagnostic (`.jaros-data/diag_decompose.py`) caught the governed
# path 0/11-ing on live gemma (WORSE than plain build_system's 10/11) from three defects, fixed
# here: (A) gemma emits the decompose list as ONE JSON ARRAY PER LINE, which the naive
# single-outermost-bracket extractor cannot parse -> `_extract_requirements_json` is now robust
# to one-array-per-line/JSONL/a single combined array; (B) gemma's `check` assumed an imagined
# import-and-assert-class API that never matches the REAL built interface (a stdin-driven CLI)
# -> requirements are now decomposed + verified as BLACK-BOX CLI checks (argv/stdin/expect) via
# the proven `harness.system_suite._run_cli`/`_resolve_entry` oracle; (C) `build_system_governed`
# now ALWAYS runs `build_system` (even when decompose yields nothing) so it degrades to
# build_system's own result rather than a hollow 0-requirement/0-module regression.

GOVERNED_DECOMPOSE_PROMPT = (
    "GOVERNED-BUILD DECOMPOSE: read this spec and enumerate every DISTINCT, INDEPENDENT "
    "requirement it implies -- do not drop or merge any, even small ones.\n\n"
    "SPEC: {spec}\n\n"
    "The system you are decomposing WILL be run as a command-line program: `python main.py`, "
    "reading ONE command per line from STDIN and printing results to STDOUT -- it is NEVER an "
    "importable class/object API.\n\n"
    "For EACH requirement, write a BLACK-BOX ACCEPTANCE CHECK for that ONE requirement alone, "
    "in the system's own CLI terms: the `argv` command-line arguments (usually an empty list), "
    "the exact `stdin` text to feed the program (one or more commands, each ending in a "
    "newline), and the `expect` substring that MUST appear in the program's combined stdout for "
    "this ONE requirement to be satisfied.\n\n"
    "Output ONLY a JSON list (no markdown fences, no prose): "
    '[{{"req_id": "<short unique id>", "description": "<one line>", '
    '"argv": [], "stdin": "<the exact stdin commands for this requirement>", '
    '"expect": "<substring that must appear in stdout>"}}]'
)

GOVERNED_REPAIR_PROMPT = (
    "GOVERNED-BUILD REPAIR: this build must satisfy ALL of the following independently-verified "
    "requirements (the SPEC OF RECORD), but at least one is UNMET. Re-ground on the FULL list "
    "before fixing -- do NOT remove or break any requirement that already works.\n\n"
    "The system is run as a command-line program: `python main.py`, reading commands from "
    "STDIN and printing results to STDOUT.\n\n"
    "ALL REQUIREMENTS:\n{all_reqs}\n\n"
    "UNMET REQUIREMENT: {req_id} -- {req_desc}\n"
    "ITS BLACK-BOX CHECK: run with argv={req_argv}, feed this STDIN:\n{req_stdin}\n"
    "EXPECTED STDOUT TO CONTAIN: {req_expect}\n"
    "ACTUAL RUN OUTPUT:\n{error}\n\n"
    "Identify which ONE module needs to change to ADD/FIX this requirement WITHOUT removing or "
    "breaking any other already-working requirement, and provide its COMPLETE corrected content. "
    "Output ONLY a JSON object (no prose, no markdown fences): "
    '{{"module": "<module_name>.py", "code": "<complete corrected module source>"}}'
)

MAX_GOVERNED_REPAIR_ROUNDS = 3   # bounded RE-GROUND repair loop, REQ-23


def _is_blackbox_requirement_check(req) -> bool:
    """The deterministic BLACK-BOX check filter (TASK-28 fix, defect B): a decomposed
    requirement survives only if it carries a well-formed black-box CLI check -- `argv` (a
    list of strings, possibly empty), `stdin` (a string, possibly empty), and a non-empty
    `expect` substring. Replaces the earlier import-and-assert-class check shape, which
    assumed an API the ACTUAL built system (a stdin-driven CLI, `python main.py`) never
    exposes -- so a parsed check would error against the real interface and every
    requirement would be falsely reported unmet. Never raises."""
    if not isinstance(req, dict):
        return False
    argv = req.get("argv", [])
    stdin = req.get("stdin", "")
    expect = req.get("expect")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        return False
    if not isinstance(stdin, str):
        return False
    if not isinstance(expect, str) or not expect.strip():
        return False
    return True


def _extract_requirements_json(raw: str) -> list:
    """Robust JSON extraction for the DECOMPOSE stage (TASK-28 fix, defect A). MEASURED (live
    gemma diagnostic, `.jaros-data/diag_decompose.py`): gemma emits the requirement list as ONE
    JSON ARRAY PER LINE -- `[{"req_id":"R1",...}]` then `[{"req_id":"R2",...}]` on separate
    lines -- not one combined array. The naive single-outermost-bracket extractor
    (`_extract_json`)'s greedy first-'['-to-last-']' match spans every line at once, which is
    not valid JSON, so it silently parsed to nothing (0 requirements). This tries the single
    COMBINED array/object case first (back-compat with a well-formed one-array response), then
    falls back to a line-by-line scan collecting every parseable JSON array or bare object --
    handling one-array-per-line, several arrays, or bare JSONL objects alike. De-dup is the
    caller's job (`_dedup_requirements`). Never raises."""
    if not raw or not raw.strip():
        return []
    whole = _extract_json(raw, "[", "]")
    if isinstance(whole, list) and whole and all(isinstance(x, dict) for x in whole):
        return whole
    objs: list = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        for opener, closer in (("[", "]"), ("{", "}")):
            if opener not in line or closer not in line:
                continue
            m = re.search(re.escape(opener) + r".*" + re.escape(closer), line, re.DOTALL)
            if not m:
                continue
            try:
                val = json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(val, list):
                objs.extend(x for x in val if isinstance(x, dict))
            elif isinstance(val, dict):
                objs.append(val)
            break
    return objs


def _dedup_requirements(reqs: list) -> list:
    """Deterministic de-dup + filter of the decomposed requirement list: keep only entries with
    a non-empty `req_id` AND a well-formed black-box check (`_is_blackbox_requirement_check`,
    TASK-28), dropping duplicate req_ids/checks. Never raises."""
    seen_ids: set = set()
    seen_checks: set = set()
    out: list = []
    for r in reqs or []:
        if not isinstance(r, dict):
            continue
        req_id = r.get("req_id")
        if not isinstance(req_id, str) or not req_id.strip() or not _is_blackbox_requirement_check(r):
            continue
        req_id = req_id.strip()
        argv = [str(a) for a in (r.get("argv") or [])]
        stdin = r.get("stdin") or ""
        expect = r.get("expect").strip()
        check_key = (tuple(argv), stdin, expect)
        if req_id in seen_ids or check_key in seen_checks:
            continue
        seen_ids.add(req_id)
        seen_checks.add(check_key)
        out.append({"req_id": req_id, "description": r.get("description", ""),
                     "argv": argv, "stdin": stdin, "expect": expect})
    return out


def _decompose_requirements(spec: str, llm) -> list:
    """One model round-trip enumerating the DISTINCT requirements implied by `spec`, each with
    its own BLACK-BOX check (`argv`/`stdin`/`expect`, TASK-28) -- the INDEPENDENT spec-of-record
    `build_system_governed` verifies against (never the build's own self-derived acceptance
    checklist, and never an imagined import-and-assert-class API). Robustly parsed
    (`_extract_requirements_json`) then filtered + de-duped (`_dedup_requirements`). Guarded --
    returns [] on any model/parse failure or when nothing survives the filter; never raises,
    never fabricates a requirement."""
    try:
        raw = _call(llm, GOVERNED_DECOMPOSE_PROMPT.format(spec=spec), max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    reqs = _extract_requirements_json(raw)
    return _dedup_requirements(reqs)


def _repair_module_for_requirement(all_reqs_blob: str, req: dict, error: str,
                                    built: "dict[str, str]", llm) -> "dict | None":
    """RE-GROUND repair call (REQ-23): asks the model to fix ONE unmet requirement while feeding
    it the FULL requirement list (`all_reqs_blob`) so it re-grounds on everything, not just the
    failing check -- the anti-drift mechanism. Returns `{"module": name, "code": code}` or None
    on any model/parse failure or an out-of-range module name (mirrors
    `_repair_module_for_check`; never raises, never a fabricated fix)."""
    try:
        raw = _call(llm, GOVERNED_REPAIR_PROMPT.format(
            all_reqs=all_reqs_blob, req_id=req.get("req_id", "?"),
            req_desc=req.get("description", ""), req_argv=req.get("argv") or [],
            req_stdin=req.get("stdin", ""), req_expect=req.get("expect", ""),
            error=(error or "")[:500], sources=_sources_blob(built)), max_tokens=BUILD_MAX_TOKENS)
    except Exception:
        return None
    fix = _extract_json(raw, "{", "}")
    if not isinstance(fix, dict):
        return None
    name, code = fix.get("module"), fix.get("code")
    if not name or name not in built or not code:
        return None
    return {"module": name, "code": code}


def _verify_requirement(root: Path, plan: "dict | None", req: dict,
                         python_exe: "str | None" = None) -> "tuple[bool, str]":
    """Independently verify ONE decomposed requirement against the ASSEMBLED system via the
    PROVEN BLACK-BOX CLI oracle (TASK-28 fix, defect B) -- reuses
    `harness.system_suite._run_cli`/`_resolve_entry` (the SAME primitives REQ-20/21 already
    built + proved) rather than an imagined import-and-assert-class API the actual built
    system (a stdin-driven CLI) never exposes. Resolves the entrypoint from `plan`, falling
    back to `root/main.py` (mirrors `system_suite._run_single_check`'s convention) when the
    plan's declared entrypoint doesn't resolve to a real file. Returns
    ``(ok, combined stdout+stderr diagnostic)``. Never raises."""
    try:
        from harness.system_suite import _resolve_entry, _run_cli

        exe = python_exe or sys.executable or "python"
        entry = _resolve_entry(plan) if isinstance(plan, dict) else None
        entry_path = (root / entry) if entry else None
        if entry_path is None or not entry_path.is_file():
            fallback = root / "main.py"
            entry_path = fallback if fallback.is_file() else None
        if entry_path is None:
            return False, "no resolvable entrypoint"
        ok, out = _run_cli(exe, entry_path, req.get("argv") or [], req.get("stdin") or "", root)
        if not ok:
            return False, out
        expect = req.get("expect") or ""
        return (expect in out), out
    except Exception as exc:
        return False, str(exc)


def _governed_result(*, modules=None, shipped: bool, done: bool, requirements_total: int = 0,
                      requirements_met: int = 0, unmet=None, note: str = "", rounds: int = 0) -> dict:
    return {
        "modules": modules or {}, "shipped": shipped, "done": done,
        "requirements_total": requirements_total, "requirements_met": requirements_met,
        "unmet": unmet or [], "note": note, "rounds": rounds,
    }


def build_system_governed(spec: str, root: "str | Path", *, llm=None,
                           max_repair: int = MAX_GOVERNED_REPAIR_ROUNDS,
                           runtime: "object | None" = None) -> dict:
    """The GOVERNED build path (REQ-23, TASK-27; hardened by TASK-28) -- realizes PRIME-001
    intent capability (g) by LIFTING long-horizon build coherence with an explicit,
    INDEPENDENTLY-verified requirement list, so no requirement is silently dropped from code OR
    acceptance (the measured `coherence_suite` failure: `build_system` dropped a requirement AND
    its self-derived acceptance checklist shared the same blind spot, so it reported `done=True`
    anyway).

    Pipeline:
      1. DECOMPOSE (`_decompose_requirements`) -- ONE model call enumerates the DISTINCT
         requirements implied by `spec`, each with its own BLACK-BOX check (`argv`/`stdin`/
         `expect`, in the system's own `python main.py`-reads-stdin terms, TASK-28). This list
         is the SPEC OF RECORD, independent of whatever `build_system`'s own checklist later
         contains.
      2. BUILD -- via the existing, UNMODIFIED `build_system(spec, root, llm=llm)` pipeline
         (plan -> topo-build -> assemble -> its own acceptance/repair). Only `shipped`/`modules`/
         `plan` are consumed here; `build_system`'s own `done` verdict is never trusted. ALWAYS
         runs (TASK-28 fix, defect C — the NO-REGRESS FLOOR), even when decompose below yielded
         nothing, so a decompose failure degrades to `build_system`'s own result rather than a
         hollow 0-requirement/0-module regression.
      3. VERIFY EACH -- every enumerated requirement's check is run via the proven BLACK-BOX CLI
         oracle (`_verify_requirement`, reusing `harness.system_suite._run_cli`/`_resolve_entry`,
         TASK-28) against the assembled system; the set of UNMET requirements is recorded.
      4. RE-GROUND + REPAIR -- for each unmet requirement, a repair call
         (`_repair_module_for_requirement`) feeds the model the FULL requirement list + the
         specific unmet one + the current module sources, asking it to ADD/fix that requirement
         WITHOUT removing already-working behavior; the fix is syntax-gated (reusing
         `syntax_ok`/`REPAIR_PROMPT`), applied, and ALL requirements are RE-VERIFIED (so a repair
         that re-drops a different requirement is caught, mirroring TASK-5's `_repair_system`
         non-degrading guard: any round that regresses a previously-met requirement is REVERTED
         and the loop stops; best-seen `(built, unmet)` is tracked). Bounded to `max_repair`
         rounds (default 3).
      5. DONE = every enumerated requirement independently verified -- NEVER the model's own
         self-checklist.

    Returns `{modules, shipped, done, requirements_total, requirements_met, unmet: [...], note,
    rounds}`. NEVER raises: any stage failure returns `shipped`/`done` False with a diagnostic
    `note`. Uses `harness.coding_loop.build_llm()` when `llm` is None (mirrors `build_system`);
    an injected `llm` (`.complete(LlmRequest) -> .text`) drives fully offline testing.

    `runtime` (EXT-037 REQ-11, Tenet 1): optional, threaded straight through to the internal
    `build_system` call and to every `_jailed_write` this function performs itself (the RE-GROUND
    repair loop's applied-fix/regression-revert writes, and the final no-regress-floor revert).
    `runtime=None` (the default) is unchanged from before this parameter existed.
    """
    root = Path(root)
    if llm is None:
        try:
            from harness.coding_loop import build_llm
            llm = build_llm()
        except Exception as exc:
            return _governed_result(shipped=False, done=False, note=f"llm unavailable: {exc}")

    # 1. DECOMPOSE -- the independent spec-of-record (never `build_system`'s own checklist).
    try:
        requirements = _decompose_requirements(spec, llm)
    except Exception:
        requirements = []

    # 2. BUILD via the existing, unmodified pipeline -- ALWAYS (TASK-28 defect C, the
    #    NO-REGRESS FLOOR): even a decompose failure below must degrade to `build_system`'s
    #    own shipped/done result, never a hollow 0-requirement/0-module regression.
    try:
        build = build_system(spec, root, llm=llm, runtime=runtime)
    except Exception as exc:
        return _governed_result(shipped=False, done=False,
                                 requirements_total=len(requirements),
                                 unmet=[r["req_id"] for r in requirements],
                                 note=f"build_system raised: {exc}")
    built = dict(build.get("modules") or {}) if isinstance(build, dict) else {}
    shipped = bool(isinstance(build, dict) and build.get("shipped"))
    plan = build.get("plan") if isinstance(build, dict) else None

    if not requirements:
        # NO-REGRESS FLOOR: nothing was independently decomposed to verify against -- fall
        # back to build_system's own (shipped/done) result instead of a degenerate 0/0.
        base_done = bool(isinstance(build, dict) and build.get("done"))
        return _governed_result(
            modules=built, shipped=shipped, done=base_done, requirements_total=0,
            requirements_met=0, unmet=[],
            note=("no requirements could be decomposed from the spec -- fell back to "
                  f"build_system's own result (shipped={shipped}, done={base_done})"),
        )

    if not shipped:
        return _governed_result(
            modules=built, shipped=False, done=False,
            requirements_total=len(requirements), requirements_met=0,
            unmet=[r["req_id"] for r in requirements],
            note=f"build failed to ship: {(build or {}).get('note', '')}",
        )

    # 3. VERIFY EACH enumerated requirement independently (BLACK-BOX, matching the built
    #    system's REAL CLI interface -- never an imagined import-and-assert-class API).
    def _verify_all() -> list:
        return [r["req_id"] for r in requirements if not _verify_requirement(root, plan, r)[0]]

    # #EXT-036-REQ-23 TASK-29 Start
    # NO-REGRESS FLOOR (TASK-29): capture build_system's INITIAL output -- its own modules,
    # already assembled on `root` -- as the BASELINE, verified against these SAME
    # independently-decomposed requirement checks, BEFORE any governed repair runs. A LIVE
    # measurement (kvdb-cli, 11 requirements) caught the repair loop chasing unmet
    # requirements (incr/keys) DAMAGING previously-working behavior (clear/usage broke),
    # ending net WORSE than a plain `build_system` call -- a Tenet-3 safety regression the
    # (count-only, in-memory) tracking below did not actually guarantee end-to-end. This
    # baseline is the floor `build_system_governed` may never end up worse than.
    baseline_built = dict(built)
    baseline_unmet_ids = _verify_all()
    baseline_met = len(requirements) - len(baseline_unmet_ids)
    # #EXT-036-REQ-23 TASK-29 End

    unmet_ids = list(baseline_unmet_ids)
    best_built, best_unmet = dict(built), list(unmet_ids)
    all_reqs_blob = "\n".join(f"- {r['req_id']}: {r.get('description', '')}" for r in requirements)
    by_id = {r["req_id"]: r for r in requirements}
    rounds = 0

    # 4. RE-GROUND + REPAIR (bounded, non-degrading -- mirrors TASK-5's `_repair_system`).
    try:
        for round_no in range(1, max_repair + 1):
            if not unmet_ids:
                break
            rounds = round_no
            pre_round_built = dict(built)
            pre_round_unmet = set(unmet_ids)
            for req_id in list(unmet_ids):
                req = by_id.get(req_id)
                if req is None:
                    continue
                ok, err = _verify_requirement(root, plan, req)
                if ok:
                    continue   # an earlier fix this round already resolved it
                fix = _repair_module_for_requirement(all_reqs_blob, req, err, built, llm)
                if not fix:
                    continue
                name, code = fix["module"], fix["code"]
                if name not in built:
                    continue
                syn_ok, syn_err = syntax_ok(code)
                for _ in range(MAX_REPAIR_ATTEMPTS):
                    if syn_ok:
                        break
                    code = _strip_fences(_call(llm, REPAIR_PROMPT.format(name=name, err=syn_err, code=code),
                                                max_tokens=BUILD_MAX_TOKENS))
                    syn_ok, syn_err = syntax_ok(code)
                if syn_ok:
                    # #EXT-037-REQ-11 Start
                    if _jailed_write(root, name, code, runtime) is None:
                    # #EXT-037-REQ-11 End
                        built[name] = code

            new_unmet = _verify_all()
            new_unmet_set = set(new_unmet)
            passed_before_round = {r["req_id"] for r in requirements} - pre_round_unmet
            regressed = passed_before_round & new_unmet_set
            if regressed:
                # a fix for one requirement silently re-dropped a DIFFERENT, previously-met one
                # -- revert this round's writes entirely and reject it (non-degrading).
                for name, code in pre_round_built.items():
                    if built.get(name) != code:
                        # #EXT-037-REQ-11 Start
                        _jailed_write(root, name, code, runtime)
                        # #EXT-037-REQ-11 End
                built = pre_round_built
                unmet_ids = sorted(pre_round_unmet)
                break

            unmet_ids = new_unmet
            if len(unmet_ids) < len(best_unmet):
                best_built, best_unmet = dict(built), list(unmet_ids)
            if len(unmet_ids) >= len(pre_round_unmet):
                break   # no progress this round -- stop (no infinite loop)
    except Exception:
        pass   # never raise -- the NO-REGRESS FLOOR below independently RE-VERIFIES the
               # actual on-disk state regardless of whatever (possibly partial/dirty)
               # in-memory bookkeeping this loop leaves behind on an aborted round.

    # Final safety net: never return worse than the best-seen (non-regressing) state the
    # round loop itself tracked.
    if len(unmet_ids) > len(best_unmet):
        built, unmet_ids = best_built, best_unmet

    # NO-REGRESS FLOOR, defensive final check (TASK-28 defect C): repair rounds only ever
    # overwrite existing module keys (never delete), so this should already be guaranteed --
    # kept explicit rather than merely incidental, per the honest-floor requirement.
    base_modules = build.get("modules") or {} if isinstance(build, dict) else {}
    if len(built) < len(base_modules):
        built = dict(base_modules)

    total = len(requirements)

    # #EXT-036-REQ-23 TASK-29 Start
    # THE FLOOR (TASK-29): independently RE-VERIFY the actual CURRENT on-disk state from
    # scratch -- never trust the loop's own bookkeeping above, which can go stale if a round
    # aborts mid-way (e.g. an exception raised partway through a repair round, after some of
    # its module write(s) already landed on disk but before that round's own end-of-round
    # regression check ever ran) -- against the SAME baseline requirement checks. If the
    # governed repair's final result is WORSE than build_system's own initial (pre-repair)
    # output on this check set -- fewer requirements independently satisfied, or the
    # governed state fails to re-verify at all -- REVERT: re-assemble the BASELINE's modules
    # back onto `root` (undoing whatever the repair loop left on disk) and return the
    # baseline's own modules/met-count. This GUARANTEES `build_system_governed`'s result is
    # always max(baseline, governed) on the independently-decomposed requirement set -- never
    # worse than a plain `build_system` call (Tenet 3: a safety FLOOR, not a claimed lift).
    try:
        final_unmet_ids = _verify_all()
        governed_met = total - len(final_unmet_ids)
    except Exception:
        final_unmet_ids, governed_met = None, -1
    if final_unmet_ids is None or governed_met < baseline_met:
        for name, code in baseline_built.items():
            # #EXT-037-REQ-11 Start
            _jailed_write(root, name, code, runtime)
            # #EXT-037-REQ-11 End
        built = dict(baseline_built)
        unmet_ids = list(baseline_unmet_ids)
        done = not unmet_ids
        met = baseline_met
        shown_governed_met = governed_met if governed_met >= 0 else "?"
        note = (
            f"GOVERNED repair did not improve on build_system (baseline {baseline_met}/{total} "
            f"vs repaired {shown_governed_met}/{total}) -- kept the single-pass build_system "
            "result (no-regress floor)"
        )
        note += ("; all requirements satisfied by the single-pass build" if not unmet_ids
                  else "; unmet: " + ", ".join(unmet_ids))
        return _governed_result(modules=built, shipped=True, done=done, requirements_total=total,
                                 requirements_met=met, unmet=unmet_ids, note=note, rounds=rounds)
    unmet_ids = final_unmet_ids
    # #EXT-036-REQ-23 TASK-29 End

    done = not unmet_ids
    met = total - len(unmet_ids)
    note = (f"GOVERNED DONE: all {total} independently-verified requirement(s) satisfied" if done
            else f"GOVERNED NOT DONE: {met}/{total} requirement(s) satisfied -- unmet: " + ", ".join(unmet_ids))
    if rounds:
        note += f" (after {rounds} repair round(s))"
    return _governed_result(modules=built, shipped=True, done=done, requirements_total=total,
                             requirements_met=met, unmet=unmet_ids, note=note, rounds=rounds)
# #EXT-036-REQ-23 End


# #EXT-036-REQ-25 Start
# TASK-33 (REQ-25): BEST-OF-K build-RELIABILITY wrapper. MEASURED (median-of-3 coherence run on
# ``harness/coherence_suite.py::HARD_SLICE``): single-pass ``build_system`` scores median coherence
# 1.0 (ZERO dropped requirements) when it succeeds, but suffers an occasional TOTAL BUILD FAILURE
# (~17% measured: 1/6 builds produced nothing runnable, scoring 0). So the failure mode this class
# actually has is RELIABILITY, not dropped requirements -- ``build_system_governed`` (REQ-23) is
# the wrong lever for it. The right lever: build the same spec up to `k` times into ISOLATED temp
# subdirs, independently SCORE each attempt (never trusting its own self-reported `done`), and
# ASSEMBLE only the best-scoring attempt onto the caller's `root`. Selection is 100% deterministic
# (test-gated); only generation (`build_system` itself) is model-driven.

# #EXT-036-REQ-30 Start
# TASK-40: `check_reviewer` keyword param (default None -- byte-identical no-op) added to
# the signature + docstring below; the review step itself is the SECOND `#EXT-036-REQ-30`
# region further down inside this function.
def _score_build_attempt(spec: str, attempt_root: Path, result: dict, llm,
                          check_reviewer=None) -> tuple[int, int]:
    """INDEPENDENT scoring for one best-of-k attempt: NEVER trust `result`'s own self-reported
    `done` -- derive a FRESH, FULL (minimum-inclusive, REQ-26/task #118) acceptance checklist
    from the attempt's own planned module API and run every check for real against the
    attempt's own assembled root, counting real passes. A draw that self-derives fewer model
    checks is still measured against the SAME deterministic minimum every other draw is, so
    best-of-k selects/early-exits on a comparable, trustworthy bar -- never a sparse
    self-accepted one. Returns ``(passed, total)``; ``total == 0`` means nothing could be
    checked at all (no plan / no built modules -- a total build failure), scored 0. Never
    raises.

    ``check_reviewer`` (EXT-036 REQ-30, task #122): OPTIONAL, mirrors `build_system`'s own
    parameter -- default ``None`` is byte-identical to before this parameter existed. When
    given, the non-minimum (model-proposed) portion of the composed checklist is
    reviewed+corrected against this attempt's own spec + built module sources before scoring."""
    # #EXT-036-REQ-30 End
    if not isinstance(result, dict):
        return 0, 0
    plan = result.get("plan")
    mods = plan.get("modules") if isinstance(plan, dict) else None
    built = result.get("modules") or {}
    if not isinstance(mods, list) or not mods or not built:
        return 0, 0
    try:
        # #EXT-036-REQ-26 Start
        checks = _compose_acceptance_checklist(spec, mods, llm, plan)
        # #EXT-036-REQ-26 End
    except Exception:
        checks = []
    # #EXT-036-REQ-30 Start
    # TASK-40: same optional review step `build_system` performs -- skipped entirely when
    # `check_reviewer` is None (the default), keeping this function byte-identical to before.
    if check_reviewer is not None and checks:
        try:
            _minimum_now = _minimum_acceptance(spec, mods, plan)
            _minimum_keys = {(c.get("name"), c.get("code")) for c in _minimum_now}
            _proposed_now = [c for c in checks if (c.get("name"), c.get("code")) not in _minimum_keys]
            if _proposed_now:
                from harness.acceptance_review import review_checks
                _reviewed_now = review_checks(spec, built, _proposed_now, check_reviewer)
                checks = list(_minimum_now) + _reviewed_now
        except Exception:
            pass  # never raises -- keep the composed checklist as-is on any reviewer failure
    # #EXT-036-REQ-30 End
    if not checks:
        return 0, 0
    passed = 0
    for c in checks:
        try:
            if _run_check(attempt_root, c):
                passed += 1
        except Exception:
            pass
    return passed, len(checks)


# #EXT-036-REQ-30 Start
# TASK-40: `check_reviewer` keyword param (default None -- byte-identical no-op) added to
# the signature + docstring below, threaded through to `build_system`/`_score_build_attempt`
# in the two call sites further down inside this function (also tagged).
def build_system_best_of_k(spec: str, root: "str | Path", *, llm=None, k: int = 3,
                            runtime: "object | None" = None,
                            check_reviewer=None) -> dict:
    """Build ``spec`` up to `k` times (each into its OWN fresh, isolated temp subdir so attempts
    never contaminate each other or `root`), independently score every attempt with a freshly
    derived + actually-RUN acceptance checklist (`_score_build_attempt`), and ASSEMBLE only the
    best-scoring attempt's modules onto the caller's `root`.

    EARLY-EXIT: an attempt that passes every one of its own acceptance checks stops the loop
    immediately -- the remaining `k` budget is never spent. Otherwise the winner is the
    highest-scoring attempt, ties broken by the FIRST/earliest-evaluated attempt (deterministic,
    never random).

    Returns ``{modules, shipped, done, attempts_run, best_score, note}``. `done` reflects the
    WINNER's own independently-verified acceptance (passed == total, total > 0) -- NEVER a
    fabricated pass. NEVER raises: a build-call exception is treated as a failed (0-scored)
    attempt; if every attempt fails, the least-bad attempt is returned with `done=False` and an
    honest note.

    Does not modify `build_system`'s own behavior/signature in any way -- this is a pure wrapper
    around it. Wiring into `/buildsystem` is an explicit follow-up (REQ-25).

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional -- threaded ONLY to the FINAL winner-assembly
    write onto the caller's real ``root`` below. Each per-attempt ``build_system`` call above
    builds into an isolated, throwaway ``tempfile.mkdtemp()`` subdirectory that is
    ``shutil.rmtree``'d before this function returns (see the ``finally`` block) -- not a
    meaningful project root to gate -- so those internal calls intentionally stay on
    ``runtime=None``. ``runtime=None`` for the final assembly too (the default) is unchanged
    from before this parameter existed.

    ``check_reviewer`` (EXT-036 REQ-30, task #122): OPTIONAL, mirrors `build_system`'s own
    parameter -- default ``None`` leaves every attempt's build + scoring byte-identical to
    before this parameter existed. When given, it is threaded to BOTH each attempt's
    `build_system` call and `_score_build_attempt`'s independent scoring, so a passed-in
    reviewer is applied consistently across generation and selection."""
    # #EXT-036-REQ-30 End
    root = Path(root)
    k = max(1, int(k)) if k else 1
    attempts: list[dict] = []
    tmp_dirs: list[Path] = []
    winner = None
    try:
        for i in range(k):
            attempt_root = Path(tempfile.mkdtemp(prefix=f"jarify_bok_{i}_"))
            tmp_dirs.append(attempt_root)
            # #EXT-036-REQ-30 Start
            # TASK-40: thread `check_reviewer` through to both generation and scoring.
            try:
                result = build_system(spec, attempt_root, llm=llm, check_reviewer=check_reviewer)
            except Exception as exc:
                result = _result(shipped=False, done=False, note=f"attempt {i} raised: {exc}")
            try:
                passed, total = _score_build_attempt(spec, attempt_root, result, llm,
                                                       check_reviewer=check_reviewer)
            except Exception:
                passed, total = 0, 0
            # #EXT-036-REQ-30 End
            attempts.append({"result": result, "passed": passed, "total": total})
            if total > 0 and passed == total:
                winner = attempts[-1]
                break

        if winner is None:
            best_idx = 0
            best_key = None
            for idx, rec in enumerate(attempts):
                key = (rec["passed"], -idx)   # highest score wins; earlier attempt breaks ties
                if best_key is None or key > best_key:
                    best_key, best_idx = key, idx
            winner = attempts[best_idx] if attempts else {"result": {}, "passed": 0, "total": 0}

        modules = dict((winner["result"] or {}).get("modules") or {})
        if modules:
            try:
                root.mkdir(parents=True, exist_ok=True)
                for name, code in modules.items():
                    # #EXT-037-REQ-11 Start
                    _jailed_write(root, name, code, runtime)
                    # #EXT-037-REQ-11 End
            except Exception:
                pass

        passed, total = winner["passed"], winner["total"]
        done = total > 0 and passed == total
        shipped = bool((winner["result"] or {}).get("shipped")) or bool(modules)
        attempts_run = len(attempts)
        if done:
            note = f"DONE (best of {attempts_run} attempt(s): {passed}/{total} acceptance checks pass)"
        elif total > 0:
            note = (f"NOT DONE — best attempt of {attempts_run} passes {passed}/{total} "
                     "acceptance checks")
        else:
            note = (f"NOT DONE — all {attempts_run} attempt(s) failed to produce a checkable "
                     "system (total build failure), returning the least-bad attempt")
        return {
            "modules": modules,
            "shipped": shipped,
            "done": done,
            "attempts_run": attempts_run,
            "best_score": passed,
            "note": note,
        }
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
# #EXT-036-REQ-25 End
