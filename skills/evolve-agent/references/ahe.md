# Agentic Harness Engineering (AHE)

Use AHE when the mutable target is agent implementation, tool orchestration,
context construction, recovery behavior, or another executable part of the
agent harness.

## Use it when

- Retained executions support task-level failure attribution.
- The candidate must change code or structured configuration, not only a prompt.
- Debugger analyses can connect observed failures to concrete harness changes.
- The evaluator remains independent from the target implementation.

## Use the shipped capabilities

Run `./evolve operator list . --json` and use its live configuration. The
shipped AHE profile normally exposes `ahe_latest` selection,
`parent_evaluation` rollout, and the `ahe` analyze operator. Invoke these direct
operators, inspect the retained task trajectories and debugger findings under
`runs/gen-<id>/`, and let the outer coding agent implement the harness change.
The configured AHE `mutate` is optional for a second opinion or unattended
driver run.

Start by running the analyzer with a bounded `--config` override if cost or
latency matters. Read `operators/analyze.py` only when the analyzer's
artifacts are insufficient or its execution needs diagnosis. Read
`library/analyze/ahe.py` or `library/mutate/ahe.py` only when the
evolution process itself must be adapted; these references are not the active
runtime implementation.

## Apply the method

1. Establish a certified baseline execution set.
2. Analyze each retained trajectory with an explicit debugging pass.
3. Aggregate repeated failure modes without hiding contradictory cases.
4. Form a change hypothesis linking target edits to predicted effects.
5. Mutate only the declared harness surface.
6. Re-evaluate the exact candidate with the frozen evaluator contract.
7. Keep, revise, or roll back based on evidence, and retain regressions.

## Guard the claim

Treat change manifests and predicted effects as explanatory metadata, not
evaluation evidence. Pin the starting source and runtime contract, and size the
iteration count, concurrency, and timeout budget before the run.

## Completion check

The exact baseline trajectories, debugger findings, harness hypothesis, code
change, predicted effect, evaluator stamp, and lineage decision are linked.
Both successes and failures remain available for attribution.
