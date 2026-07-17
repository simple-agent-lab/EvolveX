# AHE on MiniSWE

This recipe keeps the AHE strategy independent from the target agent. Bounded
current-generation Harbor evidence is converted into one falsifiable harness
hypothesis, and Harbor's installed `mini-swe-agent` CLI edits only `target/**`.

Canonical evaluation is deliberately different: the frozen
`MiniSweSourceAgent` adapter installs the returned candidate source and invokes
its Python API with evaluator-owned model and resource limits. The strict
hill-climb gate retains only score improvements.

```bash
evolve init /path/to/ahe-run --recipe ahe --dataset /absolute/path/to/harbor/tasks
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

Live runs need Docker, Harbor, model credentials, and an immutable evaluator
runtime. The recipe never requires a local Codex command.
