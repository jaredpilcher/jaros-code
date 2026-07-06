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
the primary actually failed to ship, capturing the marginal coverage without losing the
primary's done-ness or latency on the common (shipped) case. Two-plane: the model does the
build; the deterministic wrapper decides WHETHER to escalate, performs the serving swap via an
injectable ``swap_fn`` (mirrors ``harness.collaborative_solve._http_swap``'s
``(model_id: str) -> None`` convention), restores the primary model afterward, and picks the
better of the two results by a fixed rule (shipped > done > module count). Never raises: a
``swap_fn``/fallback-build failure gracefully falls back to the primary-only result. Live
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


def _extract_json(raw: str, opener: str, closer: str):
    """Best-effort JSON extraction: the model output may carry prose or markdown fences
    around the JSON payload; pull the outermost {..}/[..] span and parse it. Returns None
    (never raises) when no parseable payload is found."""
    m = re.search(re.escape(opener) + r".*" + re.escape(closer), raw or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None


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
    arity-aware round-trip check are left strict/unchanged."""
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

# #EXT-036-REQ-4 Start
def _result(*, modules=None, shipped: bool, done: bool, unmet=None, plan=None, note: str = "",
            repairs=None, plan_repair: str = "", security=None, quality=None) -> dict:
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
    return {"modules": modules or {}, "shipped": shipped, "done": done,
            "unmet": unmet or [], "plan": plan, "note": note, "repairs": repairs or [],
            "plan_repair": plan_repair, "security": security, "quality": quality}
    # #EXT-037-REQ-8 End


# #EXT-036-REQ-30 Start
# TASK-40: `check_reviewer` keyword param (default None -- byte-identical no-op) added to
# the signature + docstring below; the actual review step lives further down in the
# ACCEPTANCE stage (see the SECOND `#EXT-036-REQ-30` region in this function).
def build_system(spec: str, root: "str | Path", *, llm=None,
                  runtime: "object | None" = None,
                  check_reviewer=None) -> dict:
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
    is a CALLER concern, out of scope here."""
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
    try:
        raw = _call(llm, PLAN_PROMPT.format(spec=spec), max_tokens=PLAN_MAX_TOKENS)
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
    # TASK-36: runs SECOND (after the entrypoint repair, while any module-count-dependent
    # conservatism above has already had its say) so BOTH measured defects in one plan get
    # repaired — the datastore plan trips both "imports unknown" and (sometimes)
    # "entrypoint not listed". Additive-only; never touches a plan with no dangling local
    # imports.
    plan, dangling_import_note = _repair_plan_dangling_imports(plan)
    plan_repair = "; ".join(n for n in (plan_repair_note, dangling_import_note) if n)
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
    # #EXT-036-REQ-4 Start
    done = not unmet
    _beat("DONE" if done else "NOT-DONE")  # #EXT-040-REQ-3
    note = "DONE (all acceptance checks pass)" if done else "NOT DONE — unmet: " + ", ".join(unmet)
    if repairs:
        rounds = len({r["round"] for r in repairs})
        note += f" (after {rounds} repair round(s))"
    # #EXT-037-REQ-8 Start
    return _result(modules=built, shipped=True, done=done, plan=plan, unmet=unmet, note=note,
                    repairs=repairs, plan_repair=plan_repair, quality=quality)
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
         ``REPAIR_PROMPT``, TASK-4's per-module gate).
      3. ASSEMBLE the modified module(s) onto ``root``.
      4. REGRESSION GATE (the honesty core, mirrors TASK-5's ``_repair_system`` revert): the
         baseline-passing checks are re-run; if ANY of them now fails, the modified module(s)
         are REVERTED to their pre-modification content (disk + the returned dict) and
         ``applied`` is False. Non-degrading — a modification is only accepted when it does
         not break anything that used to work.
      5. Best-effort: a NEW-behavior checklist is derived from ``mod_sentence`` itself and run
         against the (accepted) modified system; ``new_behavior_ok`` reports whether it passed
         (advisory — ``applied`` never depends on it, since the model-authored new-behavior
         check could itself be wrong, and REQ-14 only REQUIRES existing behavior preserved).

    Returns ``{modules, applied, regressed: [names], new_behavior_ok, note}``. Uses
    ``harness.coding_loop.build_llm()`` when ``llm`` is None (mirrors ``build_system``); an
    injected ``llm`` (``.complete(LlmRequest) -> .text``) drives fully offline testing.

    ``runtime`` (EXT-037 REQ-11, Tenet 1): optional, same contract as ``build_system``'s own
    ``runtime`` -- threaded to every module write below (the current-system assembly, the
    modified-module assembly and its half-written revert, and the regression-gate revert).
    ``runtime=None`` (the default) is unchanged from before this parameter existed.
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
    if not targets:
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

    if not changed_names:
        return _modify_result(modules=modules, applied=False,
                               note="modification produced no syntactically valid change — no change made")

    # 3. ASSEMBLE the modified module(s).
    # #EXT-037-REQ-1 Start
    _assembly_error: "str | None" = None
    for name in changed_names:
        # #EXT-037-REQ-11 Start
        escape = _jailed_write(root, name, modules[name], runtime)
        # #EXT-037-REQ-11 End
        if escape is not None:
            _assembly_error = escape
            break
    if _assembly_error is not None:
        for name in changed_names:                # never leave a half-written system
            modules[name] = pre_mod[name]
            # #EXT-037-REQ-11 Start
            _jailed_write(root, name, pre_mod[name], runtime)
            # #EXT-037-REQ-11 End
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
        all_regressed = regressed + [n for n in import_regressed if n not in regressed]
        note = "modification regressed existing behavior — reverted: " + ", ".join(regressed) if regressed else \
            "modification reverted"
        if import_regressed:
            note += ("; " if regressed else " — ") + "import-broken: " + ", ".join(import_regressed)
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
    return _modify_result(modules=modules, applied=True, new_behavior_ok=new_behavior_ok, note=note)
# #EXT-036-REQ-14 End


# #EXT-036-REQ-13 Start
# TASK-13 (REQ-13): hard-tier ESCALATION core — run the default (primary) model first; only pay
# for the stronger fallback (measured: Qwen2.5-Coder-7B) when the primary actually failed to ship.
# OFFLINE, test-gated. Live CLI/Jetson wiring of a real `swap_fn` (e.g.
# `harness.collaborative_solve._http_swap(manager_url)`) is an explicit OUT-OF-SCOPE follow-up.

def _better_result(fallback: dict, primary: dict) -> dict:
    """Deterministic tie-break rule (REQ-13): prefer shipped over not-shipped, then done over
    not-done, then more built modules. The PRIMARY wins an exact tie — the fallback must be
    STRICTLY better to be worth the extra latency/cost it already paid. Never raises — a
    malformed dict is treated as the worst possible result."""
    def _score(r: dict) -> tuple:
        r = r if isinstance(r, dict) else {}
        return (
            1 if r.get("shipped") else 0,
            1 if r.get("done") else 0,
            len(r.get("modules") or {}),
        )
    return fallback if _score(fallback) > _score(primary) else primary


def build_system_escalating(spec: str, root: "str | Path", *, primary_llm, fallback_llm=None,
                             swap_fn=None, fallback_model_id: "str | None" = None,
                             primary_model_id: "str | None" = None,
                             runtime: "object | None" = None) -> dict:
    """ESCALATE-ONLY-ON-FAILURE wrapper around ``build_system`` (REQ-13). Runs the default
    (``primary_llm``) build first; if it ships, returns it AS-IS — ``fallback_llm``/``swap_fn``
    are NEVER invoked, so the common case pays no extra latency. Only when the primary FAILS to
    ship, and a ``fallback_llm`` is supplied, does it swap to the stronger fallback model (via
    ``swap_fn(fallback_model_id)`` when a ``swap_fn`` is given — the two-plane serving swap) and
    retry with ``build_system(spec, root, llm=fallback_llm)``, returning whichever result is
    BETTER by ``_better_result``'s deterministic rule (shipped > done > module count). Restores
    the primary model afterward (``swap_fn(primary_model_id)`` in a ``finally`` block) whenever a
    swap to the fallback was made and both ``swap_fn``/``primary_model_id`` are available.

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
    if primary_result.get("shipped"):
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
