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
| `cli.py` | 200 | argument parsing and verb dispatch only — no logic |
| `config.py` | 300 | read/render `evolve.yaml`: recipes, experiment values, surface lists, operator blocks |
| `driver.py` | 1360 | the generation sequencer: orchestrates baseline eval, verbs + operators (incl. novelty, self-modification admission gates, sealed anchors); validates operator outputs; computes verified_fixes; audit quarantine; doctor repair |
| `feedback.py` | 220 | assemble current and historical rollout evidence plus ledger-derived feedback for the meta-agent |
| `operators.py` | 150 | subprocess runner for workspace operator scripts (contract: env vars, --config, timeout) |
| `population.py` | 150 | genid/lineage bookkeeping for fan-out generations |
| `archive.py` | 270 | append-only event store: merge semantics, stamped-field protection, mirroring, integrity fsck |
| `evaluator.py` | 150 | clean-checkout canonical evaluation: tree assertion, exit-code contract, score parsing |
| `candidate_snapshot.py` | 80 | exact candidate Git tree construction, temporary materialization, and reviewed-tree commit verification |
| `candidate_smoke.py` | 130 | run evaluator smoke against an exact candidate snapshot and persist redacted diagnostics |
| `git.py` | 150 | thin git subprocess helpers — nothing evolve-specific |
| `surface.py` | 150 | mutable-surface pattern matching and violation checks |
| `report.py` | 182 | status/report rendering, best-ever recomputation, claim checklist |
| `trace_analysis.py` | 410 | deterministic shared transforms used by the independent trace-analyzer operator variants |
| `splits.py` | 210 | freeze deterministic train/gate/sealed Harbor task membership and materialize exact runtime selections |
| `workspace.py` | 510 | `evolve init` scaffolding: file copies, operator binding, deterministic dataset and Harbor runtime config, generated operator palette, protocol stamping, seed + mechanism vendoring, inner-skill copy |

### The frozen ring (`src/evolve/frozen/`)

The invariant-enforcers: the operator contract, the operator SDK, and the
self-modification admission gate. Grouped so the ring is legible; vendored into
each workspace, immutable there because it sits outside the mutable surface
(the ruler itself is the experiment-side frozen — see `frozen/__init__.py`).

| File | Budget (lines) | Responsibility (one line — keep it true) |
| --- | --- | --- |
| `frozen/__init__.py` | 30 | the frozen-ring definition (litmus + two homes: contract/gate vs the ruler) — the canonical anchor a contributor reads |
| `frozen/interfaces.py` | 330 | operator ABCs (incl. trace analyzer, novelty, and reflect), the registry, result schemas, payload validation |
| `frozen/sdk.py` | 420 | Python operator entrypoint and file-contract IO; no library algorithm policy |
| `frozen/meta_eval.py` | 130 | self-modification admission gate: confound-free replay of old vs new operator surface (mechanism 1) |

Total `src/evolve/` budget: **4800 lines**. The increase admits the explicit,
redacted trace-analysis boundary between rollout and feedback assembly; if the mechanism wants to
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
