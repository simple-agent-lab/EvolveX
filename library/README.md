# library/ — the reference operator catalog

A curated, framework-versioned pool of operator implementations to **consult and
adapt**, one folder per verb. This is reference material, not the runtime: it is
**not** copied wholesale into a workspace, and nothing here is executed as-is.

See `DESIGN.md` §7 for the full rationale. In short:

- The meta-agent (an agent) reads `library/<verb>/*.py`, then adapts a variant
  **into** the workspace's active `operators/<verb>.py`. Only that adapted-in,
  committed copy ever runs — so meta_eval replay and the self-reference gate
  always act on in-tree code, and the catalog needs no freeze, digest, or gate.
- It is surfaced to the meta-agent through the skill (`operators/meta_agent.md` points here),
  not vendored in — fat skills, thin workspace.
- It is also the **harvest sink**: operators that evolve well in real runs get
  promoted back here, closing `framework seeds → workspace evolves → good
  variants flow back` (M8).

## Layout

```
library/
├─ select/   greedy · newest · random · score_weighted · ahe_latest
├─ meta_agent/   agent_command · ahe_evidence_editor · prompts/ahe_evolve.md
├─ gate/     hillclimb · parent_eligible · ahe_artifact_valid
├─ rollout/  failure_focused · noop · ahe_trace_analysis · prompts/ahe_debugger*.md
├─ record/   jsonl · ahe_manifest
└─ _skeletons/   "write a new operator of verb X" starting points   (planned move)
```

## Canonical verb set

`select · rollout · meta_agent · novelty · gate · record · reflect` (+ `distill`,
deferred with weights). The authority is `src/evolve/frozen/interfaces.py`.

Method-faithful variants may use a research-method name when that name describes
actual operator behavior and artifacts, not a preset label. The AHE family is
one example: it consumes the generic evaluator `task_vector.json` and
`evaluation_artifacts.json` contracts, produces trace-analysis and change
manifest artifacts, and is selected as five distinct operator implementations.
