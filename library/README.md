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
├─ select/   greedy · newest · random · score_weighted · score_child_prop
├─ meta_agent/   agent_command · hyperagents
├─ validate/ hyperagents
├─ gate/     hillclimb · parent_eligible
├─ rollout/  failure_focused · noop
├─ record/   jsonl · hyperagents
└─ _skeletons/   "write a new operator of verb X" starting points   (planned move)
```

## Canonical verb set

`select · rollout · meta_agent · novelty · gate · record · reflect` (+ `distill`,
deferred with weights). The authority is `src/evolve/frozen/interfaces.py`.
