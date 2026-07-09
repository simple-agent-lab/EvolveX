# AutoResearch

This is the live Harbor recipe for agent-owned search on MiniSWE. It keeps
`mode: agent`, edits through `agent_command`, and evaluates the result on
`swe-bench-lite` instead of the old training-script stub path.

`surface.include: target/**` lets the meta-agent edit the live MiniSWE source tree
that Harbor installs from `target/`.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
