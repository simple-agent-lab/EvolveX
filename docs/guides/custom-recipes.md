# Creating a custom recipe

A recipe selects the target seed, mutable surface, operator implementations,
evaluator contract, and execution runtime for an experiment. It is an
initialization input: `evolve init` copies its resolved configuration and
operator code into a new workspace.

## Start from the nearest supported recipe

Copy the recipe whose behavior is closest to the experiment you want:

```bash
mkdir -p my-recipes
cp -R recipes/gepa my-recipes/my-gepa
```

Keep `evolve.yaml` at the root of the copied directory. A custom recipe can be
passed either as a directory or as its YAML file:

```bash
uv run --frozen evolve preflight /tmp/my-experiment \
  --recipe-path "$PWD/my-recipes/my-gepa" \
  --dataset /absolute/path/to/harbor/tasks
```

Use `--recipe` only for names shipped under the repository's `recipes/`
directory. Use `--recipe-path` for your own recipe. The two options cannot be
combined.

## Recipe structure

A small recipe directory usually looks like this:

```text
my-gepa/
├── evolve.yaml
├── README.md
└── evaluator/             # optional additional evaluator assets
```

Recipe-local operator directories are rejected. Put reusable implementations
in the source checkout's `library/<stage>/<name>.py`; a recipe only selects and
configures them. Generated evaluator files are framework-owned, and a custom
`evaluator/` asset may not replace files such as `eval.sh`, `eval.env`,
`splits.json`, or `runtime.json`.

## The main configuration sections

Every recipe uses these top-level sections:

| Section | What it controls |
| --- | --- |
| `experiment` | generation limit, children per generation, budget, target score, and random seed |
| `target` | the initial agent or repository copied into `target/` |
| `surface` | paths a candidate is allowed to change |
| `operators` | active implementation and settings for each evolution stage |
| `evaluator` | fixed scoring engine, dataset, agent, split, concurrency, retries, and anchors |
| `execution_runtime` | host backend and resource checks for the experiment |

The safest way to create a recipe is to preserve the full structure of a
working recipe and change one concern at a time.

## Choose the target seed

The recipe can declare a built-in target:

```yaml
target:
  seed: builtin-codex
```

It can also declare a Git URL:

```yaml
target:
  seed: https://github.com/example/my-agent.git
  revision: 0123456789abcdef0123456789abcdef01234567
```

For local development, override the recipe seed without editing the recipe:

```bash
uv run --frozen evolve preflight /tmp/my-experiment \
  --recipe-path "$PWD/my-recipes/my-gepa" \
  --seed /absolute/path/to/my-agent \
  --dataset /absolute/path/to/harbor/tasks
```

The same `--seed` value must be supplied to `evolve init`. A Git revision
should be pinned for a reproducible experiment.

## Declare the mutable surface

The surface is the authoritative candidate-change boundary:

```yaml
surface:
  include:
    - target/**
  exclude:
    - target/generated/**
```

Most recipes should mutate only `target/**`. A method that intentionally
co-evolves operator policy, such as HyperAgents, may include selected
`operators/**` paths as well.

`operators.mutate.config.editable_roots` controls what the mutation agent receives
permission to edit, but it does not expand the recipe surface. Keep it equal to
or narrower than the surface:

```yaml
operators:
  mutate:
    operator: gepa
    timeout_s: 3600
    config:
      editable_roots: [target]
```

The evaluator, `.evolve/`, archive records, split manifest, and other
measurement infrastructure must remain outside the mutable surface.

## Select and configure operators

Each enabled stage selects exactly one named `operator` or one explicit
`script`. `timeout_s` belongs to the stage binding; all operator-specific
settings live under `config`:

```yaml
operators:
  select:
    operator: pareto
    timeout_s: 600
    config:
      seed: 0
```

Named operators are portable because the source catalog owns their identity.
To add one:

1. Run `evolve operator new <stage> <name>` in a source checkout, or copy the
   closest `library/<stage>/_skeleton.py`.
2. Implement the corresponding interface from `evolve.frozen.interfaces`.
3. Validate configuration in the entry file and pass the validator to
   `sdk.main(..., validate_config=validate_config)`.
4. Run `evolve operator describe <stage>/<name>` and
   `evolve operator check <stage>/<name> --config '<json>'`.
5. Select it in `evolve.yaml`, then run `evolve recipe check`.

```yaml
operators:
  select:
    operator: my_selector
    config: {}
```

See the [operator reference](../reference/operators.md) for stage contracts and
the built-in operator catalog. Helpers whose file or directory name begins
with `_` are importable by entry files but are not discovered as operators;
shared validators live in `library/_shared/config.py`.

An explicit `script:` remains executable for an escape hatch:

```yaml
operators:
  select:
    script: ./custom/select.py
    timeout_s: 600
    config: {}
```

Relative paths resolve from the recipe directory, but script bindings are
reported as non-portable: the recipe depends on that external filesystem path.
Use a named library operator for a recipe intended to travel between checkouts.

## Configure the evaluator and split

A Harbor evaluator needs a dataset and candidate agent:

```yaml
evaluator:
  engine: harbor
  dataset: my-task-set
  agent: target.agent:HarborAgent
  split:
    train: 0.5
    gate: 0.4
    sealed: 0.1
    seed: 0
  sampling: static
  tasks_per_round: 10
  repetitions: 1
  n_concurrent: 4
  max_retries: 1
```

Pass the real local task directory with `--dataset`; this overrides
`evaluator.dataset` during initialization. `evolve init` freezes task names and
content identities into `evaluator/splits.json`.

- **train** data may feed rollout analysis and mutation.
- **gate** data decides whether a candidate is eligible to advance.
- **sealed** data is an evaluation anchor and must not be exposed as mutation
  feedback.

Keep `operators.mutate.config.expose_gate_data: false` unless the experiment
explicitly intends to expose protected evaluation history.

## Prepare images and authentication

The repository's `setup_terminal_bench.sh` helper only accepts the supported
recipe names. For a custom recipe, you are responsible for making every image
named in `evolve.yaml` available to Docker:

```bash
docker build -t my-meta-agent:latest containers/meta-agent-codex
docker image inspect my-meta-agent:latest
```

Then reference that exact image:

```yaml
operators:
  mutate:
    operator: hyperagents
    timeout_s: 3600
    config:
      runner: harbor
      environment: docker
      image: my-meta-agent:latest
```

Keep API keys and auth files outside recipe YAML. Supply them through the
documented environment or auth-file mechanism for the selected agent.
See [Environment Variables](../reference/environment-variables.md) for loading
rules, runtime identity, cache paths, proxies, and the startup checklist.

## Validate before initialization

Run the prospective preflight first:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-runtime-digest"

uv run --frozen evolve preflight /tmp/my-experiment \
  --recipe-path "$PWD/my-recipes/my-gepa" \
  --seed /absolute/path/to/my-agent \
  --dataset /absolute/path/to/harbor/tasks
```

Fix every failed check before `evolve init`. After changing a recipe, target,
operator, evaluator asset, image, or dataset membership, initialize a **new**
workspace. Existing workspaces are intentionally frozen experiment records.
