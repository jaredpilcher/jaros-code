"""Background job worker entrypoint (EXT-052 REQ-2): runs exactly ONE headless request detached
from the submitting CLI process, then records the job's completion.

Invoked as ``python -m harness.bg_worker <job_id>`` by ``harness.bg_jobs.submit_job`` -- never
invoked directly by a user.

Reuses the EXISTING EXT-043 one-shot path (``harness.cli._run_one_shot``) UNCHANGED as the unit of
work -- this is NOT a second execution mechanism, it is the exact same gated ``JcodeCli.handle()``
pipeline a foreground ``jcode "<request>"`` already runs, so any host-project write the job
performs still passes through the real ``code.write_file`` Decision exactly as before this spec
(Tenet 1, two-plane discipline preserved for backgrounded work). Wraps the call in
``harness.heartbeat.heartbeat`` (EXT-040) so a running background job is visible in `/status`'s
activity trail -- reusing the existing observability mechanism rather than inventing a new one.
"""
from __future__ import annotations

import sys

# #EXT-052-REQ-2 Start


def main(argv: "list[str]") -> int:
    if len(argv) < 1:
        print("usage: python -m harness.bg_worker <job_id>", file=sys.stderr)
        return 2
    job_id = argv[0]

    from harness import bg_jobs

    rec = bg_jobs.get_job(job_id)
    if rec is None:
        print(f"error: unknown job {job_id!r} -- no job record found", file=sys.stderr)
        return 1

    try:
        from harness.cli import _run_one_shot
        from harness.heartbeat import heartbeat as _heartbeat

        with _heartbeat("bg_job", run_id=job_id, detail=rec.request[:80]):
            text, code = _run_one_shot(rec.request, None, "text", None)
        print(text)
    except Exception as exc:  # a worker must record failure honestly, never crash silently
        print(f"error: background job {job_id} crashed: {exc}", file=sys.stderr)
        bg_jobs.mark_finished(job_id, exit_code=1)
        return 1

    bg_jobs.mark_finished(job_id, exit_code=code)
    return code
# #EXT-052-REQ-2 End


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
