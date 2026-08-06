# Runtime Package and Recipe Demo Design

## Goal

Reduce the number of first-class modules under `src/evolve` by grouping the
existing core runtime modules into one package, and replace the AHE-specific
Terminal-Bench demo with one short runner that can launch any supported recipe.

This is an organizational and usability refactor. It does not change runtime,
evaluation, archive, receipt, authentication, or proxy semantics.

## Runtime package

The four existing modules become:

```text
src/evolve/runtime/
├── __init__.py
├── process.py
├── auth.py
├── config.py
└── environment.py
```

`runtime.py` moves to `runtime/process.py`. The package `__init__.py` re-exports
its stable process and evaluation-attempt APIs so existing imports such as
`from evolve.runtime import OwnedResult` continue to work. Internal users of
private process helpers import `evolve.runtime.process` directly.

`runtime_auth.py`, `runtime_config.py`, and `runtime_environment.py` move to
`runtime/auth.py`, `runtime/config.py`, and `runtime/environment.py`. All
repository-owned imports and tests move to those package paths. No top-level
compatibility shim files remain because retaining them would defeat the
decluttering goal; these three modules are treated as internal interfaces.

`host_runtime.py`, `uv_runtime.py`, and the existing `execution_runtime/`
package remain where they are. Consolidating them would mix distinct concerns
and turn this small structural refactor into an architectural redesign.

## General recipe demo

`scripts/run_terminal_bench_demo.sh` becomes
`scripts/run_recipe_demo.sh`. The first positional argument selects any recipe
in the supported recipe inventory and defaults to `ahe`.

The script exposes only common controls:

- `WORKSPACE`, defaulting to `./runs/<recipe>-demo`
- `TASKS`, defaulting to `3`
- `GENERATIONS`, defaulting to `1`
- optional `DATASET`
- optional `SEED`
- `ENV_FILE`, defaulting to `.env` when that file exists

It passes `--dataset` and `--seed` only when the corresponding override is
present. Recipe-specific defaults and requirements stay in recipe YAML and
recipe documentation; the shell script contains no recipe-name branches.

The same `uv run --frozen` command prefix is used for initialization,
preflight, execution, status, and verification. When `ENV_FILE` exists it is
passed with `--env-file`, allowing `OPENAI_API_KEY` to come from that file.
An explicitly exported environment variable takes precedence. The script
checks for `OPENAI_API_KEY` inside that resolved environment before creating a
workspace and never copies credentials into the workspace.

The demo runs:

1. dependency synchronization;
2. workspace initialization for the selected recipe;
3. model-backed preflight smoke;
4. the requested number of generations with one child per generation;
5. status and archive verification.

The README will show both the default AHE invocation and a second recipe with a
dataset override. Recipe documentation remains the source of truth for image,
dataset, seed, and host-runtime prerequisites.

## Failure behavior

The script retains `set -euo pipefail`. It fails before initialization when the
resolved environment lacks `OPENAI_API_KEY`. Invalid recipe names, unavailable
datasets, missing runtime prerequisites, and failed smoke checks remain errors
from the existing Evolve commands rather than being reimplemented in shell.

## Verification

Tests will verify that:

- public `evolve.runtime` process imports remain available;
- all repository imports use the new runtime package paths;
- runtime, authentication, configuration, and environment behavior is
  unchanged;
- the demo accepts a recipe argument and optional dataset/seed overrides;
- the demo uses an exported key or `ENV_FILE`, requires `OPENAI_API_KEY`, has no
  recipe-specific branches or private machine paths, and remains short;
- README examples use the generalized script.

The full local suite and the focused runtime/demo suites must pass. The exact
committed head will receive a DevBox smoke covering runtime imports, demo
argument construction, and both proxy/no-proxy environment resolution. Existing
real experiment evidence remains valid because this refactor changes import
locations and orchestration inputs, not evaluation behavior.

## Non-goals

- No runtime schema or runtime-consistency redesign.
- No changes to proxy, authentication, evaluation, archive, or receipt policy.
- No automatic recipe-specific dataset preparation or container builds.
- No movement of `host_runtime.py`, `uv_runtime.py`, or `execution_runtime/`.
- No compatibility shims for the former internal module paths.
