# A-Evolve

This recipe maps the default `AEvolveEngine` workspace-mutation pass from
`a-evolve` onto Evolve's existing operator protocol.

Each generation uses a fixed train split as the observation batch, retains
complete execution records, summarizes observations from the latest two cycles
(at most 30 cases), and asks an isolated Harbor editing agent to improve the
built-in Codex target's prompt and reusable skills. Drafts under
`target/skills/_drafts/` are included in the prompt and cleared after a
successful evolution pass, matching `AEvolveEngine`.

The mapping is:

| A-Evolve responsibility | Evolve implementation |
| --- | --- |
| solve tasks and retain observations | Harbor rollout |
| recent observation history | `runs/gen-*/rollout/cases.json` |
| build task summaries and review drafts | `meta_agent: aevolve` |
| LLM with workspace shell access | Harbor meta-agent runner |
| mutate prompt and skills | `target/prompt.md`, `target/skills/**` |
| Git snapshots | generation tags |
| holdout validation | disjoint gate split plus strict hill-climb gate |

The full SkillForge orchestration has two optional capabilities that this
recipe does not claim to reproduce:

- the solver cannot currently return newly proposed draft skills into
  `target/skills/_drafts/`; the meta-agent will review drafts if another process
  places them there;
- the built-in Codex target consumes its prompt and skills, but not
  `memory/*.jsonl` or custom `tools/`, so this recipe disables memory and tool
  evolution. A target adapter that loads those layers can enable both flags.

Initialize with a local Harbor dataset so the train/gate/sealed split can be
frozen:

```bash
evolve init /tmp/evolve-aevolve \
  --recipe aevolve \
  --dataset /absolute/path/to/harbor/tasks
```
