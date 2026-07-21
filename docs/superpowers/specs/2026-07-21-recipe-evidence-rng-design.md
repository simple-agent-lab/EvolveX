# Faithful Recipe RNG and Evidence Design

## Goal

Make the HyperAgents and AHE recipes behave more like their official implementations while keeping the changes small, recipe-oriented, and native to the existing Evolve framework.

This design covers four changes:

1. deterministic RNG streams that vary across generations;
2. compact AHE prompt composition with full evidence available for drill-down;
3. bounded HyperAgents prompt composition with filesystem-backed history;
4. official-style AHE attribution, best-ever, and stability signals.

The design does not introduce a new execution framework, evidence store, history database, operator stage, or rollback mechanism.

## Upstream Reference Points

- HyperAgents: `facebookresearch/HyperAgents` at commit `59a68f672dfb92c74aeb7e61535d776fb36e172d`.
- AHE: `china-qijizhifeng/agentic-harness-engineering` at commit `faf44bc4aea57413c520bc5711c6ebf628e0da1e`.

The recipes remain framework ports targeting MiniSWE, not reproductions of the upstream benchmark configurations.

## Non-Goals

- Do not replace either recipe gate with hill climbing.
- Do not automatically roll back an AHE generation after a score regression.
- Do not change AHE's `k=2` evaluation or all-task debugger defaults.
- Do not add new persistent RNG state.
- Do not remove, truncate, or overwrite full trace and debugger artifacts.
- Do not change unrelated recipes' evidence prompts.
- Do not attempt to reproduce AHE's NexAU benchmark scores with MiniSWE.

## 1. Deterministic Generation-Varying RNG

### Problem

The SDK currently constructs `random.Random(seed)` independently for every operator invocation. A selector configured with a fixed seed therefore receives the same first draw in every generation. This collapses HyperAgents' stochastic archive exploration into a repeatable single chain.

### Design

Keep `OperatorContext.rng` and all operator interfaces unchanged. Derive the integer passed to `random.Random` from a canonical encoding of:

- the configured seed;
- `EVOLVE_GENID`;
- `EVOLVE_PARENT`, using an empty string when absent.

Use SHA-256 rather than Python's process-randomized `hash()`. Convert a fixed portion of the digest to an integer.

The same seed, generation, and parent must produce the same random sequence. A different generation or parent must produce a different sequence. Multiple fan-out choices within one selector invocation continue to advance the same `Random` instance normally.

This is the only framework-level change because deterministic, non-repeating operator randomness is useful to every recipe using `ctx.rng`.

### Failure Behavior

Non-integer configured seeds retain the current validation behavior. Generation and parent identifiers may be arbitrary strings.

## 2. AHE Prompt Composition

### Problem

The AHE analyzer creates a useful layered evidence corpus, but the current meta-agent prompt recursively inlines `selected.md`, which concatenates every task detail and bounded case. In the observed run this produced a prompt larger than 500 KB.

Official AHE stores all task details but injects only a compact overview, allowing the evolution agent to open relevant details selectively.

### Design

Do not change which tasks are analyzed or which artifacts are produced. Keep:

- `trace_analyzer/analysis/overview.md`;
- `trace_analyzer/analysis/detail/*.md`;
- `trace_analyzer/evidence/cases.jsonl`;
- full rollout and raw trace artifacts.

Change only the AHE meta-agent prompt builder. It must inline:

- the complete `analysis/overview.md`;
- compact `analysis/change_evaluation.json`;
- the prior change manifest;
- recent archive outcomes and surface rules.

It must provide stable paths to per-task detail reports, bounded cases, and raw traces. It must not inline task detail bodies or `cases.jsonl`.

A missing or empty overview is an operator error. The meta-agent must not silently continue with incomplete evidence.

## 3. HyperAgents Prompt Composition

### Problem

The shared feedback loader recursively inlines linked historical metrics. HyperAgents prompt size therefore grows with every generation even though complete history is already available through the mounted workspace.

### Design

Implement prompt selection inside the HyperAgents recipe operator rather than changing the shared feedback loader.

Inline:

- the current generation's bounded selected trace summary;
- a compact lineage table containing generation, parent, score, and status;
- a compact summary of the most recent accepted change.

Provide paths to:

- complete feedback and history;
- prior generation artifacts;
- raw trace evidence;
- the archive;
- detailed metrics and diffs.

Apply a recipe-local maximum to inline evidence. The maximum must include a visible truncation marker and the path to the complete artifact. Truncation affects only the prompt view and never modifies stored evidence.

If the selected trace summary is absent, fall back to the compact rollout or attempts summary. If no compact current evidence exists, fail with a clear message rather than recursively inlining arbitrary files.

The bound should be a named constant in the HyperAgents operator. It does not become a new global configuration surface.

## 4. AHE Analysis Signals

### Problem

The current AHE analysis reports task transitions and whether predictions or risks were observed, but it omits the compact decision signals used by official AHE: per-change verdicts, best-ever performance, and historical task stability.

### Design

Extend existing artifacts; do not create upstream-specific `task_history.json` or `best_ever.json` files.

#### Change Attribution

Extend `analysis/change_evaluation.json` with `change_evaluations`, `unattributed_regressions`, and a compact summary. Preserve the existing fields for compatibility.

For each prior manifest change, compute:

- predicted fixes that actually flipped from fail to pass;
- predicted fixes that still failed;
- declared risks that regressed from pass to fail;
- an official-style verdict.

Verdict rules match upstream AHE:

- `HARMFUL`: at least one declared risk was realized and no predicted fix occurred;
- `MIXED`: at least one declared risk and at least one predicted fix occurred;
- `EFFECTIVE`: every non-empty predicted fix occurred and no declared risk was realized;
- `PARTIALLY_EFFECTIVE`: at least one, but not all, predicted fixes occurred and no declared risk was realized;
- `INEFFECTIVE`: no predicted fix occurred and no declared risk was realized.

A regression not named in any change's predictions or risks is unattributed.

#### Best-Ever

Derive the best-ever generation from selection-eligible canonical rows already stored in `archive.jsonl`. Show its generation and score in `analysis/overview.md`. This is advisory and does not change the next parent.

#### Task Stability

Derive task histories from canonical archive task vectors. Match AHE's task-level classification:

- with multiple rollouts, a task passes only when every observed rollout passes;
- `stable_pass`: only pass outcomes observed;
- `stable_fail`: only fail outcomes observed;
- `possibly_unstable`: both pass and fail observed across fewer than three evaluated generations;
- `unstable`: both pass and fail observed across at least three evaluated generations;
- infrastructure-only tasks may be summarized separately when no verifier outcome exists.

Add compact counts and relevant task names to `analysis/overview.md`. Stability is advisory and does not exclude tasks from evaluation or parent selection.

## Data Flow

```text
canonical evaluation
  -> archive score and task vector
  -> AHE debugger reports and change attribution
  -> compact overview in initial AHE prompt
  -> agent-selected detail and raw-trace reads
  -> mutation and manifest
  -> next canonical evaluation

current HyperAgents evaluation
  -> bounded current trace summary
  -> compact lineage and latest-change summary
  -> bounded initial prompt plus filesystem paths
  -> agent-selected historical reads
  -> mutation
```

## Compatibility

- Existing operator interfaces remain unchanged.
- Existing AHE analysis fields remain present.
- Full evidence artifacts remain present at their existing paths.
- Gate and selection policies remain unchanged.
- Other recipes retain their current prompt construction.
- The SDK RNG sequence changes intentionally for any operator that uses `ctx.rng`; fixed-seed reruns remain reproducible.

## Verification

### RNG

- Same seed, generation, and parent produce the same sequence.
- Different generation or parent produces a different sequence.
- String generation identifiers work.
- Fan-out choices advance one invocation's RNG normally.

### AHE Prompt

- The prompt contains the complete overview and stable detail paths.
- The prompt does not contain detail report bodies or bounded case bodies.
- Missing or empty overview fails explicitly.
- Full detail and case artifacts remain unchanged.

### HyperAgents Prompt

- Current bounded evidence and compact lineage are present.
- Full artifact paths are present.
- Historical task-level metrics are not recursively inlined.
- Oversized inline evidence is visibly truncated below the recipe-local bound.
- Missing selected evidence uses the documented compact fallback.

### AHE Analysis

- Fixtures cover all five attribution verdicts.
- Unattributed regressions are reported.
- Best-ever ignores ineligible/non-canonical rows.
- Fixtures cover stable pass, stable fail, possibly unstable, unstable, and infrastructure-only cases.
- Multi-rollout task outcomes use the all-rollouts-pass rule.
- Analysis remains advisory; gate outcomes do not change.

### Regression Coverage

Run focused SDK, AHE, HyperAgents, feedback, and driver-operator tests. Run an initialized-recipe smoke test that validates prompt sizes and artifact paths without launching paid benchmark evaluations.
