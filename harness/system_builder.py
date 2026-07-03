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
"""

from __future__ import annotations

import json
import os
import py_compile
import re
import tempfile
from pathlib import Path

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
        for imp in m.get("imports", []) or []:
            if imp not in names:
                d.append(f"{m.get('name')}: imports unknown '{imp}'")
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


def _derive_acceptance_checklist(spec: str, mods: list[dict], llm) -> list[dict]:
    """Executable acceptance CHECKLIST (REQ-2/REQ-7 probe logic), derived contract-first
    from the SPEC + the module API (not the built code). Guarded — returns [] on any
    model/parse failure (never a fabricated pass)."""
    try:
        raw = _call(llm, CHECKLIST_PROMPT.format(spec=spec, api=_module_api(mods)),
                    max_tokens=CHECKLIST_MAX_TOKENS)
    except Exception:
        return []
    checks = _extract_json(raw, "[", "]")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and c.get("code")]


def _run_check(root: Path, check: dict) -> bool:
    """RUN one acceptance check against the assembled system (the real Tenet-3 gate — not
    prose). Reuses ``harness.multi_file._run`` (timeout + tree-kill already handled there).
    A temp check-script name is used so it never collides with a planned module."""
    from harness.multi_file import _run as _run_cmd

    code = check.get("code", "")
    if not code:
        return False
    chk_path = root / "_s2s_acceptance_check.py"
    try:
        chk_path.write_text(code, encoding="utf-8", newline="\n")
        ok, _out = _run_cmd(str(root), "python _s2s_acceptance_check.py")
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
    check can be fed back to the model as repair feedback (REQ-5). Reuses the same
    execution path (``harness.multi_file._run``); never raises."""
    from harness.multi_file import _run as _run_cmd

    code = check.get("code", "")
    if not code:
        return False, "no check code"
    chk_path = root / "_s2s_acceptance_check.py"
    try:
        chk_path.write_text(code, encoding="utf-8", newline="\n")
        ok, out = _run_cmd(str(root), "python _s2s_acceptance_check.py")
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
                    unmet: list[str], llm, *, max_repair: int = MAX_SYSTEM_REPAIR_ROUNDS
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
    no further progress. Bounded, never raises."""
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
                        try:
                            (root / name).write_text(code, encoding="utf-8", newline="\n")
                            built[name] = code
                            record["applied"] = True
                            record["module"] = name
                        except OSError:
                            pass
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
                    try:
                        (root / name).write_text(prev_code, encoding="utf-8", newline="\n")
                    except OSError:
                        pass
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
            repairs=None) -> dict:
    return {"modules": modules or {}, "shipped": shipped, "done": done,
            "unmet": unmet or [], "plan": plan, "note": note, "repairs": repairs or []}


def build_system(spec: str, root: "str | Path", *, llm=None) -> dict:
    """PLAN -> topological BUILD (syntax-gated + repair) -> ASSEMBLE -> ACCEPTANCE.

    Returns ``{modules: {name: code}, shipped: bool, done: bool, unmet: [names], plan: {...}}``
    (plus a diagnostic ``note``). NEVER raises: any stage failure returns
    ``shipped``/``done`` False with a `note` explaining why. `done` requires the derived
    acceptance checklist to actually PASS (Tenet 3), not just parse.

    Uses ``harness.coding_loop.build_llm()`` when `llm` is None (mirrors the convention in
    ``harness.daily_driver._generate_tests``); an injected `llm` (any object exposing
    ``.complete(LlmRequest) -> .text``) drives fully offline testing.
    """
    root = Path(root)
    if llm is None:
        try:
            from harness.coding_loop import build_llm
            llm = build_llm()
        except Exception as exc:
            return _result(shipped=False, done=False, note=f"llm unavailable: {exc}")

    # 1. PLAN (REQ-1)
    try:
        raw = _call(llm, PLAN_PROMPT.format(spec=spec), max_tokens=PLAN_MAX_TOKENS)
    except Exception as exc:
        return _result(shipped=False, done=False, note=f"planning call failed: {exc}")
    plan = _extract_json(raw, "{", "}")
    if not isinstance(plan, dict):
        return _result(shipped=False, done=False, note="planner produced no parseable JSON plan")
    defects = validate_plan(plan)
    if defects:
        return _result(shipped=False, done=False, plan=plan,
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
            return _result(modules=built, shipped=False, done=False, plan=plan,
                            note=f"build failed for {name}: {exc}")
        if not ok:
            return _result(modules=built, shipped=False, done=False, plan=plan,
                            note=f"module {name} failed the syntax gate after {MAX_REPAIR_ATTEMPTS} repair attempt(s)")
        built[name] = code

    # 3. ASSEMBLE
    try:
        root.mkdir(parents=True, exist_ok=True)
        for name, code in built.items():
            (root / name).write_text(code, encoding="utf-8", newline="\n")
    except OSError as exc:
        return _result(modules=built, shipped=False, done=False, plan=plan, note=f"assembly failed: {exc}")

    # 4. ACCEPTANCE (REQ-2/REQ-7 probe logic) — the real DONE gate, not prose
    checks = _derive_acceptance_checklist(spec, mods, llm)
    if not checks:
        return _result(modules=built, shipped=True, done=False, plan=plan,
                        unmet=["no acceptance checklist derived"],
                        note="shipped, but no executable acceptance checklist could be derived")
    unmet = [c.get("name", "?") for c in checks if not _run_check(root, c)]
    # #EXT-036-REQ-4 End
    # #EXT-036-REQ-5 Start
    # 5. SYSTEM-LEVEL REPAIR (REQ-5): drive shipped -> DONE from the acceptance-check
    # feedback. Skipped entirely when already done (non-degrading, no wasted calls).
    repairs: list[dict] = []
    if unmet:
        built, unmet, repairs = _repair_system(spec, root, built, checks, unmet, llm)
    # #EXT-036-REQ-5 End
    # #EXT-036-REQ-4 Start
    done = not unmet
    note = "DONE (all acceptance checks pass)" if done else "NOT DONE — unmet: " + ", ".join(unmet)
    if repairs:
        rounds = len({r["round"] for r in repairs})
        note += f" (after {rounds} repair round(s))"
    return _result(modules=built, shipped=True, done=done, plan=plan, unmet=unmet, note=note, repairs=repairs)
# #EXT-036-REQ-4 End
