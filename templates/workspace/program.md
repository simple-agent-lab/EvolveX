# Evolution Program

Run select, rollout, meta_agent, commit, eval, gate, and record through the
mechanism verbs. The rollout writes its summary to
`runs/gen-<id>/rollout/summary.json` for the meta-agent to read. The canonical
evaluator and archive are not part of the mutable surface. Meta-agents should
run `evolve surface-check` before proposing a child so out-of-surface edits are
caught early.

## Split contract (evaluator/splits.json)

Three partitions: `train` feeds rollout feedback, `gate` scores the
canonical eval that drives selection, and `sealed` is never selected on and
only ever evaluated on human request — it guards against probing the test
set. Rollout must only use `train`; the gate score must only come from
`gate`. (Task-level enforcement of these partitions lands with the Harbor
task-partitioning wiring; today the split shape is reserved and honored by
convention.)
