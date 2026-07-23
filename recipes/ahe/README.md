# AHE on Terminal-Bench 2.0

This recipe keeps the AHE strategy independent from the target agent. It uses
the local `terminal-bench-2-10-10-10` dataset. Workspace initialization freezes
disjoint 10-task train, gate, and sealed partitions with seed 0. The train
partition is the optimization set: each candidate is evaluated on those same
10 tasks with one trial per task. That certified evaluation is replayed as the
next AHE debugger input, so its score
and debugger evidence come from the same retained Harbor trajectories rather
than a separate rollout run. Each task receives one required LLM debugger
analysis using the same model configuration as the meta-agent. Failures stop
the generation after three attempts; there is no silent deterministic fallback.

The MiniSWE target is pinned to commit
`388da74aad620a384ab47669b17c52133e30e7c3`, whose checked-in `uv.lock` is part
of the candidate runtime contract. Because upstream does not track that lock,
workspace initialization generates and freezes it explicitly.

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

Generation 0 and generations 1 through 10 use the same frozen optimization
set. The configured gate partition is unused during evolution, and sealed
tasks remain isolated from meta-agent feedback. The evaluator is frozen with
capacity for 10 workers; set `EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=5` for a
five-worker generation-1 smoke, then omit the override for the full run.

```bash
cd /path/to/simple-evolve-agent
evolve init /path/to/ahe-run --recipe ahe
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

Live runs need Docker, Harbor, model credentials, and an immutable evaluator
runtime. Build the small workspace image once before running:

```bash
docker build -t evolve-meta-agent-app:ubuntu-latest containers/meta-agent
```

The recipe never requires a local Codex command.
