# AHE

AHE treats evolution as adversarial hardening: run the current Codex target on
the frozen train split, give concrete failures to a Codex mutator, and retain a
candidate only when its gate score does not regress. The sealed split remains
hidden until the final anchor evaluation.

`children_per_gen: 1` makes a single proposed hardening step per round.
`surface.include: target/**` evolves the agent scaffold only.
`select.variant: greedy` chooses the strongest eligible archive parent.
`target.seed: builtin-codex` exposes prompt, skills, and Codex policy as the genome.
`rollout.variant: harbor` gathers bounded train-split failure evidence.
`trace_analyzer.variant: failure_patterns` independently clusters
verifier-grounded failure signatures and retains passing behaviors for the
modify agent; other trace views are documented in
[`TRACE_ANALYZER.md`](../../TRACE_ANALYZER.md).
`mutate.variant: agent_command` runs the host Codex CLI in the candidate checkout.
`gate.variant: hillclimb` rejects gate-score regressions.
`evaluator.engine: harbor` supplies pass/fail reward evidence.
`sampling: static` keeps the gate task set fixed across generations.
`n_concurrent: 4` limits simultaneous container setup pressure.
`agent_setup_timeout_multiplier: 3` allows up to three times Harbor's default setup timeout.
`max_retries: 1` retries transient setup and network failures once.
Each enabled operator has an explicit timeout: 3600 seconds for the long-running
`rollout` and `mutate` stages, and 600 seconds for `select`, `trace_analyzer`,
`gate`, and `record`.
The top-level `operators.timeout_s: 600` remains the fallback for newly added operators.

## Run

```bash
evolve init /path/to/ahe-run --recipe ahe --dataset /absolute/path/to/harbor/tasks
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

The host must have `docker`, `harbor`, and `codex` on `PATH`. Authentication
must use exactly one of these paths:

```bash
# API authentication
export OPENAI_API_KEY=...

# Or an existing ChatGPT/Codex CLI login
codex login
export CODEX_FORCE_AUTH_JSON=1
```

`OPENAI_BASE_URL` is required only for a compatible custom endpoint.
`EVOLVE_HARBOR_MODEL` overrides the inner target model; otherwise
`target/codex.toml` supplies it. `DOCKER_HOST` is normally unnecessary on
Linux; set it only when Docker uses a non-default socket such as Colima.

## Operator Routing

`select: {variant: greedy}` resolves to [`library/select/greedy.py`](../../library/select/greedy.py).
`rollout: {variant: harbor, budget_tasks: 1, ...}` resolves to [`library/rollout/harbor.py`](../../library/rollout/harbor.py).
`trace_analyzer: {variant: failure_patterns, ...}` resolves to [`library/trace_analyzer/failure_patterns.py`](../../library/trace_analyzer/failure_patterns.py).
`mutate: {variant: agent_command, ...}` resolves to [`library/mutate/agent_command.py`](../../library/mutate/agent_command.py).
`gate: {variant: hillclimb}` resolves to [`library/gate/hillclimb.py`](../../library/gate/hillclimb.py).
`record: {variant: jsonl}` resolves to [`library/record/jsonl.py`](../../library/record/jsonl.py).
