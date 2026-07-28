# Unified Four-Experiment Runtime Design

Date: 2026-07-28

## Objective

Start four new, clean experiments later, each with a new experiment ID and a
generation-0 evaluation. The four experiments must preserve their existing
method- and benchmark-specific behavior while sharing one explicit runtime
policy for timeout multipliers, benchmark retries, meta-agent limits,
trace-debugger retries, and partial-score handling.

The four stopped workspaces are historical evidence only. They must not be
resumed or reused as the new experiments.

## Configuration contract

Changed values are marked **changed**. All other rows explicitly preserve the
previous configuration.

| Setting | AHE / TB2 | AHE / HLE | HyperAgents / TB2 | HyperAgents / HLE |
|---|---|---|---|---|
| Host | DevBox | DevBox | DevBoxS | DevBox |
| New experiment ID | New unique ID at launch | New unique ID at launch | New unique ID at launch | New unique ID at launch |
| ID format | `ahe-tb2-clean-rN-unified-YYYYMMDD` | `ahe-hle-clean-rN-unified-YYYYMMDD` | `hyperagents-tb2-clean-rN-unified-YYYYMMDD` | `hyperagents-hle-clean-rN-unified-YYYYMMDD` |
| ID allocation | `N` is the next unused revision on the target host; the date is the actual launch date | Same rule | Same rule | Same rule |
| Starting point | New workspace; generation 0 | New workspace; generation 0 | New workspace; generation 0 | New workspace; generation 0 |
| Existing stopped run | Do not resume | Do not resume | Do not resume | Do not resume |
| Evolution method | AHE | AHE | HyperAgents | HyperAgents |
| Experiment mode | `driver` | `driver` | `driver` | `driver` |
| Experiment seed | 0 | 0 | 0 | 0 |
| Maximum generations | 10 | 10 | 10 | 10 |
| Children per generation | 1 | 1 | 1 | 1 |
| Target score | None | None | None | None |
| Target repository | `SWE-agent/mini-swe-agent` | Same | Same | Same |
| Target revision | `388da74aad620a384ab47669b17c52133e30e7c3` | Same | Same | Same |
| Generate target lock | Yes | Yes | Yes | Yes |
| Harbor target agent | `miniswe-source` | Same | Same | Same |
| Benchmark agent | `evolve_harbor_adapter:MiniSweSourceAgent` | Same | Same | Same |
| Benchmark model | `openai/gpt-5.4-2026-03-05` | Same | Same | Same |
| Candidate runtime | UV project `target`, Python 3.12 | Same | Same | Same |
| Candidate `UV_OFFLINE` | Agent side only | Agent side only | Agent side only | Agent side only |
| Candidate surface | `target/**` | `target/**` | `target/**`, `operators/**` | `target/**`, `operators/**` |
| Dataset | Terminal-Bench 2 fixed 89-task dataset | HLE parity fixed 249-task dataset | Terminal-Bench 2 fixed 89-task dataset | HLE parity fixed 249-task dataset |
| Train/gate/sealed counts | 50 / 19 / 20 | 100 / 49 / 100 | 50 / 19 / 20 | 100 / 49 / 100 |
| Split seed | 0 | 42 | 0 | 42 |
| Evaluation split | Train | Train | Train | Train |
| Sampling | Static | Static | Static | Static |
| Tasks per round | 50 | 100 | 50 | 100 |
| Trials per task (`k`) | 1 | 1 | 1 | 1 |
| Benchmark concurrency | 25 | 25 | 25 | 25 |
| Agent setup timeout multiplier | **1 (changed)** | **1 (changed)** | **1 (explicit)** | **1 (explicit)** |
| Agent timeout multiplier | **1 (changed)** | **1 (changed)** | **1 (changed)** | **1 (changed)** |
| Verifier timeout multiplier | **1 (explicit)** | **1 (explicit)** | **1 (explicit)** | **1 (explicit)** |
| Absolute benchmark timeouts | Harbor task definitions | Harbor task definitions | Harbor task definitions | Harbor task definitions |
| Timeout parity rule | Same effective Harbor settings as HyperAgents/TB2 | Same effective Harbor settings as HyperAgents/HLE | Same effective Harbor settings as AHE/TB2 | Same effective Harbor settings as AHE/HLE |
| Cross-benchmark absolute parity | Not required; TB2 and HLE retain their own task-defined base timeouts | Not required | Not required | Not required |
| Harbor benchmark retries | **0** | **0** | **0** | **0** |
| Harbor attempts per task | 1 | 1 | 1 | 1 |
| Automatic driver re-evaluation | 0 | 0 | 0 | 0 |
| Timeout reward policy | `benchmark_timeout_is_zero: true` | Same | Same | Same |
| Partial-score floor | **0.9 (changed/explicit)** | **0.9 (explicit)** | **0.9 (changed/explicit)** | **0.9 (changed/explicit)** |
| Agent step limit | 100 | 100 | 100 | 100 |
| Agent reasoning effort | High | High | High | High |
| Agent cost limit | 0 | 0 | 0 | 0 |
| Agent environment command timeout | 30 seconds | 30 seconds | 30 seconds | 30 seconds |
| HLE judge model | Not applicable | `gpt-5.4-mini-2026-03-17` | Not applicable | `gpt-5.4-mini-2026-03-17` |
| Select operator | `ahe_latest`, 10-minute timeout | `ahe_latest`, 10-minute timeout | `score_child_prop`, seed 0 | `score_child_prop`, seed 0 |
| Rollout operator | `evaluation_replay`, field limit 2,000, 10-minute timeout | Same | Same | Same |
| Trace analyzer | AHE debugger | AHE debugger | `trace_browser` | `trace_browser` |
| Trace input limit | Up to 50 tasks; field limit 2,000 | Same | 30,000 characters | 30,000 characters |
| Trace concurrency | 25 | 25 | Not separately configured | Not separately configured |
| Trace per-job timeout | 10 minutes | 10 minutes | 10-minute operator timeout | 10-minute operator timeout |
| Trace overall timeout | 1 hour | 1 hour | 10 minutes | 10 minutes |
| Trace-debugger whole-job retries | **0 (changed)** | **0 (changed)** | Not applicable; no debugger job | Not applicable; no debugger job |
| Trace-debugger total attempts | **1** | **1** | Not applicable | Not applicable |
| Trace failure behavior | Record analysis unavailable and continue | Same | Preserve trace-browser behavior | Preserve trace-browser behavior |
| Meta-agent variant | AHE | AHE | HyperAgents | HyperAgents |
| Meta-agent runner | Harbor | Harbor | Harbor | Harbor |
| Meta-agent implementation | `FileTaskMiniSweAgent` | Same | Same | Same |
| Meta-agent model | `openai/gpt-5.4-2026-03-05` | Same | Same | Same |
| Meta-agent environment | Docker | Docker | Docker | Docker |
| Meta-agent image | `evolve-meta-agent-app:20260724-tools-mswe245` | Same | Same | Same |
| Meta-agent editable roots | `target` | `target` | `target`, `operators` | `target`, `operators` |
| Meta-agent reasoning effort | High | High | High | High |
| Meta-agent maximum tokens | 64,000 | 64,000 | 64,000 | 64,000 |
| Meta-agent cost limit | 0 | 0 | 0 | 0 |
| Meta-agent timeout per attempt | **1 hour** | **1 hour** | **1 hour (changed from 6 hours)** | **1 hour (changed from 6 hours)** |
| Meta-agent whole-job retries | **1 (changed)** | **1 (changed)** | **1 (changed)** | **1 (changed)** |
| Meta-agent maximum total attempts | 2 | 2 | 2 | 2 |
| Gate/validation | `ahe_artifact_valid`, 10 minutes | Same | HyperAgents validation, 5 minutes; `parent_eligible` gate | Same |
| Record operator | JSONL, 10 minutes | JSONL, 10 minutes | HyperAgents record operator | HyperAgents record operator |
| General operator timeout | 10 minutes | 10 minutes | 10 minutes | 10 minutes |
| LLM/API transport retries | Preserve existing client/library behavior | Same | Same | Same |

## Retry-layer definitions

The word "retry" must remain unambiguous:

1. **Harbor benchmark retry** reruns a benchmark trial. It is zero.
2. **Driver re-evaluation** reruns an evaluation after infrastructure failure.
   It is disabled.
3. **Trace-debugger whole-job retry** reruns a failed trace-analysis agent job.
   It is zero, so each job has one total attempt. A failure becomes
   "analysis unavailable" and does not abort the experiment.
4. **Meta-agent whole-job retry** reruns the important meta-agent job. It is
   one, allowing at most two total attempts, each with a one-hour timeout.
5. **LLM/API transport retry** handles transient request failures inside an
   otherwise single agent attempt. Its existing client/library behavior is
   preserved and is not controlled by the benchmark, driver, trace-job, or
   meta-job retry values above.

## Timeout policy

No absolute agent, verifier, setup, or environment timeout is imposed by the
experiment configuration. Setup, agent, and verifier multipliers are explicitly
one. Harbor therefore applies each task's native timeout.

"Same effective timeout" means method parity within a benchmark:

- AHE/TB2 and HyperAgents/TB2 receive identical Harbor timeout settings.
- AHE/HLE and HyperAgents/HLE receive identical Harbor timeout settings.
- TB2 and HLE may retain different absolute durations because their native
  Harbor task definitions differ.

## Configuration sources and precedence

The recipe, scaffolded workspace, generated evaluator environment, launch
environment, and actual Harbor arguments must agree. Ambient variables must not
silently override the frozen experiment contract.

For the controlled values in this design:

- recipes and scaffolded `evolve.yaml` files contain explicit values;
- generated evaluator environment files contain no conflicting values;
- launch shells do not inherit conflicting `EVOLVE_HARBOR_*` overrides;
- actual Harbor commands use one trial and zero benchmark retries;
- no actual Harbor timeout multiplier is greater than one.

This validation is an operator-run preflight outside the experiment code. It
does not add a preflight stage to the candidate or benchmark implementation.

## Launch procedure

When the user later requests launch:

1. Allocate four new unique IDs using the naming rule above.
2. Scaffold four clean workspaces from the pinned recipes and datasets.
3. Confirm each target is mini-swe-agent and contains `pyproject.toml` and
   `uv.lock`.
4. Audit the frozen YAML, generated evaluator environment, and launch
   environment against the configuration table.
5. Confirm Harbor benchmark retries are zero, driver re-evaluation is disabled,
   trace jobs have one total attempt, and meta-agent jobs have at most two total
   attempts.
6. Start each controller in a controlled state, inspect its actual Harbor
   arguments, and stop immediately if any controlled value differs.
7. Continue all four experiments only after all four effective configurations
   match this contract.

## Verification

Before any real launch, targeted automated tests must cover:

- all four recipes contain setup, agent, and verifier multipliers of one;
- all four recipes contain Harbor `max_retries: 0`;
- all four recipes contain partial floor 0.9;
- all four meta-agents use one-hour timeout and one whole-job retry;
- AHE trace-debugger jobs have one total attempt;
- a trace-debugger failure is recorded without aborting evolution;
- driver evaluation has no automatic infrastructure re-evaluation;
- generated evaluator environment files cannot reintroduce positive Harbor
  retries or timeout multipliers greater than one;
- runtime command construction preserves LLM/API retry behavior while enforcing
  the separate whole-job retry limits.

At launch time, the operator must also verify the actual process arguments on
both hosts. Static configuration tests alone are insufficient.

## Out of scope

- Starting or resuming an experiment during design or implementation.
- Changing models, datasets, splits, task counts, concurrency, UV scoping,
  images, prompts, editable roots, or operator algorithms.
- Changing Harbor's native task timeout definitions.
- Disabling lower-level LLM/API transport retries.
- Reusing any of the four stopped workspaces as a new experiment.
