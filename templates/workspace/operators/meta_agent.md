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

Environment feedback is optional. When dependency or runtime uncertainty is
relevant, you may run the protected command `./evolve candidate-smoke --full`
and read its sanitized result artifact. Do not edit the command, evaluator,
Harbor wrapper, lock, or environment machinery, and do not install packages
manually. Full smoke initializes the configured model path but makes no model
request. A smoke failure is evidence to diagnose, not permission to modify
evaluator-owned files.
