# AHE

This is the live Harbor recipe for adversarial hardening on MiniSWE. It keeps
greedy parent choice and the stricter `parent_eligible` gate, but now edits the
seeded source agent through `agent_command` and scores it on
`swe-bench-lite`.

`target.harbor_agent: miniswe-source` binds the Harbor wrapper to the cloned source tree.
`meta_agent: {variant: agent_command, timeout_s: 3600}` resolves to [`library/meta_agent/agent_command.py`](../../library/meta_agent/agent_command.py).
`gate: {variant: parent_eligible}` resolves to [`library/gate/parent_eligible.py`](../../library/gate/parent_eligible.py).
