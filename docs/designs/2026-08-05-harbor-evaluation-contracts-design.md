# Harbor Evaluation Contracts

Date: 2026-08-05

## Context

DevBox smoke runs exposed three different classes of issue:

1. A candidate source tree created with a restrictive host umask could not be
   installed by Harbor's runtime user.
2. `EVOLVE_TASK_LIMIT=1` limited Harbor execution to one task while the frozen
   split and score parser still described three tasks.
3. A direct smoke harness passed a bare model name to Harbor, which requires a
   provider-qualified model identifier.

The first two are framework-owned contract failures. The third is caller-owned:
`EVOLVE_HARBOR_MODEL` and Harbor's `--model` accept Harbor model identifiers,
while `OPENAI_MODEL` is Evolve's explicit OpenAI convenience input.

## Goals

- Make a limited evaluation describe, execute, hash, and score one deterministic
  effective task set.
- Transfer candidate source into Harbor without depending on host permissions,
  container UID mappings, or a privileged post-upload `chmod`.
- Preserve the reviewed candidate snapshot and keep recipes and experiment
  scripts free of runtime-specific repairs.
- Fail at the owning boundary with an actionable classification.

## Non-goals

- Guess a provider for bare Harbor model names.
- Introduce a generic artifact transport subsystem for every Harbor adapter.
- Change benchmark scoring, retry policy, or recipe algorithms.
- Make candidate source writable on the host.

## Ownership decisions

### Effective task selection is framework-owned

`EVOLVE_TASK_LIMIT` is a supported evaluation input. The framework must apply
it before recording the runtime selection. Users choose the limit; they do not
coordinate Harbor arguments, task hashes, or expected-trial counts.

### Candidate source portability is framework-owned

The candidate adapter promises to install an exact candidate snapshot in an
isolated Harbor environment. Host umask and container user identity are runtime
details owned by the adapter.

### Harbor model syntax is caller-owned

`EVOLVE_HARBOR_MODEL` remains a provider-qualified Harbor identifier such as
`openai/gpt-5.4-2026-03-05`. `OPENAI_MODEL` remains the convenience input for a
bare OpenAI model name. Evolve must preserve these two meanings rather than
guessing that every bare name belongs to OpenAI.

## Design

### 1. One effective task set

Task limiting moves into split selection. The selector receives the optional
limit and deterministically truncates the already deterministic split order.
It then writes `task-names.txt`, `task-split.json`, and `task_set_hash` from the
limited names.

The same effective members are used by the host evaluation record. Its
`task_set_hash` and `expected_trials` therefore describe the tasks that can
actually produce evidence. Expected trials are:

```text
number of effective tasks * Harbor attempts per task
```

The Harbor engine may retain `--n-tasks` as a defensive cap, but it is not a
second selection mechanism. For a resolved split, its value equals the number
of names already selected. The score parser uses the recorded runtime selection
as the authority. For datasets without a resolved split manifest, it falls back
to the explicit expected-trial value produced by the engine.

Before returning an evaluation record, the framework verifies that the runtime
selection agrees with the host's effective members. A disagreement is an
infrastructure failure, not a partial benchmark result.

This keeps these values aligned:

- selected task names;
- task-set identity;
- Harbor include filters and task count;
- expected trial count;
- score-parser coverage.

### 2. Runtime-user-owned candidate source

The candidate adapter packages the exact reviewed source snapshot into a
temporary archive. Archive member modes are normalized to owner-readable and
owner-writable, with owner execution enabled only for directories and files
that were executable in the snapshot. The original source modes are unchanged.

The transport archive itself is readable by the Harbor runtime. The adapter
uploads that single artifact and extracts it without privilege as the same user
that subsequently runs `uv sync`. Extraction uses no saved host owner, so the
runtime user owns the resulting source tree. The temporary local archive is
removed after upload. The uploaded archive remains owned by Harbor's transport
layer and is removed with the disposable environment; the runtime user does not
mutate or delete uploader-owned artifacts.

Archive construction rejects absolute paths, parent traversal, and symlinks
whose targets escape the candidate tree. Such a tree is candidate-invalid.
Upload or extraction failures are infrastructure failures. Dependency and
candidate-project synchronization retain their existing classifications.

The current world-writable staging-copy helper and post-upload permission
repair are removed. No recipe, script, or container-UID special case is added.

### 3. Model configuration boundary

No automatic normalization is added to `EVOLVE_HARBOR_MODEL` or Harbor's direct
`--model` argument. Generated evaluator configuration continues to emit a
provider-qualified value. When `OPENAI_MODEL` is used, the engine continues to
construct `openai/<name>` explicitly.

Documentation will state this distinction next to the evaluator environment
variables. Errors returned by Harbor remain visible; Evolve will not silently
reinterpret an identifier for a different provider.

## Failure behavior

- A non-positive or malformed task limit is rejected before Harbor starts.
- An empty effective split is rejected as an evaluation configuration error.
- A host/runtime task-selection disagreement is infrastructure-owned and
  produces no benchmark claim.
- An unsafe candidate archive path is candidate-invalid.
- Candidate archive upload or extraction failure is infrastructure-owned.
- A provider-invalid Harbor model remains a caller configuration failure with
  Harbor's original diagnostic.

## Test strategy

Tests are written before the production changes.

1. A resolved three-task split with limit one records one deterministic member,
   executes one task, expects one trial per attempt, and accepts a zero reward as
   a complete evaluation.
2. Limits larger than the split do not inflate expected trials.
3. Multiple attempts multiply the limited member count exactly once.
4. Host evaluation identity and runtime selection agree under a limit.
5. Candidate source beginning with `0700` directories and `0600` files is
   archived without changing the original and extracted through the unprivileged
   runtime path.
6. Archive modes grant write access only through runtime ownership, not through
   world-writable source members.
7. Unsafe archive paths and escaping symlinks are rejected with candidate-owned
   diagnostics.
8. Existing exact agent-role, session metadata, evaluator, and recipe tests stay
   green.
9. DevBox repeats the installed adapter run, candidate installation smoke, and a
   limited real candidate evaluation whose outer status is complete.

## Compatibility and migration

Full evaluations without `EVOLVE_TASK_LIMIT` are unchanged. Limited evaluations
become deterministic and correctly identified; any consumer that previously
treated the full split hash as the identity of a limited run will now receive
the truthful limited-set identity.

The canonical and legacy MiniSWE adapter names are unchanged. Candidate authors
do not need to alter repository permissions or recipes.
