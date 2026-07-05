# Implementation Tasks

### [TASK-1] Build JCODE.md discovery/load/injection + the `/init` generator

Build the deterministic `JCODE.md` instruction-memory hierarchy (project + user levels), wire its
auto-load into the orchestrator/planner context, and add the `/init` starter-file generator + CLI
command.

#### Steps
1. Create `harness/jcode_md.py`: `load_project_jcode_md(root=".")` reads `<root>/JCODE.md` bounded
   to a `MAX_CHARS` budget (mirror `harness/project_md.py`'s precedent), returns `""` on
   absent/unreadable, never raises. `load_user_jcode_md()` reads `~/.jcode/JCODE.md` (via
   `Path.home()`), same bounding/never-raise contract. `load_jcode_md(root=".")` combines both into
   one string with a `"PROJECT INSTRUCTIONS (JCODE.md)"` section (project content) and a
   `"USER INSTRUCTIONS (JCODE.md)"` section (user content), including only the sections that have
   content; returns `""` when both are empty.
2. In `harness/cli.py`, extend `_augment_with_history(text, history, project_md="", memory=None,
   jcode_md="")` with a new optional `jcode_md` parameter: when non-empty, prepend it as its own
   part BEFORE the existing `project_md` (JAROS.md)/`memory`/`history` parts, using the label
   already embedded in `load_jcode_md`'s combined string (no double-labeling). Update both call
   sites (`handle()`'s orchestrator branch and `_nl_fix`) to pass `getattr(self, "jcode_md", "")`.
   In `JcodeCli.__init__`, add `self.jcode_md = load_jcode_md(".")` (imported from
   `harness.jcode_md`), cached once per instance exactly like `self.project_md`.
3. In `harness/jcode_md.py`, add `init_jcode_md(root=".")`: build a starter Markdown document (an
   overview placeholder, a "## Structure" section populated from
   `harness.repo_map.build_repo_map(root)` when it returns non-empty content — falling back to a
   minimal generic template otherwise — and a "## How to run" section), then write it to
   `<root>/JCODE.md` through a root-jailed path (reuse the `_pathjail.path_jail` helper under
   `.jaros-data/tools/`, mirroring `harness/system_builder.py`'s `_jailed_write` pattern). If
   `<root>/JCODE.md` already exists, do NOT overwrite it — return a message noting this and make no
   write. Never raises (wrap `build_repo_map` and the write in `try`/`except`).
4. Add `cmd_init` to the `JcodeCli` class in `harness/cli.py`: imports and calls
   `harness.jcode_md.init_jcode_md(".")`, returning its result string. Add a `/init` line to the
   module docstring's command list (near `/remember`/`/memory`) so `/help` lists it. No new
   dispatch/registration table needed — the existing dynamic `cmd_<name>` routing picks it up.
5. Write `tests/test_ext042_jcode_md.py` covering: project-level load; user-level load (patch
   `Path.home()` or the module's home lookup); combined `load_jcode_md` labeling and section
   presence/absence; character bounding; never-raises on missing/malformed paths; the injected
   `"PROJECT INSTRUCTIONS (JCODE.md)"` block reaching a stubbed orchestrator's `decide()` context
   and the NL-fix instruction text (mirroring `tests/test_ext036_project_md.py`'s stubbing
   approach); absent-JCODE.md byte-identical-to-today regression check; `init_jcode_md` writes a
   non-empty file, does not clobber an existing one, and never raises; `/init` CLI wiring.

#### Implements
- [REQ-1] JCODE.md discovery + load (project + user levels)
- [REQ-2] Inject JCODE.md into the orchestrator/planner context
- [REQ-3] `/init` starter-file generator
- [REQ-4] `/init` CLI command

### [TASK-2] Route `/init` and `/remember` writes through a real Jaros Decision (Tenet 1)

Fix the Tenet-1 gap: `init_jcode_md` and `append_memory` write to the HOST project via raw
`Path.write_text`, bypassing the Jaros two-plane path. Thread an optional `runtime` through both
so a real CLI call routes the write through a `code.write_file` Decision (gate + EXT-037 root-jail
+ hash-chain log), mirroring the EXT-037 REQ-5 `_git_tool` root-anchored-Runtime pattern.

#### Steps
1. In `harness/jcode_md.py`, add `import uuid` and change `init_jcode_md(root=".")` to
   `init_jcode_md(root=".", runtime=None)`. When `runtime` is not `None`, build a
   `jaros.core.create_decision(id=f"init-jcode-md-{uuid.uuid4().hex}", source="jcode_md.init",
   type="code.write_file", payload={"path": resolved, "content": content, "root": root_str})`
   (reusing the already-computed `resolved = path_jail(root_str, "JCODE.md")` and `content`) and
   call `runtime.apply(decision)` inside a `try/except Exception` that degrades to
   `f"failed to write {resolved}: {exc}"` on any failure (gate rejection or otherwise) — never
   raises. When `runtime is None`, keep the existing direct `Path(resolved).write_text(...)` path
   unchanged.
2. In `harness/project_memory.py`, add the same optional `runtime=None` parameter to
   `append_memory(cwd, note, runtime=None)`. Compute the new full file content exactly as today,
   then: if `runtime` is given, build and apply a `code.write_file` Decision
   (`payload={"path": str(p), "content": new_content, "root": str(Path(cwd).resolve())}`) through
   it inside a `try/except Exception` returning `""` on failure; otherwise keep the existing direct
   `p.write_text(...)` path unchanged.
3. In `harness/cli.py`, add a small private helper `JcodeCli._write_runtime(self)` that builds and
   returns a root-anchored `harness.coding_loop.Runtime` — mirroring `_git_tool`'s construction
   (`root=os.path.abspath(".")`, `hooks_config=self.hooks_config`, `mode=self.mode`,
   `permission_rules=self.permission_rules`, `ask_callback=(self._ask_permission if
   self._interactive else None)`, plus the existing streaming `on_event` wiring) — returning `None`
   on any construction failure. Update `cmd_init` to call
   `init_jcode_md(".", runtime=self._write_runtime())` and `cmd_remember` to call
   `append_memory('.', arg, runtime=self._write_runtime())`, handling a falsy return from
   `append_memory` with an honest `"remember refused: ..."`-style message instead of the old
   unconditional `f"remembered -> {path}"`.
4. Extend `tests/test_ext042_jcode_md.py` (or add a new test module) proving: `init_jcode_md`
   called with a fake/real `runtime` builds and applies a `code.write_file` Decision (assert the
   fake runtime's `.apply()` was called with the right decision type/payload, or that a real
   `Runtime(data_dir=tmp_path, root=tmp_path)` actually wrote the file); a gate rejection (e.g. an
   escaping `path` fed directly to a real root-anchored `Runtime.apply`) degrades to an honest
   string, never raises; `runtime=None` still behaves exactly as before (existing tests
   untouched); `/init`'s CLI dispatch still writes `JCODE.md` end to end. Add the analogous
   coverage for `append_memory`/`cmd_remember` in `tests/test_ext009_specialists.py` or a
   dedicated new test file, whichever the existing `/remember` tests live in.

#### Implements
- [REQ-5] Route `/init` and `/remember` host-project writes through a real Jaros Decision (Tenet 1)
