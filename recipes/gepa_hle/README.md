# GEPA HLE Parity

Runs GEPA for ten generations on the fixed 249-task HLE parity set:
100 train tasks, 49 held-out gate tasks, and 100 final sealed tasks.

The target is MiniSWE using `gpt-5.4-2026-03-05` at high reasoning effort.
The Harbor-hosted Codex proposer uses `gpt-5.4` at xhigh effort and validates
proposals on the same train minibatch before held-out gate selection. Gate and
sealed task identities and trajectories are hidden from the meta-agent.

Initialize with the local MiniSWE seed and generated HLE task directory. The
generated `evaluator/splits.json` must exactly match
`dataset/hle-parity-100-49-100/split.json`.
