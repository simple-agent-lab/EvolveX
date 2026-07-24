# Current Shared-Optimizer Experiments Lark Report Design

## Purpose

Create a concise Lark document that supports a 5–10 minute presentation of the current AHE `v9-clean` and HyperAgents `v6` Terminal-Bench experiments. The document must make the experiment conditions immediately comparable and explain the evolution behavior using direct evidence from every available meta-agent trace and every per-round `model_patch.diff`.

## Scope

- Treat AHE `v9-clean` and HyperAgents `v6` as the authoritative current runs.
- Mention earlier failed, stopped, or superseded variants only when they explain provenance, restarts, or validity caveats.
- Use the experiment artifacts and current state on `DevBoxS` as the source of truth.
- Record an explicit observation timestamp because run state may change.
- Do not reproduce complete traces or patches.

## Audience and Length

The audience is a technical project group familiar with agents and evaluation but not necessarily with the details of these runs. The main reading path should fit a 5–10 minute oral presentation. Target four substantive sections plus a brief provenance note, with tables carrying the comparison-heavy content.

## Document Structure

1. **Executive summary.** One short paragraph stating what is being compared, the current run state, and the strongest evidence-backed takeaway.
2. **Experiment-condition table.** AHE and HyperAgents side by side. Include recipe, benchmark/task sampling, repeats, planned generations, optimizer and selection settings, candidate and meta-agent models, reasoning levels, concurrency, budgets, runtime/image identity, current round, score/status, and validity caveats. Unknown or not-yet-produced values must be shown as such rather than inferred.
3. **Trace and patch analysis.** A compact per-round table for each run with round, observed trace signal, patch intent/mechanism, outcome, and interpretation. Read all available trace and patch artifacts, but quote or paraphrase only one or two representative examples per run.
4. **Cross-run findings and next checks.** A short synthesis separating supported conclusions from tentative hypotheses and naming the most informative next validation.
5. **Operational provenance.** Exact remote experiment paths and observation timestamp in a compact closing note.

## Evidence Method

Each analytical claim should follow the chain:

`trace symptom → meta-agent diagnosis → patch mechanism → subsequent evaluation outcome`

The analysis should distinguish:

- changes well grounded in trace evidence from speculative edits;
- patches that target the diagnosed failure from patches that broaden scope;
- local or one-round improvements from repeated, stable improvements;
- model behavior failures from evaluator, runtime, or orchestration failures;
- absent evidence from negative evidence.

Scores and statuses should be drawn from structured run artifacts where available and cross-checked against logs or Git generation tags. Configuration values should come from the frozen experiment config and relevant runtime records.

## Presentation Style

- Lead with the condition table; it is the most important component.
- Prefer short analytical paragraphs over bullet-heavy narration.
- Use plain, precise language and define experiment-specific terms once.
- Keep raw filenames and paths in code style.
- Include only representative trace or diff excerpts, each shortened to the minimum needed to support the interpretation.
- Avoid decorative components. Use a single restrained informational callout only if a comparability caveat would otherwise be missed.

## Quality Checks

- Every available round has been inventoried for both trace and patch artifacts.
- Condition values agree with the frozen configs and run records.
- The document does not imply causal improvement from a single noisy score.
- Superseded runs are not mixed into the authoritative comparison.
- Raw traces and full diffs are excluded.
- The main narrative can be presented in 5–10 minutes.
- The created Lark document is fetched after creation and checked for table integrity, duplicated titles, omissions, and formatting errors.
