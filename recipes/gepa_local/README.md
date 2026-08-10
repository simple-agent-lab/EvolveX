# GEPA, fully local

GEPA over `evolve.harbor_local:LocalEnvironment`: real Harbor trials as local
processes, with no Docker daemon. The default seed is `builtin-local-smoke`, a
deterministic test agent that answers tasks from `target/knowledge.md`; evolving
that document is the optimization problem. Baseline, rollout, validation, and
gate evaluation require neither a model nor network access. A driver-owned
mutation uses an installed local CLI agent and therefore uses that agent's
existing login and network connection.

Swap the seed (`--seed`) and dataset (`--dataset`) to optimize your own
artifact once the loop is familiar. The local environment executes with the
current user and no isolation — use it only with tasks you trust.

The meta-agent uses
`evolve.integrations.harbor.local_auto_agent:LocalAutoAgent`. It discovers the
first installed CLI in this order: Codex, Claude Code, Gemini CLI, OpenCode.
Set `EVOLVE_LOCAL_AGENT=claude-code` (or another supported name) to override the
choice. Each CLI is executed through Harbor's own installed-agent adapter, so
the trial retains a validated ATIF `agent/trajectory.json` instead of an
Evolve-specific trace format. Codex reuses `~/.codex/auth.json` when present;
credentials are copied into the per-trial local root rather than written into
the workspace or run artifacts.

```bash
evolve preflight ws --recipe gepa_local --dataset /path/to/tasks
evolve init ws --recipe gepa_local --dataset /path/to/tasks
cd ws && ./evolve run . --max-generations 0
# With Codex, Claude Code, Gemini CLI, or OpenCode installed:
./evolve run . --max-generations 1
```

Codex defaults to `gpt-5.4` in this recipe. For another CLI that requires an
explicit model, set `operators.mutate.model` in `evolve.yaml`, or provide a
per-agent entry under `operators.mutate.agent_kwargs.model_by_agent`.

## Task directory checklist

Harbor only discovers a task directory when ALL of these exist:

```text
task-name/
├── task.toml          minimal: [metadata] name = "task-name"
├── instruction.md     what the agent is asked to do
├── environment/       required by discovery even when LocalEnvironment
│   └── Dockerfile     ignores it — a stub is fine
└── tests/test.sh      writes the reward: $HARBOR_LOGS_DIR/verifier/reward.txt
```

`evolve preflight --dataset ...` validates every entry against Harbor's real
discovery rule and names the directories that would be silently skipped.

## Candidate contract

An agent must read candidate files through the `EVOLVE_CANDIDATE_SOURCE`
environment variable (see `seeds/local-smoke/agent.py`), never relative to
`__file__` — module import paths point at the parent candidate during
admission minibatch runs, so `__file__`-relative reads silently evaluate the
wrong candidate.

## Admission criterion

`validate` uses `criterion: non_decreasing`: a child that does not regress the
train minibatch is admitted, and the frozen gate evaluation still decides the
champion. Switch to `strict` when you want mutations rejected unless they
improve on optimization data — stronger protection against gate probing, but
it also blocks fixes whose effect is only visible outside the train split.
