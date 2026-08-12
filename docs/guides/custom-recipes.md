# Creating a custom recipe

A recipe selects the target seed, mutable surface, operator implementations,
evaluator contract, and execution runtime for an experiment. It is an
initialization input: `evolve init` copies its resolved configuration and
operator code into a new workspace.

This page is a configuration reference, not authority to start source or
deployment work. For guided authoring, follow the repository playbooks in
`skills/evolve-agent/references/experiment-design.md`,
`recipe-authoring.md`, `operator-authoring.md`, and `deployment.md`.
Repository-local Codex discovers that canonical skill through
`.agents/skills/evolve-agent`; Claude discovers it through
`.claude/skills/evolve-agent`. Both are identical thin wrappers that delegate
to `skills/evolve-agent/SKILL.md` and its canonical reference base, so neither
adapter copies or forks the playbooks. There is no `.codex/skills` repository
adapter.

Before copying a recipe, qualify the evaluator's coverage, determinism,
leakage boundary, runtime compatibility, positive and negative calibration,
score direction and domain, aggregation, missing/failure handling, thresholds,
ties, acceptance semantics, limitations, and supported claims. Stop or route to
evaluation authoring if that evidence is insufficient. Record the target,
mutable surface, evaluator, partitions, runtime boundary, budget, alternatives,
and risks in the task record, then obtain architecture approval. Materialize
the custom recipe and its durable `README.md` only after that approval.

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
evolve recipe check /read-only/source/my-recipes/my-gepa/evolve.yaml --json
```

Use a verified direct `evolve` executable from an already-existing
pre-provisioned environment. Materialize the reviewed source identity into the
read-only boundary before execution; never run authored imports from the
writable checkout. If the executable or boundary is absent, stop for separately
approved remediation instead of creating `.venv`, synchronizing, downloading,
or provisioning. Rerun recipe check after the target phase, after the evaluator
phase, after the operator phase, and on the exact source-review identity. Every
result proves selected-operator resolution, normalization, and composition
only. Record target-digest-bound target/surface review, operator config/schema,
evaluator config/schema, focused behavior, and calibration evidence separately.

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

For remote Git, both the credential-free URL and full immutable revision are
required source-approved recipe fields. Never pass a remote Git URL with
`--seed`: the override discards `target.revision`. Guided `--seed` is reserved
for a reviewed, content-addressed, read-only local snapshot prepared after
separate authorization. Built-in seeds remain recipe fields and are bound by a
deterministic packaged-resource-tree digest.

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

In guided authoring, each enabled stage selects exactly one named `operator`.
`timeout_s` belongs to the stage binding; all operator-specific settings live
under `config`:

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

The resolver retains an explicit `script:` compatibility escape, but guided
authoring must stop on it even when the user labels the request expert. This
repository supplies no named external script-review playbook. Do not invent
equivalent checks or an ad hoc exception; select a named `operator:` or defer.
Only a future named external playbook could define another flow; none is
supplied here.

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

At the first `evolve run`, RSIHub evaluates `gen/0` on the configured primary
split and then evaluates it once on every sealed task. The sealed result is
non-selectable and is not included in the mutation feedback bundle. Keep
`operators.mutate.config.expose_gate_data: false` whenever a sealed split is
present; every supported recipe does so, and the Harbor mutate runner rejects
`true` for a non-empty sealed split.

Record scoring semantics beside the qualified evaluator: whether higher or
lower is better; valid score domain, range, and unit; aggregation and weighting;
handling of missing, invalid, timed-out, or failed cases; thresholds and ties;
and the exact candidate acceptance or non-regression rule.

## Prepare images and authentication

The repository's `setup_terminal_bench.sh` helper only accepts the supported
recipe names. For a custom recipe, you are responsible for making every image
named in `evolve.yaml` available to Docker. The following commands are command
shapes, not source-authoring steps. Obtain separate explicit authority for any
image build, download, or other environment mutation before running them:

```bash
docker build -t my-mutate-runner:latest containers/mutate-codex
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

Obtain source approval for a clean commit or a complete source-tree
manifest/digest with explicit base, staged, unstaged, untracked, ignored, and
exclusion coverage. The packet includes a digest of its durable rationale,
narrowly scoped recipe checks, separately named static/config/schema evidence,
target-bound checks, identities, and limitations. Reject credential-bearing
URLs and use approved out-of-band authentication.

Record source approval in an authoritative immutable or append-only
hash-chained external event with approver identity, timestamp/event id,
predecessor, and source and packet digests. Ordinary Git notes are only mirrors
or pointers unless externally anchored; they are not authority alone. Put
later preflight, remediation, deployment, and initialization events in the same
chain. Update and reapprove the rationale when a material decision changes.

Prospective `evolve preflight` writes no workspace receipt, but executing it and
its selected operators is not inherently non-mutating. This repository ships
no trusted containment launcher or allowlist sanitizer, so guided preflight
stops by default. Proceed only after a separate remediation decision provides
both as verified pre-provisioned tools with named executable identity/version
or digest and exact accepted-output schema. The Agent must not improvise them.
Inside that boundary, use the verified direct `evolve` executable, reviewed
source mounted read-only, no ambient credentials or environment files, no
network, and disposable locations for every permitted write and cache.

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:replace-with-your-runtime-digest"

evolve preflight /tmp/my-experiment \
  --recipe-path /read-only/source/my-recipes/my-gepa \
  --seed /absolute/path/to/content-addressed-read-only-target \
  --dataset /absolute/path/to/harbor/tasks
```

The optional `--seed` above is local-only. A remote URL plus full revision or a
built-in resource remains in the source-approved recipe and omits the override.

Before preflight, derive the target manifest from the actual filesystem using
the framework's copy exclusions and symlink semantics, not Git status alone.
Record every included/excluded tracked, staged, unstaged, untracked, and
Git-ignored path; file type, mode, and content digest; and symlink text target
and containment result. Reject unsafe symlinks. For built-ins, recursively
digest the sorted packaged resource tree. Secret-scan every included regular
file byte.

After separately authorized preparation, materialize a local closure as a
content-addressed read-only immutable snapshot, verify its digest, and bind
deployment approval to it. If the framework cannot consume and enforce that
safe snapshot, stop; recompute-then-init against a mutable path is not atomic.
A target byte/layout change invalidates target-bound source checks and source
approval; a semantic target change invalidates architecture too.

Fix every failed check before `evolve init`. After changing a recipe, target,
operator, evaluator asset, image, or dataset membership, initialize a **new**
workspace. Existing workspaces are intentionally frozen experiment records.

The command does not generate a receipt or validate authentication identity,
remote reachability, credential validity, or actual evaluator/runtime
readiness. The named sanitizer captures raw stdout/stderr only inside the
disposable boundary, rejects fields outside its schema, emits sanitized content
only, and destroys raw bytes with the boundary. Post-display redaction is
unsafe. Append the sanitized result and exact source, packet, target, content,
image, runtime, containment, and sanitizer identities to the authoritative
hash chain. Request deployment approval for that exact packet.

Initialize remote Git only from the recipe-pinned revision, local content only
from the approved immutable snapshot, and built-in content only after its
resource digest is revalidated. Before accepting generation zero, require the
copied `target/` manifest (including deterministic framework metadata) to equal
the approved expected post-copy manifest. Verify remote frozen provenance names
the exact revision. A mismatch stops the handoff. Baseline spend requires
separate authority.
