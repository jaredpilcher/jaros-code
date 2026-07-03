"""EXT-036 REQ-16: per-repo long-term memory + memory-AGENT selective recall.

The measured small-model memory design (docs/GAP-MAP.md, ``.jaros-data/mem_experiment2.py``):
raw transcript context is fine IN-session, but a memory-agent's real value is CROSS-SESSION /
large-scale recall — and it must be PRECISE. Dumping every stored fact into the prompt is the
measured retrieval-negative regression (noisy context hurts the small model); a narrow agent
that SELECTS only the relevant few facts is what helps.

Two-plane split:
  - ``add_fact`` / ``load_facts``: deterministic file I/O, a per-repo store at
    ``<root>/.jaros/memory.jsonl``. Never raises.
  - ``select_relevant``: the ONE model judgment — given the current request and the stored
    facts, pick the subset directly relevant to it. Deterministic fallback (guarded): any
    failure or unparseable output returns ``[]`` (inject nothing), NEVER all facts.
"""

# #EXT-036-REQ-16 Start
from __future__ import annotations

import json
import re
import time
from pathlib import Path

MEM_REL_PATH = Path(".jaros") / "memory.jsonl"
MAX_FACTS = 200           # bound the store read (cap facts loaded)
MAX_SELECT_FACTS = 60     # cap facts offered to the selection prompt (small-model context)


def _mem_path(root: "str | Path" = ".") -> Path:
    return Path(root) / MEM_REL_PATH


def add_fact(text: str, root: "str | Path" = ".") -> bool:
    """Append a durable fact to the per-repo store (``<root>/.jaros/memory.jsonl``).
    Deterministic file I/O; guarded — never raises. Returns True on a successful append,
    False for an empty/blank fact or any I/O failure."""
    text = (text or "").strip()
    if not text:
        return False
    try:
        p = _mem_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text, "ts": time.time()}) + "\n")
        return True
    except OSError:
        return False


def load_facts(root: "str | Path" = ".", cap: int = MAX_FACTS) -> list[str]:
    """The stored facts for `root`'s repo (oldest-first), bounded to the most recent `cap`
    entries. Deterministic; guarded — returns [] when the store is absent, empty, or
    corrupt (never raises)."""
    try:
        p = _mem_path(root)
        if not p.is_file():
            return []
        out: list[str] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            text = rec.get("text") if isinstance(rec, dict) else None
            if text:
                out.append(text)
        return out[-cap:]
    except OSError:
        return []


def select_relevant(request: str, facts: "list[str]", llm=None) -> list[str]:
    """Memory-AGENT recall: a NARROW model judgment that picks the subset of `facts`
    directly relevant to `request` — mirrors the validated selection-prompt shape from
    ``.jaros-data/mem_experiment2.py`` (numbered facts -> comma-separated relevant numbers).

    Deterministic fallback (guarded): [] when there are no facts, the model call fails, or
    its output is unparseable / names no in-range fact. NEVER falls back to returning all
    facts — that is the exact regression this design guards against (a noisy dump hurts the
    small model more than it helps; see the retrieval-negative finding)."""
    usable = [f for f in (facts or []) if f][:MAX_SELECT_FACTS]
    if not usable:
        return []
    try:
        if llm is None:
            from harness.coding_loop import build_llm
            llm = build_llm()
        from jaros.llm import LlmRequest
        prompt = (
            "You are a MEMORY agent. Given a TASK and a numbered list of stored project "
            "facts, return ONLY the comma-separated NUMBERS of the facts DIRECTLY relevant "
            "to the task (usually 0-3; if none are relevant, return nothing). Nothing else.\n\n"
            f"TASK: {request}\n\nFACTS:\n"
            + "\n".join(f"{i}. {f}" for i, f in enumerate(usable))
            + "\n\nRelevant fact numbers:"
        )
        text = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 60})).text
    except Exception:
        return []
    try:
        picked = sorted({int(n) for n in re.findall(r"\d+", text or "") if 0 <= int(n) < len(usable)})
    except (ValueError, TypeError):
        return []
    return [usable[i] for i in picked]
# #EXT-036-REQ-16 End
