# Harbor Disposable Full Workspace

## Goal

Run Harbor meta-agents in the same repository-shaped environment as local
meta-agents. HyperAgents and AHE should be able to inspect the selected parent,
the complete experiment history, raw traces, evaluator, configuration, and Git
history from one working directory without gaining an alternate path for
persistent host mutations.

This change also relaxes the HyperAgents prompt so target changes are strongly
preferred rather than mandatory. AHE manifest validation, model pins, budgets,
and recipe parameters remain unchanged.

## Design

### One disposable workspace

Each Harbor editing task receives a self-contained repository at
`/app/workspace`. It is assembled before the task from:

- the selected parent checkout, including all tracked workspace files;
- self-contained Git history and generation tags;
- `archive.jsonl`, evaluation receipts, and the complete `runs/` history;
- current feedback, debugger reports, and raw trace evidence.

Transient host worktrees and Harbor job directories are excluded so assembling
the workspace cannot recursively copy the currently running task.

The workspace is an ordinary writable directory inside the task. The agent can
use normal filesystem and Git tools there, exactly as a local meta-agent would.
No read-only filesystem policy is required because this is a disposable copy,
not a bind mount of the real host workspace.

### Return and trust boundary

Harbor returns `/app/workspace` as the task artifact. The host retains a trusted
pre-run snapshot and compares the returned filesystem against it without
trusting returned Git metadata.

The existing surface policy remains authoritative:

1. detect changed tracked candidate paths from the trusted before/after trees;
2. reject a proposal when any candidate path is outside `surface.include` or
   inside `surface.exclude`;
3. validate returned editable roots for symlinks and special files;
4. transactionally install only the configured editable roots (`target` for
   AHE; `target` and `operators` for HyperAgents);
5. discard returned `.git`, evaluator, configuration, archive, receipts, and
   run artifacts even when unchanged.

Changes to evidence-only runtime files are never an output channel. They are
discarded. Attempts to change protected tracked files such as `evolve.yaml`,
`evaluator/**`, or `.evolve/**` are surface violations and reject the proposal.

### Prompt paths

Both strategies are told:

- repository and selected parent: `/app/workspace`;
- archive: `/app/workspace/archive.jsonl`;
- historical and current artifacts: `/app/workspace/runs`;
- feedback and raw evidence: beneath the current generation directory;
- persistent edits must obey the supplied surface rules.

There is no separate `/app/candidate` or `/app/context` concept.

### HyperAgents prompt policy

HyperAgents strongly prefers a substantive `target/**` improvement because
prior experiments found direct target work productive. Operator-only changes
remain allowed when the agent explains why improving the search or improvement
process is currently higher leverage and how it should benefit later target
proposals. Cosmetic target edits made only to satisfy the preference are
discouraged.

### AHE scope

AHE uses the same full workspace and can drill from summaries into raw traces.
Its simplified change-manifest schema and existing structural gate remain
unchanged.

## Failure Handling

- Failure to assemble a complete workspace fails the operator visibly.
- Missing or malformed returned workspaces fail before host installation.
- Unexpected changes to protected tracked files reject the proposal.
- Installation remains transactional: either every editable root is replaced
  after validation, or the original checkout is restored.
- The real experiment workspace is never mounted into the task, so edits cannot
  bypass the surface comparison.

## Tests

Tests are written before implementation and cover:

1. the task contains a self-contained `/app/workspace` with selected-parent
   files, Git history, archive, prior runs, and current raw evidence;
2. transient worktrees and recursive Harbor job directories are excluded;
3. the Harbor command works in and returns `/app/workspace`;
4. protected tracked changes are detected and rejected;
5. only configured editable roots are installed back;
6. HyperAgents and AHE prompts use container-visible workspace paths;
7. HyperAgents encourages target work without requiring it;
8. existing Harbor runner, AHE, HyperAgents, and full test suites remain green.

## Non-Goals

- Strict validation of the official AHE manifest schema.
- Pinning evaluator or model versions.
- Equalizing budgets, concurrency, task counts, or recipe settings.
- Persisting edits to runtime evidence, evaluator files, configuration, or Git
  metadata returned by the model.
