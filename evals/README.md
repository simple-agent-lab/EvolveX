# Evaluation assets

`evals/` contains reviewable evaluation definitions and recorded result
snapshots for project-owned agents and skills. It is a research and quality
evaluation area, not the evaluator runtime used by a generated Evolve
workspace.

## Current layout

```text
evals/
├── README.md
└── skills/
    └── evolve-agent/
        ├── README.md
        ├── behavior_cases.jsonl
        ├── invocation_cases.jsonl
        ├── rubric.json
        ├── render_prompt.py
        └── *_results.json
```

The current suite evaluates [`skills/evolve-agent/SKILL.md`](../skills/evolve-agent/SKILL.md)
in two ways:

- behavior cases compare an Agent with and without the skill;
- invocation cases check whether a real skill-aware runner loads the skill for
  tasks that need it and skips it for unrelated tasks.

Read [`skills/evolve-agent/README.md`](skills/evolve-agent/README.md) before
adding cases or interpreting a result snapshot.

## Choose the right directory

| Need | Directory |
| --- | --- |
| Test a skill's behavior, routing, or user-visible process change | `evals/skills/<skill-name>/` |
| Test deterministic framework code, invariants, or CLI behavior | `tests/` |
| Configure a runnable evolution method and its target/evaluator | `recipes/` |
| Provide evaluator templates for generated experiment workspaces | `scaffolds/evaluators/` |
| Inspect local generated generations and run artifacts | `runs/` (ignored, never source documentation) |

Keep the subject under test and the evidence boundary explicit in each
evaluation README. New result snapshots must say which skill or revision they
measured, which protocol produced them, and what the evaluation does not prove.

## Adding a new skill evaluation

Create `evals/skills/<skill-name>/` with a README, input cases, a rubric that
the candidate Agents cannot see, and result files that retain the evaluated
revision. Add deterministic shape/integrity checks under `tests/`; those tests
should validate the assets without pretending to run a live Agent grader.
