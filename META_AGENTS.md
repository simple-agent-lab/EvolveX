# Meta-agent execution

The meta-agent receives rollout-derived feedback and edits the uncommitted child
candidate before canonical evaluation. `variant` selects the improvement strategy;
`runner` selects how that strategy launches its editing agent.

## `runner: local`: arbitrary trusted host command

There is no command catalog or allowlist. The configured string is passed to
`sh -c` with the child checkout as its working directory. The process inherits
the host environment and receives the complete assembled prompt in the temporary
file named by `EVOLVE_PROMPT_FILE`.

Resolution order is:

1. `operators.meta_agent.command`;
2. `EVOLVE_AGENT_COMMAND`;
3. otherwise the operator fails because no concrete agent was selected.

Examples:

```yaml
# Codex
meta_agent:
  variant: hyperagents
  runner: local
  command: codex exec --full-auto - < "$EVOLVE_PROMPT_FILE"
  timeout_s: 3600
```

```yaml
# Claude Code; permission policy should be chosen deliberately for the host.
meta_agent:
  variant: hyperagents
  runner: local
  command: claude -p --dangerously-skip-permissions "Implement the task supplied on stdin." < "$EVOLVE_PROMPT_FILE"
  timeout_s: 3600
```

```yaml
# Any custom executable or script
meta_agent:
  variant: hyperagents
  runner: local
  command: /absolute/path/to/my-agent --prompt-file "$EVOLVE_PROMPT_FILE"
  timeout_s: 3600
```

The command must edit files in its current working directory and exit zero.
Because it is a trusted host command, it can access inherited credentials,
network, Git metadata, and paths outside the candidate. The mutable-surface
repair only constrains observable candidate changes; it is not a host sandbox.

## `runner: harbor`: isolated agent with artifact return

The Harbor runner copies configured repository-relative `editable_roots` into a
generated Harbor Exec task at `/app/candidate`. Harbor returns the complete
bundle; the runner rejects missing or unexpected roots, symlinks, special files,
and out-of-surface changes, then installs every root transactionally. AHE
transports only `target`; HyperAgents transports `target` and `operators`.

```yaml
meta_agent:
  variant: hyperagents
  runner: harbor
  agent: mini-swe-agent
  model: openai/gpt-5.4
  environment: docker
  editable_roots: [target, operators]
  image: ubuntu:24.04       # optional; Harbor defaults to ubuntu:latest
  max_retries: 0
  timeout_s: 3600
```

Useful optional keys are:

- `agent`: Harbor built-in name, `module.path:ClassName`, or supported ACP shorthand;
- `editable_roots`: complete repository trees transported through Harbor (defaults to `[target]`);
- `model`: model identifier expected by that Harbor adapter;
- `agent_kwargs`: mapping converted to repeated Harbor `--agent-kwarg key=value` flags;
- `agent_env`: mapping converted to repeated Harbor `--agent-env KEY=VALUE` flags;
- `agent_pythonpath`: path or list of paths added to the Harbor host process for custom adapters;
- `environment`, `image`, `jobs_dir`, `max_retries`, and `timeout_s`.

Harbor 0.18 includes agents such as `codex`, `claude-code`, `aider`,
`gemini-cli`, `mini-swe-agent`, `opencode`, `openhands`, `swe-agent`, and
others. Availability, required credentials, model naming, and adapter kwargs
belong to the installed Harbor version.

For a custom agent folder, expose a Harbor `BaseAgent` implementation and make
it importable by the Harbor host process:

```yaml
meta_agent:
  variant: hyperagents
  runner: harbor
  agent: my_agent.harbor_adapter:MyAgent
  agent_pythonpath: /absolute/path/to/folder
  model: my-model
  timeout_s: 3600
```

A folder containing only an arbitrary executable is not a Harbor agent adapter;
use `local` for that executable, or add a Harbor adapter class.

Keep credentials in the environment rather than recipe YAML. Harbor's Codex
adapter accepts `OPENAI_API_KEY`, or host `auth.json` when
`CODEX_FORCE_AUTH_JSON=1` is exported. Proxy values are forwarded from the
standard proxy environment or `EVOLVE_HARBOR_*_PROXY` overrides.

## Retained Harbor evidence

Each Harbor meta-agent run retains:

```text
runs/gen-N/meta_agent/harbor/prompt.md
runs/gen-N/meta_agent/harbor/command.json
runs/gen-N/meta_agent/harbor/harbor.log
runs/gen-N/meta_agent/harbor/trial.json
runs/gen-N/meta_agent/harbor/artifact-manifest.json
runs/gen-N/meta_agent/harbor/jobs/
runs/gen-N/meta_agent/harbor/tasks/
```

On success the active strategy writes the standard `meta_agent/changed.json`,
`patch.diff`, `surface-check.json`, `rationale.md`, and `usage.json` regardless
of the selected runner. AHE may additionally preserve `ahe-report.json`.
