# Target-Required Broad-Surface HyperAgents Design

## Goal

Run a new HyperAgents experiment in which the meta-agent may still modify the full approved surface (`target/**` and `operators/**`), but every generation must make a substantive target change that can directly affect the benchmark.

## Motivation

The stopped broad-surface run produced one target-modification generation and then concentrated on operator-only changes. Because the target tree remained identical, later training-score variation was evaluation noise rather than evidence of target improvement. The next experiment should correct this search incentive without adding a new scheduling or credit-assignment framework.

## Design

Start from the clean pre-evolution broad-surface seed, not from any evolved candidate in the stopped run. Preserve the existing surface policy:

```yaml
surface:
  include:
    - target/**
    - operators/**
```

Change only `operators/meta_agent.md`. The strategy will retain the existing HyperAgents self-modification guidance and add these requirements:

1. The benchmark directly evaluates `target/**`.
2. Every proposal must include at least one substantive `target/**` change intended to improve downstream task performance.
3. `operators/**` remains editable, including the meta-agent itself, but operator changes should accompany—not replace—the target improvement.
4. Re-evaluating an unchanged target cannot establish improvement and should be avoided.
5. The proposal remains one coherent repository change whose complete patch is inherited by descendants.

No Python operator implementation, evaluator, selector, rollout, validator, gate, recorder, or outer-driver code will be changed for this correction.

## Verification

First run the existing candidate smoke/doctor checks for the modified clean seed. Then run a fresh 3-task, 3-generation smoke experiment.

The smoke passes only if:

- all three generated candidates pass the existing surface and validation checks;
- every generation changes at least one path under `target/**`;
- no generation is operator-only;
- operator changes remain permitted and are recorded if the meta-agent chooses them;
- each evaluated generation uses the candidate target tree recorded for that generation;
- all smoke artifacts and target-tree hashes are preserved.

If the prompt-only smoke fails because a generation is operator-only, stop and report that evidence before adding a hard validation rule. Do not silently introduce more framework machinery.

## Full Run

If the smoke passes, create a fresh experiment root and reuse the previously fixed, non-overlapping 30-train and sealed 30-test task lists. Run 20 generations with one child per generation and 10 evaluator workers. Keep the held-out list sealed until the best valid canonical training candidate is recorded. Then run exactly one isolated 30-task held-out evaluation and audit the artifacts.

The stopped experiment remains immutable as a diagnostic artifact and is not used as a parent or seed for the new run.
