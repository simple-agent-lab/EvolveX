# Creating a custom recipe

A recipe selects the target seed, mutable surface, operator implementations,
evaluator contract, and execution runtime for an experiment. It is an
initialization input: `evolve init` copies its resolved configuration and
operator code into a new workspace.

This page is a configuration reference, not authority to start source or
deployment work. For guided authoring, follow the repository playbooks in
`skills/evolve-agent/references/experiment-design.md`,
`recipe-authoring.md`, `operator-authoring.md`, and `deployment.md`.

Before copying a recipe, qualify the evaluator's coverage, determinism,
leakage boundary, runtime compatibility, positive and negative calibration,
limitations, and supported claims. Stop or route to evaluation authoring if
that evidence is insufficient. Record the target, mutable surface, evaluator,
partitions, runtime boundary, budget, alternatives, and risks in the task
record, then obtain architecture approval. Materialize the custom recipe and
its durable `README.md` only after that approval.

Author the approved recipe in this order:

1. target and mutable surface;
2. qualified evaluator, partitions, and runtime contract;
3. operator composition and configuration.

After each coherent phase, run the complete recipe check and record a
checkpoint before proceeding. The reference sections below explain individual
fields and are not a different authoring order.

## Start from the nearest supported recipe

Copy the recipe whose behavior is closest to the experiment you want:

```bash
mkdir -p my-recipes
cp -R recipes/gepa my-recipes/my-gepa
```

Keep `evolve.yaml` at the root of the copied directory. A custom recipe can be
passed either as a directory or as its YAML file. Recipe resolution imports
selected named operators. Before executing it, statically review every entry
file and local import for import-time filesystem, network, process, credential,
deployment, or model side effects. Then run the check with no ambient
credentials in a disposable, network-disabled environment whose readable
files, writable temporary directory, executable tools, and environment
variables are explicitly allowlisted:

```bash
uv run --frozen evolve recipe check "$PWD/my-recipes/my-gepa/evolve.yaml" --json
```

Rerun that full check after every phase and on the exact source-review tree.
A passing check proves resolution, schemas, and normalized configuration. It
does not qualify evaluator behavior, prove authentication or runtime
readiness, approve source, or authorize deployment.

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

For local development, record an absolute local target path as the eventual
`--seed` override without editing the recipe. Add it to the prospective
preflight command only after source approval, using the isolation and approval
procedure below, and supply that same `--seed` value to `evolve init`. A Git
revision should be pinned for a reproducible experiment.

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

Configure this section only after the evaluator, partition, and runtime phase
has passed its checkpoint. It appears here solely as a field reference.

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
The inspection commands in the following sequence execute operator code.
Before any invocation, apply the static review and credential-free isolated
boundary described above. To add one:

1. Run `evolve operator new <stage> <name>` in a source checkout.
2. Implement the corresponding interface from `evolve.frozen.interfaces`.
3. Declare configuration with `evolve.frozen.config.Config` and pass it to
   `sdk.main(..., config_schema=CONFIG)`.
4. Run `evolve operator describe <stage>/<name>` and
   `evolve operator check <stage>/<name> --config '<json>'`.
5. Select it in `evolve.yaml`, then run `evolve recipe check`.

Successful import or schema output is not behavior validation.

```yaml
operators:
  select:
    operator: my_selector
    config: {}
```

See the [operator reference](../reference/operators.md) for stage contracts and
the built-in operator catalog. Helpers whose file or directory name begins
with `_` are importable by entry files but are not discovered as operators;
shared schema fragments may live in an underscore-prefixed stage helper.

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
named in `evolve.yaml` available to Docker. The following commands are command
shapes, not source-authoring steps. Obtain separate explicit authority for any
image build, download, or other environment mutation before running them:

```bash
docker build -t my-mutate-runner:latest containers/meta-agent-codex
docker image inspect my-mutate-runner:latest
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
      image: my-mutate-runner:latest
```

Keep API keys and auth files outside recipe YAML. Supply them through the
documented environment or auth-file mechanism for the selected agent.
See [Environment Variables](../reference/environment-variables.md) for loading
rules, runtime identity, cache paths, proxies, and the startup checklist.

## Validate before initialization

Obtain source approval for the exact Git tree, durable rationale, normalized
recipe check, identities, evidence, and limitations before prospective
preflight. Reject credential-bearing URLs: remove URL userinfo and secret query
parameters before command execution or output retention, and use an out-of-band
authentication mechanism.

Prospective `evolve preflight` is a read-only initialization checklist. Recipe
resolution still executes named operator inspection, so repeat static review
and run it with no ambient credentials in the same allowlisted,
network-disabled isolation boundary. Its representable inputs are the
destination, exactly one of recipe or recipe path, optional seed, dataset, and
task limit, and the declared `EVOLVE_RUNTIME_DIGEST` shown below:

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

The command does not generate a receipt or validate authentication identity,
remote reachability, credential validity, or actual evaluator/runtime
readiness. Manually sanitize stdout before retaining it. In the task or recipe
record, save the exact secret-free command, sanitized stdout, independently
established Git/content/image/runtime identities and digests, and every
unchecked assumption. Request deployment approval bound to that packet before
`evolve init`; baseline evaluation spend requires separate authority.
