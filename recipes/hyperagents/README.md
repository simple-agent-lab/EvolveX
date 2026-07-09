# HyperAgents

This is the live Harbor recipe for process-plus-agent evolution on MiniSWE. It
keeps the wider mutable surface and randomized parent choice while switching
the meta-agent operator to `agent_command` and evaluation to Harbor on
`swe-bench-lite`.

`surface.include` exposes both `target/**` and `operators/**`.
`evaluator.agent: target.harbor_agent:MiniSweSourceAgent` is the real Harbor entrypoint.
`target/harbor_agent.py` binds the Harbor wrapper to the cloned MiniSWE source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`select: {variant: random, seed: 0}` resolves to [`library/select/random.py`](../../library/select/random.py).
Changes to `operators/meta_agent.py` affect later children forked from an accepted
generation; gate and record edits can affect the same generation because those
operators run after the candidate edit.
