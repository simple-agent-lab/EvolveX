# Evolution Program

Use either `./evolve run .` to run the driver or let the outer agent
orchestrate one generation. In the latter mode, run `operator list`, then
invoke configured select, rollout, and trace-analyzer capabilities with
`operator run`. Read their files under `runs/gen-<id>/`, form a hypothesis, and
edit the child worktree directly. `mutate` is optional when the outer agent
owns the mutation.

When an evaluator returns natural-language feedback, read
`analyze/feedback.md` and the `Feedback.natural_language_feedback` fields
in the reflective evidence before forming the hypothesis. Treat the protocol's
binary completion reward as execution bookkeeping, not as the quality judgment.

All state transitions still go through the mechanism: fork the selected parent,
surface-check the child, run every configured `validate` and `novelty` operator,
commit it, evaluate the exact tag, then call `finalize` to apply gate and
record. Admission results are bound to the candidate tree; edit again and they
must be rerun. The canonical evaluator and archive are not part of the mutable
surface. Never write their fields manually, and do not start the unattended
driver while an Agent child worktree is open.

## Split contract (evaluator/splits.json)

Three partitions: `train` feeds rollout feedback, `gate` scores the
canonical eval that drives selection, and `sealed` is never selected on and
only ever evaluated on human request — it guards against probing the test
set. Rollout must only use `train`; the gate score must only come from
`gate`. (Task-level enforcement of these partitions lands with the Harbor
task-partitioning wiring; today the split shape is reserved and honored by
convention.)
