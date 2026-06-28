# Intent

Probe whether the 2B model has latent capability that the current pass@1 harness cannot extract — by sampling k independent code completions per task and scoring each against the hidden oracle. If pass@k >> pass@1, the bottleneck is SELECTION (verifier), not model capability, confirming the no-ceiling thesis and directing the next harness investment toward a selector.
