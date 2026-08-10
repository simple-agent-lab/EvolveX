# `library/` — reusable operators

The source catalog is organized by fixed lifecycle stage. Every public Python
entry at `library/<stage>/<name>.py` is a named operator; adding a valid file
makes it discoverable without a registry edit. Recipes contain no operator
code. They select a name and provide configuration, and initialization freezes
only the recipe-selected active scripts into `operators/`. The generated
`library/` contains the closed root underscore helper bundle plus the
underscore helper bundle for each selected named stage; unselected public
operators are never copied.

```text
library/
├─ _shared/     shared underscore-prefixed helpers
│  └─ runners/ local · harbor
├─ select/      greedy · newest · pareto · random · score_weighted
├─ rollout/     failure_focused · harbor · noop · parent_evaluation
├─ analyze/     failure_patterns · trace_browser · trajectory_only · …
├─ mutate/      aevolve · ahe · gepa · hyperagents
│  └─ _support/ shared evidence loading
├─ validate/    hyperagents · minibatch_improvement
├─ novelty/     accept_all · diff_similarity
├─ gate/        hillclimb · parent_eligible · ahe_artifact_valid
├─ record/      gepa · hyperagents · jsonl
└─ reflect/     credit
```

Files and directories beginning with `_` are importable helpers and are not
discovered as named operators. Each stage directory also has an `_skeleton.py`
authoring starting point.

## Author and validate an operator

Create a complete SDK entry file from the CLI:

```bash
evolve operator new mutate my_operator
evolve operator describe mutate/my_operator
evolve operator check mutate/my_operator --config '{}'
evolve operator list mutate
```

Every named entry must call `sdk.main` with a configuration validator. Use the
shared helpers to require a JSON object, normalize defaults, and reject unknown
keys:

```python
from library._shared.config import config_object, reject_unknown


def validate_config(raw):
    config = config_object(raw)
    reject_unknown(config, {"mode"})
    return {"mode": config.get("mode", "safe")}


if __name__ == "__main__":
    sdk.main(MyOperator, validate_config=validate_config)
```

Discovery reads only paths. Description and validation execute the entry in a
subprocess, so framework code never imports operator modules in-process.

## Select an operator in a recipe

The binding contains only the name, timeout, and opaque nested config:

```yaml
operators:
  rollout:
    operator: harbor
    timeout_s: 3600
    config:
      path: /path/to/train-tasks
      budget_tasks: 8
      n_concurrent: 2
      max_retries: 1
```

Run `evolve recipe check /path/to/evolve.yaml` before initialization. A named
operator is portable with the source catalog. An explicit `script:` path is an
executable escape hatch but is reported as non-portable.

## Harbor mutation execution

The `aevolve`, `ahe`, `gepa`, and `hyperagents` mutate operators choose an
improvement strategy. Their `runner` config selects a trusted local command or
an isolated Harbor editing agent:

```yaml
operators:
  mutate:
    operator: hyperagents
    timeout_s: 3600
    config:
      runner: harbor
      agent: mini-swe-agent
      model: openai/gpt-5.4
      environment: docker
      editable_roots: [target, operators]
```

See the [mutate operator guide](../docs/guides/mutate-operators.md) for runner
semantics, supported Harbor agent identifiers, adapter configuration, and the
artifact boundary. See [the protocol](PROTOCOL.md) for every stage interface
and output file.
