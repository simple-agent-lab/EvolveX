# AutoResearch

This is the live Harbor recipe for agent-owned search on MiniSWE. It keeps
`mode: agent`, mutates through `agent_command`, and evaluates the result on
`swe-bench-lite` instead of the old training-script stub path.

`surface.include: target/**` lets the mutator edit the live MiniSWE source tree
that Harbor installs from `target/`.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`mutate: {variant: agent_command, timeout_s: 3600}` resolves to [`library/mutate/agent_command.py`](../../library/mutate/agent_command.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
