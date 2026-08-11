# Author a custom recipe

Use this playbook after architecture approval selects a code-free custom
composition. A recipe selects existing target, evaluator, runtime, and named
operator contracts; it does not create a second workflow engine or contain
reusable operator code.

## Copy the nearest supported recipe

Start from the supported recipe whose evaluation and operator behavior is
closest to the approved experiment:

```bash
mkdir -p my-recipes
cp -R recipes/gepa my-recipes/my-gepa
```

Preserve its complete structure and change one approved concern at a time. Keep
`evolve.yaml` at the recipe root. Put reusable Python implementations only in
`library/<stage>/<name>.py`; recipe-local operator directories are invalid.
Work in this order: target and mutable surface; qualified evaluator,
partitions, and runtime contract; then operator composition and configuration.
After each phase, run the complete recipe check described below and record the
resulting checkpoint before changing the next concern.

## Keep the rationale durable

Create or update the recipe's `README.md` beside `evolve.yaml`. Record the
goal, target and mutable surface, evaluator qualification and partitions,
selected composition, rejected alternatives, decision packets, assumptions,
risks, limitations, the architecture-approval binding, and source identities.
Before source approval, record a superseding decision instead of silently
rewriting history. Source approval freezes this file; the deployment playbook
owns every later record.

A minimal custom recipe directory is:

```text
my-gepa/
├── evolve.yaml
├── README.md
└── evaluator/        # only approved additional evaluator assets, when needed
```

Keep credentials out of both files. Custom evaluator assets may not replace
framework-owned generated files. Guided authoring rejects every explicit
`script:` binding: select named `operator:` identities only. A user calling the
request expert does not create an escape. This repository supplies no named
external script-review playbook, so stop on `script:`; do not invent equivalent
checks or a one-off approval process. Only a future named external playbook
could define another flow; none is supplied here.

## Resolve the complete composition

Select each named implementation with its stage's `operator:` key. Keep
operator-owned settings under the nested `config:` mapping, stage timeout under
`timeout_s`, and candidate permissions no broader than the recipe's mutable
surface.

Recipe resolution inspects every selected named operator, so first perform the
[static import-safety review](operator-authoring.md). Check the recipe inside
the same credential-free read-only sandbox used for operator describe/check,
using the verified direct pre-provisioned executable:

```bash
evolve recipe check /read-only/source/my-recipes/my-gepa/evolve.yaml --json
```

Fix every selected-operator resolution, normalization, and composition
problem. Rerun the isolated check after the target/surface phase, after the
evaluator/partition/runtime phase, after the operator phase, and once more on
the source-approval identity. Each successful recipe check proves only those
three properties. Record static target and surface review bound to the exact
target digest, operator config/schema checks, evaluator configuration/schema
checks, focused behavior tests, and calibration as separately named source
evidence. Target snapshot, dataset, runtime, destination, and other deployment
inputs remain subject to later prospective preflight; none of these checks
authorizes source or deployment.

For a remote Git target, put both the credential-free URL and full 40-character
immutable `target.revision` in the source-approved recipe. Guided deployment
prohibits a remote Git `--seed` override because the override discards the
recipe revision. A `--seed` override is reserved for a reviewed local immutable
snapshot prepared by the deployment playbook.

## Record the custom-recipe invocation

Record the eventual secret-free preflight command with the custom directory or
its `evolve.yaml` supplied through `--recipe-path`. Do not execute preflight
from this source-authoring phase:

```bash
evolve preflight /absolute/path/to/new-workspace \
  --recipe-path /read-only/source/my-recipes/my-gepa \
  --seed /absolute/path/to/content-addressed-read-only-target \
  --dataset /absolute/path/to/tasks
```

Use `--recipe` only for a repository-shipped recipe name. Never combine it with
`--recipe-path`, and keep the exact recipe, seed, dataset, runtime, and
destination inputs identical when later requesting deployment approval. After
source approval, the [deployment playbook](deployment.md) reruns import-safety
review and executes this command shape inside its credential-free isolation
boundary.

## Present source approval

Present either a clean commit or a complete source-tree manifest/digest with
explicit base, staged, unstaged, untracked, ignored, and exclusion coverage;
the durable `README.md` rationale; machine-readable recipe-check output with
its narrow claim; normalized configuration; static target/surface evidence
bound to the exact target digest; evaluator checks; referenced identities;
focused test and calibration evidence; limitations; exact bytes initialization
would freeze; and a digest of the whole packet.

Source approval covers that reviewed recipe and any approved source changes. It
does not authorize installation, downloads, image builds, credential access,
preflight remediation, initialization, model calls, or baseline spend. Continue
to the deployment playbook only after source approval is durably recorded in an
authoritative immutable or append-only hash-chained event with approver
identity, timestamp/event id, predecessor, and source and packet digests. That
approval freezes `README.md`. Store later events in the same external chain,
not in the recipe. An ordinary Git note may mirror or point to an externally
anchored event but is not authority alone. If a material decision changes the
rationale, or target bytes/layout invalidate target-bound evidence, obtain
renewed source approval; semantic target change also reopens architecture.
