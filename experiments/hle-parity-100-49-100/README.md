# HLE Parity 100/49/100 Split

This folder freezes a partner-shareable split of Harbor's 249-task HLE parity
set:

- `train.txt`: 100 tasks used during evolution;
- `gate.txt`: 49 held-out development tasks;
- `sealed.txt`: 100 tasks reserved for final evaluation;
- `source-task-names.txt`: Harbor's complete 249-task parity population;
- `split.json`: source identity, seed, ratios, memberships, and checksums.

The source list comes from Harbor's
[`adapters/hle/run_hle_parity.yaml`](https://github.com/harbor-framework/harbor/blob/main/adapters/hle/run_hle_parity.yaml)
at Git blob `ac0147d4a5f748810a9567ac9f6d257aa1fd9b74`.
The second-stage split uses this framework's deterministic SHA-256 ordering
with seed `42`.

## Prepare the local dataset

Each partner must obtain access to the gated
[`cais/hle`](https://huggingface.co/datasets/cais/hle) dataset independently
and use Harbor's HLE adapter to generate the parity task directories. Do not
commit or redistribute the questions, answers, images, or generated task
directories.

Place the 249 generated Harbor task directories in a flat local directory
named `hle_parity`, or pass its absolute path through `evolve init --dataset`.
Before starting an experiment, compare its immediate task-directory names
against `source-task-names.txt`. The sets must match exactly.

Initialize with either HLE recipe:

```bash
cd /path/to/simple-evolve-agent
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-immutable-evaluator-image-digest"

uv run evolve init /path/to/ahe-hle-run \
  --recipe ahe_hle \
  --dataset /path/to/hle_parity

uv run evolve init /path/to/hyperagents-hle-run \
  --recipe hyperagents_hle \
  --dataset /path/to/hle_parity
```

Both HLE configurations are supported recipes in the public `--recipe`
inventory.

The generated workspace's `evaluator/splits.json` must reproduce
`split.json`'s `tasks` membership. If Harbor changes its parity list, create a
new versioned split package instead of editing this one.
