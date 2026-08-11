---
name: evolve-agent
description: "Design, initialize, or operate an evolution workspace for agents, prompts, skills, and agent harnesses. Use when asked to turn requirements into an EvolveX recipe, choose or author reusable operators, deploy a frozen workspace, run generations, inspect lineage, recover state, or report an evidence-backed champion."
---

# Design and operate an evidence chain

Treat evolution as:

```text
requirements → contract → baseline → evidence → hypothesis
             → candidate → evaluation → lineage
```

## 1. Route from filesystem evidence

- **Initialized workspace:** read `AGENTS.md`, `evolve.yaml`, and `program.md`;
  run `./evolve status .`, `./evolve verify .`, and
  `./evolve operator active . --json`; then read
  [the workspace contract](references/workspace-contract.md).
- **EvolveX source checkout:** read
  [the decision protocol](references/decision-protocol.md) and
  [experiment design](references/experiment-design.md) before source work.
- **External target project:** treat it as the candidate, then use the same
  decision and experiment-design playbooks to locate a writable EvolveX source
  checkout. Do not clone or edit an installed package without approval.
- **Insufficient context:** ask one focused location question and do not guess.

State the evidence for the classification.

**Completion check:** Name the context, target, authoritative checkout or
workspace, and next playbook.

## 2. Design before implementation

Define target, mutable surface, evaluator, partitions, budget, execution
boundary, and proof required for acceptance. Evaluation precedes method
selection. For every material choice, present the options and use
[the decision protocol](references/decision-protocol.md).

Use [experiment design](references/experiment-design.md) for a new experiment.
Read [scientific foundations](references/scientific-foundations.md) when
measurement semantics or research claims change. Read only the method cards
whose evidence requirements fit the experiment:

| Observable condition | Method | Read |
| --- | --- | --- |
| A minimal attributable control is enough | Hill Climb | [hill-climb.md](references/hill-climb.md) |
| Behavioral traces or generated-artifact rubrics should guide prompt or skill mutation | A-Evolve | [a-evolve.md](references/a-evolve.md) |
| The evaluator returns per-task results and the target splits into components | GEPA | [gepa.md](references/gepa.md) |
| Failures are execution-shaped and justify harness changes | AHE | [ahe.md](references/ahe.md) |
| The evolution process itself may also change | HyperAgents | [hyperagents.md](references/hyperagents.md) |

End design with architecture approval bound to the recorded experiment brief.
Do not write source or deploy before approval.

**Completion check:** The recipe rationale names the evaluator-first contract,
selected composition, rejected alternatives, custom capability gaps, risks,
unknowns, and architecture approval.

## 3. Author and review source

Inspect capabilities through `uv run --frozen evolve operator list --json` and
`uv run --frozen evolve operator describe <stage>/<name> --json`. Configure an
existing operator when it fits. When the approved gap requires reusable code,
read [operator authoring](references/operator-authoring.md).

Run operator checks, focused tests, and
`uv run --frozen evolve recipe check <recipe-path> --json`. Present source
approval bound to the Git diff or commit and normalized check evidence.

**Completion check:** Every custom operator has a named catalog identity,
declarative config, focused behavior test, valid recipe binding, limitations,
and source approval.

## 4. Prepare and deploy

Read [deployment](references/deployment.md). Run read-only preflight, explain
remediation options, and obtain deployment approval before initialization.
Ask separately before live model or evaluation spend.

**Completion check:** The preflighted inputs match the initialized workspace,
provenance and integrity verify, and any baseline spend was authorized.

## 5. Operate the frozen experiment

Orient with `./evolve status .`, `./evolve verify .`, and
`./evolve operator active . --json`. Treat active bindings—not file
presence—as capability authority.

Choose exactly one control path for the next generation:

- Use `./evolve run . --max-generations 1` when the configured mutate stage
  should own the edit.
- Use `./evolve operator run . <stage> --genid <id>` and the mechanism-owned
  fork, commit, eval, and finalize transitions when the outer Agent owns the
  hypothesis and edit.

Do not run both paths for one generation. Tune a configured capability before
reading source; read active operator source only to diagnose or explicitly
change the running process.

**Completion check:** The chosen control path, parent, active direct stages,
retained evidence, mutable surface, and interrupted state are all explicit.

## 6. Close the loop

1. Establish and inspect the certified baseline.
2. Select a parent through the configured select stage.
3. Retain rollout and configured analysis evidence.
4. State one evidence-linked hypothesis and predicted effect.
5. Produce one candidate inside the declared mutable surface.
6. Run surface and every configured final-tree admission check.
7. Commit, evaluate, finalize, and verify through mechanism-owned transitions.

**Completion check:** The candidate has an exact lineage identity; admission
and evaluator-stamped results exist; verification passes; accepted and rejected
outcomes remain auditable; no child worktree is unaccounted for.

## 7. Report only what the chain proves

Start from `./evolve report .`. Report baseline, champion, parent-child change,
accepted and rejected mutations, evaluation partition, runtime identity,
retained evidence, and limitations. Resolve conflicts in favor of verified
evaluator-stamped lineage rather than generated summaries.

**Completion check:** Every score and champion identity derives from trusted
lineage, and every generalization claim names its partition and evidence.

## Guard the chain

- Keep one evaluator and runtime identity within an experiment.
- Keep optimization, gate, and sealed task identities disjoint.
- Change only the declared mutable surface.
- Match the execution boundary to candidate trust.
- Preserve linked worktrees outside `runs/worktrees/` unless their owner
  explicitly authorizes a change.
- Keep credentials out of prompts, artifacts, recipes, and reports.
- Spend live model or evaluation budget only when explicitly authorized.

## Historical-workspace note

Older initialized workspaces retain the mechanism, configuration, stage names,
and source frozen at creation time. Operate them through their vendored
`./evolve` and local skill; start a new workspace to use the current authoring
model.
