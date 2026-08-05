# This is an Evolve workspace

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
.env                          optional local credentials and endpoint settings
.python-version               pinned Python version
AGENTS.md                     workspace agent entry point
PROTOCOL.md                   human-readable operator contract
README.md                     this workspace guide
archive.jsonl                 append-only lineage ledger
evolve                        workspace console
evolve.yaml                   rendered recipe configuration
library/                      recipe-relevant operator variants
operators/                    active operator scripts, supporting Markdown, and index
program.md                    loop orchestration guidance
pyproject.toml, uv.lock       locked workspace runtime
runs/                         generated per-generation state
artifacts/user/               durable user context
artifacts/generations/        durable per-generation context
skills/evolve-workspace/      workspace operating manual
target/                       seed selected by the recipe
```

The frozen evaluator is generated under `evaluator/`: internal `eval.sh`, `eval.env`,
`agent.env`, `environment.kwargs`, `splits.json`, `dataset.pin`, `runtime.pin`,
`stub_eval.py`, and `engines/local.sh`. Harbor recipes also receive
`cleanup_harbor.py`, `harbor_artifacts.py`, `parse_score.py`, and `smoke.sh`.
Recipes may add selected operator assets and evaluator assets.

The vendored framework includes framework-owned integrations under
`.evolve/evolve/integrations/harbor/`. No standalone Harbor adapter package is
generated at the workspace root.

Commands load local settings only from the project-root `.env`; explicitly
exported environment variables take precedence. Caller and parent `.env` files
are not loaded, and `.env` is ignored by Git.

The minimal setup is `OPENAI_API_KEY=...`. `OPENAI_BASE_URL` is optional for a
custom OpenAI-compatible endpoint. Codex agents may instead use an explicit
absolute `CODEX_AUTH_JSON_PATH`; it takes precedence over the API key, and the
framework never searches `~/.codex/auth.json`. Standard `HTTP_PROXY`,
`HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` values are passed through unchanged.
Do not invoke `evaluator/eval.sh` directly; workspace evaluation prepares its
private runtime input files first.

## Rules

Only paths allowed by `surface` in `evolve.yaml` may evolve. `evaluator/`, the
vendored `.evolve/` runtime, and stamped archive fields are not candidate
inputs. Use `./evolve status`, `./evolve report`, and `./evolve verify` to
inspect the experiment rather than editing its lineage records directly.
