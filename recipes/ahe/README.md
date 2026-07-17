# AHE on MiniSWE

This recipe keeps the AHE strategy independent from the target agent. Each task's
bounded Harbor traces receive one required LLM debugger analysis using the same
model configuration as the meta-agent. Failures stop the generation after three
attempts; there is no silent deterministic fallback.

Canonical evaluation is deliberately different: the frozen
`MiniSweSourceAgent` adapter installs the returned candidate source and invokes
its Python API with evaluator-owned model and resource limits. A required change
manifest links every target edit to debugger evidence and predicted effects. The
newest valid generation remains the next parent even after a score regression,
allowing the following generation to attribute it and choose KEEP, REVISE, or
ROLLBACK + PIVOT.

```bash
evolve init /path/to/ahe-run --recipe ahe --dataset /absolute/path/to/harbor/tasks
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

Live runs need Docker, Harbor, model credentials, and an immutable evaluator
runtime. Build the small workspace image once before running:

```bash
docker build -t evolve-meta-agent-app:ubuntu-latest containers/meta-agent
```

The recipe never requires a local Codex command.
