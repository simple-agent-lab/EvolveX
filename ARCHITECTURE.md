# Architecture Map

> **Note:** the enforced current-state map of `src/evolve/`. The design rationale
> (three rings, the frozen contract, the operator registry) lives in
> [the design guide](docs/concepts/design.md); this file is the authority on modules and budgets.

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
| `archive.py` | 475 | append-only event store: merge semantics, stamped-field protection, mirroring, integrity fsck |
| `candidate/__init__.py` | 10 | candidate-boundary package marker |
| `candidate/smoke.py` | 225 | run install or one-request model smoke against an exact candidate snapshot and persist redacted evidence |
| `candidate/snapshot.py` | 100 | exact candidate Git tree construction, temporary materialization, and reviewed-tree commit verification |
| `cli.py` | 450 | argument parsing and verb dispatch only — no logic |
| `config.py` | 225 | read/render `evolve.yaml`, including evaluator repetition and inline runtime normalization |
| `driver.py` | 1800 | the generation sequencer: orchestrates baseline eval, verbs + operators (incl. novelty, self-modification admission gates, sealed anchors); validates operator outputs; computes verified_fixes; audit quarantine; doctor repair |
| `doctor.py` | 250 | read-only local/experiment preflight profiles and persisted diagnostic receipts |
| `evaluator_doctor.py` | 275 | frozen evaluator contract checks for local runtime preparation, task assets, and model-free smoke probes |
| `evaluation/__init__.py` | 75 | typed evaluation identity, contract, and result facade |
| `evaluation/contract.py` | 500 | resolve, hash, persist, and project the single authoritative evaluation contract identity |
| `evaluation/diagnostics.py` | 375 | materialize missing trials and own bounded diagnostic projection and validation |
| `evaluation/evidence.py` | 175 | evaluator-output reading, validation, and conversion into canonical trial results |
| `evaluation/execution.py` | 475 | clean-checkout canonical evaluation: preflight gate, run plan, tree assertion, lifecycle, artifacts, and score parsing |
| `evaluation/legacy.py` | 275 | read-only task-set identity compatibility for pre-contract workspaces |
| `evaluation/results.py` | 250 | evaluation result types, outcome classification, and persisted record shape |
| `evaluation/run_plan.py` | 100 | authoritative per-attempt task, trial-count, commit, and runtime plan |
| `execution_runtime/__init__.py` | 25 | execution-runtime package facade |
| `execution_runtime/command.py` | 50 | shell-facing runtime endpoint resolver |
| `execution_runtime/config.py` | 75 | validation for the portable execution_runtime config section |
| `execution_runtime/environment.py` | 100 | host environment bridge for configured Docker Compose commands |
| `execution_runtime/models.py` | 125 | host execution configuration, resolved context, and redacted receipt types |
| `execution_runtime/probes.py` | 275 | daemon, Compose, disk, and bind-mount preflight probes |
| `execution_runtime/resolve.py` | 175 | explicit/env/Linux/macOS Docker endpoint resolution |
| `experiment_smoke.py` | 200 | isolated one-task gen0-to-gen1 full-loop canary |
| `feedback.py` | 250 | assemble current and historical rollout evidence plus ledger-derived feedback for the meta-agent |
| `operators.py` | 200 | subprocess runner for workspace operator scripts (contract: env vars, --config, timeout) |
| `operator_cli.py` | 150 | agent-facing operator discovery and one-stage invocation command group |
| `orchestration.py` | 400 | safe outer-agent composition of driver verbs, stage handoffs, retries, and admission receipts |
| `patching.py` | 150 | mutable-surface patch creation and parent-reference selection |
| `population.py` | 100 | genid/lineage bookkeeping for fan-out generations |
| `preflight/__init__.py` | 50 | stable public preflight facade and prospective-check exports |
| `preflight/checks.py` | 100 | exact-environment host tool and candidate dependency-lock probes |
| `preflight/models.py` | 150 | typed checks, failure categories, and atomic receipt serialization |
| `preflight/prospective.py` | 225 | pre-init checklist mirroring init refusals without writing |
| `preflight/runner.py` | 350 | ordered validation, typed domain-error mapping, redaction, and model-smoke delegation |
| `report.py` | 250 | status/report rendering, best-ever recomputation, claim checklist, and certified evidence coverage |
| `run_summary.py` | 200 | recipe-aware terminal-state assessment and machine-readable run assertion receipts |
| `runtime/__init__.py` | 25 | stable process and evaluation-attempt runtime facade |
| `runtime/process.py` | 250 | generated-workspace owned-process and evaluation-attempt helpers |
| `runtime/auth.py` | 100 | explicit API-key or Codex auth-file selection without home-directory discovery |
| `runtime/config.py` | 300 | inline runtime validation, endpoint identity, canonical resolution, and trusted loading |
| `runtime/environment.py` | 450 | strict and legacy role-specific credential, endpoint, proxy, template, and redacted Harbor environment planning |
| `runtime/uv.py` | 550 | locked uv candidate-runtime construction and command execution |
| `splits.py` | 650 | freeze content-backed task identity/membership and materialize authoritative limited runtime selections |
| `surface.py` | 150 | mutable-surface pattern matching and violation checks |
| `trace_analysis.py` | 775 | deterministic shared transforms used by the independent trace-analyzer operator variants |
| `workspace.py` | 1100 | `evolve init` scaffolding: file copies, operator binding, deterministic dataset and Harbor runtime config, generated operator palette, protocol stamping, safe seed + mechanism vendoring, inner-skill copy |
| `git.py` | 150 | thin git subprocess helpers — nothing evolve-specific |
| `harbor_local.py` | 250 | minimal in-place Harbor environment for fast trials against a pre-configured local agent runtime |
| `host_runtime.py` | 100 | host-side locked runtime process helpers |
| `integrations/__init__.py` | 10 | external runtime integration package boundary |
| `integrations/harbor/__init__.py` | 10 | Harbor integration package boundary |
| `integrations/harbor/local_auto_agent.py` | 275 | local CLI discovery and delegation to Harbor installed-agent adapters with required ATIF output |
| `integrations/harbor/_agent_roles.py` | 50 | canonical MiniSWE role names and narrow compatibility aliases |
| `integrations/harbor/_candidate_source.py` | 75 | exact candidate-source validation and archive-copy boundary |
| `integrations/harbor/codex_candidate.py` | 75 | Codex adapter for OpenAI-compatible Responses endpoints |
| `integrations/harbor/prime_agent.py` | 275 | Prime Agent adapter with continual-harness injection and export |
| `integrations/harbor/miniswe_candidate.py` | 550 | exact-candidate MiniSWE Harbor evaluator agent |
| `integrations/harbor/miniswe_task_file.py` | 130 | large-task MiniSWE meta-agent transport |
| `meta_agent_budget.py` | 150 | shared Harbor meta-agent retry and timeout budget calculations |

### The frozen ring (`src/evolve/frozen/`)

The invariant-enforcers: the operator contract, the operator SDK, and the
self-modification admission gate. Grouped so the ring is legible; vendored into
each workspace, immutable there because it sits outside the mutable surface
(the evaluator itself is the experiment-side frozen — see `frozen/__init__.py`).

| File | Budget (lines) | Responsibility (one line — keep it true) |
| --- | --- | --- |
| `frozen/__init__.py` | 50 | the frozen-ring definition (litmus + two homes: contract/gate vs the evaluator) — the canonical anchor a contributor reads |
| `frozen/interfaces.py` | 350 | operator ABCs, registry, result schemas, and strict operator payload validation |
| `frozen/sdk.py` | 300 | Python operator entrypoint and file-contract IO; no library algorithm policy |

Total `src/evolve/` budget: **17005 lines**. The budget admits the explicit content-backed
evaluation-contract boundaries, the opt-in in-place Harbor runtime, and the redacted trace-analysis
boundary between rollout and feedback assembly; if the mechanism wants to
grow past that, something belongs in a workspace operator instead —
that is the spec's rule, not a style preference.

## Root files

| File | Meaning |
| --- | --- |
| `ARCHITECTURE.md` | this map (enforced by tests/test_coherence.py) |
| `docs/concepts/design.md` | the design + rationale (three rings, mechanisms) — a maintained doc |
| `docs/` | MkDocs user, technical, and contributor documentation |
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
share them. `test_runtime_recipe_conformance.py` is the acceptance matrix for
AEvolve, AHE, GEPA, and HyperAgents runtime configuration parity.
