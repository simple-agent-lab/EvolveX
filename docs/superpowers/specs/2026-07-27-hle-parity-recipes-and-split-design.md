# HLE Parity Recipes and Shared Split Design

## Objective

Add isolated AHE and HyperAgents experiment recipes for Harbor's 249-task
Humanity's Last Exam (HLE) parity subset. Freeze a reproducible 100/49/100
train/gate/sealed partition that two partners can share without redistributing
the gated HLE questions, answers, images, or generated task directories.

The existing `ahe` and `hyperagents` recipes remain unchanged.

## Source Dataset Identity

The split source is the exact 249-task list checked into Harbor's
`adapters/hle/run_hle_parity.yaml`. The shared artifacts record:

- the GitHub source URL;
- the Harbor source blob SHA;
- all 249 Harbor task names;
- the split algorithm and seed;
- per-split task counts and membership checksums.

The source task-name list is safe to commit because it contains only opaque
task identifiers. No HLE question content is copied into this repository.

## Split Algorithm

Use the framework's existing deterministic splitter without adding another
randomization implementation. For each task name, it computes a SHA-256 digest
from the split seed and task name, orders tasks by that digest, and slices the
ordered list into train, gate, and sealed partitions.

Use split seed `42` and these recipe ratios:

```yaml
split:
  train: 0.40160642570281124
  gate: 0.19678714859437751
  sealed: 0.40160642570281124
  seed: 42
```

For exactly 249 task names, these values produce exactly:

- train: 100 tasks;
- gate: 49 tasks;
- sealed: 100 tasks.

The checked-in task memberships, not the seed alone, are the authoritative
cross-partner contract. Recomputing the split is a verification step.

## Shared Split Package

Create:

```text
experiments/hle-parity-100-49-100/
├── README.md
├── source-task-names.txt
├── train.txt
├── gate.txt
├── sealed.txt
└── split.json
```

`source-task-names.txt` preserves the 249-task Harbor parity population.
The three split text files contain one exact Harbor task name per line.
`split.json` contains versioned machine-readable metadata, source identity,
algorithm identity, seed, ratios, counts, task lists, and SHA-256 membership
digests.

`README.md` explains how each partner obtains the gated HLE content through
their own authorized access, generates or downloads the same Harbor parity
tasks, and verifies the local task names against this package.

The repository does not contain copied or symlinked HLE task directories.

## Recipes

Add:

```text
recipes/ahe_hle/
├── evolve.yaml
└── README.md

recipes/hyperagents_hle/
├── evolve.yaml
└── README.md
```

Each recipe derives from its existing non-HLE counterpart and changes only
the experiment and benchmark-specific configuration needed for HLE:

- a distinct experiment ID;
- the expected local Harbor HLE parity dataset path;
- the exact 100/49/100 ratios and seed `42`;
- `evaluation_split: train`;
- `tasks_per_round: 100`, so canonical evolutionary evaluation covers all
  100 training tasks;
- documentation describing how to supply the authorized local dataset and
  verify its membership.

The AHE and HyperAgents operator strategies, mutable surfaces, target seed,
runtime pinning, model settings, and meta-agent behavior remain aligned with
their respective existing recipes. The existing recipe directories are not
modified.

During evolution, only the 100-task train split is evaluated. The 49-task gate
and 100-task sealed partitions remain outside the evolutionary feedback loop.
Their later use is explicit and manual: gate supports development-time
confirmation or finalist selection, and sealed supports the final untouched
evaluation.

## Validation

Add automated tests that establish:

1. The source list contains exactly 249 unique task names.
2. Train, gate, and sealed contain exactly 100, 49, and 100 unique names.
3. The three partitions are pairwise disjoint.
4. Their union equals the source list.
5. Recomputing with the framework splitter, ratios, and seed reproduces every
   checked-in membership exactly.
6. Recorded membership digests match the checked-in files.
7. The new recipes are included in recipe inventory and initialize with the
   intended HLE dataset, split, and 100-task evolutionary evaluation.
8. The original `ahe` and `hyperagents` recipe configuration remains
   unchanged.

Tests operate only on task names and synthetic task directories; they do not
require access to the gated HLE dataset, Docker, Harbor execution, or API keys.

## Failure Handling

Workspace initialization should continue to enforce the framework's existing
dataset drift checks. If a partner's local HLE task directory does not contain
the exact expected 249 task names, setup instructions direct them to stop and
resolve the adapter/dataset mismatch rather than silently generating a
different split.

If Harbor changes its parity task list, that is a new dataset version and must
produce a new shared split package rather than mutating this one.

## Non-Goals

- Downloading or committing gated HLE questions, answers, images, or task
  directories.
- Modifying the existing AHE or HyperAgents recipes.
- Treating the 249-task parity subset as an official HLE train/test split.
- Changing the framework's deterministic splitting algorithm.
- Adding dynamic or per-generation task sampling.
- Automating gate or sealed evaluation as part of the evolutionary loop.
