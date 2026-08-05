"""FROZEN — the irreducible immutable core that keeps the fitness signal honest.

Litmus test for what belongs here: *if evolution rewrote this to cheat, would a
score become a lie?* If yes, it is frozen. Everything else — including the
evolution logic itself (the operators) — is evolvable.

Frozen lives in TWO physical homes, because the evaluator is per-experiment:

  1. Mechanism-side (this package) — the same for every experiment, vendored into
     each workspace, immutable because it sits outside the mutable surface:
       - interfaces.py : the operator contract (types + OPERATORS registry + validation)
       - sdk.py        : the operator contract's runtime (context IO, output validation)

  2. Experiment-side (workspace `evaluator/`, from scaffolds/evaluators/harbor/) — the
     evaluator: eval + splits + score stamping. Frozen because it is excluded from
     the mutable surface AND every eval asserts its tree still matches gen/0
     (a changed evaluator fails the eval). The stamp lives in archive.py
     (STAMPED_FIELDS + tamper-evident eval receipts).

What is NOT frozen: the seed operators/algorithms (library/ + a workspace's
operators/). Those are the *evolvable genome* — the whole point is that the
evolution logic can itself be evolved while evaluation certification remains frozen.
"""
