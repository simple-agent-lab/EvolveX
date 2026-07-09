# The five invariants (shared reference)

Enforced, not documented-and-hoped. Everything else in a workspace is open to
evolution; these are not. Full rationale in `DESIGN.md` §3.

1. **The ruler never moves.** `evaluator/eval.sh` (and the engine it calls) never
   changes inside the loop — one ruler, all generations.
2. **Scores enter only via the frozen stamp.** Operators and agents never pass a
   score; `record` has no score argument. Frozen fields come only from
   `runs/gen-<id>/stamp.json`.
3. **best-ever is recomputed by a frozen rule**, and a champion change requires
   a replication re-eval.
4. **Training data never contains gate/sealed tasks** and never comes from
   audit-flagged generations.
5. **Checkpoints enter the lineage only through canonical eval.** A checkpoint
   is a candidate; training is a variation operator; the same ruler scores it.
