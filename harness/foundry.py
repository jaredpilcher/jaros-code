"""The Foundry — assemble + ship-gate loop (EXT-035 REQ-2).

Deterministic assemble+run+grade step that composes REQ-1's
`synthesize_cli` (harness/cli_wrapper.py) into a reusable capability. NO
model calls here — the model plane's lib source is passed in as a string —
so the ship-gate logic is fully offline-testable and the (flaky)
build_from_intent oracle can never sink a correct tool: the gate is on the
RUN, not on the build oracle.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.cli_wrapper import synthesize_cli

# #EXT-035-REQ-2 Start

FOUNDRY_ROOT = Path(".jaros-data/foundry")
SHIP_LOG = FOUNDRY_ROOT / "ship_log.jsonl"


@dataclass
class ShipResult:
    ship: bool
    cli_code: str
    cases: list = field(default_factory=list)
    project: str = "foundry"
    # #EXT-035-REQ-4 Start
    incomplete_modules: list = field(default_factory=list)
    # #EXT-035-REQ-4 End


def _sandbox_dir(project: str, work_dir: str | None) -> Path:
    if work_dir is not None:
        sandbox = Path(work_dir)
    else:
        sandbox = FOUNDRY_ROOT / f"{project}_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    for stale in sandbox.glob("*.py"):
        stale.unlink()
    return sandbox


def _append_ship_log(
    project: str,
    ship: bool,
    cases: list,
    # #EXT-035-REQ-4 Start
    incomplete_modules: list | None = None,
    # #EXT-035-REQ-4 End
) -> None:
    SHIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "project": project,
        "ship": ship,
        "cases": [{"argv": c["argv"], "ok": c["ok"]} for c in cases],
        # #EXT-035-REQ-4 Start
        "incomplete_modules": incomplete_modules or [],
        # #EXT-035-REQ-4 End
    }
    with open(SHIP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def assemble_and_ship(
    lib_code: str,
    module_name: str,
    entry_func: str,
    ship_cases: list,
    *,
    arg_mode: str = "ints",
    work_dir: str | None = None,
    project: str = "foundry",
    # #EXT-035-REQ-4 Start
    module_oracles: dict[str, bool] | None = None,
    # #EXT-035-REQ-4 End
) -> ShipResult:
    """Assemble `lib_code` + a synthesized CLI wrapper in a sandbox, RUN it on
    every `(argv, expected_stdout)` in `ship_cases`, and grade binary
    ship/no-ship by exact stdout match. Appends one line to the ship-log.

    `ship_cases` is a list of `(argv_list, expected_stdout)` tuples.
    """
    sandbox = _sandbox_dir(project, work_dir)

    module_path = sandbox / f"{module_name}.py"
    module_path.write_text(lib_code, encoding="utf-8")

    cli_code = synthesize_cli(str(module_path.resolve()), entry_func, arg_mode=arg_mode)
    cli_path = sandbox / "cli.py"
    cli_path.write_text(cli_code, encoding="utf-8")
    abs_cli_path = cli_path.resolve()

    cases: list[dict[str, Any]] = []
    for argv, expected in ship_cases:
        try:
            p = subprocess.run(
                [sys.executable, str(abs_cli_path), *argv],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(sandbox),
            )
            got = (p.stdout or "").strip()
        except Exception as exc:  # noqa: BLE001 - record any failure, never crash the gate
            got = repr(exc)
        ok = got == expected
        cases.append({"argv": argv, "expected": expected, "got": got, "ok": ok})

    ship = bool(cases) and all(c["ok"] for c in cases)

    # #EXT-035-REQ-4 Start
    incomplete = sorted(m for m, ok in (module_oracles or {}).items() if not ok)
    ship = ship and not incomplete

    _append_ship_log(project, ship, cases, incomplete)

    return ShipResult(
        ship=ship,
        cli_code=cli_code,
        cases=cases,
        project=project,
        incomplete_modules=incomplete,
    )
    # #EXT-035-REQ-4 End

# #EXT-035-REQ-2 End
