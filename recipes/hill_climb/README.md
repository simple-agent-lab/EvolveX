# Hill Climb

This is the live Harbor recipe for single-parent hill climbing on MiniSWE.
It edits the seeded source agent with `agent_command`, evaluates on
`swe-bench-lite`, and keeps children only when the hill-climb gate admits them.

`target.seed` points at `https://github.com/SWE-agent/mini-swe-agent.git`.
`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
