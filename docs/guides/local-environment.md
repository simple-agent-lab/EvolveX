# Local Harbor environment

`evolve.harbor_local:LocalEnvironment` runs Harbor commands directly in the
current host instead of creating a sandbox. Its primary use case is running
short feedback loops against an agent that is already installed and configured
locally—for example, asking Codex to iterate on a skill, prompt, or small piece
of functionality and retaining a normal Harbor trajectory and verifier result.

This removes Docker startup and image-build overhead. It does not replace a
sandbox when tasks are untrusted or depend on the packages and operating system
declared by a Dockerfile.

```yaml
operators:
  rollout:
    operator: harbor
    config:
      environment: evolve.harbor_local:LocalEnvironment
      environment_kwargs: {workdir: /app}
  mutate:
    operator: hyperagents
    config:
      runner: harbor
      environment: evolve.harbor_local:LocalEnvironment
      environment_kwargs: {workdir: /app}
  validate:
    operator: minibatch_improvement
    config:
      environment: evolve.harbor_local:LocalEnvironment

evaluator:
  engine: harbor
  environment: evolve.harbor_local:LocalEnvironment
  environment_kwargs: {workdir: /app}
  n_concurrent: 1
```

Every operator that launches Harbor trials needs its own `environment` entry:
a `validate` stage without one silently falls back to Docker and reports every
child trial as an infrastructure failure. The `gepa_local` recipe ships all of
this preconfigured.

Task directories must satisfy Harbor discovery — `task.toml`,
`instruction.md`, an `environment/` directory (required even though this
backend ignores its Dockerfile), and `tests/test.sh` writing
`$HARBOR_LOGS_DIR/verifier/reward.txt`. `evolve preflight --dataset ...`
checks every entry against the real discovery rule.

Recipe-owned local evaluators can also ship `evaluator/doctor.json`. The
contract declares required task assets, a local runtime hook, and a model-free
smoke command. `./evolve doctor . --profile experiment` checks that contract;
`run`, `eval`, and `retry` repeat it automatically before spending rollout or
judge budget. A contract declaring `backend: local` must bind Harbor's
`LocalEnvironment`, and the evaluator refuses to fall back to Docker when that
binding is missing. Runtime caches are reused, so repeated checks validate the
pinned local renderer without rebuilding it.

Candidate agents must read candidate files through the
`EVOLVE_CANDIDATE_SOURCE` environment variable (see
`seeds/local-smoke/agent.py`), never relative to `__file__`: module import paths
point at the parent candidate during admission minibatch runs, so
`__file__`-relative reads evaluate the wrong candidate.

The same backend can be passed directly to Harbor:

```bash
CODEX_FORCE_AUTH_JSON=1 uv run harbor run \
  -p /absolute/path/to/tasks \
  -a codex \
  -m gpt-5.4 \
  --env evolve.harbor_local:LocalEnvironment \
  --environment-kwarg 'workdir="/workspace"' \
  -n 1
```

Harbor reuses the Codex executable and login already available on the host. A
successful Codex run still produces `agent/trajectory.json`, so it can be
inspected with `harbor view <jobs-dir>`. RSIHub's corresponding EvidenceCase
keeps a workspace-relative path and SHA-256 digest for that ATIF rather than
embedding another complete copy.

The import path is available inside generated workspaces because the mechanism
package is vendored under `.evolve/evolve` and installed by the locked workspace
runtime.

This backend intentionally:

- executes with the current process user and environment;
- ignores Dockerfiles, Compose files, and Harbor mount configuration;
- does not enforce network, CPU, memory, filesystem, or process isolation;
- does not clean or delete caller-owned files or processes on `stop()`.

Harbor's conventional task paths (`/app`, `/logs`, `/tests`, `/solution` on
Linux and their `C:/...` equivalents for Windows tasks) are mapped into
`<trial-dir>/local-environment/`. The host does not need root access and no
Docker daemon is involved. Set `environment.workdir` in the task or
`environment_kwargs.workdir` in `evolve.yaml` to choose the virtual workspace
path.

Harbor commands are translated before execution, but commands spawned inside a
task script are outside that translation boundary. Portable task scripts should
therefore use their current directory for workspace files and these variables
for Harbor-owned directories:

- `HARBOR_WORKDIR`
- `HARBOR_LOGS_DIR`
- `HARBOR_TESTS_DIR`
- `HARBOR_SOLUTION_DIR`
- `EVOLVE_LOCAL_ROOT`

For example, write verifier output to
`$HARBOR_LOGS_DIR/verifier/reward.txt`, not `/logs/verifier/reward.txt`.
Higher concurrency is supported because every trial has its own mapped root,
although task code can still interfere through other caller-owned paths or
shared processes.

Use this backend when the local machine already has everything the task needs.
Use Docker or another isolated Harbor environment for untrusted tasks,
dependency-sensitive benchmarks, sidecars, resource limits, or reproducible OS
images.

## Timing

Harbor records phase timestamps in every trial `result.json`. Use
`agent_execution.started_at` to `agent_execution.finished_at` for the agent's
task execution time, and top-level `started_at` to `finished_at` for total trial
time. Keep both values when comparing environments so setup and verifier
overhead are not attributed to the agent.
