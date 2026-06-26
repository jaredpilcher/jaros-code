"""Single-purpose agent ``code-writer`` (EXT-013 / REQ-1).

The THIRD grain of the behavioral solve: given the commit intent, the behavior spec
(Gherkin), and the parent source, implement/repair the function and emit an inert
``code.write_file`` Decision.  It does NOT write to the host directly; the Runtime
gates + executes (write_file tool) + hash-chain logs every write (Tenet 1 / Tenet 3).

The prompt reuses the exact logic from ``harness/commit_replay.g_code`` — the proved
held-out 6/37 result.  Generated code is piped through the parse-gated
``repair_indentation`` from ``body_completer_agent`` (the +12% syntax-repair, already
proven on HumanEval).  Repair fires ONLY when the output does not parse, so it never
re-generates correct logic — it only fixes indentation errors the 2B commonly makes.
"""
from __future__ import annotations

# #EXT-013-REQ-1 Start
import re
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "code-writer"

_PROMPT = (
    "Implement the Python function `{name}` to satisfy these behavior scenarios:\n{gherkin}\n\n"
    "{ctx}{cur}"
    "COMMIT INTENT: {intent}\n{fb}\n"
    "Output ONLY the complete `def {name}(...):` definition — valid Python, correct "
    "indentation, no markdown, no prose, no test code."
)


class CodeWriterBoundary:
    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = ctx.get("intent", "")
        name = ctx.get("func") or ctx.get("name", "")
        parent_src = ctx.get("current_src")
        module_ctx = ctx.get("context", "")
        gherkin = ctx.get("gherkin", "")
        feedback = ctx.get("feedback", "")
        code_path = ctx.get("code_path", f".jcode/{name}.py")

        cur = f"Current version:\n{parent_src}\n" if parent_src else ""
        ctx_block = f"Module context:\n{module_ctx}\n" if module_ctx else ""
        fb = (f"\nYour previous code FAILED its own tests:\n{feedback[:600]}\nFix the cause.\n"
              if feedback else "")

        params = {"temperature": 0.0, "max_tokens": 800}
        if "seed" in ctx:
            params["seed"] = ctx["seed"]

        reply = self._llm.complete(LlmRequest(
            prompt=_PROMPT.format(
                name=name, gherkin=gherkin, ctx=ctx_block, cur=cur,
                intent=intent, fb=fb),
            params=params)).text

        # Extract the def block (mirrors g_code extraction logic exactly)
        s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
        i = s.find(f"def {name}")
        code = s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")

        if not code:
            return [create_decision(
                id=f"cw-{uuid.uuid4().hex}", source=NAME, type="advance",
                payload={"events": ["start", "fail"],
                         "note": f"code-writer: no def {name}() produced"})]

        # Parse-gated syntax-repair (proven +12% on HumanEval — fires only when the
        # output doesn't parse, so it never re-generates correct logic)
        try:
            from .body_completer_agent import repair_indentation
            code = repair_indentation(self._llm, code,
                                      seed=ctx.get("seed", 0))
        except ImportError:
            # Fallback for direct-module execution (not inside a package)
            try:
                import importlib.util
                import os
                _dir = os.path.dirname(__file__)
                spec = importlib.util.spec_from_file_location(
                    "body_completer_agent",
                    os.path.join(_dir, "body_completer_agent.py"))
                _mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(_mod)  # type: ignore[union-attr]
                code = _mod.repair_indentation(self._llm, code,
                                               seed=ctx.get("seed", 0))
            except Exception:  # noqa: BLE001 — repair is best-effort, never block the solve
                pass
        except Exception:  # noqa: BLE001 — repair is best-effort, never block the solve
            pass

        return [create_decision(
            id=f"cw-{uuid.uuid4().hex}", source=NAME, type="code.write_file",
            payload={"path": code_path, "content": code,
                     "note": f"code-writer: implementation of {name}"})]


def build(llm) -> CodeWriterBoundary:
    return CodeWriterBoundary(llm)
# #EXT-013-REQ-1 End
