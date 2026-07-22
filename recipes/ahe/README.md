# AHE on Terminal-Bench 2.0

This recipe keeps the AHE strategy independent from the target agent. Each
candidate is evaluated on the complete 89-task Terminal-Bench 2.0 dataset with
two trials per task. That certified evaluation is replayed as the next AHE
debugger input, so its score and debugger evidence come from the same retained
Harbor trajectories rather than a separate rollout run. Each task receives one
required LLM debugger analysis using the same model configuration as the
meta-agent. Failures stop the generation after three attempts; there is no
silent deterministic fallback.

Canonical evaluation is deliberately different: the frozen
`MiniSweSourceAgent` adapter installs the returned candidate source and invokes
its Python API with evaluator-owned model and resource limits. The prompt asks
for a change manifest linking target edits to debugger evidence and predicted
effects, but that manifest is best-effort metadata: a missing or malformed block
does not discard an otherwise surface-valid patch. The raw response, changed
paths, and patch are preserved and passed to the next meta-agent; predicted-fix
and risk attribution is used only when available. The newest valid generation
remains the next parent even after a score regression, allowing the following
generation to attribute it and choose KEEP, REVISE, or ROLLBACK + PIVOT.

Generation 0 and generations 1 through 10 are all evaluated on the same full
benchmark. The resulting 89-task learning curve measures optimization on
Terminal-Bench 2.0; it is not a held-out generalization result and has no final
sealed anchor.

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
