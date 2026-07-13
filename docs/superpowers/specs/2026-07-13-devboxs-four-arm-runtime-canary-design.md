# DevBoxS Four-Arm Runtime Canary Design

## Objective

Measure the runtime correctness and overhead of the shared framework-hardening
changes on DevBoxS. This is an evaluation-only canary, not an evolution-quality
experiment. It does not run meta-agents or claim that the unfinished
preflight/retry/process-ownership work is validated.

## Compared Arms

| Arm | Framework | Candidate source |
|---|---|---|
| `ahe-old` | method-faithful AHE `ab4fc2384fef473c598843b82b80eefa920d2cac` | AHE experiment `gen/0` target tree |
| `ahe-hardened` | framework-hardening `a785ee7` | exact copy of the `ahe-old` candidate source |
| `hyper-old` | method-faithful HyperAgents `7639e5c` | HyperAgents experiment `gen/0` target tree |
| `hyper-hardened` | framework-hardening `a785ee7` | exact copy of the `hyper-old` candidate source |

Old and hardened results are compared only within the same recipe. The AHE and
HyperAgents generation-zero target trees differ, so cross-recipe score or speed
comparisons are descriptive rather than causal.

## Workload

Each arm evaluates the same fixed five SWE-bench Pro training tasks with two
Harbor trials per task and two independent repetitions. Their outcomes in the
recorded AHE generation-zero evaluation are shown only to document the intended
mix:

| Task ID | Prior outcome |
|---|---|
| `instance_ansible__ansible-0ea40e09d1b35bcb69ff4d9cecf3d0defa4b36e8-v30a923fb5c164d6cd18280c02422f75e611e8fb2` | pass/pass |
| `instance_ansible__ansible-11c1777d56664b1acb56b387a1ad6aeadef1391d-v0f01c69f1e2528b935359cfe578530722bca2c59` | fail/fail |
| `instance_flipt-io__flipt-05d7234fa582df632f70a7cd10194d61bd7043b9` | fail/pass |
| `instance_future-architect__vuls-73f0adad95c4d227e2ccfa876c85cc95dd065e13` | pass/pass |
| `instance_internetarchive__openlibrary-f8cc11d9c1575fdba5ac66aee0befca970da8d64-v13642507b4fc1f8d234172bf8129942da2c2ca26` | fail/fail |

The exact task IDs are copied into the experiment root before launch, hashed,
and reused by all four arms. The total planned workload is:

```text
4 arms × 5 tasks × 2 trials × 2 repetitions = 80 Harbor trials
```

## Isolation and Identity

The experiment root is append-only and timestamped:

```text
/data00/home/zimuwang/simple-evolve-agent-project/experiments/
  framework-hardening-runtime-canary-<timestamp>/
```

It contains:

- immutable framework snapshots for the tested commits;
- one workspace, `EVOLVE_HOME`, Harbor jobs root, log, and result directory per
  arm and repetition;
- the fixed task list and SHA-256 hash;
- candidate target-tree hashes proving old/hardened equality within a recipe;
- launch metadata, PIDs, process groups, return codes, and timing records;
- a final machine-readable summary.

No existing experiment, workspace, Harbor job directory, or stale container is
modified or removed.

## Readiness Gate

Before the 80-trial matrix:

1. snapshot the hardened commit to DevBoxS and run its full local test suite;
2. initialize all four isolated workspaces;
3. verify evaluator/task/candidate hashes;
4. run one task with one trial sequentially for every arm;
5. require a terminal Harbor trial, a parseable task vector, retained artifacts,
   a return code, and a cost record where supported;
6. stop without launching the matrix if any arm remains pending, loses its
   Harbor process, or leaves an unowned active container.

The current `hillclimb-seed-gen0-test30-20260713` job is not evidence of
readiness: its job record shows all 30 trials pending and no active Harbor
process.

## Parallel Execution

To minimize elapsed time while preserving paired conditions:

1. run `ahe-old` and `ahe-hardened` concurrently;
2. run `hyper-old` and `hyper-hardened` concurrently;
3. use eight Harbor workers per arm, for sixteen requested workers total;
4. run both repetitions with new job directories and no evidence overwrite.

If the one-minute load average exceeds 14, container startup repeatedly fails,
or either paired arm stops making progress for ten minutes, reduce both arms in
that pair to five workers. Worker counts always change symmetrically within a
pair and are recorded in the result metadata.

## Measurements

For each arm and repetition, record:

- launch, first-trial-start, first-trial-finish, and final-finish timestamps;
- total wall time, setup latency, trials per hour, and worker count;
- Harbor return code and framework return code;
- expected, completed, failed, timed-out, cancelled, and missing trial counts;
- reward vector and aggregate score as descriptive data;
- total observed USD cost, including failed trials when available;
- exception type, first-line message, owner, reward, and canonical outcome;
- task-vector and artifact-index hashes;
- archive `valid_parent`, `selection_eligible`, and status fields.

Primary comparisons are paired old-versus-hardened differences in throughput,
wall time, setup time, cost, and classification correctness. Score differences
are diagnostics: the candidate and task inputs are fixed, but model execution
may still be stochastic.

## Correctness Criteria

The hardened arms pass only if:

- every expected trial reaches a terminal classified outcome;
- reward never overrides an exception or nonzero Harbor return code;
- infrastructure failures have no score and cannot be valid parents;
- failed work retains observed cost and safe artifact evidence;
- task and artifact hashes resolve to retained files;
- the two repetitions use distinct job/evidence directories;
- old/hardened candidate target hashes match within each recipe.

The matrix is reported as invalid, not partially successful, if an arm silently
remains pending after its Harbor process exits.

## Overhead Interpretation

The hardened runtime is considered operationally acceptable when its paired
median wall time is no more than 15% slower than the old framework and it
introduces no systematic increase in model cost. This threshold is a canary
criterion, not a general performance guarantee; two repetitions are too few for
formal statistical claims.

## Safety and Stop Conditions

Stop the affected pair and retain evidence when:

- a readiness canary fails;
- no trial state changes for ten minutes and no active Harbor process owns it;
- the load average remains above 14 for five minutes;
- free space under `/data00` falls below 500 GB;
- an experiment process or container cannot be tied to the current experiment;
- credentials or proxy values appear in retained prompts or artifacts.

Do not clean global Docker state as part of this experiment. Cleanup is limited
to process groups and containers created by the new experiment and only after
their identities have been recorded.

## Deliverables

The experiment root must contain:

- `design.json` with commits, task hash, candidate hashes, worker policy, and
  success thresholds;
- per-arm/repetition logs, return codes, timing, task vectors, costs, and
  artifact indexes;
- `summary.json` and `summary.md` with paired comparisons and every stop/fallback
  decision;
- exact reproduction commands with secrets excluded.
