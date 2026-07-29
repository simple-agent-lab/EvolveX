# GEPA Terminal-Bench Full

Runs the established MiniSWE/Codex/Responses-bridge GEPA configuration for ten
generations against the fixed Terminal-Bench 2 split with 50 train, 19 gate,
and 20 sealed tasks.

Each generation rolls out and validates on all 50 train tasks with concurrency
10, then evaluates an improving candidate on all 19 gate tasks. The final
anchor evaluates the selected candidate on all 20 sealed tasks. The reflective
dataset retains up to 10 representative cases for the GEPA proposer, matching
the previously exercised configuration. Gate data is not exposed to the
meta-agent. Both the parent rollout and same-minibatch child validation retain
infrastructure-owned or incomplete cases as zero-reward, auditable evidence;
neither stage launches an outer repair batch.

Supply the local MiniSWE seed and Terminal-Bench dataset with `evolve init`.
