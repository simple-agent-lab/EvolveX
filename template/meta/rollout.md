# Rollout strategy (paired prose for operators/rollout.py — evolvable)

The dev lane is formative: its purpose is aim-able feedback for mutate, not
scoring. Default failure-focused, budget-capped. Sample as cheaply as you can
— but dev trajectories are also the ONLY source of future training data
(distill, M5), so don't economize down to zero trajectories.
Only ever run the train (dev) split; the gate and sealed splits do not belong
to this lane.
