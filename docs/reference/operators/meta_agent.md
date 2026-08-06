# Meta Agent

`meta_agent` converts observations into candidate edits. It is required and may
change only paths permitted by both `editable_roots` and the recipe's mutable
surface.

## Contract

```python
class MetaAgentOperator:
    def run(self, checkout, observation, ctx) -> MetaAgentResult: ...
```

The result contains changed paths, notes, and usage.

## Variants

| Variant | Mutation strategy |
| --- | --- |
| `aevolve` | distill recent task observations into prompt, skill, memory, or tool updates |
| `ahe` | make one testable agent-harness change from current evidence |
| `gepa` | reflect on configured components and propose a component edit |
| `hyperagents` | self-referential mutation that may co-evolve target and selected operator policy |

## Runner configuration

`variant` chooses the mutation strategy. `runner` chooses how its editing agent
is launched.

```yaml
operators:
  meta_agent:
    variant: gepa
    runner: harbor
    expose_gate_data: false
    agent: codex
    model: gpt-5.4
    environment: docker
    image: evolve-meta-agent-codex:20260805-codex0145
    editable_roots: [target]
    max_retries: 1
    timeout_s: 3600
```

- `runner: local` executes a trusted host command.
- `runner: harbor` creates an isolated writable copy and transactionally
  imports allowed returned files.
- `editable_roots` does not expand `surface.include`.
- `expose_gate_data` defaults to `false`; keep it false for disjoint mutation
  and protected evaluation.

Variant-specific path keys include `components`, `prompt_path`, `skills_dir`,
`memory_dir`, and `tools_dir`.

## Artifacts

Standard outputs include:

```text
runs/gen-N/meta_agent/changed.json
runs/gen-N/meta_agent/patch.diff
runs/gen-N/meta_agent/surface-check.json
runs/gen-N/meta_agent/rationale.md
runs/gen-N/meta_agent/usage.json
```

Harbor runs additionally retain prompt, command, trial, artifact manifest,
jobs, and tasks under `runs/gen-N/meta_agent/harbor/`.

See [Meta-agent execution](../../guides/meta-agents.md) for runner semantics,
artifact handoffs, authentication, and custom Harbor adapters.

