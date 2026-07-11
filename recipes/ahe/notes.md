# Notes

This recipe is method-faithful rather than a rollback-shaped scaffold. The
rollout reads verified training evidence, writes `rollout/analysis/` reports,
and the source editor writes `meta_agent/change_manifest.json`. The gate checks
the canonical evaluator artifacts before accepting the edit; the record keeps
the manifest digest, analysis paths, predicted fixes, and risk tasks in the
archive row.

The fixed evaluator list contains training tasks only. The Harbor adapter and
all evaluator-owned files remain outside the mutable target surface.
