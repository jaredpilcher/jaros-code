# Design — Real-systems capability suite

`harness/real_systems_suite.py` defines a small set of `RealSystemTask`s (real systems from a sentence),
each pinned to ONE of the landed independent oracles, and a runner that builds each task via
`build_system` with the leaf path OFF and grades ONLY by that task's black-box oracle.

```text
   real_systems_suite.py
     RealSystemTask{ name, cls, sentence, oracle_kind, oracle_spec }
     run_real_systems_suite(tasks, llm) -- per-task pass@1, leaves-OFF asserted
        |
        +-- oracle_kind='fs'   -> harness/fs_oracle.py (seed tree -> run -> independent byte-compare)
        +-- oracle_kind='import' -> harness/import_driver.py (import built module, injected clock)
        +-- oracle_kind='cli-exact' -> exact-stdout/rc check variants (harness/system_suite.py)
```

Guardrails (Tenet 3), enforced in the runner: assert no leaf fingerprint fires for these specs
(`leaf_for_spec` disabled / classifier asserted False); grade only by the task's own oracle output
(never the model's self-acceptance, never a reference implementation); every expected value derives from
the visible sentence; pass@1, frozen held-out. A green earned by a template is a Tenet-3 violation.
