# Mutation strategy (paired prose for operators/mutate.py — evolvable)

- Read the dev feedback's failure clusters first; aim mutations at failures,
  don't wander.
- Every generation must state predicted_fixes (which tasks this change should
  fix) — the next generation's reflect will verify them; abandon directions
  that keep being refuted.
- When you rely on a playbook insight, report it honestly in used_insights —
  credit backfill depends on it.
- One hypothesis per generation. The smaller the diff, the cleaner the
  attribution.
- Never touch FROZEN/; don't touch operators/ before M3 either.
