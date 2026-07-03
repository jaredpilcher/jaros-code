"""EXT-036 TASK-4: productionize the sentence-to-system pipeline (REQ-1/REQ-3/REQ-4).

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


def _result(*, modules=None, shipped: bool, done: bool, unmet=None, plan=None, note: str = "") -> dict:
    return {"modules": modules or {}, "shipped": shipped, "done": done,
            "unmet": unmet or [], "plan": plan, "note": note}


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
    done = not unmet
    note = "DONE (all acceptance checks pass)" if done else "NOT DONE — unmet: " + ", ".join(unmet)
    return _result(modules=built, shipped=True, done=done, plan=plan, unmet=unmet, note=note)
# #EXT-036-REQ-4 End
