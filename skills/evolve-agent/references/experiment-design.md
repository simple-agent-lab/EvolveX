# Design an evolution experiment

Use this playbook before writing a recipe, operator, evaluator asset, or workspace. Read `decision-protocol.md` first. Ask one focused question at a time; prefer choices only after enough evidence exists to explain them.

## Classify the starting context

- In an initialized workspace, stop source authoring and use `workspace-contract.md`.
- In an EvolveX source checkout, keep authoring on an isolated branch or worktree and preserve unrelated changes.
- In an external target project, treat it as the candidate and locate a writable EvolveX source checkout. Do not clone or modify an installed package without approval.
- If evidence is insufficient, ask for the target or checkout location rather than guessing.

State the evidence for the classification.

## Establish the experiment brief

Name the target, mutable surface, protected paths, desired behavior, observed failures, frozen evaluator, optimization/gate/sealed partitions, candidate budget, concurrency, timeouts, cost boundary, execution boundary, credentials mode, baseline requirement, and evidence required for acceptance and claims.

Write confirmed choices, assumptions, and limitations into the custom recipe `README.md`. Do not encode credentials in the recipe or rationale.

## Design evaluation before optimization

Inspect existing evaluation assets before selecting a method. Present a decision packet with these choices when relevant:

1. Configure existing evaluation assets.
2. Author a Harbor-compatible evaluation when isolated tasks can express the desired behavior.
3. Develop a new evaluator engine only when a named execution or scoring requirement does not fit Harbor, or the user selects it after reviewing its larger trusted-framework cost.

This delivery implements option 1. For option 2, stop after the approved evaluation design and route to the Harbor evaluation-authoring project. For option 3, stop after the decision and require a separate evaluator-engine design and threat review. Do not initialize an experiment with an unvalidated measurement contract.

Use `scientific-foundations.md` when evaluator semantics, partitions, acceptance rules, or claims are being defined or changed.

## Compare composition options

Read only the method cards supported by the available evidence. Present the nearest supported recipe, a code-free custom composition when needed, and deferral when the evaluator or target contract is incomplete. Explain the evidence each method consumes, the paths it may change, and the claims it can support.

Inspect the live operator catalog before claiming that custom source is needed. Do not use file presence in an initialized workspace as the source catalog.

## Record the architecture decision

Before source work, present architecture approval bound to the target, evaluation identity, partitions, recipe composition, proposed custom operator gaps, mutable surface, runtime, budget, risks, unknowns, and recipe rationale.

Do not initialize, build external assets, call models, or implement source before the user approves this exact architecture. A changed measurement contract returns the workflow to evaluation design.
