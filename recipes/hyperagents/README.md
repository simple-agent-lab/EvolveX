# HyperAgents

This is the live Harbor recipe for process-plus-agent evolution on MiniSWE. It
keeps the wider mutable surface and randomized parent choice while switching
mutation to `agent_command` and evaluation to Harbor on `swe-bench-lite`.

`surface.include` exposes both `target/**` and `operators/**`.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`mutate: {variant: agent_command, timeout_s: 3600}` resolves to [`library/mutate/agent_command.py`](../../library/mutate/agent_command.py).
`select: {variant: random, seed: 0}` resolves to [`library/select/random.py`](../../library/select/random.py).
