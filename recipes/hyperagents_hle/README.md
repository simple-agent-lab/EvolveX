# HyperAgents on HLE Parity

This recipe preserves the existing HyperAgents method and evaluates each
generation on the 100-task training partition of Harbor's 249-task HLE parity
set. The 49 gate tasks and 100 sealed tasks are not exposed to the evolutionary
loop.

Prepare the gated Harbor task directories independently, then initialize with:

```bash
evolve init /path/to/hyperagents-hle-run \
  --recipe hyperagents_hle \
  --dataset /path/to/hle_parity
```

The local directory must contain exactly the task names recorded in
[`experiments/hle-parity-100-49-100`](../../experiments/hle-parity-100-49-100/README.md).
After initialization, verify that `evaluator/splits.json` matches the shared
`split.json`. Do not commit or redistribute HLE task content.
