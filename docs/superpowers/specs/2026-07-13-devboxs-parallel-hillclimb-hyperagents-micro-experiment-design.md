# DevBoxS Parallel Hill-Climb and HyperAgents Micro-Experiment

**Date:** 2026-07-13

**Status:** Approved for execution planning

## Purpose

Run two small, comparable training experiments on DevBoxS to answer two
questions:

1. Does the hardened MiniSWE runtime reproduce the locked dependency
   environment across training and post-training evaluation without recurring
   FastAPI, LiteLLM build, setup-timeout, or proxy-inheritance failures?
2. Does the current HyperAgents recipe still produce repeated, low-value
   patches after dependency feedback becomes reliable?

The hill-climb arm is the simple runtime and meta-agent control. The
HyperAgents arm exercises its method-specific selector, mutable meta-agent
workflow, validation, gate, and experience record.

## Fixed Experiment Shape

Run both arms concurrently with the same benchmark task lists and runtime
inputs.

| Setting | Hill climb | HyperAgents |
| --- | ---: | ---: |
| Fixed training tasks | 3 | 3 |
| Generated candidates | 3 | 3 |
| Candidate fan-out | 1 | 1 |
| Harbor workers | 3 | 3 |
| Trials per task (`k`) | 1 | 1 |
| Held-out test tasks | 3 | 3 |

Each arm evaluates generation 0 and generations 1 through 3. This produces 12
training trials per arm. Each arm then evaluates one generated candidate on
three held-out tasks, for 15 trials per arm and 30 trials total.

The two arms use separate experiment roots, workspaces, Harbor job roots, logs,
and PID files. They may use the same canonical warmed uv package cache. No
cache pruning or mutation outside normal uv operation occurs during the run.

## Task Sets

Choose one fixed three-instance training list from the existing validated
SWE-bench Pro training set. Use the identical list in both arms.

Choose one fixed, disjoint three-instance test list from the existing sealed
test set. Keep this list outside both evolution workspaces. Test task names,
traces, scores, and artifacts must not be available to either meta-agent during
training.

Both arms use the `swebenchpro@1.0` registry dataset. The framework records the
task-set hashes so the two training arms and two post-loop evaluations can be
checked for exact agreement.

## Runtime and Environment

Use the latest local `codex/framework-hardening` snapshot without pushing it.
Transfer it to a fresh, commit-identified framework directory on DevBoxS and
initialize both workspaces from the matching local MiniSWE source seed.

The candidate dependency pair is `pyproject.toml` plus `uv.lock`. Candidate
installation must use frozen synchronization, and benchmark execution must use
the materialized virtualenv Python directly. Plain unresolved
`uv run --project /installed-agent/miniswe-source` is forbidden during trials.

Both arms reuse the verified warmed uv cache. Installation may use the
configured installation proxy. Model execution must not inherit generic
uppercase or lowercase HTTP, HTTPS, or ALL proxy variables. Explicit model
endpoint configuration and credentials continue to propagate normally.

Source the DevBoxS project `.env` silently. Never print, copy into artifacts,
or include credential or proxy values in commands, prompts, or reports.

The protected command `./evolve candidate-smoke --full` remains optional for
both meta-agents. It is prompt-visible environment feedback, not a mandatory
candidate boundary.

## Training Behavior

### Hill-climb arm

Use the generic `agent_command` meta-agent, greedy selection, and hill-climb
gate. This arm supplies the simpler control for determining whether the locked
runtime and ordinary feedback loop work across multiple candidates.

### HyperAgents arm

Use the shipped HyperAgents variants unchanged:

- score-and-child-count parent selection;
- mutable `target/**`, `operators/meta_agent.py`, and
  `operators/meta_agent.md` as one atomic candidate;
- fixed HyperAgents validation, parent-eligibility gate, and experience record;
- optional protected runtime smoke guidance.

Three generated candidates are required because a meta-agent workflow edit can
only influence a later selected descendant. Record each selected parent so a
repeated proposal can be attributed to selection, history use, or descendant
activation rather than described only as duplicate text.

## HyperAgents Repetition Analysis

Analyze the retained prompts, parent identities, candidate diffs, outputs,
validation results, experience records, and evaluation results after the run.
Do not modify the recipe during this diagnostic.

Classify a proposal as repetitive when one or more of these conditions holds:

- its normalized patch is identical or nearly identical to an earlier patch;
- it changes the same files with the same root-cause hypothesis but cites no
  new evidence;
- it reapplies behavior already present in its selected parent;
- it proposes a change without using relevant prior evaluation evidence;
- a meta-agent workflow edit is present in a selected parent but does not
  affect the later descendant's prompt or behavior.

Attribute the likely cause explicitly:

- repeated selection of generation 0 is selection-driven;
- repetition from a parent that already contains the change is a current-source
  or history-inspection failure;
- proposals based only on dependency or setup failures indicate unusable
  runtime feedback;
- repetition despite healthy dependency materialization and normal benchmark
  evidence points to the HyperAgents prompt or experience mechanism.

A patch does not need to improve the score to be meaningful. It must be a real,
valid behavioral change supported by a distinct hypothesis or new evidence.

## Post-Loop Test Evaluation

After each arm completes generation 3, choose its newest runnable generated
candidate:

1. Prefer generation 3 when its dependency preflight, surface validation, and
   training evaluation are complete.
2. Otherwise fall back to generation 2, then generation 1.
3. Do not require the candidate to be the best-scoring or gate-selected parent.
4. Never substitute generation 0.
5. If no generated candidate is runnable, mark that arm unsuccessful and do
   not run its test evaluation.

Export the exact selected candidate tree into a separate evaluation-only
workspace. Evaluate it once on the three held-out tasks with three Harbor
workers and `k=1`. Store test jobs outside the evolution workspace. No later
meta-agent call or generation may consume the test results.

## Monitoring and Failure Handling

Launch both arms with explicit process groups, PID files, top-level logs, and
separate Harbor state and jobs paths. Verify the framework commit, task hashes,
worker counts, candidate lock hashes, cache path, and first jobs immediately
after launch.

An arm-local candidate failure does not stop the other arm. Stop both arms only
for a shared infrastructure problem such as credential failure, incorrect
runtime identity, Docker or Harbor failure, corrupted shared cache behavior,
lost process ownership, or evidence that generic proxies reached model
execution.

Do not clean up unrelated DevBoxS containers or processes. Do not repair a
candidate interactively inside a trial. Preserve all terminal evidence and
classify frozen-materialization failures using the framework's explicit
candidate-runtime outcome.

## Expected Duration

Both arms run concurrently, so wall time is governed by the slower arm rather
than the sum of both arms.

- optimistic: 2 to 3 hours;
- likely: 3 to 5 hours;
- slow benchmark or meta-agent turns: 5 to 8 hours.

DevBoxS has 16 CPUs, 31 GiB of memory, and sufficient disk, but it currently
has many existing containers and elevated system load. Allow roughly 20 to 40
percent timing variance. The configured HyperAgents meta-agent timeout is much
larger than the expected turn time, so monitoring must distinguish healthy
progress from a stalled call instead of waiting blindly for the timeout.

## Success Criteria

The dependency/runtime question passes when both arms demonstrate:

- matching project and lock validation;
- successful frozen materialization from the shared cache;
- MiniSWE and configured LiteLLM-path preflight success;
- direct virtualenv Python execution in every retained trial;
- no missing FastAPI, LiteLLM build, repeated resolution, or setup-timeout
  failure attributable to the candidate dependency graph;
- installation-proxy presence only during installation and absence from model
  execution;
- a post-loop held-out evaluation of a generated, non-seed candidate.

The HyperAgents question is diagnostic rather than pass/fail. The report must
state whether repetition occurred, identify the selected-parent sequence, show
the relevant patch relationships, and attribute the most likely mechanism. A
three-generation micro-run can establish a concrete failure mode or demonstrate
short-horizon improvement; it cannot establish long-run statistical quality.

## Deliverables

Retain and report:

- experiment roots, framework identity, workspace paths, PIDs, and logs;
- fixed train/test task hashes without exposing test tasks during training;
- per-generation parent, candidate, patch, runtime, score, and terminal status;
- protected smoke attempts, if either meta-agent chose to run them;
- post-loop selected candidate identities and held-out results;
- a concise cross-arm runtime comparison;
- a HyperAgents repetition and cause analysis;
- credential and proxy leak scans reported only as safe booleans.

Do not push the branch or any experiment change without explicit approval.
