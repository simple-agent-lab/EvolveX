---
name: evolve-agent
description: "Run evidence-driven evolution of agents, prompts, skills, and agent harnesses. Use when asked to initialize or operate an evolution workspace, choose Hill Climb, A-Evolve, GEPA, AHE, or HyperAgents, invoke evolution operators directly, improve a candidate through repeated evaluation, analyze traces or lineage, recover interrupted evolution, or report an evidence-backed champion."
---

# Build an evidence chain

Treat evolution as an evidence chain:

```text
contract → baseline → evidence → hypothesis → candidate → evaluation → lineage
```

A higher score alone is insufficient. Link every candidate to the evidence that
motivated it, its exact snapshot, frozen evaluation, and lineage decision.

## 1. Establish the contract

Detect whether the current directory is an initialized evolution workspace.

- In a workspace, read `AGENTS.md`, `evolve.yaml`, `program.md`, then run
  `./evolve status .` and `./evolve verify .`.
- For a new experiment, identify the target, mutable surface, evaluator, data
  partitions, budget, and execution boundary before initialization.
- Read [the workspace contract](references/workspace-contract.md) before
  creating, operating, recovering, or interpreting a workspace. Its "Create a
  workspace" section gives the initialization and baseline-certification
  commands and the preconditions they enforce.

**Completion check:** Name the target, mutable surface, frozen evaluator (the
`evaluator/` contract that scores every candidate), data
partitions, candidate budget, and execution boundary. In an existing workspace,
also identify the current champion, next generation, and interrupted state.

## 2. Choose one method

The method is fixed when the workspace is created; inside an existing
workspace, follow the configured operators instead of re-choosing. For a new
experiment, GEPA is the default; choose Hill Climb when the experiment needs
the simplest attributable control. Match the method to the available evidence
and allowed mutable surface. Read only the selected method card; it maps the
method to shipped operator capabilities as well as explaining its scientific
boundary.

| Observable condition | Method | Read |
| --- | --- | --- |
| A minimal attributable control is enough | Hill Climb | [hill-climb.md](references/hill-climb.md) |
| Only behavioral traces should guide prompt or skill mutation | A-Evolve | [a-evolve.md](references/a-evolve.md) |
| The evaluator returns per-task results and the target splits into components | GEPA | [gepa.md](references/gepa.md) |
| Failures are execution-shaped and justify harness changes | AHE | [ahe.md](references/ahe.md) |
| The evolution process itself may also change | HyperAgents | [hyperagents.md](references/hyperagents.md) |

Read [scientific foundations](references/scientific-foundations.md) only when
defining or changing evaluator semantics, partitions, acceptance rules, or
research claims.

**Completion check:** State why the method matches both the evidence and the
declared mutable surface. If it does not, choose again before running anything.

## 3. Prefer capabilities over source

For agent-led evolution, start from the stable workspace interface:

```bash
./evolve operator list . --json
./evolve operator run . <stage> --genid <id> [stage arguments]
```

Treat `operator list --json` as the live authority for which stages are
configured and whether their access is `direct`, `driver`, or `finalize`.
Invoke configured direct operators, read their retained artifacts under
`runs/gen-<id>/`, and make the candidate change yourself.

Escalate progressively:

1. Tune one call with `--config` when the capability is right but its bounds are
   wrong.
2. Read `PROTOCOL.md`, operator guidance, or `operators/README.md` when an input
   or artifact is unclear.
3. Read the active `operators/<stage>.py` only to diagnose behavior or change
   the active evolution process.
4. Read `library/<stage>/` only to compare or adapt another implementation.

Do not read implementation source merely to invoke a working operator. Do not
edit `library/` and assume runtime behavior changed; active code lives under
`operators/`.

Use the configured driver when its mutation stage should own the edit and an
unattended run is desired:

```bash
./evolve run . --max-generations 1
```

Driver and agent-led paths share the same evaluation and lineage mechanism. Do
not run them concurrently or replace an existing driver with a custom loop.

**Completion check:** Choose exactly one control path for the next generation.
For agent-led evolution, name the configured direct operators and the artifacts
that will justify the edit; source inspection must have a concrete reason.

## 4. Close the loop

1. Establish and inspect the certified baseline.
2. Select a parent and retain the method's required evidence.
3. State one evidence-linked hypothesis and predicted effect.
4. Produce one candidate inside the declared mutable surface.
5. Run every configured admission check against the final candidate snapshot.
6. Evaluate and finalize through the workspace mechanism.
7. Verify lineage before beginning another generation.

**Completion check:** The candidate has an exact lineage identity; required
admission decisions and evaluator-stamped results exist; lineage verification
passes; accepted and rejected outcomes remain auditable.

## 5. Report only what the chain proves

Start from `./evolve report .`, which writes the experiment report and
research-claim checklist from stamped records. Around it, report the baseline,
champion, parent-child changes, accepted and rejected mutations, evaluation
scope, retained evidence, and limitations. Tie every quality claim to
evaluator-stamped artifacts from the run.

**Completion check:** Every score and champion identity is derivable from
trusted lineage records, and every generalization claim names its data
partition.

## Guard the chain

- Keep one evaluator and runtime identity within an experiment. Start a new
  experiment when the evaluator changes.
- Take scores and champion state only from mechanism-owned stamped records.
- Keep optimization, gate, and sealed task identities disjoint.
- Change only the declared mutable surface.
- Treat linked worktrees outside `runs/worktrees/` as user-owned. Report them;
  never remove or modify them without explicit authorization.
- Match the execution boundary to candidate trust.
- Keep credentials out of prompts, artifacts, and reports.
- Spend live evaluation budget only when the request authorizes execution.
