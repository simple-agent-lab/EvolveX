# Training strategy (paired prose for operators/distill.py + train/recipe.yaml, M5+)

- Data comes from dev trajectories only and must pass the FROZEN/decontam
  stamp — that is an invariant, not a strategy.
- Task-level selection: a successful task trajectory from a failed generation
  is still good data.
- Cap near-duplicate trajectories per task, or the data distribution
  collapses onto easy tasks.
- Trigger training on plateaus (best-ever stagnant for K gens), not on a
  fixed generation count.
- A checkpoint is a candidate, not a deliverable: it goes through canonical
  eval like any mutation and gets eliminated if it scores worse.
