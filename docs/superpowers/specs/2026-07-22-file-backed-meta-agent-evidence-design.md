# File-Backed Meta-Agent Evidence Design

## Purpose

Reduce noise in HyperAgents and AHE meta-agent prompts by keeping detailed
rollout and debugger evidence in the files that already own it. Prompts explain
what each relevant file contains, give its path, and require a simple reading
order instead of embedding the file contents.

## Goals

- Keep meta-agent prompts short and easy to understand.
- Preserve complete rollout and debugger evidence without truncation.
- Reuse the current run directory, feedback bundle, and Harbor workspace.
- Limit changes to the HyperAgents and AHE prompt builders and their tests.
- Make the evidence reading order explicit before the meta-agent edits files.

## Non-goals

- Change the frozen framework under `src/evolve/`.
- Add a new evidence directory, evidence schema, or shared prompt abstraction.
- Change Harbor staging or artifact-return behavior.
- Change trace analyzer or feedback generation behavior.
- Apply the policy to A-Evolve, GEPA, or other meta-agent strategies.
- Generate a new inline evidence summary.

## Existing Evidence Layout

The required evidence is already available to local and Harbor meta-agents.
This design keeps the existing files authoritative.

HyperAgents uses:

- `runs/gen-N/feedback/index.md` as the feedback entry point;
- `runs/gen-N/feedback/evidence/selected.md` for selected rollout findings;
- `runs/gen-N/feedback/last_accepted.diff` for the latest accepted change;
- `runs/gen-N/trace_analyzer/evidence/` for detailed analyzed evidence;
- `runs/gen-N/rollout/` for raw rollout results.

AHE uses:

- `runs/gen-N/trace_analyzer/analysis/overview.md` for the debugger overview;
- `runs/gen-N/trace_analyzer/analysis/change_evaluation.json` for the prior
  change verdict and task transitions;
- `runs/gen-N/trace_analyzer/analysis/detail/` for per-task debugger reports;
- `runs/gen-<parent>/meta_agent/` for the prior manifest, output, changed paths,
  and patch;
- `runs/gen-N/rollout/` for raw rollout results;
- `archive.jsonl` for historical outcomes.

Harbor prompts use paths rooted at `/app/task/workspace`. Local prompts use the
existing host workspace and checkout paths. This behavior does not change.

## HyperAgents Prompt

Remove the inline contents currently produced by `_prompt_evidence`, including
selected evidence and the latest accepted diff. Do not replace them with a new
generated summary.

The prompt contains a short evidence section that describes the existing paths
and requires this reading order:

1. Read `feedback/index.md`.
2. Read `feedback/evidence/selected.md` and `feedback/last_accepted.diff`.
3. Inspect relevant trace-analyzer evidence.
4. Open raw rollout artifacts only when the analyzed evidence is insufficient.
5. Edit the candidate after reviewing the evidence.

Repository location, current-generation artifact paths, and remaining
iterations stay inline. Lineage remains in the feedback files with the other
experimental evidence. Full evidence bodies and diffs do not appear inline.

## AHE Prompt

Remove inline bodies for:

- the debugger overview;
- `change_evaluation.json`;
- prior meta-agent output and patch artifacts;
- the archive tail.

Replace those bodies with short descriptions and direct paths. The prompt
requires this reading order:

1. Read `analysis/overview.md`.
2. Read `analysis/change_evaluation.json` and decide KEEP, REVISE, or
   ROLLBACK + PIVOT.
3. Read only the per-task reports relevant to the chosen hypothesis.
4. Inspect the selected parent's manifest and patch when evaluating the prior
   change.
5. Open raw rollout artifacts only to resolve missing or conflicting evidence.
6. Edit the candidate and write the required AHE change manifest.

The AHE strategy instructions, surface rules, evidence-path descriptions, and
required manifest template remain inline because they define the task rather
than report experimental results.

For the baseline generation, the prompt explicitly says that no prior
meta-agent change exists instead of pointing to a nonexistent parent directory.

## Failure Behavior

Prompt construction does not read evidence bodies, so missing optional evidence
does not fail prompt assembly. Required evidence remains enforced by the stages
that produce or consume it today; this change does not introduce a second
validation policy.

The prompt tells the meta-agent to use the available files and continue with
the strongest supported hypothesis if an optional detailed artifact is absent.

## Testing

HyperAgents prompt tests verify that:

- the prompt includes the evidence entry point and direct evidence paths;
- the prompt includes the required reading order;
- selected evidence content and the accepted diff body are absent;
- Harbor and local paths retain their current roots.

AHE prompt tests verify that:

- the prompt includes paths for overview, change evaluation, per-task details,
  parent meta-agent artifacts, raw rollouts, and the archive;
- the prompt includes the required reading order and decision sequence;
- debugger overview content, attribution JSON content, prior output, prior patch,
  and archive row bodies are absent;
- the baseline prompt handles the absence of a prior change explicitly;
- surface and manifest instructions remain intact.

Existing meta-agent execution and artifact-preservation tests remain unchanged
except where their prompt assertions must reflect the file-first contract.

## Scope of Code Changes

Implementation is limited to:

- `library/meta_agent/hyperagents.py`;
- `library/meta_agent/ahe.py`;
- `tests/test_hyperagents_meta_agent.py`;
- `tests/test_ahe_meta_agent.py`.

No framework, runner, trace analyzer, feedback writer, recipe, or workspace
layout changes are required.
