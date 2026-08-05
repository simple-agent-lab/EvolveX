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
That includes Git-ignored files: a local meta-agent can overwrite the
workspace's `.venv`, caches, or other untracked state. Use `runner: harbor` when
the editing agent must not be able to mutate the framework environment.

## `runner: harbor`: isolated agent with artifact return

The Harbor runner builds a disposable writable experiment workspace at
`/app/task/workspace`. Gate visibility is controlled by
`operators.meta_agent.expose_gate_data`, which must be a boolean and defaults to
`false`. Git-ignored host state, including nested `.venv` directories and
caches, is omitted from the disposable copy. A meta-agent may create new
ignored paths inside the task, but they are not imported into the host checkout.

With `expose_gate_data: false`, the task receives the selected parent,
configuration, a clean Git baseline, and the `rollout`, `trace_analyzer`, and
`feedback` inputs from current and prior generations. Evaluator files, task
partitions, archive/receipt records, selection artifacts, gate/record
directories, and gate/sealed evaluations are not copied. The clean Git baseline
supports normal `git diff` and `git status` use without retaining sensitive
paths in object history.

With `expose_gate_data: true`, the task instead receives the full Git history,
evaluator and split files, archive/receipt records, and the retained run tree,
including gate/sealed evaluations. Enable this only for methods whose intended
feedback contract includes those results. The real host workspace is never
mounted in either mode.

The bundled recipes make this choice explicitly. All real recipes use `false`
so gate and sealed data remain held out from mutation. AHE and HyperAgents
still receive their retained training evaluations through the normalized
rollout, trace-analyzer, and feedback inputs.
Harbor returns the complete disposable workspace; the runner compares it with a
trusted pre-run manifest, rejects protected changes, symlinks, and special files,
then transactionally imports configured `editable_roots` and the current
generation's durable artifact namespace. Changes to Git metadata and runtime
evidence are discarded; durable user and prior-generation artifacts are
read-only from the runner's perspective.
AHE imports only `target`; HyperAgents imports `target` and `operators`.

## Durable meta-agent artifacts and handoffs

Every workspace has a gitignored durable area:

```text
artifacts/
├── user/                       # user-supplied context
└── generations/
    └── <genid>/                # arbitrary files from that generation
        └── handoff.md          # optional free-form convention
```

Meta-agents may read the whole tree, but a generation may persist writes only
under `artifacts/generations/<genid>/`. The runner copies the tree into Harbor
and imports only that current namespace; attempted returned edits to `user/` or
prior generations are discarded. Prompts identify `handoff.md` from the selected
parent, when present, as orientation rather than proof. A missing handoff is
normal and non-fatal. Artifact files never become part of a candidate patch.

```yaml
meta_agent:
  variant: hyperagents
  runner: harbor
  expose_gate_data: false
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
- `expose_gate_data`: expose full evaluator/archive/run history, including gate/sealed data (defaults to `false`);
- `editable_roots`: top-level repository trees eligible for transactional import (defaults to `[target]`);
- `model`: model identifier expected by that Harbor adapter;
- `agent_kwargs`: mapping converted to repeated Harbor `--agent-kwarg key=value` flags;
- `agent_env`: mapping converted to repeated Harbor `--agent-env KEY=VALUE` flags;
- `environment`, `image`, `jobs_dir`, `max_retries`, and `timeout_s`.

Harbor 0.18 includes agents such as `codex`, `claude-code`, `aider`,
`gemini-cli`, `mini-swe-agent`, `opencode`, `openhands`, `swe-agent`, and
others. Availability, required credentials, model naming, and adapter kwargs
belong to the installed Harbor version.

For a custom adapter, expose a Harbor `BaseAgent` implementation as an
installable Python package. Add it to the generated workspace's locked runtime
and reference its module directly:

```bash
cd /path/to/workspace
uv add /absolute/path/to/my-agent-package
git add pyproject.toml uv.lock
```

```yaml
meta_agent:
  variant: hyperagents
  runner: harbor
  agent: my_agent.harbor_adapter:MyAgent
  model: my-model
  timeout_s: 3600
```

Harbor and the framework are always launched with `uv run --project
<workspace> --frozen`. `agent_pythonpath`, `PYTHONPATH`, and runtime
`sys.path` edits are no longer supported. A folder containing only an
arbitrary executable is not a Harbor agent adapter; use `local` for that
executable, or package a Harbor adapter class.

`uv --frozen` guarantees that the declared lock is respected; it is not a
filesystem permission boundary. Isolation comes from the Harbor copy-and-import
contract above. Candidate dependency preparation directs `uv sync` to a
temporary environment under the run directory rather than `target/.venv`, and
removes that temporary environment after preparation.

API-key authentication is the default for every agent. Codex agents may instead
use an explicit `CODEX_AUTH_JSON_PATH`; this path takes precedence over
`OPENAI_API_KEY`, and there is no automatic home-directory lookup. Non-Codex
agents do not accept Codex auth files. Credentials are forwarded at runtime and
never written into the recipe, target, retained Harbor command, profile, or
contract. Standard uppercase proxy variables are forwarded unchanged.

## Retained Harbor evidence

Each Harbor meta-agent run retains:

```text
runs/gen-N/meta_agent/harbor/prompt.md
runs/gen-N/meta_agent/harbor/command.json
runs/gen-N/meta_agent/harbor/exec-config.json  # config-driven adapters
runs/gen-N/meta_agent/harbor/harbor.log
runs/gen-N/meta_agent/harbor/trial.json
runs/gen-N/meta_agent/harbor/artifact-manifest.json
runs/gen-N/meta_agent/harbor/jobs/
runs/gen-N/meta_agent/harbor/tasks/
```

On success the active strategy writes the standard `meta_agent/changed.json`,
`patch.diff`, `surface-check.json`, `rationale.md`, and `usage.json` regardless
of the selected runner. AHE may additionally preserve `ahe-report.json`.
