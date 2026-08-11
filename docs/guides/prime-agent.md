# Prime Agent

[Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) is a coding
agent built around a **continual harness**: supplemental prompts, memories,
skills and subagent specs that the agent refines itself while it works. The
adapter at `evolve.integrations.harbor.prime_agent:PrimeAgent` runs it against
Harbor tasks and, optionally, pins each run to a specific harness checkpoint so
a chain of harness generations can be measured.

## Running a task

```bash
harbor run \
  -p /path/to/tasks \
  --agent evolve.integrations.harbor.prime_agent:PrimeAgent \
  --model openai-codex/gpt-5.6-sol \
  --agent-kwarg auth_json_path='"/home/you/.prime/agent/auth.json"' \
  --agent-kwarg thinking=medium
```

`auth_json_path` points at the credential store Prime writes on the host
(`~/.prime/agent/auth.json` after `prime-agent` `/login`); the adapter uploads
it into the isolated agent directory it creates per trial. Credentials never
need to be baked into an image.

In a recipe:

```yaml
evaluator:
  engine: harbor
  agent: evolve.integrations.harbor.prime_agent:PrimeAgent
```

## Measuring the continual harness

The adapter isolates Prime's state under `--agent-kwarg agent_dir` (default
`/tmp/prime-agent-dir`), injects a checkpoint before the run and exports the
whole directory afterwards to `<logs>/prime-agent-dir/`:

```bash
  --agent-kwarg auto_refine=true \
  --agent-kwarg harness_state_path='"checkpoints/gen-003/harness_state.json"'
```

Harbor tears every trial container down, so harness state does not survive from
one task to the next on its own — a learning stream has to export after each
episode and inject the result into the next.

Two upstream behaviours are worth knowing before interpreting a result.

**Refinement requires a session.** Prime gates auto-refine on a session-local
harness directory, so a run started with `--no-session` never refines, whatever
`autoRefine` says. The adapter therefore keeps a session when `auto_refine=true`
and stays sessionless otherwise, so a frozen or probe run cannot persist
anything. This matters because a sessionless run still looks completely
healthy — reward, trajectory and exit status are all normal — while producing no
refinement at all.

**The shipped trigger thresholds rarely fire on a benchmark.** Prime defaults to
`turnInterval=25` and a 20 minute cooldown; a task that finishes in a handful of
turns never reaches either. Leave them alone to measure shipped behaviour, or
set them explicitly to measure refinement itself:

```bash
  --agent-kwarg refine_turn_interval=1 \
  --agent-kwarg refine_cooldown_ms=0
```

These are different questions with different answers, so the choice belongs in
the experiment configuration rather than in a default.

Refinement also writes to the **session-local** harness rather than the global
one, so an export contains both the injected parent copy and whatever the
episode produced. Carrying a chain forward means merging them, not picking one:
preferring the global file replays the parent unchanged, and preferring the
session-local file discards everything learned earlier.

## Restricted networks: a pre-baked runtime

By default the adapter installs Node and Prime Agent inside the task container.
Prime's postinstall provisions a Python runtime, which needs unrestricted access
to several release CDNs; where that is unavailable, build the runtime once and
mount it read-only instead:

```bash
docker run --rm -v "$PWD/out:/out" debian:bookworm bash -euxc '
  apt-get update && apt-get install -y curl ca-certificates xz-utils
  export UV_PYTHON_INSTALL_DIR=/opt/prime-runtime/python
  export PRIME_AGENT_KERNEL_VENV=/opt/prime-runtime/kernel-venv
  # …install Node and prime-agent under /opt/prime-runtime…
  tar -C /opt -czf /out/prime-runtime.tar.gz prime-runtime'
```

Build the interpreter and the kernel venv at the paths they will occupy at run
time: a virtualenv bakes absolute paths into `pyvenv.cfg` and its script
shebangs, so one built elsewhere and copied in will not start.

Then mount it and point the adapter at it:

```bash
harbor run \
  --mounts '[{"type":"bind","source":"/srv/prime-runtime","target":"/opt/prime-runtime","read_only":true}]' \
  --agent-kwarg runtime_prefix='"/opt/prime-runtime"' \
  ...
```

`install()` degrades to a version check and the run needs no network for the
agent itself. Pinning the bundle's digest also fixes Node, Prime Agent and the
Python runtime together, which is a stronger guarantee than a version string
when arms of an experiment run on different days.
