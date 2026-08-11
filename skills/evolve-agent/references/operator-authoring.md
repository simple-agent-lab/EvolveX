# Author a reusable operator

Use this playbook only in a writable EvolveX source checkout after architecture
approval identifies a capability that the live catalog does not provide. Read
`decision-protocol.md` before crossing the source-approval boundary.

## Prove the capability gap

Discover the live catalog before reading or writing an implementation:

```bash
uv run --frozen evolve operator list --json
uv run --frozen evolve operator describe mutate/hyperagents --json
```

Explain why the relevant existing operators and their declared configuration
schemas cannot meet the approved behavior. When realistic, present existing
configuration, adaptation of an existing operator, a new named operator, and
deferral as decision options. Do not start source work until the user selects
the new-source option.

## Scaffold one named catalog entry

Run the scaffold command from the source checkout:

```bash
uv run --frozen evolve operator new mutate critic_editor
```

The reusable entry is `library/<stage>/<name>.py`. Recipes select and configure
named entries; they do not contain reusable operator code. Use
underscore-prefixed helpers only for code shared by catalog entries.

Implement the selected stage interface from `evolve.frozen.interfaces` and
return its typed result. Declare every accepted setting once with
`evolve.frozen.config.Config`, including descriptions, defaults, constraints,
and required fields. For example:

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

## Test behavior, then inspect normalization

Add a focused behavior test for the approved policy. Cover its failure boundary
and assert the stage's typed result; configuration inspection does not replace
this test. Run the smallest relevant test node, then capture catalog evidence:

```bash
uv run --frozen evolve operator describe mutate/critic_editor --json
uv run --frozen evolve operator check mutate/critic_editor --config '{}' --json
```

The description records the public schema and the check records the normalized
configuration. Rejecting unsupported or unconstrained configuration is part of
the schema contract, not a reason to permit arbitrary recipe values.

## Compose and approve the source change

Select the named entry under the recipe stage's `operator:` key. Put only
operator-owned values below that stage's nested `config:` mapping, then check
the complete recipe:

```bash
uv run --frozen evolve recipe check /absolute/path/to/evolve.yaml --json
```

Prepare a source-approval packet containing the Git diff or commit, operator
description, normalized configuration, focused-test result, recipe-check
output, limitations, and the exact source identity that initialization will
freeze. Source approval authorizes the reviewed source change; it is distinct
from deployment approval, which must bind the selected recipe, evaluator,
dataset, runtime identities, preflight, and live-spend boundary before
initialization.

Editing the source catalog never changes an existing initialized workspace.
Changed frozen content requires a new workspace and the approvals named by
`decision-protocol.md` must be reconsidered.
