# Running EvolveX Reliably

Use the lightweight checks for local skill and plugin iteration. Use the
experiment checks before a real multi-generation benchmark run.

Load the same credentials, endpoint, runtime identity, proxy, and storage
settings for initialization and every resumed command. See
[Environment Variables](../reference/environment-variables.md) when a command
cannot reach the model, Docker-host service, cache, or experiment state.

## Local skill or plugin iteration

```bash
evolve doctor /path/to/candidate --profile local
evolve smoke /path/to/workspace --profile local
```

The local doctor checks the Codex CLI and login, plugin/hook layout, and local
workspace capacity. Add `--probe-model` when you want a real Codex request; the
default is cheap and does not consume model quota. Codex CLI may use a ChatGPT
login from `CODEX_HOME/auth.json`; an API key is not required.

The local backend is trusted and in-process. It is suitable for prompt, skill,
hook, and small feature iteration, but it does not provide Docker isolation or
resource enforcement.

## Long-running experiment preflight

```bash
evolve doctor /path/to/experiment --profile experiment --probe-model
evolve smoke /path/to/experiment --profile experiment --task TASK_NAME
```

The experiment doctor additionally verifies:

- the fixed evaluator, task-set, and runtime identity;
- local task content digests;
- the immutable evaluator runtime pin;
- Docker daemon and Compose availability;
- free workspace and Docker storage;
- a real host-to-container bind-mount round trip.

The experiment smoke clones the workspace under
`runs/experiment-smoke/attempt-N/workspace`, reduces the run to one task and one
child, and requires a complete gen0-to-gen1 lineage whose tag resolves to the
recorded candidate commit. It does not write candidates or scores into the
source experiment.

## Execution runtime

Recipes declare the host execution backend separately from the candidate's
Python dependency runtime:

```yaml
execution_runtime:
  backend: docker
  minimum_free_gib: 80
  # docker_host: ssh://builder.example
  # compose_command: [docker, compose]
```

Resolution precedence is explicit `docker_host`, `DOCKER_HOST`,
`DOCKER_CONTEXT`, then platform discovery. Linux supports the system socket and
rootless `$XDG_RUNTIME_DIR/docker.sock`; macOS supports Colima and Docker
Desktop sockets. Keep the workspace and dataset on a path visible to the Docker
daemon. On remote daemons and Docker Desktop, the doctor cannot read daemon
volume capacity directly and reports the manual check instead.

## Dataset preparation

Never substitute a similarly named local directory for a recipe dataset. Set up
the shared content-bound Terminal-Bench subset and selected recipe image with:

```bash
./scripts/setup_terminal_bench.sh ahe
./scripts/run_recipe_demo.sh ahe
```

To download the complete upstream Harbor dataset without preparing the pinned
EvolveX subset, export it directly:

```bash
uv run --frozen harbor download terminal-bench@2.0 \
  --export \
  -o /absolute/path/to/terminal-bench-2
```

`evolve init --dataset ...` writes the selected task names and content digests
into `evaluator/splits.json`. A canonical attempt also writes `run-plan.json`;
the Harbor launcher and score parser consume that same plan, so task selection,
expected trial count, generation commit, and runtime identity cannot drift
between configuration layers.

## Failure recovery

```bash
evolve status /path/to/experiment
evolve retry /path/to/experiment GENID
evolve repair /path/to/experiment
```

`status` reports the latest generation status and failing operator stage.
`retry` creates a new certified evaluation attempt even after a terminal
infrastructure or candidate failure; it does not overwrite prior evidence.
`repair` is the only command that cleans interrupted driver state such as stale
worktrees. `doctor` is a preflight and does not repair the workspace.

Keep failed attempts and their `runs/evaluations/.../run-plan.json`, logs, task
vector, and artifact index. Compare generations only when their stamped
evaluator, task-set, runtime, and candidate-commit identities agree.
