# AHE Evidence Editor

Read the experiment evidence before editing. Work in this order: analysis overview, previous attribution, evolution history, current source, then the surface rules. Do not read sealed-test data or infer it from task names.

Choose one decision for this generation:

- `KEEP`: retain a prior direction only when the evidence supports it, and make a distinct source-level improvement.
- `REVISE`: adjust the implicated MiniSWE source component when the root-cause hypothesis remains credible.
- `ROLLBACK + PIVOT`: explicitly revert the harmful change using generation tags as references, then move to a different component level or root-cause hypothesis. Do not immediately reapply the failed approach.

Edit only the mutable MiniSWE source under `target/`. Do not wrap or invoke the `mini` CLI. Never modify `target/harbor_agent.py`, evaluator files, Harbor or Docker configuration, `.env`, model configuration, or proxy configuration.

Use the smallest general harness change supported by the evidence. Keep one logical source change per commit-sized unit. Before finishing, run relevant validation commands and repair all surface violations.

Environment feedback is optional. When dependency or runtime uncertainty is relevant, you may run the protected command `./evolve candidate-smoke --full` and read its sanitized result artifact. Do not edit the command, evaluator, Harbor wrapper, lock, or environment machinery, and do not install packages manually. Full smoke initializes the configured model path but makes no model request. A smoke failure is evidence to diagnose, not permission to modify evaluator-owned files.

Write a JSON manifest to the required manifest path. It is mandatory for any source proposal and must use this schema:

```json
{
  "schema_version": 1,
  "generation": "current generation",
  "parent": "selected parent generation",
  "decision": "keep|revise|rollback_pivot",
  "changes": [
    {
      "id": "change identifier",
      "type": "new|improvement|rollback",
      "files": ["target/source_file.py"],
      "failure_evidence": [{"task_id": "task id", "report": "rollout/analysis/detail/task.md"}],
      "root_cause": "evidence-backed cause",
      "targeted_fix": "specific source change",
      "predicted_fixes": ["task id"],
      "risk_tasks": ["task id"],
      "component_level": "prompt|tool|model_adapter|environment|control_flow"
    }
  ],
  "validation": {"status": "passed", "commands": ["command run"]}
}
```

Each changed path must be listed exactly once. Every evidence report path must be relative to this run and already exist. `risk_tasks` may be empty, but it must be present. Do not report a patch in chat instead of writing the manifest.
