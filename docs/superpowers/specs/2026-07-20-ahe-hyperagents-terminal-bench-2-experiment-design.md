# AHE and HyperAgents on Terminal-Bench 2.0

## Purpose

Run two independent experiments that test whether this repository provides
reasonably faithful, usable implementations of AHE and HyperAgents on
Terminal-Bench 2.0.

These experiments are not a head-to-head competition between AHE and
HyperAgents. Each implementation is judged against the lifecycle and design of
its own official repository. Separate collaborators are responsible for running
the official repositories, so this project does not reproduce those baselines.

The experiment may report each method's learning curve, reliability, cost, and
mutations. It must not rank AHE against HyperAgents because their rollout counts,
evaluation multiplicities, mutation surfaces, and search procedures differ.

## Shared Environment

- Benchmark: the official 89-task `terminal-bench@2.0` dataset.
- Dataset source revision for the initial run:
  `laude-institute/terminal-bench-2` commit
  `2fd12b88aafdd04a52c298e3940bcb189f9766d6`.
- DevBoxS already contains all 89 matching task images under
  `alexgshaw/<task>:20251031`. Runs must reuse these local images rather than
  rebuilding or repulling them. The pinned dataset definitions, tests, and
  verifiers still need to be present on the server because images alone do not
  define the benchmark.
- Execution engine: Harbor with Docker environments.
- Target agent: the same initial MiniSWE source snapshot for both experiments.
  The resolved source commit must be recorded in each experiment workspace.
- Task and meta-agent model condition: GPT-5.4 through the configured OpenAI
  endpoint. The exact resolved model string must be recorded, but a permanent
  repository-level model pin is not required.
- Concurrency: four Harbor task workers per experiment. When both experiments
  run concurrently, the expected maximum is eight task workers, excluding
  debugger and meta-agent calls.
- Each experiment gets a unique, committed experiment ID and an independent
  workspace. They may share a read-only dependency/download cache.
- The evaluator, benchmark tasks, credentials, endpoints, and resource limits
  are protected from model-generated changes.

"Full benchmark" means that every evaluated candidate runs all 89 tasks. It is
independent of the number of evolution generations.

## AHE Experiment

### Fidelity target

Follow the official AHE `evaluate -> analyze -> improve` lifecycle:

1. Evaluate the current harness on all 89 Terminal-Bench 2.0 tasks with `k=2`.
2. Preserve both rollouts and their raw trajectories for every task.
3. Run Agent Debugger analysis over those same evaluation trajectories.
4. Give the debugger reports, raw evidence, history, and previous change
   attribution to the AHE evolve agent.
5. Produce one coherent target-harness mutation.
6. Evaluate that new harness at the start of the next iteration.

There must not be a separate train rollout followed by a second candidate gate
evaluation. The evaluation that produces the score is also the source of the
debugger evidence. This avoids evaluating the benchmark twice per iteration and
matches the official AHE ordering.

### Configuration

- Initial evaluated snapshot: generation 0.
- Evolved candidates: generations 1 through 10.
- Total evaluated snapshots: 11, including generation 0.
- Tasks per evaluated snapshot: 89.
- Rollouts per task: `k=2`.
- Expected benchmark trials per snapshot: 178.
- Expected benchmark trials for a complete run: 1,958, before infrastructure
  retries.
- Parent policy: continue from the latest valid generation.
- Mutation surface: `target/**` only.
- Meta-agent changes: one coherent mutation per generation.
- Meta-agent retry policy: two retries after the first attempt.
- Debugger retry policy: three attempts per task analysis.
- No train, gate, or sealed task split. Structural candidate validation remains.
- No separate final anchor evaluation.

The official-style change manifest remains intentionally lightweight. Strict
validation of the official AHE schema is out of scope, but every accepted change
must connect failure evidence, root cause, the targeted component, predicted
fixes, and regression risks.

Because the same full benchmark drives improvement and reports the learning
curve, this experiment measures optimization on Terminal-Bench 2.0. It does not
by itself demonstrate held-out generalization.

## HyperAgents Experiment

### Fidelity target

Follow the official HyperAgents archive-and-child lifecycle:

1. Select a valid parent from the archive using `score_child_prop`.
2. Give the meta-agent the editable repository plus prior agents and evaluation
   results.
3. Let the meta-agent modify the task agent and its self-improvement machinery.
4. Validate that the returned repository is installable and respects the
   protected benchmark boundary.
5. Immediately evaluate the produced child on all 89 Terminal-Bench 2.0 tasks.
6. Add a successfully evaluated child to the archive and repeat parent
   selection.

Unlike AHE, HyperAgents retains immediate child evaluation. It must not be
forced into AHE's delayed `evaluate -> analyze -> improve` lifecycle.

### Configuration

- Initial evaluated snapshot: generation 0.
- Evolved candidates: generations 1 through 10.
- Total evaluated snapshots: 11, including generation 0.
- Tasks per evaluated snapshot: 89.
- Rollouts per task: `k=1`.
- Expected benchmark trials per snapshot: 89.
- Expected benchmark trials for a complete run: 979, before infrastructure
  retries.
- Parent selection: `score_child_prop`, matching the official default.
- Mutation surface: `target/**` and `operators/**`.
- The prompt strongly prefers a substantive `target/**` improvement, based on
  earlier experimental evidence, but permits a justified operator-only change.
- Meta-agent retry policy: two retries after the first attempt.
- No train, gate, or sealed task split. Structural candidate validation remains.
- No separate final anchor evaluation.
- Skip the optional official staged evaluation. Every installable candidate is
  evaluated directly on the full 89-task benchmark.

The official HyperAgents repository does not provide a Terminal-Bench 2.0
domain. This experiment therefore adapts its search lifecycle to Terminal-Bench
while preserving the official archive, self-reference, immediate evaluation,
and parent-selection behavior. It is a protocol-faithful adaptation, not an
exact reproduction of an official HyperAgents Terminal-Bench result.

## Workspace and Mutation Boundary

Both meta-agents receive a disposable writable repository at
`/app/task/workspace`. It contains the selected parent, self-contained Git
history, configuration, archive, prior run artifacts, current evidence, and raw
traces.

The returned workspace is compared with a trusted pre-run snapshot. Only the
configured editable roots are installed back:

- AHE: `target/**`.
- HyperAgents: `target/**` and `operators/**`.

Changes to the evaluator, benchmark tasks, experiment configuration, runtime
evidence, archive, credentials, or Git metadata are discarded and reject the
proposal when they violate the declared surface. The host experiment workspace
is never directly mounted as the returned mutation source.

## Corrected Smoke Experiment

Before either full run, execute both methods on the same small collection of
unmodified tasks copied from the official dataset revision:

- `cancel-async-tasks`
- `largest-eigenval`
- `prove-plus-comm`
- `regex-log`

The task names, `task.toml`, environment definitions, instructions, tests, and
verifiers must remain unchanged. Do not create renamed `-train` or `-gate`
copies.

Smoke configuration:

- Four official tasks.
- Four workers per experiment.
- Generation 0 plus two evolved candidates.
- AHE: four tasks times `k=2`, or eight trials per evaluated snapshot.
- HyperAgents: four tasks times `k=1`, or four trials per evaluated snapshot.
- No task split, staged subset, or final anchor.
- Both experiments run concurrently after Docker capacity preflight.

Smoke success does not require a score improvement. It requires:

1. exact expected task and trial counts for every completed evaluation;
2. no renamed or duplicated benchmark tasks;
3. score and trace evidence produced by the same AHE evaluation;
4. successful AHE debugger reports and a trace-linked change manifest;
5. successful HyperAgents archive access, mutation, validation, immediate child
   evaluation, and parent selection;
6. protected-file and surface checks passing;
7. complete, internally consistent generation records and reports;
8. no unexplained infrastructure failures, orphaned processes, containers, or
   Docker networks after completion.

## Score Semantics

Generation 0 is the evaluated baseline. Generation N is the score of the
candidate stored at generation N, never the rollout score of its parent.

For a stopped or interrupted run:

- `latest completed score` is the score of the highest completed generation;
- `best score` is the highest score among completed, valid generations;
- an in-progress generation has no score and must not silently appear as zero;
- a final score is reported only when the configured terminal generation has a
  complete evaluation.

The previous readiness smoke contains completed generation-0 scores of 0.0 and
completed generation-1 scores of 0.5 for both methods. It was interrupted during
generation-2 rollouts and had no final anchor, so 0.0 was not its final score.

## Recorded Outputs

For every evaluated snapshot, retain:

- aggregate score and task-level trial vector;
- task-set identity and dataset source revision;
- candidate and parent commits;
- raw Harbor trajectories and verifier results;
- benchmark, agent, and infrastructure error counts;
- model usage, estimated cost, and wall-clock duration;
- mutation paths, accepted diff, validation outcome, and surface violations;
- AHE debugger reports and change attribution, when applicable;
- HyperAgents parent-selection and archive metadata, when applicable.

Reports for AHE and HyperAgents remain separate. A combined operational summary
may compare completion rate, infrastructure reliability, and total resource use,
but it must not present the methods as a controlled performance ranking.

## Launch Safeguards

Before a smoke or full launch:

1. verify the official dataset revision, exact task count, and presence of all
   89 expected `alexgshaw/<task>:20251031` images without pulling them;
2. verify the MiniSWE source commit and resolved model name;
3. commit the experiment configuration and unique experiment ID into generation
   0 so evaluation-cache identities cannot collide;
4. export credentials by sourcing the server-side environment file without
   printing secret values;
5. verify the meta-agent image and Harbor runtime;
6. verify Docker capacity and remove only confirmed stale experiment resources;
7. configure the shared UV cache mount;
8. confirm four task workers for each experiment;
9. launch under a persistent process supervisor and stop through the driver,
   rather than abruptly killing it;
10. monitor completed-trial counts, infrastructure errors, API retry rates,
    containers, networks, disk usage, and estimated cost.

The full experiments may start only after the corrected official-task smoke
satisfies every smoke success condition.

## Sources

- AHE official repository:
  <https://github.com/china-qijizhifeng/agentic-harness-engineering>
- AHE shared configuration:
  <https://github.com/china-qijizhifeng/agentic-harness-engineering/blob/main/configs/base.yaml>
- AHE GPT-5.4 configuration:
  <https://github.com/china-qijizhifeng/agentic-harness-engineering/blob/main/configs/experiments/exp-simple-code-gpt54.yaml>
- HyperAgents official repository:
  <https://github.com/facebookresearch/HyperAgents>
- Terminal-Bench 2.0 repository:
  <https://github.com/laude-institute/terminal-bench-2>
