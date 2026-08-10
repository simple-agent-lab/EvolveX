# Champion Full-Benchmark Evaluation Design

## Goal

Evaluate the eight previously selected champion agents once on their complete
benchmark datasets without changing the original experiment repositories or
their historical archives.

The evaluation matrix contains:

- four Terminal-Bench 2 champion evaluations over exactly 89 tasks each; and
- four Tau3 Banking champion evaluations over exactly 97 instances each.

The full run therefore contains 744 primary trials. Seed-agent baselines and
additional repetitions are outside scope.

## Champion Inputs

Each candidate is identified by an immutable source repository, generation
tag, and resolved commit. The evaluated agent is the `target/` tree from that
tag, not the source repository's current checkout.

| Host | Benchmark | Method / target | Source repository relative to `/data00/home/zimuwang/simple-evolve-agent-full89-20260724` | Tag | Commit |
| --- | --- | --- | --- | --- | --- |
| DevBox | Terminal-Bench 2 | AHE / MiniSWE | `workspaces/ahe-terminal-bench-2` | `gen/6` | `1f9de64bb4f2a1689818f237af7e425422191f0a` |
| DevBoxS | Terminal-Bench 2 | HyperAgents / MiniSWE | `workspaces/hyperagents-terminal-bench-2-full-20260730-r2` | `gen/10` | `90fc97b05ebbe976c7467f36db886eca4622e8c4` |
| DevBox | Terminal-Bench 2 | AHE / Codex | `workspaces/ahe-codex-terminal-bench-2-full-20260801-r1` | `gen/7` | `6b800ca0ce773147675b60454bda22e1664923ba` |
| DevBox | Terminal-Bench 2 | HyperAgents / Codex | `workspaces/hyperagents-codex-terminal-bench-2-full-20260801-r1` | `gen/5` | `991ec292eb3e0315d6bc1f0d890844c1e092b7b7` |
| DevBox | Tau3 Banking | AHE / MiniSWE | `experiments/ahe-miniswe-tau3-banking-50x10-safe-20260803T113701Z-8b2c5b83` | `gen/6` | `ddf8f5f84405934f34eb16f8d4c05f15cecab867` |
| DevBox | Tau3 Banking | HyperAgents / MiniSWE | `experiments/hyperagents-miniswe-tau3-banking-50x10-safe-20260803T113701Z-8b2c5b83` | `gen/1` | `17d0be50bcbc797980244ecf911a359084355816` |
| DevBox | Tau3 Banking | AHE / Codex | `experiments/ahe-codex-tau3-banking-50x10-safe-20260803T113701Z-8b2c5b83` | `gen/8` | `d2baf329149eb408eecf3dbbb7bc258e83b2eb2b` |
| DevBoxS | Tau3 Banking | HyperAgents / Codex | `experiments/hyperagents-codex-tau3-banking-50x10-safe-20260803T113701Z-8b2c5b83` | `gen/7` | `705173529d8069296598c7d4122bc8674253d955` |

Before any paid trial, the launcher must resolve every tag again and require
the full commit to equal the value above.

## Evaluation Isolation

Create a new evaluation root on each host under:

`/data00/home/zimuwang/simple-evolve-agent-full89-20260724/full-evals/champion-full-20260810/`

Every matrix row receives a separate Git-backed evaluation workspace. The
workspace uses the audited corrected-rerun evaluator pattern for its benchmark
and target type, while its `target/` tree is replaced with the exact champion
tree and committed as the evaluated candidate. This preserves the evaluator
fixes without changing the champion.

The original experiment repositories, tags, archives, run directories,
mirrors, and corrected sealed-rerun workspaces are read-only inputs. New
evaluation records, task vectors, logs, and retry evidence stay beneath the
new evaluation root.

The preflight must prove that the runtime imports or mounts the candidate from
the detached evaluated checkout. It must not import the agent from
`EVOLVE_WORKSPACE`, the original experiment's current checkout, or a shared
seed directory.

## Dataset Contract

Terminal-Bench 2 uses the complete dataset at:

`/data00/home/zimuwang/simple-evolve-agent-full89-20260724/terminal-bench-2-full89`

The selected task manifest must contain exactly 89 unique task IDs, and each
ID must resolve to exactly one task in that dataset.

Tau3 Banking uses this corrected 97-instance safe-health v0.33 dataset on both
hosts:

`/data00/home/zimuwang/simple-evolve-agent-full89-20260724/datasets/tau3-banking-97-codex-safe-health-v033-1d244f5dca42944b67a379b44bfeb9f5748f189d-seed626729-r1`

The selected manifest must contain exactly 97 unique task IDs. All four Tau3
evaluations use simulator seed `626729` at the runtime call site. A
configuration field that merely declares another seed is not sufficient;
persisted trial evidence must show the effective simulator seed.

Dataset membership and normalized task-manifest hashes must match between
DevBox and DevBoxS before preflight begins. Every primary instance is executed
once (`k = 1`).

## Preflight

Preflight runs one real benchmark instance for each of the eight champions,
for eight paid preflight instances total. It uses the same candidate commit,
agent adapter, model, reasoning settings, environment, dataset, and Tau3 seed
as the corresponding full run.

Before the real instance, each row must pass read-only checks for:

- source tag and commit identity;
- clean, isolated evaluation workspace construction;
- exact full-dataset manifest membership and count;
- Docker and Harbor availability, disk capacity, and image availability;
- required auth and proxy variables by presence only, without printing values;
- candidate dependency preparation or Codex auth, as appropriate;
- effective concurrency of 25 for the later full run; and
- absence of another launch that would exceed the per-host worker limit.

A row passes its real preflight only if it produces one scoreable task record,
complete indexed artifacts, a candidate-runtime receipt bound to the expected
commit, and—on Tau3—the effective simulator seed `626729`. Any failed row stops
the full matrix. Preflight artifacts remain separate from full-run results.

## Full-Run Scheduling

Each evaluation uses 25 concurrent workers. DevBox may run three evaluations
at once (75 workers), and DevBoxS may run one (25 workers), for a global maximum
of 100 workers.

Run two benchmark-aligned waves:

### Wave 1: Terminal-Bench 2

- DevBox: AHE / MiniSWE, AHE / Codex, and HyperAgents / Codex concurrently;
- DevBoxS: HyperAgents / MiniSWE concurrently; and
- each row executes its 89-task manifest.

### Wave 2: Tau3 Banking

- DevBox: AHE / MiniSWE, HyperAgents / MiniSWE, and AHE / Codex concurrently;
- DevBoxS: HyperAgents / Codex concurrently; and
- each row executes its 97-instance manifest with simulator seed `626729`.

Wave 2 starts only after all four Wave 1 primary runs reach terminal state and
their artifacts pass the completeness audit. No host may exceed its approved
worker limit.

## Failure and Retry Policy

Primary results are append-only. A scoreable result is never replaced by a
later duplicate.

After each wave, audit by task ID. If and only if an instance is missing or
failed for an infrastructure-owned reason, create a retry manifest containing
only those IDs and retry each at most once. Candidate failures, benchmark-agent
timeouts with a valid zero reward, verifier-declared failures, and ordinary
zero rewards remain primary outcomes and are not retried.

Merge primary and retry evidence by task ID with explicit provenance. If an
instance remains unscoreable after its single infrastructure retry, report the
run as incomplete rather than silently changing the denominator.

## Evidence and Completion Criteria

Each row retains:

- source repository, champion tag, and resolved commit;
- evaluated candidate commit and candidate-runtime receipt;
- normalized task manifest and its hash;
- effective runtime configuration with secrets redacted;
- preflight receipt and one-instance artifacts;
- full-run logs, indexed evaluation artifacts, and per-task results;
- retry manifest and retry artifacts when applicable;
- merged `task_vector.json` with provenance; and
- aggregate score, numerator, denominator, cost, and wall time.

The work is complete only when all four Terminal-Bench rows contain 89/89
scoreable task records and all four Tau3 rows contain 97/97 scoreable instance
records, or when any unrepaired missing records are explicitly reported as an
incomplete run. The final handoff reports all eight rows separately and does
not combine benchmark scores into a single metric.
