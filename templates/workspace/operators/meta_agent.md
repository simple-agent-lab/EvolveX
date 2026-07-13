# Meta-Agent

Improve the MiniSWE source under `target/` by editing source files directly.
Do not solve the benchmark task itself, do not wrap the `mini` CLI, and do not
change evaluator, LLM, Docker, or Harbor configuration.

Use the feedback bundle as evidence. Before changing files, identify:

1. Failure evidence: which task behavior or feedback motivates the edit.
2. Root cause: why the current MiniSWE source likely failed.
3. Targeted fix: the smallest source change that addresses that root cause.
4. Predicted impact: expected fixes and possible regressions.

Prefer general harness improvements over task-specific logic. Before finishing,
run `evolve surface-check` and repair any violations. In your final output, add
`predicted_fixes: [...]` and, when you can name them, `risk_tasks: [...]`.

When runtime uncertainty is relevant, run `./evolve candidate-smoke --full`.
Read its stdout/stderr artifacts, repair the candidate environment with the
candidate's own tools, and rerun smoke. Do not edit evaluator-owned files.
