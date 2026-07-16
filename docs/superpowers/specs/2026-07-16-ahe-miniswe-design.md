# AHE on MiniSWE Design

## Goal

Replace the placeholder AHE recipe with one faithful, framework-native implementation of Agentic Harness Engineering (AHE), using MiniSWE as the agent harness being evolved.

The implementation should preserve AHE's main ideas while avoiding framework abstractions that only AHE needs. The generic framework remains a small operator loop; AHE-specific diagnosis, hypotheses, change manifests, predictions, and decision review belong to AHE operators and their artifacts.

References:

- [Agentic Harness Engineering paper](https://arxiv.org/pdf/2604.25850)
- [Reference implementation](https://github.com/china-qijizhifeng/agentic-harness-engineering)

## Design Principles

1. **One implementation.** There is no provisional and final AHE recipe. The current placeholder is deleted and replaced by the implementation described here.
2. **Use the existing loop.** AHE is a recipe over the existing select, rollout, optional trace-analyzer, meta-agent, gate, and record operators. It does not introduce a second orchestration pipeline.
3. **Keep the framework method-neutral.** Only experiment-independent execution and trust-boundary behavior belongs in `src/evolve`. AHE reasoning belongs in `library/trace_analyzer` and `library/meta_agent`.
4. **Preserve the scientific boundary.** The target harness may evolve; the foundation model, task partitions, evaluator, Harbor adapter, credentials, and resource limits may not.
5. **Implement the main idea, not every incidental detail.** The design preserves component, experience, and decision observability. It does not reproduce NexAU's exact taxonomy, deployment stack, prompts, or every rollback mechanism.
6. **Prefer inspectable artifacts over new schemas.** AHE may emit additional reports, but the framework does not interpret their method-specific contents.

## Why MiniSWE

MiniSWE is the best substrate already supported by this repository. The workspace initializer can seed its complete source tree under `target/`, and `MiniSweSourceAgent` installs and executes that candidate source inside Harbor. This makes source-level harness changes real evaluation inputs.

MiniSWE is also small enough that a meta-agent can understand its control loop, prompt/configuration, model adapter, and environment interface without a separate component registry. AHE may add new harness components such as skills, memory, middleware, or subagent support when an observed failure justifies them.

MiniSWE does not expose NexAU's seven named component types. The exact taxonomy is not an AHE invariant. For this implementation, component observability means that the editable harness is ordinary, explicit source with auditable file-level changes and understandable component boundaries. Empty components will not be created merely to match the paper's labels.

The alternatives are rejected:

- A built-in Codex target exposes a narrower, less transparent harness surface.
- A new NexAU integration would add substantial coupling and deployment work without improving the three essential observability properties.

## Trust and Mutable-Surface Boundary

The AHE recipe seeds MiniSWE source and configures `target.harbor_agent:MiniSweSourceAgent`. Its mutable surface includes `target/**`, subject to the framework's implicit exclusions. In particular, `target/harbor_agent.py` is already rejected by the surface checker and remains frozen.

The mutable target may contain:

- MiniSWE's agent loop and control policy;
- system prompts and agent configuration;
- tool and environment interfaces;
- error recovery, stopping, and verification behavior;
- new skills, memory, middleware, or subagent components that are actually used;
- dependency declarations and the corresponding lockfile when a justified harness change requires them.

The following remain frozen:

- the Harbor adapter and evaluator tree;
- the foundation model selected by Harbor;
- train, gate, and sealed task partitions;
- evaluation and gate scoring;
- credentials and service endpoints;
- rollout and evaluation resource limits;
- the vendored framework mechanism and archive authority.

The existing MiniSWE runner already overwrites the candidate model name. It must also receive explicit frozen step, cost, and environment-timeout limits from the evaluator/recipe boundary instead of falling back to mutable MiniSWE config. This is a targeted hardening of the existing adapter, not a new framework interface. Other harness policy, including prompts and ordinary control configuration, remains evolvable.

Candidate installation continues to use `uv sync --frozen`. A dependency change is valid only when the candidate updates both its declaration and lockfile.

## Recipe and Data Flow

Each generation follows the existing driver sequence:

1. Greedy selection chooses the best eligible parent.
2. Harbor rollout executes the selected MiniSWE source on a bounded subset of the frozen train split.
3. The AHE trace analyzer converts the current rollout into compact task-level evidence.
4. The mechanism assembles its ordinary feedback bundle.
5. The AHE meta-agent reads the evidence and feedback, inspects the MiniSWE source, writes its optional AHE analysis report, and edits the target directly.
6. Existing validation and surface checks reject invalid or out-of-surface changes.
7. Canonical Harbor evaluation scores the child on the gate split.
8. The existing hill-climb gate admits only an improving eligible child.
9. The ordinary JSONL recorder records generic outcome and provenance fields.

The archive retains all candidates. A rejected child is not an eligible parent, so the next greedy selection returns to the best accepted harness. This provides generation-level rollback without a new rollback operator or fragile per-file reversal logic.

## AHE Trace Analyzer

The AHE trace analyzer is deliberately narrow. It analyzes only `rollout/cases.json` from the current generation. It does not traverse lineage, inspect source history, compare change manifests, verify prior predictions, or make mutation decisions.

For each observed task, it preserves a bounded normalized record containing:

- task or trial identity;
- outcome and reward;
- a clipped task instruction;
- ordered agent messages, tool calls, and observations;
- final response and verifier evidence;
- exception, usage, and timing information when present.

It emits a small set of concrete artifacts under `trace_analyzer/`:

- `feedback.md`, a bounded human-readable overview for the existing feedback-bundle assembler;
- `evidence/selected.md`, the same bounded selection in the existing selected-evidence location;
- `evidence/overview.json`, with counts, rewards, and compact per-task outcomes;
- `evidence/cases.jsonl`, with bounded task details for failures and representative successes.

Failures are retained first in rollout order, followed by successes in rollout order until the configured evidence bound is reached. This selection is deterministic but is only evidence retention; it does not compare generations or decide whether an edit worked.

The analyzer returns the existing `TraceAnalyzerResult(summary, artifacts)`. No new trace-analyzer interface or shared AHE schema is added. The result summary stays small, while artifact files hold inspectable detail.

The analyzer must degrade cleanly when optional case fields are absent. Malformed individual case fields are represented as missing or clipped evidence; they do not cause the analyzer to invent causal explanations. A missing or unreadable `rollout/cases.json` produces an explicit empty/error summary rather than a fabricated diagnosis.

This replaces the current heavyweight multi-variant AHE placeholder behavior. Generic trace-analyzer variants may remain available for other recipes, but the AHE recipe uses its focused analyzer.

## AHE Meta-Agent

The AHE meta-agent is the method's reasoning center. It consumes the current trace evidence and the mechanism-owned feedback bundle, inspects the selected MiniSWE source, and proposes one coherent harness change.

Its strategy requires it to:

1. identify observed failures or inefficiencies and cite concrete trace evidence;
2. map the evidence to an existing or missing harness component;
3. state a falsifiable hypothesis about the proposed change;
4. inspect relevant source before editing;
5. make a focused, internally consistent source change;
6. preserve observed passing behavior where possible;
7. run proportionate local checks and the surface check;
8. record what changed, expected effects, risks, and the next decision rule.

The operator uses the existing `MetaAgentResult(changed, notes, usage)` contract. It may additionally write `meta_agent/ahe-report.json`. That report is an AHE artifact, not a framework contract. Its recommended fields are:

```json
{
  "evidence": [],
  "diagnosis": "",
  "component": "",
  "hypothesis": "",
  "changes": [],
  "expected_effects": [],
  "risks": [],
  "decision_rule": ""
}
```

The AHE operator prompts for and preserves this report when available. A missing or malformed report is noted in `MetaAgentResult.notes` but does not create a new mechanism-level failure mode if the source edit and required generic result are otherwise valid. This keeps the framework extensible while giving AHE decision observability.

The meta-agent, rather than a deterministic comparator, reviews prior accepted/rejected outcomes and earlier AHE reports when deciding whether to retain, refine, pivot, or abandon a hypothesis. The implementation does not add a comparison operator.

## Prediction and Falsification Cleanup

The current generic mechanism embeds `predicted_fixes`, derives `verified_fixes`, and writes a weak falsification page. These concepts are not consumed by generic selection, evaluation, validation, gating, reporting, or lineage correctness. Their current default is also misleading: the SDK can treat changed file paths as predicted fixes.

They will therefore be removed from the generic contracts and defaults:

- the SDK will stop creating `meta_agent/predicted_fixes.json`;
- the driver will stop requiring or validating that file;
- generic archive rows and record annotations will stop adding `predicted_fixes` and `verified_fixes`;
- the generic feedback bundle will stop writing prediction-derived falsification content;
- generic meta-agent prompts and command adapters will stop requiring prediction lines;
- the unused credit-reflection variant based only on `verified_fixes` will be removed;
- affected templates, documentation, tools, and tests will be updated.

Historical archive rows containing these fields remain readable as ordinary unknown JSON fields; no migration is required.

AHE predictions remain available inside `ahe-report.json` as `expected_effects`, `risks`, and `decision_rule`. Their interpretation stays entirely within the AHE meta-agent. The generic record operator records generic provenance and outcome only; no AHE-specific record or reflect operator is introduced.

## Existing Interfaces Kept Intact

This work does not redesign `RolloutResult`, `TraceAnalyzerResult`, or artifact transport. Both results retain the existing minimal `summary` and `artifacts` fields. The precise meaning and validation of artifact references is a broader framework question and is intentionally deferred.

The design also adds no structured hypothesis type, component registry, deterministic observation comparator, rollback operator, AHE record operator, or AHE reflect operator.

## Failure Handling

- Harbor rollout remains authoritative for execution and fails explicitly when no trial results are produced.
- Trace analysis distinguishes absent evidence from agent failure and never upgrades an infrastructure error into a harness diagnosis.
- The meta-agent may not edit the frozen adapter, evaluator, mechanism, or archive; existing surface repair and rejection remain authoritative.
- Invalid MiniSWE projects, missing lockfiles, failed frozen sync, and import failures remain candidate-invalid outcomes through the existing adapter.
- A failed or rejected generation remains archived but cannot become the next greedy parent.
- Optional AHE analysis-report problems are visible in notes and artifacts without corrupting the generic operator result.

## Verification

Tests should establish the following behavior:

1. Initializing the AHE recipe seeds MiniSWE source, writes the MiniSWE Harbor adapter, and binds the AHE rollout, trace-analyzer, meta-agent, gate, and record variants.
2. `target/harbor_agent.py`, evaluator files, the mechanism, and archive authority remain outside the mutable surface.
3. Harbor executes the candidate MiniSWE source and forces the configured foundation model and resource limits even when mutable candidate config requests different values.
4. The AHE trace analyzer reads only current `rollout/cases.json`, emits bounded overview/details artifacts, handles missing optional fields, and does not traverse lineage or compare predictions.
5. The AHE meta-agent receives current evidence, edits MiniSWE within the surface, returns the ordinary meta-agent result, and preserves an optional AHE report without requiring framework awareness of its contents.
6. Generic runs no longer require, synthesize, validate, record, or display `predicted_fixes` or `verified_fixes`.
7. A rejected child remains archived and greedy selection naturally returns to the best eligible parent.
8. An end-to-end smoke run exercises MiniSWE rollout, AHE trace analysis, AHE editing, canonical evaluation, gating, and recording with frozen evaluator identity.

The full repository test suite and lint checks must pass after the old placeholder expectations are replaced.

## Explicit Non-Goals

- Reproducing NexAU's exact component taxonomy or runtime.
- Adding all seven component categories before evidence justifies them.
- Reproducing the reference repository's E2B deployment or Agent Debugger implementation.
- Adding deterministic trace or observation comparison.
- Automatically verifying predictions in generic framework code.
- Performing automatic per-file or multi-edit rollback.
- Evolving the foundation model, evaluator, task partitions, or resource budget.
- Redesigning rollout/trace result artifact semantics.
- Adding an AHE-specific orchestration pipeline, record operator, or reflect operator.
- Maintaining the current placeholder AHE recipe alongside the real implementation.
