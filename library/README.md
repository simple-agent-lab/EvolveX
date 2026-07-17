# library/ — the reference operator catalog

A curated, framework-versioned pool of operator implementations to **consult and
adapt**, one folder per verb. This is reference material, not the runtime: it is
**not** copied wholesale into a workspace, and nothing here is executed as-is.

See `DESIGN.md` §7 for the full rationale. In short:

- The meta-agent reads `library/<verb>/*.py`, then adapts a variant
  **into** the workspace's active `operators/<verb>.py`. Only that adapted-in,
  committed copy ever runs — so meta_eval replay and the self-reference gate
  always act on in-tree code, and the catalog needs no freeze, digest, or gate.
- It is surfaced to the meta-agent through the workspace skill and operator prompts,
  not vendored in — fat skills, thin workspace.
- It is also the **harvest sink**: operators that evolve well in real runs get
  promoted back here, closing `framework seeds → workspace evolves → good
  variants flow back` (M8).

## Layout

```
library/
├─ select/   greedy · newest · random · score_weighted
├─ rollout/  failure_focused · harbor · noop
├─ trace_analyzer/ failure_patterns · failed_traces · trace_browser · execution_records · utility_metrics
├─ meta_agent/ hyperagents
│  ├─ support/  shared evidence loading
│  └─ runners/ local · harbor
├─ validate/ hyperagents
├─ gate/     hillclimb · parent_eligible
├─ record/   jsonl · hyperagents
└─ _skeletons/   "write a new operator of verb X" starting points   (planned move)
```

## Canonical verb set

Required: `select · rollout · meta_agent · gate · record`. Optional:
`trace_analyzer · validate · novelty · reflect`.
The authority is `src/evolve/frozen/interfaces.py`.

## Harbor rollout

`rollout/harbor.py` is an opt-in live variant. It runs the current candidate
through the frozen Harbor train split and normalizes results into
`rollout/cases.json`. A separate `trace_analyzer` operator chooses and renders
bounded meta-agent evidence under `trace_analyzer/evidence/`.

Select it in a recipe before `evolve init`:

```yaml
operators:
  rollout: {variant: harbor, path: /path/to/train-tasks, budget_tasks: 8, n_concurrent: 2}
```

The train `path` is required in config or through `EVOLVE_HARBOR_ROLLOUT_TASKS`.
Optional keys are `agent`, `model`, `include_task_name`, `jobs_dir`,
`field_limit`, and `pass_threshold` (default `1.0`). The custom checkout agent
defaults to `evaluator/eval.env`; `EVOLVE_HARBOR_MODEL` and
`EVOLVE_ROLLOUT_JOBS_DIR` are additional environment overrides.

The rollout path is intentionally not inherited from `EVOLVE_HARBOR_TASKS`:
verifier output is meta-agent feedback and may reveal tests. Set `path` or
`EVOLVE_HARBOR_ROLLOUT_TASKS` to a train-only task set, never the gate or sealed
set used for final evaluation.

## Meta-agent execution

Meta-agent variants define the improvement strategy. `hyperagents.py` consumes
normalized rollout feedback and implements self-referential editing. Its
`runner` selects how the editing agent is executed.

`runners/local.py` executes a trusted host command. `runners/harbor.py` instead
transports configured repository trees as `/app/candidate` and transactionally
installs the validated artifact:

```yaml
operators:
  meta_agent:
    variant: hyperagents
    runner: harbor
    agent: mini-swe-agent
    model: openai/gpt-5.4
    environment: docker
    editable_roots: [target, operators]
    timeout_s: 3600
```

See [`META_AGENTS.md`](../META_AGENTS.md) for command examples, supported Harbor
agent identifiers, custom adapter configuration, and the artifact boundary.
