# Intent

This spec exists to build capability the way PRIME-001 mandates under Tenets 1 and 2:
not from one large prompt or a bigger model, but from many small, single-purpose
Gemma 4 2B (`e2b`) reasoning boundaries, each making ONE narrow judgement and emitting only
inert `Decision` data that a deterministic EXT-001 tool executes. Every agent here —
propose one exact edit, propose one shell command, decide one search term, judge a test
run PASS or FAIL, edit a config file or a Dockerfile — has a tiny prompt and a tiny
output contract, which is precisely the regime where a 2B model is reliable. The agents
never escalate to a larger model and never touch the host; their only job is to decide,
and the tool plane acts. They are deliberately specialized rather than broad, because the
path to Opus-4.8 parity is a wide fleet of sharp specialists wired so each actually
fires, never a few generalists. This is the composition that closes the gap a single big
agent cannot.
