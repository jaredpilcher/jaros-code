"""EXT-036 REQ-18: TODO task creation + management (user-facing).

Claude-Code-style task tracking for the user's work: create/list/update tasks tied to the
current repo, plus a narrow model-proposed breakdown of a request into tracked steps. Mirrors
``harness/repo_memory.py``'s two-plane split and robustness style:

  - ``add_task`` / ``list_tasks`` / ``update_task``: deterministic file I/O, a per-repo store
    at ``<root>/.jaros/tasks.jsonl``. Guarded — never raise.
  - ``propose_tasks``: the ONE model judgment — decompose a plain-language request into 2-6
    concrete task strings. Deterministic fallback (guarded): any failure or unparseable output
    returns ``[]`` (never fabricate tasks).
"""

# #EXT-036-REQ-18 Start
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

TASKS_REL_PATH = Path(".jaros") / "tasks.jsonl"
MAX_TASKS = 500          # bound the store (cap tasks kept/read)
MAX_PROPOSED = 6         # cap proposed tasks (2-6 concrete steps)

STATUSES = ("pending", "in_progress", "done")


def _tasks_path(root: "str | Path" = ".") -> Path:
    return Path(root) / TASKS_REL_PATH


def _load_all(root: "str | Path" = ".") -> list[dict]:
    """All stored task records (oldest-first), unbounded (update/list need the full set to
    find-by-id). Deterministic; guarded — returns [] when the store is absent, empty, or
    corrupt (never raises)."""
    try:
        p = _tasks_path(root)
        if not p.is_file():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(rec, dict) and rec.get("id") and rec.get("text"):
                out.append(rec)
        return out
    except OSError:
        return []


def _write_all(records: "list[dict]", root: "str | Path" = ".") -> bool:
    try:
        p = _tasks_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return True
    except OSError:
        return False


def add_task(text: str, root: "str | Path" = ".", status: str = "pending") -> "dict | None":
    """Create a task in the per-repo store (``<root>/.jaros/tasks.jsonl``) and return it
    (with a stable ``id``). Deterministic file I/O; guarded — never raises. Returns None for
    an empty/blank task text or any I/O failure."""
    text = (text or "").strip()
    if not text:
        return None
    if status not in STATUSES:
        status = "pending"
    task = {"id": uuid.uuid4().hex[:8], "text": text, "status": status, "ts": time.time()}
    try:
        records = _load_all(root)
        records.append(task)
        records = records[-MAX_TASKS:]
        if not _write_all(records, root):
            return None
    except OSError:
        return None
    return task


def list_tasks(root: "str | Path" = ".", cap: int = MAX_TASKS) -> "list[dict]":
    """The stored tasks for `root`'s repo (oldest-first), bounded to the most recent `cap`
    entries. Deterministic; guarded — [] when the store is absent/empty/corrupt."""
    try:
        return _load_all(root)[-cap:]
    except Exception:
        return []


def update_task(task_id: str, root: "str | Path" = ".", *, status: "str | None" = None,
                 text: "str | None" = None) -> "dict | None":
    """Update the status and/or text of the task with `task_id` (pending/in_progress/done).
    Deterministic file I/O; guarded — never raises. Returns the updated task, or None when
    `task_id` isn't found, an invalid `status` is given, or the write fails."""
    task_id = (task_id or "").strip()
    if not task_id:
        return None
    if status is not None and status not in STATUSES:
        return None
    try:
        records = _load_all(root)
    except OSError:
        return None
    updated: "dict | None" = None
    for rec in records:
        if rec.get("id") == task_id:
            if status is not None:
                rec["status"] = status
            if text is not None:
                new_text = text.strip()
                if new_text:
                    rec["text"] = new_text
            rec["updated_ts"] = time.time()
            updated = rec
            break
    if updated is None:
        return None
    if not _write_all(records, root):
        return None
    return updated


def propose_tasks(request: str, llm=None) -> "list[str]":
    """Model-proposed breakdown (a NARROW judgment): decompose `request` into 2-6 concrete
    task strings. Deterministic parse/guard: the model must emit a JSON list; on any model
    failure or unparseable output this returns ``[]`` — it NEVER fabricates a breakdown from
    a guess or a partial parse."""
    request = (request or "").strip()
    if not request:
        return []
    try:
        if llm is None:
            from harness.coding_loop import build_llm
            llm = build_llm()
        from jaros.llm import LlmRequest
        prompt = (
            "Break the following request into 2-6 concrete, actionable TODO task steps. "
            "Respond with ONLY a JSON list of short task strings — no prose, no numbering, "
            "nothing else.\n\n"
            f"REQUEST: {request}\n\nJSON list of tasks:"
        )
        text = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 220})).text
    except Exception:
        return []
    try:
        m = re.search(r"\[.*\]", text or "", re.S)
        if not m:
            return []
        data = json.loads(m.group(0))
        if not isinstance(data, list):
            return []
        tasks = [str(t).strip() for t in data if str(t).strip()]
        return tasks[:MAX_PROPOSED]
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
# #EXT-036-REQ-18 End
