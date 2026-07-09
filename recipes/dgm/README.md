# DGM

This is the live Harbor recipe for archive-sampled Darwin/Godel style search on
MiniSWE. It keeps the population fan-out, score-weighted parent selection, and
parent-eligible gate while switching the meta-agent operator to `agent_command` and evaluation
to `swe-bench-lite`.

`children_per_gen: 4` preserves the small archive fan-out.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`select: {variant: score_weighted, seed: 0}` resolves to [`library/select/score_weighted.py`](../../library/select/score_weighted.py).
