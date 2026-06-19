"""Read-only agent: ``text-metrics``.

Proposes a `text.count` decision to measure a text file (line/word/char counts).
Read-only — the `text.count` tool opens the file for reading only.
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision

NAME = "text-metrics"


class TextMetricsBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        path = context.get("path", "README.md") if isinstance(context, dict) else "README.md"
        return [create_decision(
            id=f"text-{uuid.uuid4().hex}",
            source=NAME,
            type="text.count",
            payload={"path": path},
        )]


def build(llm) -> TextMetricsBoundary:
    return TextMetricsBoundary(llm)
