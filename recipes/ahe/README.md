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

`target.harbor_agent:MiniSweSourceAgent` remains the Harbor adapter and is
explicitly excluded from the mutable surface. Supply the source-agent command
with `EVOLVE_AGENT_COMMAND` (or the configured AHE meta-agent/debugger command)
before running this real recipe.
