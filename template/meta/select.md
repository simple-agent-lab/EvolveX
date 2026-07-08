# Selection strategy (paired prose for operators/select.py — evolvable)

Default parent-balancing: high scorers deserve preference, but one champion's
descendants must not flood the population
(p ∝ score_norm × 1/(1+offspring)^α). Before editing this prose or switching
variants, ask: is the current bottleneck "not exploiting enough" or
"diversity collapse"? Check the mean pairwise task_vector distance of the
valid-parent set in the ledger first, then act.
