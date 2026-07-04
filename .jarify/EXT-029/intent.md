# Intent

This spec exists to test the cheapest form of multi-model collaboration on the hard
multi-step-repo class where both gemma-4-2b and qwen2.5-coder-3b independently fail (0/8
baseline): a one-shot DRAFT → CRITIQUE → REVISE loop across two complementary models — qwen's
stronger code structure paired with gemma's stronger intent reasoning — with the deterministic
test as the sole final judge. The hypothesis is that two models with decorrelated strengths may
together crack tasks neither can alone. It is the base-case proof-of-concept for the richer
multi-round debate explored separately (issue #33), and it is engineered for efficient Jetson
use by batching all model swaps at the loop level rather than per task.

It converges toward the Prime Directive by exercising the L6 routing/multi-model rung of the
escalation ladder — but honestly: the models only GENERATE, and the deterministic test gate
SELECTS the winner, never a model-as-judge (the same principle the directive fixes for the
router, since model-as-judge measured net-negative). It upholds Tenet 3 — the test is the sole
arbiter of `solved`, reported against the known 0/8 baseline — and Tenet 2, since every
reasoning call still runs on a local Jetson-fitting model at zero cost.
