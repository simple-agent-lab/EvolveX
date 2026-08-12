# Scientific foundations and evidence

Read this reference when defining a new experiment, changing evaluator or data
semantics, or making a research claim from an evolution run.

## Load theory and implementation progressively

1. Read the current project's experiment model and trust-boundary documentation.
2. Read its operator or method contract before changing interfaces or write
   scopes.
3. Read the selected method's rationale and executable configuration.
4. Trace configuration values to the live implementation only when explaining,
   debugging, or adapting behavior.
5. Read the current workspace's source, configuration, and stamped artifacts
   before making claims about a concrete run.

Use repository search and the project's own discovery interfaces to find these
resources. Do not encode current backend names, source paths, or method wiring
into the experiment methodology.

## Define the experiment contract

Define before mutation:

- target and mutable surface;
- optimization objective and frozen evaluator, including score direction,
  domain and units, aggregation and weighting, missing/failure handling,
  thresholds, tie behavior, and acceptance semantics;
- task identities and optimization, gate, and sealed semantics;
- candidate budget, concurrency, timeouts, and cost boundary;
- parent and champion selection rules;
- evidence required to accept, reject, or replicate a candidate.

Do not change the evaluator or task split mid-run and compare the new score with
the old lineage. Start a new experiment when the evaluator changes.

## Bound claims

Distinguish setup smoke, optimization performance, held-out gate performance,
and sealed transfer. A successful mutation shows improvement only under the
evaluation scope actually executed. Preserve failed candidates, task coverage,
runtime identity, decisions, and retained evidence so the result can be audited.

## Completion check

Before mutation, every experiment-contract field above has one declared value.
Before reporting, every claim names its evaluation partition and points to a
retained candidate identity, runtime identity, decision, and stamped result.
