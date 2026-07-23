# July 23 Handoff Consolidation and Shared Optimization Design

**Goal:** Consolidate the July 23 handoff changes on local `main`, configure AHE and HyperAgents to optimize on the same frozen 10 Terminal-Bench tasks, and launch comparable full experiments on DevBoxS after verification.

## Current repository state

The workspace is already on local `main`, which is 11 commits ahead of
`origin/main`. The feature branches relevant to the current experiment stack
are already ancestors of local `main`; they do not require another branch
merge. The July 23 handoffs correspond to uncommitted changes in the shared
working tree plus the untracked `handoff-0723-21/` notes.

Historical branches whose commit graphs diverged before the repository history
rewrite are not consolidation inputs. They must not be merged merely because
`git branch --no-merged` lists them.

## Handoff modification reminder

### 1. File-backed AHE debugger evidence

- `run_readonly_agent` accepts bounded input files and writes them beneath the
  read-only task's `inputs/` directory.
- AHE stores each task's complete bounded trace collection in
  `/app/task/inputs/trace-evidence.json`.
- The debugger prompt contains task instructions and the evidence path instead
  of embedding the complete trace JSON in the user message.
- Input filenames are restricted to a single safe relative component.

This reduces prompt noise without removing evidence: the debugger can inspect
the full pass/fail rollout set from the mounted file.

### 2. AHE analyzer resilience and observability

- One debugger job is still created per selected task, with all trials for that
  task grouped together.
- Individual debugger failures become explicit `ANALYSIS UNAVAILABLE` reports
  instead of aborting the entire analyzer stage.
- Failed jobs retain their usage and error details.
- `analysis/summary.json` records `debugger_errors`.
- The real-run health gate is ten task detail reports and
  `debugger_errors == 0`; fail-soft behavior preserves evidence but does not
  silently qualify an unhealthy experiment.

### 3. OpenAI Responses runtime and 64k output budget

- OpenAI-backed MiniSWE candidate and meta-agent paths use the Responses model
  rather than the Chat Completions wrapper.
- Responses requests default to `max_output_tokens=64000`, while an explicit
  caller override remains authoritative.
- Reasoning is sent in Responses format and encrypted reasoning content is
  included.
- Each agent receives a stable per-agent `prompt_cache_key` and matching
  `extra.session_id` routing value.
- Both recipes explicitly route candidate and meta-agent calls through the
  configured Responses endpoint.
- Candidate reasoning remains `high`; AHE meta-agent reasoning remains
  `xhigh`; HyperAgents meta-agent reasoning remains `high`.

The July 23 smokes observed clean tool calls, no truncation, and no
`RepeatedFormatError`. The previous failures were caused by the wrong
Responses route/payload rather than the Docker image.

### 4. Experiment capacity and lifecycle

- AHE and HyperAgents evaluator concurrency changes from four to five workers.
- AHE retains `k=2`; HyperAgents retains `k=1` because this is a
  method-specific setting rather than infrastructure parity.
- `--max-generations` limits evolution rounds only. It does not cap evaluator
  attempts, task count, agent steps, or the complete Harbor task lifecycle.
- Earlier tmux loss killed parent controllers while leaving Harbor children
  alive temporarily. New launches need durable controller logging and exact
  process/container verification.

### 5. Expanded meta-agent image definition

- `containers/meta-agent/Dockerfile` now installs the expanded shell and Python
  tool set from PR 15, including `jq`, `ripgrep`, `rsync`, `tree`,
  `python3-pip`, and `python3-venv`.
- The proven DevBoxS image is still the locally tagged July 18 image
  `evolve-meta-agent-app:ubuntu-latest`, image ID
  `sha256:61b800306be7032671455fe02b60002dad7853ef2e8de1e3e772f91dcb059998`.
- The expanded Dockerfile has not yet been built and is not reproducible
  because it inherits `ubuntu:latest` and installs unpinned packages.

The full experiments will use the proven July 18 image for continuity and
record its exact image ID. Building and publishing a pinned replacement image
is follow-up work, not a prerequisite for these experiments.

## Shared optimization-set design

Both `recipes/ahe/evolve.yaml` and `recipes/hyperagents/evolve.yaml` will set:

```yaml
evaluator:
  evaluation_split: train
  split:
    train: 0.3333333333333333
    gate: 0.3333333333333333
    sealed: 0.3333333333333333
    seed: 0
  sampling: static
  tasks_per_round: 10
```

The manifest remains disjoint and deterministic. Candidate evaluation is
redirected from the gate partition to the train partition. Because both
recipes use `evaluation_replay`, the retained candidate evaluation supplies
the next meta-agent's rollout feedback. Therefore learning feedback and
during-evolution scoring use the same ten task identities without implementing
overlapping split semantics.

Both recipes use the same dataset, ratios, seed, sampling mode, and task count,
so their frozen optimization task lists must match exactly. The configured
gate partition remains unused and available for a later robustness check. The
sealed partition remains inaccessible during evolution and is reserved for
final evaluation.

The documentation will call the train partition the **optimization set** to
avoid confusing the framework's gate operator with the dataset split named
`gate`. Gate operators continue to decide candidate eligibility using the
canonical score; only the canonical evaluation task identities change.

## Consolidation and verification

The uncommitted July 23 source, recipe, Dockerfile, test, ignore-file, and
handoff-note changes will be reviewed as one coherent integration and committed
on local `main`. Only relevant branches already incorporated by ancestry are
considered merged; unrelated historical branch tips are left untouched.

Before remote execution:

1. Add tests that require both real recipes to use `evaluation_split: train`.
2. Update recipe documentation to describe the shared optimization set and
   sealed holdout accurately.
3. Run focused tests for recipe initialization, split identity, AHE analysis,
   Harbor file transport, and MiniSWE Responses configuration.
4. Run the complete local test suite and `git diff --check`.
5. Initialize fresh local or remote workspaces and compare their frozen
   `evaluator/splits.json` train members byte-for-byte.

## DevBoxS experiment launch

Fresh AHE and HyperAgents experiment workspaces will be initialized from the
same consolidated source state. They will use:

- dataset `terminal-bench-2-10-10-10`;
- 10 generations;
- 10 optimization tasks per round;
- five evaluator workers;
- model `openai/gpt-5.4-2026-03-05`;
- the Responses endpoint recorded in the recipes;
- `EVOLVE_RUNTIME_DIGEST=tb2-10x3-runtime-20260722-v3`;
- `EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv`;
- the proven July 18 meta-agent image, with its exact image ID recorded.

Each fresh workspace first runs through one generation as a real-path health
gate. The same workspace then continues to generation 10, so successful smoke
work is retained rather than repeated.

Promotion requires:

- frozen train membership is identical across AHE and HyperAgents;
- live requests show the expected Responses endpoint, reasoning effort, and
  64k default;
- no API routing, truncation, formatting, controller, or archive error;
- AHE produces ten task detail reports with `debugger_errors == 0`;
- candidate evaluation completes and the generation is durably archived.

If either recipe fails its method-specific health gate, preserve its workspace
and evidence, stop only its matching controller and task containers, and do
not promote that run blindly.

## Out of scope

- Merging historical branches that diverged before the repository history
  rewrite.
- Publishing or pinning a replacement meta-agent image.
- Equalizing AHE `k=2` and HyperAgents `k=1`.
- Using the sealed set during evolution.
- Starting the old inline-versus-file-backed AHE comparison as the final
  two-recipe experiment.
