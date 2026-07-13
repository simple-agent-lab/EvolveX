# AHE

This is the live Harbor recipe for adversarial hardening on the MiniSWE source
agent. It evaluates the fixed 30-task training set from the SWE-bench Pro
registry with two trials per task and five concurrent Harbor workers.

The method is active in the operator routing: `ahe_latest` selects an eligible
parent, `ahe_trace_analysis` investigates verified training traces with at most
five debugger workers, `ahe_evidence_editor` proposes a source-only change,
`ahe_artifact_valid` admits only complete evidence, and `ahe_manifest` records
the compact AHE lineage. The configured prompt is
[`library/meta_agent/prompts/ahe_evolve.md`](../../library/meta_agent/prompts/ahe_evolve.md);
the debugger prompt assets live under
[`library/rollout/prompts/`](../../library/rollout/prompts/).

The four `operators.rollout.analyze` switches independently control failures,
regressions, timeouts, and predicted risks, and all default to enabled. Partial
`k=2` outcomes are failure-bearing. The nested `training` allowlist must match
the generic evaluator task-set stamp before retained evidence reaches a prompt.
The editor includes only selected current-run detail reports and bounds them with
the nested `evidence` limits. `rollback.allow_partial` controls whether a subset
may be reverted; `rollback.pivot_after_revert` requires a distinct non-rollback
pivot, which the manifest validator enforces for `rollback_pivot` decisions.

`target.harbor_agent:MiniSweSourceAgent` remains the Harbor adapter and is
explicitly excluded from the mutable surface. Supply the source-agent command
with `EVOLVE_AGENT_COMMAND` (or the configured AHE meta-agent/debugger command)
before running this real recipe.
