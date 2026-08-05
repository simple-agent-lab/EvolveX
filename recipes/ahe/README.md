# AHE on Terminal-Bench 2.0

This recipe keeps the AHE strategy independent from the target agent. It uses
the local `terminal-bench-2-10-10-10` dataset. Workspace initialization freezes
all 30 curated instances as one optimization set without synthesizing train,
gate, and sealed partitions. Each candidate is evaluated on those same 30 tasks
with one trial per task. That certified evaluation is replayed as the next AHE
debugger input, so its score
and debugger evidence come from the same retained Harbor trajectories rather
than a separate rollout run. Each task receives one required LLM debugger
analysis using the same model and runner as the meta-agent. The debugger uses
`high` reasoning so its short MiniSWE protocol reliably reaches the required
tool call; the change-producing meta-agent also uses `high`. Both paths receive
an explicit 64k output budget through Harbor's `max_tokens` constructor field
because mini-swe-agent otherwise uses its 1,000-token default. Failures
stop the generation after three attempts; there is no silent deterministic
fallback.

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

Generation 0 and generations 1 through 10 use the same frozen 30-task
optimization set. The gate operator decides parent eligibility from that
evaluation; it does not invoke a separate task partition. The evaluator is
frozen with capacity for 10 workers; set
`EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=5` for a five-worker generation-1 smoke,
then omit the override for the full run.
Candidate execution uses Harbor's native task timeouts
(`agent_timeout_multiplier: 1`).

```bash
export HARBOR_TASKS="/absolute/path/to/terminal-bench-2-10-10-10"
cd /path/to/simple-evolve-agent
evolve init /path/to/ahe-run --recipe ahe --dataset "$HARBOR_TASKS"
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

Live runs need Docker, Harbor, and model credentials. Build the small
meta-agent image once before running:

```bash
docker build --build-arg MINISWE_VERSION=2.4.5 \
  -t evolve-meta-agent-app:20260724-tools-mswe245 containers/meta-agent
```

The recipe never requires a local Codex command.
