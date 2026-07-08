# Gate strategy (paired prose for operators/gate.py — evolvable)

Default open: anything that didn't crash is a valid parent — an open-ended
population that delegates elimination to selection weights rather than a hard
gate. Before tightening (hillclimb / elitist+rollback), remember: a gate can
only pollute the population, never the fitness signal (scores and best-ever
are guarded by the frozen side). So err loose; never fake-strict.
