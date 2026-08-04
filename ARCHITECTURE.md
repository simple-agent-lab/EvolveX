# Architecture Map

> **Note:** the enforced current-state map of `src/evolve/`. The design rationale
> (three rings, the frozen contract, the operator registry) lives in
> [`DESIGN.md`](DESIGN.md); this file is the authority on modules and budgets.

The ownership map of the mechanism. **This file is enforced**: 
`tests/test_coherence.py` fails if a module exists that is not listed
here, is listed but missing, or exceeds its line budget. Change the
table in the same commit that changes the code — a new module needs a
row and a one-line meaning *before* it can exist; growing past a budget
requires raising the budget here, with the reason in the commit message.

Budgets are speed bumps, not walls: they exist to force a conscious
decision (and usually a demolition pass) instead of silent sprawl.

## Mechanism modules (`src/evolve/`)

| File | Budget (lines) | Responsibility (one line — keep it true) |
| --- | --- | --- |
| `__init__.py` | 10 | package marker, version |
| `__main__.py` | 10 | `python -m evolve` entry |
| `agent.py` | 200 | agent command execution and error/result types |
| `archive.py` | 400 | append-only event store: merge semantics, stamped-field protection, mirroring, integrity fsck |
| `candidate/__init__.py` | 10 | candidate-boundary package marker |
| `candidate/smoke.py` | 150 | run evaluator smoke against an exact candidate snapshot and persist redacted diagnostics |
| `candidate/snapshot.py` | 100 | exact candidate Git tree construction, temporary materialization, and reviewed-tree commit verification |
| `cli.py` | 300 | argument parsing and verb dispatch only — no logic |
| `config.py` | 200 | read/render `evolve.yaml`: recipes, experiment values, surface lists, operator blocks |
| `driver.py` | 1800 | the generation sequencer: orchestrates baseline eval, verbs + operators (incl. novelty, self-modification admission gates, sealed anchors); validates operator outputs; computes verified_fixes; audit quarantine; doctor repair |
| `evaluation/__init__.py` | 50 | pure evaluation-result facade |
| `evaluation/evidence.py` | 150 | evaluator-output validation and conversion into canonical trial results |
| `evaluation/execution.py` | 350 | clean-checkout canonical evaluation: tree assertion, targeted task execution, lifecycle, artifacts, and score parsing |
| `evaluation/identity.py` | 150 | canonical task-set identity plus checkout and frozen-baseline comparability |
| `evaluation/results.py` | 200 | evaluation result types, outcome classification, and persisted record shape |
| `feedback.py` | 250 | assemble current and historical rollout evidence plus ledger-derived feedback for the meta-agent |
| `operators.py` | 200 | subprocess runner for workspace operator scripts (contract: env vars, --config, timeout) |
| `patching.py` | 150 | mutable-surface patch creation and parent-reference selection |
| `population.py` | 100 | genid/lineage bookkeeping for fan-out generations |
| `report.py` | 200 | status/report rendering, best-ever recomputation, claim checklist |
| `runtime.py` | 250 | generated-workspace runtime entrypoint helpers |
| `splits.py` | 250 | freeze deterministic train/gate/sealed Harbor task membership and materialize exact runtime selections |
| `surface.py` | 150 | mutable-surface pattern matching and violation checks |
| `trace_analysis.py` | 750 | deterministic shared transforms used by the independent trace-analyzer operator variants |
| `uv_runtime.py` | 550 | locked uv runtime construction and command execution |
| `workspace.py` | 950 | `evolve init` scaffolding: file copies, operator binding, deterministic dataset and Harbor runtime config, generated operator palette, protocol stamping, seed + mechanism vendoring, inner-skill copy |
| `git.py` | 150 | thin git subprocess helpers — nothing evolve-specific |
| `harbor_local.py` | 250 | minimal in-place Harbor environment for fast trials against a pre-configured local agent runtime |
| `host_runtime.py` | 100 | host-side locked runtime process helpers |
| `integrations/__init__.py` | 10 | external runtime integration package boundary |
| `integrations/harbor/__init__.py` | 10 | Harbor integration package boundary |
| `integrations/harbor/miniswe_candidate.py` | 550 | exact-candidate MiniSWE Harbor evaluator agent |
| `integrations/harbor/miniswe_task_file.py` | 130 | large-task MiniSWE meta-agent transport |
| `meta_agent_budget.py` | 150 | shared Harbor meta-agent retry and timeout budget calculations |
| `viewer/__init__.py` | 30 | read-only experiment viewer package facade |
| `viewer/models.py` | 300 | stable viewer API models and internal source/snapshot records |
| `viewer/reader.py` | 450 | validated cached reads of archive, stage, evaluation, and Harbor-root evidence |
| `viewer/snapshot.py` | 700 | derive health, stages, changes, performance, trials, and artifact references from source evidence |
| `viewer/harbor_bridge.py` | 250 | ephemeral symlink federation and canonical trial links for Harbor inspection |

### The frozen ring (`src/evolve/frozen/`)

The invariant-enforcers: the operator contract, the operator SDK, and the
self-modification admission gate. Grouped so the ring is legible; vendored into
each workspace, immutable there because it sits outside the mutable surface
(the ruler itself is the experiment-side frozen — see `frozen/__init__.py`).

| File | Budget (lines) | Responsibility (one line — keep it true) |
| --- | --- | --- |
| `frozen/__init__.py` | 50 | the frozen-ring definition (litmus + two homes: contract/gate vs the ruler) — the canonical anchor a contributor reads |
| `frozen/interfaces.py` | 350 | operator ABCs (incl. trace analyzer, novelty, and reflect), the registry, result schemas, payload validation |
| `frozen/sdk.py` | 300 | Python operator entrypoint and file-contract IO; no library algorithm policy |

Total `src/evolve/` budget: **12935 lines**. The budget admits the explicit content-backed
evaluation-contract boundaries, the opt-in in-place Harbor runtime, and the redacted trace-analysis
boundary between rollout and feedback assembly; if the mechanism wants to
grow past that, something belongs in a workspace operator instead —
that is the spec's rule, not a style preference.

## Root files

| File | Meaning |
| --- | --- |
| `ARCHITECTURE.md` | this map (enforced by tests/test_coherence.py) |
| `DESIGN.md` | the design + rationale (three rings, mechanisms) — a maintained doc |
| `docs/coding-style.md` | coding conventions — a maintained doc |
| `README.md` | user-facing overview — must never overstate milestone reality |
| `CONTRIBUTING.md` | contributor entry (setup + the enforced constraints) |
| `pyproject.toml`, `uv.lock` | packaging; runtime is stdlib-only |

## Dependency rules (enforced where cheap, reviewed otherwise)

- `cli.py` may import anything; nothing imports `cli.py`.
- `git.py`, `surface.py`, `archive.py` are leaves (stdlib-only imports
  besides each other is a smell — keep them independent).
- `STAMPED_FIELDS` is defined in exactly one place (`archive.py`).
- The mechanism never imports or executes workspace code in-process;
  workspace operators run only via `operators.run_operator`.
- Test hooks (`EVOLVE_FAKE_*`, `*_FAKE=`) never appear under `src/`.

## Tests (`tests/`)

Test files map to spec milestones/sections by name
(`test_m<N>_<topic>.py`, `test_coherence.py`). Tests are spec, not scar
tissue: when behavior changes, delete the outdated test in the same
commit — do not shim around it. Test files have no line budgets, but
duplicated fixtures belong in `tests/conftest.py` once three files
share them.
