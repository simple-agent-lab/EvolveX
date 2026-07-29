# A-Evolve HLE Parity

Runs A-Evolve for ten generations on the fixed 249-task HLE parity set:
100 train tasks, 49 held-out gate tasks, and 100 final sealed tasks.

The target is MiniSWE using `gpt-5.4-2026-03-05` at high reasoning effort.
The behavior-only trajectory judge uses `gpt-5.4-mini-2026-03-17` through its
explicit judge endpoint. The Harbor-hosted Codex meta-agent uses `gpt-5.4` at
xhigh effort with the host's local `auth.json`; it does not inherit the judge
or target bridge endpoint. Gate and sealed task identities and trajectories
are hidden from the meta-agent.

Initialize with the local MiniSWE seed and generated HLE task directory. The
generated `evaluator/splits.json` must exactly match
`dataset/hle-parity-100-49-100/split.json`.
