"""BEST-OF-K ORACLE LIFT (roadmap NOW: is best-of-k a generic reliability lever?).

The honest question: does best-of-k (k=5) lift the REAL accept-rate over a single build (k=1),
measured against the INDEPENDENT oracle (t.checks), across ALL creation classes — not just
datastore, and not on best-of-k's own self-derived acceptance?

Per task: build k=1 (single build_system) AND k=5 (build_system_best_of_k), then score BOTH
winners against the SAME oracle checklist (t.checks) with the same runner used by the suite.
best-of-k selects on its OWN derived checks; we score the assembled winner against the oracle
SEPARATELY — so a positive lift means self-acceptance genuinely correlates with real correctness
(no oracle leak: the oracle is never given to the builder or the selector).

gemma-only, $0, NO Jetson swap. Writes incrementally after each task so progress is observable.
Honest caveats recorded: single run per (task,k) — gemma build variance means per-task n=1 is an
anecdote; the AGGREGATE + per-tier rates are the signal. Never commits; temp dirs only.
"""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.system_suite import ALL_CREATION_TASKS, _run_single_check
from harness.system_builder import build_system, build_system_best_of_k
from harness.coding_loop import build_llm

OUT = Path(__file__).resolve().parents[1] / ".jaros-data" / "artifacts" / "bestofk_oracle_lift.json"
K = 5


def _oracle_accept(task, root, result):
    """Independently score `result`'s assembled system against the oracle checks (t.checks)."""
    plan = result.get("plan") if isinstance(result, dict) else None
    checks = task.checks or []
    if not checks:
        return 0, 0, False
    opass = sum(1 for c in checks if _run_single_check(c, root, plan, sys.executable))
    return opass, len(checks), (opass == len(checks))


def main():
    llm = build_llm()
    rows = []
    t_start = time.time()
    for i, t in enumerate(ALL_CREATION_TASKS):
        # k=1 single build
        d1 = Path(tempfile.mkdtemp(prefix="bok1_"))
        try:
            r1 = build_system(t.sentence, d1, llm=llm)
        except Exception as e:
            r1 = {"modules": {}, "done": False, "note": f"{type(e).__name__}: {e}"}
        p1, n1, acc1 = _oracle_accept(t, d1, r1)

        # k=K best-of-k (its own isolated temp dirs; assembles winner onto d5)
        d5 = Path(tempfile.mkdtemp(prefix="bok5_"))
        try:
            r5 = build_system_best_of_k(t.sentence, d5, llm=llm, k=K)
        except Exception as e:
            r5 = {"modules": {}, "done": False, "attempts_run": 0, "note": f"{type(e).__name__}: {e}"}
        p5, n5, acc5 = _oracle_accept(t, d5, r5)

        rows.append({
            "name": t.name, "tier": t.tier,
            "k1_oracle": f"{p1}/{n1}", "k1_accept": acc1, "k1_selfdone": bool(r1.get("done")),
            "k5_oracle": f"{p5}/{n5}", "k5_accept": acc5, "k5_selfdone": bool(r5.get("done")),
            "k5_attempts": r5.get("attempts_run"),
            "rescued": (acc5 and not acc1), "regressed": (acc1 and not acc5),
        })
        # incremental write so progress is observable mid-run
        n = len(rows)
        summ = {
            "k": K, "done_so_far": n, "n_total": len(ALL_CREATION_TASKS),
            "k1_accept": sum(1 for r in rows if r["k1_accept"]),
            "k5_accept": sum(1 for r in rows if r["k5_accept"]),
            "rescued": [r["name"] for r in rows if r["rescued"]],
            "regressed": [r["name"] for r in rows if r["regressed"]],
            "elapsed_s": round(time.time() - t_start, 1),
            "rows": rows,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(summ, indent=2), encoding="utf-8")
        print(f"[{n}/{len(ALL_CREATION_TASKS)}] {t.name:26} k1={r1.get('done')!s:5}({p1}/{n1}) "
              f"k5={r5.get('done')!s:5}({p5}/{n5}) att={r5.get('attempts_run')} "
              f"{'RESCUED' if rows[-1]['rescued'] else ('REGRESSED' if rows[-1]['regressed'] else '')}",
              flush=True)

    # final aggregate
    k1 = sum(1 for r in rows if r["k1_accept"])
    k5 = sum(1 for r in rows if r["k5_accept"])
    print(f"\n=== BEST-OF-{K} ORACLE LIFT ===")
    print(f"k=1 oracle-accept: {k1}/{len(rows)}  |  k={K} oracle-accept: {k5}/{len(rows)}  "
          f"| lift: {k5-k1:+d}")
    print("rescued (k1 fail -> k5 pass):", [r["name"] for r in rows if r["rescued"]])
    print("regressed (k1 pass -> k5 fail):", [r["name"] for r in rows if r["regressed"]])


if __name__ == "__main__":
    main()
