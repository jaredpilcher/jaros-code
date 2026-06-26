# Intent

This spec exists to make the small model's inference deterministic and honest, serving
Tenets 2 and 3 of PRIME-001. The stock adapter samples at a high temperature, so the same
prompt yields different completions across runs — observed directly as a solvable task
failing intermittently purely from sampling variance. Greedy, seeded decoding stops adding
that avoidable noise, making the model both more reliable and byte-repeatable without
changing the model itself; the intelligence stays in the harness. Every reasoning call goes
only to a local engine — llama.cpp (intended: Gemma 4 2B (`e2b`) on the Jetson) or the
legacy Ollama path — with zero paid or cloud
inference, ever, and the backend is selected by configuration so the harness is local-only
but not engine-locked. Because Tenet 2 is a load-bearing claim and not a slogan, the client
counts and logs every real call to the local model (timestamp, model, latency, sizes),
giving undeniable, ongoing proof that the work is genuinely done by the local model —
never skipped, cached, or quietly served by something larger — regardless of which local
engine is in use.
