# HyperAgents

Use HyperAgents when the research question explicitly allows both the target
agent and selected parts of the evolution process to change.

## Use it when

- Improvements may come from agent behavior, evidence collection, reflection,
  mutation, validation, selection, or memory of prior candidates.
- A population should explore multiple process variants instead of following
  only the current best target.
- The experiment can support admission checks for self-referential changes.

Establish a target-only control first whenever possible; HyperAgents creates a
harder attribution problem than target-only evolution.

## Use the shipped capabilities

Run `./evolve operator list . --json` before choosing a stage. The shipped
HyperAgents profile normally combines population-aware selection,
`parent_evaluation`, `trace_browser`, a `hyperagents` meta agent, and an
independent `hyperagents` validate stage. Invoke configured direct evidence
and admission stages and inspect their generation artifacts. Use the configured
`meta_agent` through the driver when it should own both target and process
edits; an outer agent may instead edit both only when both paths are declared in
the mutable surface.

Read active `operators/<stage>.py` files only for a justified process diagnosis
or mutation. Use the matching `library/select/`, `library/trace_analyzer/`,
`library/meta_agent/hyperagents.py`, and `library/validate/hyperagents.py`
implementations as adaptation references, never as evidence that the active
workspace already runs them.

## Apply the method

1. Declare the target and process parts of the mutable surface separately.
2. Select a parent while preserving enough diversity for process exploration.
3. Expose only the evidence view permitted by the experiment contract.
4. Produce an evidence-linked target hypothesis and any process mutation.
5. Admit process changes through an independent contract or replay check.
6. Evaluate the resulting candidate with the frozen evaluator.
7. Record target and process changes separately in the lineage.

## Guard the claim

Keep evaluator, runtime identity, scope enforcement, and stamped evidence
outside both mutable scopes. A higher score alone does not establish whether the
target change or the process change caused the improvement.

## Completion check

Target and process diffs are recorded separately; every process change passed
its independent admission rule; the evaluator remained outside both mutable
surfaces; and the report preserves the attribution ambiguity when both changed.
