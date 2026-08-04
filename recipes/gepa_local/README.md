# GEPA, fully local

GEPA over `evolve.harbor_local:LocalEnvironment`: real Harbor trials as local
processes — no Docker daemon, no model key, no network. The default seed is
`builtin-local-smoke`, a deterministic test agent that answers tasks from
`target/knowledge.json`; evolving that file is the optimization problem, which
makes this recipe the fastest way to exercise the full evolution loop
(baseline → rollout → mutation → validate → gate) end to end on one machine.

Swap the seed (`--seed`) and dataset (`--dataset`) to optimize your own
artifact once the loop is familiar. The local environment executes with the
current user and no isolation — use it only with tasks you trust.

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-run"
evolve preflight ws --recipe gepa_local --dataset /path/to/tasks
evolve init ws --recipe gepa_local --dataset /path/to/tasks
cd ws && ./evolve run . --max-generations 0
```

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
