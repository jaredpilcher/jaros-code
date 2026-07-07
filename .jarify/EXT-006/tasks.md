# Implementation Tasks

### [TASK-1] Greedy, seeded Ollama client (legacy back-compat path)

An `LlmClient` implementation calls the local Ollama server with temperature 0 and a fixed
seed so a given prompt yields a stable, repeatable completion. This is the legacy path
(Ollama `gemma2:2b`); the intended path is Gemma 4 2B (`e2b`) via llama.cpp (TASK-4). It
uses only the local endpoint, never paid or cloud inference (Tenet 2).

#### Steps
1. Implement the `LlmClient` contract (`complete(LlmRequest) -> LlmResponse`) in
   `harness/ollama_client.py` (lines 38-103).
2. Send Ollama's `/api/generate` options with `temperature: 0` and a fixed `seed` by
   default so repeated calls with the same prompt are deterministic.
3. Select the model name from the `OLLAMA_MODEL` environment variable (default
   `gemma2:2b`), using only the Python standard library (no external HTTP dependency) for
   this legacy path.
4. Allow per-request overrides via `LlmRequest.params` (e.g. `temperature`, `seed`,
   `num_predict`) so callers can opt out of the defaults when needed.

#### Implements
- [REQ-1] Greedy, seeded Ollama client (legacy back-compat path)

### [TASK-2] Harness uses deterministic inference by default

The coding loop builds its LLM client through this module's factory so every reasoning
step defaults to greedy, repeatable inference without callers having to opt in explicitly.

#### Steps
1. Implement `harness.coding_loop.build_llm` (or the equivalent factory in
   `harness/ollama_client.py`) to return the deterministic client by default.
2. Verify the same prompt returns identical text across repeated calls under the default
   greedy configuration.
3. Raise a clear, surfaced error on a failed local-model call rather than failing silently
   or falling back to a different model.

#### Implements
- [REQ-2] Harness uses deterministic inference by default

### [TASK-3] Model-call telemetry (proof the local model is doing the work)

The client counts every real call to the local model and appends an audit line to a log
file, giving undeniable, ongoing proof that the work is done by the local model — not
skipped, cached, or silently swapped for a different model.

#### Steps
1. Increment a call counter and record the model name plus latency on each successful
   `complete` call in `harness/ollama_client.py`.
2. Append one line per call (timestamp, model, latency, request/response sizes) to
   `model_calls.log`, tailable in real time.
3. Record `modelCalls` (count, model, total latency) in the eval scorecard.
4. Surface the per-run call count and average latency for the local model in the report
   output.

#### Implements
- [REQ-3] Model-call telemetry (proof the local model is doing the work)

### [TASK-4] Pluggable local backend (Ollama or llama.cpp)

The reasoning client stays local-only but is not Ollama-locked: the backend is selected via
`JCODE_LLM_BACKEND`, so the same harness can run against local Ollama (`/api/generate`) or
a llama.cpp `llama-server` (OpenAI-compatible `/v1/chat/completions`), such as the Jetson
Orin Nano on the LAN — both zero-paid, local inference paths (Tenet 2).

#### Steps
1. Implement backend selection in `build_llm` keyed off `JCODE_LLM_BACKEND`
   (`llamacpp` as the default/intended backend; `ollama` retained for legacy back-compat).
2. Implement a llama.cpp client that posts to the OpenAI-compatible chat-completions
   endpoint greedily and seeded, parsing the reply and honoring per-request param overrides
   (`temperature`/`seed`/`num_predict` mapped to `max_tokens`).
3. Read `LLAMACPP_HOST` to select the server URL, and probe a `health()` endpoint before
   switching over to confirm the server is reachable.
4. Reuse the same model-call telemetry (TASK-3) for the llama.cpp path so the proof-of-
   local-work log is backend-independent.

#### Implements
- [REQ-4] Pluggable local backend (Ollama or llama.cpp)
