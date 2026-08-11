# Guided recipe/operator authoring: final-fix report

Date: 2026-08-11

Reviewed base: `30d50c06c898df483cff2e8019497831978437f8`

Functional fix commit: `e3f57140751152a574b6e664a497f0bbba6f85a4`

Report commit: this file is added by the report-only commit that follows the
functional commit; the handoff message records its exact identity.

## Status

All eight final-review findings and the interaction findings discovered during
integration are addressed. The implementation is confined to the skill,
progressive references, maintained recipe guide, evaluation assets, and
deterministic structural/package tests. It changes no `src/evolve/` runtime
code, dependency metadata, or recorded score snapshot.

## Findings addressed

### 1. Qualify evaluation before method selection

`references/experiment-design.md` now requires explicit evaluator evidence for
coverage, determinism, leakage, runtime compatibility, known-positive and
known-negative calibration, limitations, and supported claims before method or
recipe selection. Insufficient evidence stops selection and routes to Harbor
evaluation authoring or evaluator-engine design according to the named gap.
Live calibration is allowed only as a separately authorized, bounded probe;
pre-existing or model-free evidence is preferred.

`SKILL.md` makes this a top-level design gate, and the
`authoring-informed-composition` behavior prompt and rubric now exercise an
existing but unqualified evaluator rather than assuming evaluation assets are
absent.

### 2. Add progressive custom-recipe authoring

The new `references/recipe-authoring.md` teaches the post-architecture flow:
copy the nearest supported recipe, maintain root `evolve.yaml` and durable
`README.md`, author target/surface then qualified evaluation/runtime then
operator composition, run and record a complete isolated recipe check after
each coherent phase, retain the exact eventual `--recipe-path` invocation,
record limitations, and request source approval without deploying.

`SKILL.md` links the reference in the source-authoring phase. The maintained
`docs/guides/custom-recipes.md` now explicitly follows the same evaluator-first,
approval-gated order and treats its command snippets as contract references,
not implicit authority. The approved concept's package tree, structural direct
link test, and wheel membership assertion include the new reference.

The new `authoring-custom-recipe` behavior case and rubric exercise progressive
phase checkpoints without recording a score.

### 3. Make filesystem routing predicate-based and non-overlapping

`SKILL.md` now uses the approved complete marker sets:

- EvolveX source checkout: `.git`, `pyproject.toml`, `src/evolve/`, `library/`,
  and `recipes/`;
- initialized workspace: `evolve.yaml`, `.evolve-components.json`,
  `archive.jsonl`, and the workspace-local `./evolve` launcher.

Complete sets take precedence. Partial EvolveX-specific markers route to one
focused location question. Generic `.git` or `pyproject.toml` files alone are
ordinary external-target evidence, and importable installed-package presence
is explicitly insufficient. A final no-candidate/no-marker branch handles
insufficient context without guessing.

The prompts and rubrics for `authoring-external-context` and
`authoring-ambiguous-context` cover the non-overlap and partial-marker paths.

### 4. Teach interrupted authoring recovery

`references/decision-protocol.md` now reconstructs the last valid checkpoint
from the task record or recipe rationale, Git status and diff, and independently
recomputed local identities or digests. It preserves approved decisions whose
inputs are unchanged, reruns inexpensive current static/isolated/focused checks,
treats absent durable approval as absent, and resumes from the last valid gate
without initialization or deployment. It distinguishes source-authoring
recovery from initialized-workspace doctor/repair flows.

The existing `authoring-resume-record` rubric now tests those taught behaviors.

### 5. Correct prospective-preflight claims and secret handling

`references/deployment.md` and the maintained recipe guide describe prospective
`evolve preflight` as a read-only initialization checklist whose stdout is not
a generated receipt. They state the inputs represented by the command and
record auth identity, runtime/image readiness, reachability, Git content,
evaluator smoke, and similar facts as unchecked unless independently proven.

The deployment record now contains the exact secret-free command, manually
sanitized stdout, independent identities/digests, and unchecked assumptions.
Credential-bearing URLs are rejected before execution or retention; userinfo
and secret query parameters must be removed and authentication supplied through
a separately authorized out-of-band mechanism. The guidance does not claim the
checklist validates authentication identity.

### 6. Harden authored-code inspection without changing runtime

`references/operator-authoring.md` explains that `operator describe` and
`operator check` execute entry code in a subprocess that inherits the launcher
environment, and that recipe resolution/preflight can inspect selected named
operators. It requires static review of entry and local-import paths first,
rejects import-time filesystem, network, process/thread, credential,
deployment, and model effects, and requires a disposable network-disabled
sandbox/container with read-only reviewed source, disposable writable storage,
explicit tool/environment allowlists, and no ambient credentials.

The same boundary is required before `describe`, `check`, `recipe check`, and
prospective preflight throughout the skill, recipe guide, and deployment
playbook. Safe catalog discovery may occur during pre-approval design, but
scaffolding, edits, and composition remain architecture/source-choice gated.

`authoring-operator-gap` makes import-time effects and inspection with ambient
credentials hard failures. No PR #47 or other `src/evolve/` runtime code was
changed.

### 7. Separate semantic and byte-only approval invalidation

`references/decision-protocol.md` now makes architecture stale for changes to
composition, configuration semantics, behavior, evaluator/scoring,
partitions, mutable surface, execution/trust boundary, budget, material risks,
or unknowns. A byte-only implementation change within the approved design does
not automatically invalidate architecture, but it does invalidate source and
deployment approval because reviewed/frozen bytes and identities changed.

The dedicated `authoring-byte-only-invalidation` prompt and rubric exercise
that distinction separately from semantic invalidation.

### 8. Strengthen machine-readable inventory and coverage honesty

`tests/test_evolve_agent_evals.py` now uses a duplicate-key-rejecting JSON
loader and asserts the exact complete behavior ID-to-dimension and invocation
ID-to-expected-skill mappings. Recorded historical behavior IDs must exactly
equal the 16 pre-authoring IDs, while the unreported partition must exactly
equal all nine `authoring-*` IDs. No case can be silently replaced while
retaining cardinality.

The evaluation README states that the rewritten head has no formal paired run
(`0/25` behavior cases), that the historical snapshot covers only its older 16
IDs, that all nine authoring cases are unreported, and that invocation coverage
is `0/8`. Qualitative pressure reports remain separate development feedback,
not a complete paired campaign, blind result, or score snapshot.

## Files changed

- `skills/evolve-agent/SKILL.md`: routing predicates, qualification gate,
  pre-approval safe catalog discovery, recipe link, isolated inspection.
- `skills/evolve-agent/references/experiment-design.md`: evaluator
  qualification, bounded calibration, task-record-first rationale.
- `skills/evolve-agent/references/recipe-authoring.md`: new progressive custom
  recipe playbook.
- `skills/evolve-agent/references/operator-authoring.md`: static import-safety
  review and credential-free isolated inspection.
- `skills/evolve-agent/references/deployment.md`: accurate prospective
  checklist, sanitization, independent evidence, unchecked assumptions.
- `skills/evolve-agent/references/decision-protocol.md`: semantic versus
  byte-only invalidation and interrupted-authoring recovery.
- `docs/guides/custom-recipes.md`: maintained guide aligned to the new order,
  safety boundary, and approval split.
- `docs/concepts/guided-experiment-authoring.md`: package tree includes the new
  reference.
- `evals/skills/evolve-agent/behavior_cases.jsonl`: strengthened authoring
  prompts plus ambiguous-context, custom-recipe, and byte-only cases.
- `evals/skills/evolve-agent/rubric.json`: operational criteria and hard
  failures for the final findings.
- `evals/skills/evolve-agent/README.md`: explicit current-head and invocation
  coverage limitations.
- `tests/test_evolve_agent_evals.py`: duplicate-safe exact inventories and
  exact historical/unreported partition.
- `tests/test_evolve_agent_skill.py`: structural direct-link/reference
  coverage.
- `tests/test_release_artifact.py`: wheel-membership assertion.

`evals/skills/evolve-agent/baseline_results.json` and
`current_results.json` are unchanged.

## RED evidence

The structural and packaging changes followed test-first RED/GREEN cycles:

1. New progressive reference:
   - `uv run --frozen pytest -q tests/test_evolve_agent_skill.py`
   - RED: `1 failed, 3 passed`; the required
     `references/recipe-authoring.md` did not exist.
2. Required authoring inventory:
   - `uv run --frozen pytest -q tests/test_evolve_agent_evals.py`
   - RED: `1 failed, 4 passed`; the behavior inventory was below the newly
     asserted requirement and lacked the ambiguous-context case.
3. New release member:
   - `uv build --out-dir /tmp/evolvex-guided-final-red.yxXHAh`
   - Build succeeded.
   - `EVOLVE_RELEASE_DIST=/tmp/evolvex-guided-final-red.yxXHAh uv run --frozen pytest -q tests/test_release_artifact.py`
   - RED: `1 failed, 1 passed`; the wheel lacked
     `evolve/skills/evolve-agent/references/recipe-authoring.md`.
4. Progressive-recipe behavior inventory:
   - `uv run --frozen pytest -q tests/test_evolve_agent_evals.py::test_behavior_eval_cases_are_unique_and_rubric_complete`
   - RED: `1 failed`; exact inventory had 24 cases while the test required the
     new `authoring-custom-recipe` mapping as case 25.

One attempted focused command named the nonexistent
`tests/test_operator_cli.py`, so pytest collected no tests. It was diagnosed as
a command-selection error and was not counted as verification. One sandboxed
uv invocation could not initialize the shared user cache (`Operation not
permitted`); the identical command was rerun with authorized access to the
existing cache. Neither event was a product failure.

## GREEN and final verification

Development checkpoints:

- Baseline before changes:
  `uv run --frozen pytest -q tests/test_evolve_agent_skill.py tests/test_evolve_agent_evals.py`
  -> `9 passed`.
- Initial skill GREEN: `tests/test_evolve_agent_skill.py` -> `4 passed`.
- Initial evaluation GREEN: `tests/test_evolve_agent_evals.py` -> `5 passed`.
- Progressive-recipe inventory GREEN (two exact nodes) -> `2 passed`.
- Initial focused CLI contract run -> `75 passed`.
- Initial post-fix artifact directory
  `/tmp/evolvex-guided-final-green.4tVKkS` -> release tests `2 passed`.
- An intermediate default-suite checkpoint before the interaction refinements
  -> `1220 passed, 3 skipped in 170.69s`.
- One intermediate focused eval cleanup emitted warnings about stale global
  pytest temporary directories while tests passed; final reruns below emitted
  no such warnings.

Final commands and outputs on the exact functional tree:

```text
uv run --frozen pytest -q tests/test_evolve_agent_skill.py tests/test_evolve_agent_evals.py
9 passed in 0.81s

uv run --frozen pytest -q tests/test_operator_authoring_cli.py tests/test_operator_library.py tests/test_init_preflight.py
75 passed in 6.88s

uv run --frozen ruff check .
All checks passed!

uv run --frozen ruff format --check .
255 files already formatted

uv run --frozen ty check
All checks passed!

uv build --out-dir /tmp/evolvex-guided-final.l6e3oq
Successfully built /tmp/evolvex-guided-final.l6e3oq/evolvex-0.1.0.tar.gz
Successfully built /tmp/evolvex-guided-final.l6e3oq/evolvex-0.1.0-py3-none-any.whl

EVOLVE_RELEASE_DIST=/tmp/evolvex-guided-final.l6e3oq uv run --frozen pytest -q tests/test_release_artifact.py
2 passed in 0.76s

uv run --frozen pytest -q
1220 passed, 3 skipped in 172.71s

git diff --check
clean (no output)

git diff --exit-code -- src/evolve pyproject.toml uv.lock \
  evals/skills/evolve-agent/baseline_results.json \
  evals/skills/evolve-agent/current_results.json
clean (no output)
```

The CLI help was also inspected with
`uv run --frozen evolve preflight --help` to ensure the guide names only the
prospective inputs represented by the actual command: destination, recipe or
recipe path, optional seed, dataset and task limit, and declared runtime digest.

No slow, live, external-service, network, credential, Docker, model-backed, or
real evolution-campaign tests were run.

## Self-review

- Scope review found no `src/evolve/`, dependency, lockfile, or score-snapshot
  change.
- The inspection safety requirement is consistently applied to describe,
  operator check, recipe check, and prospective preflight; the maintained guide
  no longer presents those commands outside the safety/approval boundary.
- Filesystem routing predicates have explicit precedence and a terminal
  insufficient-context route; ordinary target `.git`/`pyproject.toml` markers
  do not create ambiguity.
- Pre-approval design permits only filesystem listing and statically reviewed,
  isolated description; source scaffolding and edits remain gated.
- Recipe authoring now materializes `README.md` only after approval and records
  a complete check after each target, evaluation/runtime, and operator phase.
- Deterministic tests inspect metadata, exact machine-readable mappings,
  inventory, links, schema shape, and package membership. They do not grep or
  assert Markdown instructional prose.
- Historical result snapshots and their qualitative interpretation were not
  rewritten.
- The fresh wheel, default suite, formatting, lint, typing, and whitespace
  checks are clean.

## Concerns and next gate

There is no implementation blocker.

The new safety boundary is skill/rubric guidance, not a runtime sandbox; this is
intentional under the constraint not to change PR #47/runtime behavior. An
operator must provide a credential-free, allowlisted isolation mechanism before
executing authored inspection commands.

Fresh-agent behavioral verification remains the controller's next gate. No
formal paired behavior run covers this rewritten head, and no invocation case
has a recorded run. The qualitative pressure reports used during authoring are
not formal paired or blind results and must remain separate from score
snapshots.
