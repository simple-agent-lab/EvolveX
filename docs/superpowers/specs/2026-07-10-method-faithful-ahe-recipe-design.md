# Method-Faithful AHE Recipe Design

**Date:** 2026-07-10

**Status:** Approved for implementation

**Scope:** Add a framework-native implementation of Agentic Harness Engineering
(AHE) for evolving the vendored MiniSWE source agent with Harbor evaluations.

## Context

The existing `ahe` recipe is not a meaningful AHE implementation. It shares the
same greedy selection, rollout, meta-agent, prompt, evaluator, and mutable target
surface as hillclimb. Its only material difference is a permissive gate, and that
difference is neutralized by greedy best-score parent selection. The stopped AHE
run remains useful as a diagnostic artifact, but its results must not be reported
as an AHE reproduction.

The replacement should reproduce the methodological core of the original AHE
design while remaining a normal composition of this framework's operator
protocol. It must not add AHE-specific policy to the frozen driver.

## Goals

1. Implement a sequential `evaluate -> analyze -> attribute -> improve` AHE loop.
2. Use Harbor for every benchmark rollout and preserve task-level evidence.
3. Use MiniSWE through its Python source API for the evolved agent, debugger
   agents, and evolution agent. The `mini` CLI is not part of the execution path.
4. Give AHE its own named operators and prompts while retaining the shared
   operator interfaces.
5. Preserve an extensible YAML contract: five stable top-level sections and
   unrestricted nested configuration owned by the selected operators.
6. Evaluate 30 SWE-bench Pro training tasks during evolution with `k=2` and five
   concurrent Harbor workers. Keep 30 test tasks sealed from all evolution agents.
7. Validate the implementation with deterministic tests and a real two-task,
   two-iteration DevBoxS smoke run before starting another 30/30 experiment.

## Non-Goals

- Reimplement the closed portions of the official Agent Debugger exactly.
- Copy the official AHE orchestrator wholesale or bypass this framework's driver.
- Add AHE-specific branches to the core driver, evaluator API, or YAML schema.
- Turn AHE into score-gated hillclimbing.
- Enable best-of-N candidate evolution in the first implementation. It can be
  added later as operator-owned configuration.
- Modify or restart the currently running hillclimb experiment.

## Design Principles

### Neutral mechanism, explicit method

The framework owns execution order, subprocess isolation, archive integrity,
surface enforcement, git snapshots, and generic evaluation artifacts. Named AHE
operators own parent policy, debugger task selection, trace analysis, attribution,
prompting, rollback decisions, and AHE record fields.

### Observable and falsifiable changes

Every proposed edit must cite task-level evidence, state a root cause and targeted
fix, and predict both fixes and regressions. The next iteration compares those
predictions with task-level outcomes and gives the evolution agent an explicit
`KEEP`, `REVISE`, or `ROLLBACK + PIVOT` recommendation.

### Staggered evaluation

Generation `N` analyzes the evaluation of its selected parent, including the
manifest that produced that parent. It then edits a child whose evaluation is
recorded for generation `N+1` to analyze. This mirrors the original AHE loop
without adding a new driver phase.

## Configuration Contract

The only framework-defined top-level YAML sections remain:

```yaml
experiment:
target:
surface:
operators:
evaluator:
```

Unknown top-level sections are rejected. Nested mappings and lists under the five
known sections are unrestricted and must survive load, render, workspace
scaffolding, and operator delivery without loss or coercion.

Within an operator block, the mechanism interprets only universal routing and
runtime keys such as `variant`, `script`, and `timeout_s`. Every other value is
passed unchanged in `OperatorContext.config`; the selected operator decides what
it means. The mechanism must not know keys such as `controls`, `analyze`,
`rollback`, or `debugger`.

The current handwritten YAML subset parser cannot satisfy this contract. Replace
it with `yaml.safe_load`/`yaml.safe_dump` from PyYAML, preserving insertion order.
PyYAML becomes a runtime dependency of both the installed package and the
workspace console bootstrap. Loading must reject non-mapping documents, unknown
top-level sections, and non-mapping values for the five sections with clear
errors.

An illustrative AHE configuration is:

```yaml
experiment:
  id: ahe
  max_generations: 50
  children_per_gen: 1
  mode: driver
  seed: 0

target:
  seed: https://github.com/SWE-agent/mini-swe-agent.git
  harbor_agent: miniswe-source

surface:
  include:
    - target/**
  exclude:
    - target/harbor_agent.py

operators:
  select:
    variant: ahe_latest

  rollout:
    variant: ahe_trace_analysis
    debugger:
      workers: 5
      command: null
      attempts: 3
    controls:
      successful: 3
      rotation_seed: 0
    analyze:
      failures: true
      regressions: true
      timeouts: true
      predicted_risks: true

  meta_agent:
    variant: ahe_evidence_editor
    command: null
    prompt: library/meta_agent/prompts/ahe_evolve.md
    rollback:
      allow_partial: true
      pivot_after_revert: true

  gate:
    variant: ahe_artifact_valid

  record:
    variant: ahe_manifest

  timeout_s: 3600

evaluator:
  engine: harbor
  dataset: swebench-pro
  agent: target.harbor_agent:MiniSweSourceAgent
  sampling: static
  task_file: tasks/train-30.txt
  tasks_per_round: 30
  k: 2
  n_concurrent: 5
  partial_floor: 0.8
```

The concrete nested keys are defaults chosen by the AHE operators, not framework
schema. Users may remove them, replace them, or add arbitrary operator-owned
values without changing framework code.

## Library Layout

The method is an explicit composition of reusable variants:

```text
library/
├── select/ahe_latest.py
├── rollout/ahe_trace_analysis.py
├── rollout/prompts/ahe_debugger.md
├── rollout/prompts/ahe_debugger_overview.md
├── meta_agent/ahe_evidence_editor.py
├── meta_agent/prompts/ahe_evolve.md
├── gate/ahe_artifact_valid.py
└── record/ahe_manifest.py
```

`recipes/ahe/evolve.yaml` selects these variants and supplies defaults.
`recipes/ahe/README.md` documents the method and its relationship to the original
AHE paper and repository.

Operator assets require a generic vendoring convention. Workspace initialization
must recursively copy non-hidden library resources needed by selected variants,
preserving their path beneath `workspace/library/<kind>/`. Asset vendoring is not
AHE-specific and must reject symlinks or paths that escape the source directory.
The active operator reads its configured prompt path from the workspace.

## Generic Evaluation Artifacts

Every evaluator may emit these optional generic files in its persistent run
directory:

```text
runs/gen-N/eval/
├── task_vector.json
└── evaluation_artifacts.json
```

### `task_vector.json`

This is the compact, portable outcome record:

```json
{
  "schema_version": 1,
  "tasks": {
    "task-id": {
      "trials": [
        {"trial": 0, "status": "complete", "reward": 1.0},
        {"trial": 1, "status": "complete", "reward": 0.0}
      ]
    }
  }
}
```

Task IDs and trial numbers must be stable. Missing trials and infrastructure
failures remain explicit rather than being converted to zero reward.

### `evaluation_artifacts.json`

This file indexes the existing Harbor task/trial directories and available files,
including agent traces, agent logs, verifier output, rewards, results, and
exceptions. It references Harbor's retained artifacts instead of copying large
traces. Entries include a path, artifact kind, size, and content hash where
practical. The evaluator never embeds `.env`, API keys, proxy credentials, or
other secret-bearing environment data.

The archive row stores the compact task vector plus the artifact-index path and
hash. Generic framework code does not interpret task outcomes beyond validating
the artifact shape.

## AHE Iteration Flow

### 1. Select the current harness

`ahe_latest.py` selects the newest numerically ordered valid generation, not the
highest-scoring generation. Invalid, infrastructure-failed, operator-failed, and
no-proposal rows are skipped. This produces a sequential harness history in which
regressions remain observable long enough to be diagnosed and explicitly
reverted.

### 2. Build attribution and select debugger tasks

`ahe_trace_analysis.py` reads:

- the selected parent's task vector and artifact index;
- its parent's task vector, when available;
- the change manifest that produced the selected parent;
- prior AHE attribution and evolution history.

For `k=2`, task states are conservative:

- `pass`: both trials pass;
- `partial`: exactly one trial passes;
- `fail`: both completed trials fail;
- `unknown`: a required trial is missing or infrastructure-failed.

An improvement is a movement from `fail -> partial/pass` or `partial -> pass`. A
regression is the reverse. Unknown states are never counted as fixes or
regressions. A predicted fix is verified only when the task reaches `pass`; a risk
is realized when its state worsens.

The operator analyzes every failure, regression, agent timeout, and predicted-risk
task, plus three successful control tasks. Controls rotate deterministically from
the configured seed and generation number. `selection.json` records every chosen
task and reason so the analysis set is reproducible.

### 3. Run MiniSWE debugger agents

Up to five debugger workers run concurrently after Harbor evaluation has
finished. Each worker uses the MiniSWE Python source API through a configurable
source wrapper, never the `mini` CLI. Debugger agents have read-only access to
Harbor artifacts and write one report under:

```text
runs/gen-N/rollout/analysis/detail/<task-id>.md
```

The prompt is adapted from the open portions of official AHE. Reports identify
trace evidence, failure phase, root cause, successful contrast when available,
and candidate harness component. A final MiniSWE debugger pass reads the detail
reports and writes `analysis/overview.md` with cross-task patterns. This
aggregation runs after the five-worker per-task pool, so concurrency never exceeds
five.

### 4. Attribute the previous change

The rollout operator writes `attribution.json`. For each prior manifest entry it
records predicted fixes, verified fixes, still-failing predictions, predicted
risks, realized risks, unexpected regressions, and one verdict:

- `EFFECTIVE`
- `PARTIALLY_EFFECTIVE`
- `MIXED`
- `INEFFECTIVE`
- `HARMFUL`

The attribution is evidence for the evolution agent. The framework and gate do
not turn these verdicts into score-based acceptance decisions.

### 5. Evolve, revise, or roll back

`ahe_evidence_editor.py` launches one MiniSWE-source evolution agent. Its prompt is
adapted from the official AHE evolve prompt and includes:

- the current experiment config;
- analysis overview and selected detail reports;
- attribution of the previous manifest;
- evolution history and prior diffs;
- surface rules and immutable infrastructure paths;
- the required manifest schema.

The agent chooses `KEEP`, `REVISE`, or `ROLLBACK + PIVOT`. A rollback is an
explicit source edit in the child worktree, using prior generation tags as the
known-good reference. The agent may partially revert a multi-file change when the
manifest and attribution provide enough separation. It must then pivot to a
different component level or root-cause hypothesis rather than immediately
reapplying the same change.

The evolved surface is upstream MiniSWE source. `target/harbor_agent.py` is
excluded because it is framework integration glue, not part of the upstream
agent. Evaluator files, Harbor configuration, Docker configuration, `.env`, model
settings, and proxy settings remain immutable.

### 6. Validate the manifest before evaluation

The AHE meta-agent operator requires `change_manifest.json` before returning a
successful proposal. A manifest contains:

```json
{
  "schema_version": 1,
  "generation": 13,
  "parent": "12",
  "decision": "keep|revise|rollback_pivot",
  "changes": [
    {
      "id": "chg-1",
      "type": "new|improvement|rollback",
      "files": ["target/path.py"],
      "failure_evidence": [
        {"task_id": "task-id", "report": "analysis/detail/task-id.md"}
      ],
      "root_cause": "...",
      "targeted_fix": "...",
      "predicted_fixes": ["task-id"],
      "risk_tasks": ["other-task"],
      "component_level": "prompt|tool|model_adapter|environment|control_flow"
    }
  ],
  "validation": {
    "status": "passed",
    "commands": ["..."]
  }
}
```

Each changed file must appear in exactly one manifest entry, every evidence path
must exist under the current run directory, and every changed path must satisfy
the mutable-surface policy. Missing evidence, predictions, risk declaration,
validation, or changed-file coverage makes the operator fail before Harbor
evaluation. An empty `risk_tasks` list is valid but must be explicit.

### 7. Evaluate with Harbor

Harbor evaluates the proposed MiniSWE source on the 30 training tasks with `k=2`
and five concurrent workers. The evaluator writes aggregate score, task vector,
and artifact index. Evaluation and debugger phases are sequential, so each phase
may use five workers without exceeding five concurrent AHE calls in that phase.

### 8. Gate and record

`ahe_artifact_valid.py` validates that the evaluation is usable and that the AHE
manifest and generic artifacts match the candidate. It does not compare child and
parent aggregate scores. A structurally valid, evaluable candidate remains in the
sequential lineage even when it regresses, allowing the next iteration to
attribute and explicitly roll it back.

`ahe_manifest.py` records compact indexed fields in `archive.jsonl`: manifest path
and hash, decision, predicted fixes, risk tasks, attribution summary, analysis
paths, task vector, and artifact-index path/hash. Large reports remain in run
artifacts rather than the append-only ledger.

## Failure Semantics

- Missing task vector or Harbor artifact index: fail the analysis operator; do
  not propose a mutation.
- Individual debugger failure: retry according to operator-owned config, then
  record the task as unanalyzed. Continue only when at least one actionable
  report remains and all regression/risk tasks have either a report or an
  explicit failure record.
- Pure infrastructure exception: mark `unknown`; never count it as a capability
  regression or a zero reward.
- Agent timeout: treat as a real failure and analyze its partial trace.
- Incomplete `k=2`: preserve completed trials, mark missing trials, and exclude
  the task from reliable flip attribution.
- Malformed or missing manifest: record `operator_failed` before evaluation.
- No source change: record `no_proposal`.
- Rollback/revision that violates the surface or manifest: do not advance the
  lineage.
- Raw Harbor artifacts are read-only to debugger and evolution agents.
- Secrets and `.env` contents are never copied into prompts, reports, manifests,
  logs produced by the framework, or archive rows.

## Experiment Protocol

### Training

- Dataset: SWE-bench Pro
- Fixed training set: 30 cached, setup-valid tasks
- Per iteration: `k=2`, 60 Harbor trials
- Harbor concurrency: 5
- Debugger concurrency: 5, after evaluation
- Evolution agents: 1 per iteration
- Planned full run: 30-50 iterations after smoke validation

### Sealed test

The fixed 30-task test set is never exposed to debugger selection, analysis,
attribution, prompts, or evolution history. It is evaluated with Harbor at the
baseline and after evolution on the final and best observed training snapshots.
Test artifacts are stored separately and are not fed back into the evolution
workspace.

### Networking

Docker images, packages, and benchmark assets should be cached before the run.
Proxy configuration may be injected only into download/setup paths. LLM calls run
without proxy variables, and no proxy setting is embedded in target source or
recipe code.

## Verification Strategy

### Unit tests

1. Arbitrarily nested YAML round-trips unchanged through load, render, scaffold,
   and `OperatorContext.config`.
2. Unknown nested operator keys require no mechanism changes; unknown top-level
   sections fail clearly.
3. Generic artifact parsing converts fake Harbor jobs into stable task vectors
   and artifact indexes, including partial trials, timeouts, and infrastructure
   failures.
4. `ahe_latest` chooses the newest valid generation rather than the best score.
5. Debugger task selection is deterministic and includes required failure classes
   plus rotating controls.
6. Attribution classifies improvements, regressions, unknowns, and prediction
   outcomes correctly for `k=2`.
7. Manifest validation catches missing evidence, missing risk declaration,
   uncovered changed files, invalid paths, and surface violations.
8. AHE gate behavior is independent of aggregate score.

### Integration tests

Use fake Harbor artifacts and deterministic source-agent commands for a
two-iteration test:

1. Generation 1 proposes a manifest-backed change.
2. Its task vector contains a predicted miss and a regression.
3. Generation 2 receives a `HARMFUL` or `MIXED` attribution.
4. The meta-agent explicitly restores the affected source and records a
   `rollback_pivot` manifest.
5. The sequential selector advances by generation, not score.

Run the complete local framework suite after the focused tests.

### DevBoxS smoke test

Before another 30/30 experiment:

- use two cached SWE-bench Pro training tasks;
- run two AHE iterations with `k=2` and five configured workers;
- verify source-only MiniSWE execution for target, debugger, and evolution roles;
- verify generic task vectors, artifact indexes, detail reports, overview,
  attribution, manifests, tags, and archive fields;
- inspect API and Harbor concurrency;
- induce or fixture one falsified prediction so the rollback path is exercised;
- confirm no LLM call receives proxy variables.

Only after this smoke test passes should a fresh 30-train/30-test AHE experiment
be launched.

## Acceptance Criteria

The design is complete when:

1. AHE and hillclimb instantiate different named operator compositions and
   prompts.
2. The driver contains no AHE-specific control flow or config keys.
3. Five known YAML sections support unrestricted nested configuration.
4. Every Harbor evaluation can be traced from aggregate score to task/trial
   outcome and retained evidence.
5. Every AHE edit has a valid falsifiable manifest.
6. The next iteration attributes the previous edit and can explicitly roll it
   back or revise it.
7. AHE follows the newest valid sequential harness rather than the best score.
8. All local tests and the real DevBoxS smoke test pass.
9. The sealed 30-task test set remains absent from all evolution inputs.

## References

- AHE paper: <https://arxiv.org/abs/2604.25850>
- Official AHE repository:
  <https://github.com/china-qijizhifeng/agentic-harness-engineering>
- Harbor: <https://github.com/harbor-framework/harbor>
- MiniSWE agent: <https://github.com/SWE-agent/mini-swe-agent>
