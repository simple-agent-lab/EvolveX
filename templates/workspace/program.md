# Evolution Program

Run select, rollout, trace analysis, mutate, commit, eval, gate, and record through the
mechanism verbs. The mechanism writes the feedback bundle (`runs/gen-<id>/
feedback/`) after trace analysis for the mutator to read. The canonical evaluator and
archive are not part of the mutable surface. Mutators should run `evolve
surface-check` before proposing a child so out-of-surface edits are caught early.

## Split contract (evaluator/splits.json)

Three partitions: `train` feeds rollout feedback, `gate` scores the
canonical eval that drives selection, and `sealed` is never selected on and
is evaluated only by configured periodic/final anchors — it guards against
probing the test set. The frozen manifest records exact task names. Harbor
rollout filters to `train`, canonical evaluation filters to `gate`, and sealed
anchor entries are excluded from the feedback bundle.
