# AHE

AHE runs the current Codex target on the frozen train split, distills concrete
failures through the trace analyzer, and gives that evidence to the framework's
meta-agent. The gate retains only non-regressing candidates, while the sealed
split is reserved for the final anchor evaluation.

```bash
evolve init /path/to/ahe-run --recipe ahe --dataset /absolute/path/to/harbor/tasks
cd /path/to/ahe-run
./evolve run . --max-generations 1
```

The host needs `docker`, `harbor`, and `codex` on `PATH`, plus valid Codex/OpenAI
authentication.
