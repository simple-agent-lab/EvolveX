# This is an EvolveX workspace

This directory is an independent Git repository. Each candidate generation is
a commit tagged `gen/<id>`; `archive.jsonl` records the append-only lineage.
Run the workspace through `./evolve`.

## Files created by `evolve init`

Every workspace receives these files or directories:

```text
.evolve/                     vendored framework runtime and launchers
.evolve-components.json       derived recipe, seed, engine, and integration manifest
.evolve-protocol-version      workspace protocol marker
.gitignore                    ignores generated state
.python-version               pinned Python version
AGENTS.md                     workspace agent entry point
PROTOCOL.md                   human-readable operator contract
README.md                     this workspace guide
archive.jsonl                 append-only lineage record
evolve                        workspace console
evolve.yaml                   rendered recipe configuration
library/                      recipe-relevant operator variants
LICENSE.evolvex               license for the vendored framework and operator library
NOTICE.evolvex                framework and third-party attribution notices
operators/                    active operator scripts, supporting Markdown, and index
program.md                    loop orchestration guidance
pyproject.toml, uv.lock       locked workspace runtime
runs/                         generated per-generation state
artifacts/user/               durable user context
artifacts/generations/        durable per-generation context
skills/evolve-agent/          method guide and workspace operating manual
target/                       seed selected by the recipe
```

The frozen evaluator is generated under `evaluator/`: `eval.sh`, `eval.env`,
`agent.env`, `environment.kwargs`, `splits.json`, `dataset.pin`, `runtime.pin`,
`stub_eval.py`, and `engines/local.sh`. Harbor recipes also receive
`cleanup_harbor.py`, `harbor_artifacts.py`, `parse_score.py`, and `smoke.sh`.
Recipes may add selected operator assets and evaluator assets.

For a local dataset, `splits.json` and `dataset.pin` bind both split membership
and each task tree's paths, bytes, file types, and modes. If those contents
change, canonical evaluation stops and requires a newly initialized experiment.
Legacy version-1 local split manifests are inspection-only.

The vendored framework includes framework-owned integrations under
`.evolve/evolve/integrations/harbor/`. No standalone Harbor adapter package is
generated at the workspace root.

The vendored framework runtime and operator library are provided under
Apache-2.0; see `LICENSE.evolvex` and `NOTICE.evolvex`.
The target under `target/` retains its own upstream licensing terms.

## Rules

Only paths allowed by `surface` in `evolve.yaml` may evolve. `evaluator/`, the
vendored `.evolve/` runtime, and stamped archive fields are not candidate
inputs. Use `./evolve status .`, `./evolve report .`, and `./evolve verify .` to
inspect the experiment rather than editing its lineage records directly.
