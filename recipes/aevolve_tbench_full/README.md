# A-Evolve Terminal-Bench Full

Runs the established MiniSWE/Codex/Responses-bridge A-Evolve configuration for
ten generations against the fixed Terminal-Bench 2 split with 50 train, 19
gate, and 20 sealed tasks.

Each generation rolls out all 50 train tasks with concurrency 10 and evaluates
the candidate on all 19 gate tasks. The final anchor evaluates the selected
candidate on all 20 sealed tasks. Target rollouts use MiniSWE with
`gpt-5.4-2026-03-05` at high reasoning effort; the Harbor-hosted Codex
meta-agent uses `gpt-5.4` at xhigh effort. Gate data is not exposed to the
meta-agent. Infrastructure-owned or incomplete train cases are preserved in
the trajectory evidence without an outer repair batch, so the meta-agent can
judge whether a target-side change is appropriate.

Supply the local MiniSWE seed and Terminal-Bench dataset with `evolve init`.
