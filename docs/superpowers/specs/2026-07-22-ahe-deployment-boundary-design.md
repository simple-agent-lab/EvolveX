# AHE Deployment-Boundary Design

## Goal

Prevent the AHE meta-agent from copying evolution-only workflow instructions into the candidate MiniSWE runtime prompt while preserving the official AHE strategy, editable target surface, and framework contracts.

## Evidence and root cause

The `ahe-v23` smoke completed successfully but rewrote `target/src/minisweagent/config/mini.yaml` with instructions to read debugger reports, `change_evaluation.json`, and the previous change manifest. Those artifacts exist in the evolution workspace for the meta-agent, not in a benchmark episode for the candidate MiniSWE agent.

The generated wording closely mirrored `AHE_PROMPT` in `library/meta_agent/ahe.py`. The prompt explains what the evolution agent should do but does not explicitly distinguish that workflow from content suitable for a deployed target prompt. The model therefore treated the meta workflow itself as a candidate prompt improvement.

## Design

Add one deployment-boundary paragraph to the recipe-local `AHE_PROMPT`:

- Files under `target/` become the deployed benchmark-solving harness.
- The deployed harness cannot rely on evolution-only debugger reports, manifests, archive records, evidence paths, or KEEP/REVISE/ROLLBACK decisions.
- When editing a target runtime prompt, write only instructions that are usable inside a benchmark episode.
- Do not copy the AHE meta workflow or manifest requirement into target files.

Keep the instruction general rather than naming `mini.yaml`, so it applies equally to future target prompt files without restricting AHE's choice of component.

## Rejected alternatives

1. Scan generated patches for particular phrases and reject them. This would be brittle, easy to evade, and would add a new validation policy for a problem better prevented at the instruction boundary.
2. Exclude `mini.yaml` or all prompt files from the editable surface. This would prevent legitimate prompt engineering and diverge from AHE.
3. Change gate or selection policy. The observed problem occurs before evaluation and is independent of AHE's faithful newest-generation policy.

## Testing

Extend the existing AHE prompt-contract test first. It must fail until the prompt explicitly communicates:

- the separation between evolution context and deployed benchmark context; and
- the prohibition on copying evolution workflow or manifest instructions into target runtime prompts.

Then run the focused AHE meta-agent tests, the full local test suite, Ruff, and `git diff --check`.

## Remote acceptance

Initialize a clean four-task, four-worker AHE smoke on DevBoxS using the existing OpenAI and managed-runtime configuration. Inspect the generated patch and manifest. The smoke is acceptable when:

- all lifecycle stages and archive integrity checks succeed;
- the candidate edit stays inside `target/**`;
- any target runtime prompt edit contains only benchmark-episode-usable instructions and does not reference evolution-only artifacts or workflow; and
- rollout, analyzer, evaluation, record, and sealed-anchor artifacts are complete.

If the corrected AHE smoke is acceptable, launch the full AHE and HyperAgents experiments with their existing faithful recipe policies and remote runtime configuration.

## Non-goals

- No framework changes.
- No patch-content validator.
- No gate, selection, budget, model, task split, or evaluator changes.
- No attempt to guarantee that a stochastic meta-agent proposal improves benchmark score in a four-task smoke.
