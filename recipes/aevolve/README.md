# A-Evolve

This recipe maps the default `AEvolveEngine` workspace-mutation pass from
`a-evolve` onto Evolve's existing operator protocol.

Each generation uses a fixed train split as the observation batch and converts
Harbor's complete ordered events into A-Evolve's `trajectory_only` evidence:
behavioral signals plus a failure-focused trajectory compression. A separate
read-only Harbor judge estimates a score, category, outcome, and failure reason
for each compressed trajectory. Pass/fail labels, reward, verifier feedback,
task text, raw-case paths, and rollout history are omitted from both judge and
editing prompts. The isolated Harbor editing agent then uses those proxy
verdicts and behavior summaries to improve the built-in Codex target's prompt
and reusable skills. Drafts under
`target/skills/_drafts/` are included in the prompt and cleared after a
successful evolution pass, matching `AEvolveEngine`.

The mapping is:

| A-Evolve responsibility | Evolve implementation |
| --- | --- |
| solve tasks and retain observations | Harbor rollout |
| behavior-only observation view | `trace_analyzer: trajectory_only` |
| infer likely outcomes | read-only per-task judge inside `trace_analyzer: trajectory_only` |
| group patterns and review drafts | `meta_agent: aevolve` |
| LLM with workspace shell access | Harbor meta-agent runner |
| mutate prompt and skills | `target/prompt.md`, `target/skills/**` |
| Git snapshots | generation tags |
| holdout validation | disjoint gate split plus strict hill-climb gate |

The full SkillForge orchestration still has optional capabilities that this
recipe does not claim to reproduce:

- upstream's reference judge is hard-wired to a Bedrock model; this recipe
  invokes the configured meta-agent model through Harbor with the same
  behavior-only input and verdict schema;
- the solver cannot currently return newly proposed draft skills into
  `target/skills/_drafts/`; the meta-agent will review drafts if another process
  places them there;
- the built-in Codex target consumes its prompt and skills, but not
  `memory/*.jsonl` or custom `tools/`, so this recipe disables memory and tool
  evolution. A target adapter that loads those layers can enable both flags.

Initialize with a local Harbor dataset so the train/gate/sealed split can be
frozen:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-immutable-evaluator-image-digest"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"
evolve init /tmp/evolve-aevolve \
  --recipe aevolve \
  --dataset "$HARBOR_TASKS"
```
