# Glossary

- **Candidate / target** — one version of the agent being improved, stored in a
  workspace's `target/` directory and tracked by its generation commit.
- **Seed** — initial target content selected by `target.seed`. Built-in seeds
  live in `seeds/`; external seeds are copied from the declared local directory
  or Git source during initialization.
- **Scaffold** — generated workspace structure owned by `scaffolds/`, separate
  from the target's evolvable content. Evaluator scaffolds are selected by
  `evaluator.engine`.
- **Integration** — framework-owned runtime behavior for an external system.
  Harbor integrations live under `src/evolve/integrations/harbor/` and travel
  inside the vendored framework runtime.
- **Supported recipe** — one of the public YAML configurations in `recipes/`:
  `aevolve`, `ahe`, `ahe_codex`, `gepa`, `hill_climb`, `hill_climb_codex`,
  `hyperagents`, or `hyperagents_codex`.
- **Test fixture** — deterministic test-only data under `tests/fixtures/`. It
  is not a supported recipe or seed.
- **Evaluator / ruler** — the frozen scoring harness in `evaluator/`. It runs
  candidates and produces the results that the mechanism stamps into the archive.
- **Mutable surface** — the `surface` include/exclude patterns in `evolve.yaml`
  that define candidate-editable paths.
- **Operator** — a subprocess stage in the evolution loop, such as select,
  rollout, meta-agent, gate, or record.
- **Archive / lineage** — `archive.jsonl` plus Git generation tags. Together
  they retain the history of candidates and their stamped outcomes.
- **Workspace** — the generated, standalone Git repository containing a target,
  operators, evaluator, rendered configuration, and vendored framework runtime.
