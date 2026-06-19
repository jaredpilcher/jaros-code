"""Read-only agent: ``disk-monitor``.

Proposes a `fs.disk_usage` decision for a path (default ``.``). Read-only —
reports free/used bytes via the `fs.disk_usage` tool.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision

NAME = "disk-monitor"


class DiskMonitorBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        path = context.get("path", ".") if isinstance(context, dict) else "."
        return [create_decision(
            id=f"disk-{uuid.uuid4().hex}",
            source=NAME,
            type="fs.disk_usage",
            payload={"path": path},
        )]


def build(llm) -> DiskMonitorBoundary:
    return DiskMonitorBoundary(llm)
