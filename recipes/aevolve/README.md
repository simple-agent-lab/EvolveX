# A-Evolve

This recipe maps the default `AEvolveEngine` workspace-mutation pass from
`a-evolve` onto EvolveX's existing operator protocol.

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

| A-Evolve responsibility | EvolveX implementation |
| --- | --- |
| solve tasks and retain observations | Harbor rollout |
| behavior-only observation view | `analyze: trajectory_only` |
| infer likely outcomes | read-only per-task judge inside `analyze: trajectory_only` |
| group patterns and review drafts | `mutate: aevolve` |
| LLM with workspace shell access | Harbor mutate runner |
| mutate prompt and complete skill directories | `target/prompt.md`, `target/skills/**` |
| Git snapshots | generation tags |
| holdout validation | disjoint gate split plus strict hill-climb gate |

Differences from the A-Evolve reference implementation:

- the reference implementation's judge is hard-wired to a Bedrock model; this recipe
  invokes the configured mutation model through Harbor with the same
  behavior-only input and verdict schema;
- the solver cannot currently return newly proposed draft skills into
  `target/skills/_drafts/`; the mutate operator will review drafts if another process
  places them there;
- the built-in Codex target consumes its prompt and skills, but not
  `memory/*.jsonl` or custom `tools/`, so this recipe disables memory and tool
  evolution. A target adapter that loads those layers can enable both flags.

Prepare and run the shared pinned Terminal-Bench 2.0 dataset:

```bash
./scripts/setup_terminal_bench.sh aevolve
./scripts/run_recipe_demo.sh aevolve
```
