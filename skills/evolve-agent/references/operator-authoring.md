# Author a reusable operator

Use the catalog-inspection and import-safety sections in a writable RSIHub
source checkout while designing the architecture. Inspection gathers evidence;
it does not authorize source changes. Use the scaffolding, implementation, and
composition sections only after architecture approval identifies a capability
that the live catalog does not provide and the user selects new source. Read
`decision-protocol.md` before crossing the source-approval boundary.

This playbook authors named catalog entries only. A `script:` binding is a hard
stop even when the user calls it expert. This repository has no named external
script-review playbook, and these checks must not be repurposed into an ad hoc
bypass.

## Prove the capability gap

Discover the live catalog before reading or writing an implementation:

```bash
evolve operator list --json
```

Catalog listing is filesystem-only. `operator describe` and `operator check`
execute the entry file in a subprocess, and that subprocess inherits the
environment used to launch the CLI. A subprocess boundary is not a security
sandbox. Resolve `evolve` to a verified direct executable in an already-existing
pre-provisioned environment. If it is unavailable, stop for separately approved
environment remediation. Do not invoke an environment manager from the
writable source tree: flags such as `--frozen` and `--no-sync` do not by
themselves prevent cache writes, `.venv` creation, environment-file loading, or
other provisioning side effects. Before inspecting any entry whose imports
have not already been reviewed, use the import-safety and isolation procedure
below. Inside that boundary, inspect the relevant schema:

```bash
evolve operator describe mutate/hyperagents --json
```

Explain why the relevant existing operators and their declared configuration
schemas cannot meet the approved behavior. When realistic, present existing
configuration, adaptation of an existing operator, a new named operator, and
deferral as decision options. Do not start source work until the user selects
the new-source option.

## Scaffold one named catalog entry

The approved capability determines the stage; do not treat `analyze` and
`mutate` as interchangeable:

- An `analyze` operator turns rollout or evaluation evidence into retained
  analysis. Implement `AnalyzeOperator.analyze(checkout, ctx) -> AnalyzeResult`.
- A `mutate` operator changes the candidate from the supplied observation.
  Implement `MutateOperator.mutate(checkout, observation, ctx) -> MutateResult`.

Run the matching scaffold command from the source checkout:

```bash
evolve operator new analyze failure_triage
evolve operator new mutate critic_editor
```

The reusable entry is `library/<stage>/<name>.py`. Recipes select and configure
named entries; they do not contain reusable operator code. Use
underscore-prefixed helpers only for code shared by catalog entries.

Implement the selected stage interface from `evolve.frozen.interfaces` and
return its typed result. Declare every accepted setting once with
`evolve.frozen.config.Config`, including descriptions, defaults, constraints,
and required fields. An approved analysis capability uses its analysis contract:

```python
from evolve.frozen.interfaces import AnalyzeOperator, AnalyzeResult


class FailureTriage(AnalyzeOperator):
    def analyze(self, checkout, ctx) -> AnalyzeResult:
        ...
```

An approved mutation capability uses its mutation contract and schema:

```python
from evolve.frozen import sdk
from evolve.frozen.config import Config, integer, string
from evolve.frozen.interfaces import MutateOperator, MutateResult


CONFIG = Config(
    {
        "mode": string(
            default="conservative",
            choices=("conservative", "aggressive"),
            description="Editing policy for approved critiques.",
        ),
        "max_edits": integer(
            default=1,
            minimum=1,
            description="Maximum edits proposed per mutation.",
        ),
    }
)


class CriticEditor(MutateOperator):
    def mutate(self, checkout, observation, ctx) -> MutateResult:
        ...


if __name__ == "__main__":
    sdk.main(CriticEditor, config_schema=CONFIG)
```

Keep exceptional custom normalization narrow and JSON-compatible. A declarative
schema is the public contract: do not add a second procedural validation path
for the same configuration.

## Review import safety before execution

Read the entry file and every project-local module it imports before running
`describe` or `check`. Import time may define constants, declarative schemas,
classes, and functions, and the guarded `sdk.main(...)` entrypoint may answer
the requested inspection mode. Reject code whose import path performs
application filesystem reads or writes, network access, process or thread
creation, credential or environment-secret access, deployment, model calls, or
any other effect unrelated to returning the inspection payload. An import-time
effect is an authoring failure even if it appears harmless in the current
checkout.

After static review, materialize the exact reviewed source identity into a
disposable inspection copy and mount it read-only in a sandbox or container
with networking disabled. Never execute authored imports from the writable
checkout. Verify that the direct executable's recipe and catalog roots resolve
to that mounted copy, not to the writable checkout or a different install.
Make only a disposable temp tree writable and redirect `HOME`,
`TMPDIR`, bytecode, tool caches, and every other allowed write there. Construct
the environment from an explicit allowlist containing the verified direct
executable path and locale; do not inherit the host environment, load `.env`,
mount auth files, or pass token, key, secret, cloud, proxy, model, or deployment
variables. If this credential-free read-only boundary is unavailable, stop
rather than inspect the entry. The CLI's own subprocess does not provide this
isolation.

## Test behavior, then inspect normalization

Add a focused behavior test for the approved policy. Cover its failure boundary
and assert the stage's typed result; configuration inspection does not replace
this test. Recheck static import safety after the final source edit, then run
the smallest relevant test node and capture catalog evidence inside the same
credential-free, allowlisted isolation boundary:

```bash
evolve operator describe analyze/failure_triage --json
evolve operator check analyze/failure_triage --config '{}' --json
evolve operator describe mutate/critic_editor --json
evolve operator check mutate/critic_editor --config '{}' --json
```

The description records the public schema and the check records the normalized
configuration. Rejecting unsupported or unconstrained configuration is part of
the schema contract, not a reason to permit arbitrary recipe values.

## Compose and approve the source change

Select the named entry under the recipe stage's `operator:` key. Put only
operator-owned values below that stage's nested `config:` mapping, then check
the complete recipe inside the same credential-free isolation boundary:

```bash
evolve recipe check /absolute/path/to/evolve.yaml --json
```

Keep each proof distinct: static transitive import review establishes that the
entry is safe to inspect; `describe` and `check` establish the declared schema
and normalized operator configuration; the focused test establishes operator
behavior; and recipe check establishes selected-operator resolution,
normalization, and composition. Recipe check does not establish target or
surface correctness, evaluator semantics, runtime readiness, or deployment
fitness.

Prepare a source-approval packet containing either a clean commit or a complete
source-tree manifest/digest with explicit base, staged, unstaged, untracked,
ignored, and exclusion coverage; the frozen recipe rationale; static review;
operator description; normalized configuration; focused test; scoped recipe
check; target-digest-bound target/surface evidence; evaluator configuration;
limitations; and a digest of the whole packet. Source approval authorizes that
exact source and packet. It is distinct from prospective preflight and
deployment approval, which bind the selected target, recipe, evaluator,
dataset, runtime, and live-spend boundary before initialization.

Editing the source catalog never changes an existing initialized workspace.
Changed frozen content requires a new workspace and the approvals named by
`decision-protocol.md` must be reconsidered.
