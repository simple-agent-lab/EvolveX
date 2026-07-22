---
name: review-change
description: Review a git diff, commit range, branch, or pull request for correctness, simplicity, user understanding, Python quality, and LLM/agent engineering. Use when asked to review code or when a Harbor review task requires a structured evidence-based report. Do not use for implementing fixes unless the user separately asks for changes.
---

# Review a change

Review the selected change, not the repository in the abstract. Lead with actionable findings and allow a clean result.

## Workflow

1. Resolve the exact base and head revisions. Inspect the diff and changed-file summary first.
2. Read repository-owned instructions and architecture documents relevant to the changed files.
3. Trace each changed user-facing path from entry point through result, error, and recovery behavior.
4. Read [references/rubric.md](references/rubric.md) and apply only categories enabled by the task.
5. Verify each suspected finding against surrounding code, tests, types, or a focused runtime check.
6. Remove findings that are preferences, hypothetical future risks, or unsupported by evidence.
7. Report findings in severity order. Do not edit the reviewed checkout.

## Finding threshold

Emit a finding only when all of these are present:

- a specific changed behavior or newly exposed risk;
- evidence at a file and, when possible, a tight line;
- concrete impact on correctness, users, maintenance, or agent reliability;
- a smallest coherent fix;
- calibrated confidence.

Use `P0` for immediate data loss, security compromise, or unusable core behavior; `P1` for a likely defect or material contract break; `P2` for actionable complexity or usability debt introduced by the change. Put unresolved design choices under questions rather than inventing a defect.

## Human output

Return:

1. findings ordered by severity, with file and line references;
2. open questions that materially affect the verdict;
3. up to three strengths worth preserving;
4. a verdict: `ready`, `needs_changes`, or `discuss`.

Keep summaries short. If there are no actionable findings, say so directly.

## Harbor report artifact

When `HARBOR_LOGS_DIR` is present, always write `$HARBOR_LOGS_DIR/agent/review-report.json` before the final response. Create its parent directory if needed. Use this exact shape:

```json
{
  "schema_version": 1,
  "verdict": "ready",
  "summary": "Concise assessment.",
  "findings": [
    {
      "severity": "P1",
      "category": "correctness",
      "title": "Imperative actionable title",
      "evidence": [{"path": "src/example.py", "line": 42, "detail": "Observed behavior."}],
      "impact": "What fails and for whom.",
      "smallest_fix": "Smallest coherent correction.",
      "confidence": "high"
    }
  ],
  "questions": [],
  "strengths": []
}
```

Use only task-enabled categories. Valid severities are `P0`, `P1`, and `P2`; confidence is `high`, `medium`, or `low`. Every finding requires non-empty evidence. Respect the task's finding limit.
