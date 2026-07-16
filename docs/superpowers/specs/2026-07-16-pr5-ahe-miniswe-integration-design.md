# PR 5 and AHE-on-MiniSWE Integration Design

## Goal

Create one coherent local implementation that combines PR 5's separation of
meta-agent strategies from execution runners with the `feat/ahe-miniswe`
branch's method-faithful AHE-on-MiniSWE work.

The combined implementation must support two scientifically distinct
meta-agent paradigms through the same generic framework:

- AHE uses an independent, fixed meta-agent to evolve only the MiniSWE target.
- HyperAgents evolves the MiniSWE target and the active operator set together.

Both production recipes use Harbor's installed `mini-swe-agent` CLI as the
editing backend. The Harbor runner supplies isolation and artifact transport;
the strategy determines improvement behavior; the surface determines what may
evolve.

Publishing, pushing, opening the combined PR, and closing PR 5 are deferred
until local development and verification are complete.

## Source Designs

PR 5 establishes these boundaries:

- a meta-agent `variant` is an improvement strategy;
- a `runner` determines how the editing agent is launched;
- `local` runs a trusted host command;
- `harbor` runs an isolated Harbor agent and returns an artifact;
- normalized rollout evidence is shared across strategies;
- `feedback_guided` is removed and `agent_command` is replaced by explicit
  strategy and runner configuration.

The AHE branch adds:

- a MiniSWE source target and frozen Harbor evaluator adapter;
- a focused AHE trace analyzer;
- an AHE strategy with evidence, hypothesis, report, and decision semantics;
- frozen model and resource ownership;
- strict AHE gating and method-specific regression coverage;
- cleanup of generic prediction and falsification fields that AHE does not need
  the framework to interpret.

The integration adopts PR 5's strategy/runner architecture as authoritative
and ports AHE behavior onto it. Obsolete `agent_command` implementations are
not mechanically merged.

## Research Semantics

### AHE

The AHE recipe follows the independent optimizer structure used by the
original AHE system:

- the evolving target is the local MiniSWE source tree under `target/`;
- the fixed AHE strategy consumes current rollout evidence and proposes one
  evidence-backed harness change;
- Harbor installs and invokes the released MiniSWE CLI as the editing agent;
- only `target/**` is mutable;
- the AHE strategy, runner, evaluator, gate, archive, and resource limits remain
  outside the mutable surface.

Using MiniSWE for both roles does not make them the same evolving program. The
meta-agent is Harbor's installed CLI; the target is the separate candidate
source tree.

### HyperAgents

The HyperAgents recipe follows a broad self-referential design:

- `target/**` and `operators/**` are mutable;
- every proposal is instructed to contain a substantive target change intended
  to improve benchmark performance;
- any active operator may change alongside that target change;
- the target-change requirement remains prompt-level policy rather than a new
  generic validator;
- the evaluator, mechanism, workspace configuration, archive authority,
  credentials, endpoints, task partitions, and resource limits remain frozen.

This makes the target agent and improvement procedure one inherited candidate
without making the Harbor runner itself mutable.

## Shared Meta-Agent Architecture

The library contains strategy, runner, and support layers with independent
responsibilities:

```text
strategy:  ahe | hyperagents
              |
              v
support:   normalized feedback/evidence loading
              |
              v
runner:    local | harbor
              |
              v
agent:     mini-swe-agent | another Harbor agent or local command
```

`library/meta_agent/ahe.py` owns only AHE prompting, reporting, and result
semantics. `library/meta_agent/hyperagents.py` owns only HyperAgents prompting,
history, and self-referential mutation semantics. Both delegate editing-agent
execution to `library/meta_agent/runners` and share evidence loading from
`library/meta_agent/support`.

Runner identity, agent identity, usage, output, patch, changed paths, and
surface results are recorded consistently across strategies.

## Harbor Editable Bundles

The Harbor runner gains an explicit `editable_roots` configuration. Roots are
transport boundaries: they determine which candidate trees the isolated agent
can inspect and return. The existing surface policy remains the write-authority
boundary.

The runner validates that roots are relative, nonempty, non-overlapping, do not
escape the checkout, and are covered by the configured mutable surface. It then
creates an isolated bundle under `/app/candidate` while preserving repository
paths.

AHE uses:

```yaml
operators:
  meta_agent:
    variant: ahe
    runner: harbor
    agent: mini-swe-agent
    editable_roots: [target]
    timeout_s: 3600
```

HyperAgents uses:

```yaml
operators:
  meta_agent:
    variant: hyperagents
    runner: harbor
    agent: mini-swe-agent
    editable_roots: [target, operators]
    timeout_s: 21600
```

The MiniSWE meta-agent is Harbor's built-in installed agent, derived from
`BaseInstalledAgent`. Harbor installs and runs the `mini-swe-agent` CLI inside
the task environment. These recipe paths do not need a local `command`.

The source-backed `MiniSweSourceAgent` remains a separate frozen evaluator
adapter. It installs and executes the evolving target source for canonical
evaluation; it is not the default meta-agent backend.

## Artifact Return and Application

Harbor returns only `/app/candidate`. Before the checkout changes, the runner
requires:

- a successful Harbor trial and artifact manifest;
- exactly the configured roots, with no unexpected top-level payload;
- ordinary files and directories only;
- no symlinks, special files, or resolved paths outside the artifact;
- a clean `git diff --check` result;
- no retained mutation outside the workspace surface policy.

The runner stages all returned roots and applies them transactionally. Either
all approved changes are installed or the original checkout is restored. A
missing root, malformed manifest, failed agent, invalid tree, invalid diff, or
surface violation leaves the checkout unchanged and produces an explicit
meta-agent failure.

Commands and logs are redacted before retention. Credentials and proxy values
are forwarded through controlled environment configuration rather than recipe
files.

## Natural Operator Stage Semantics

HyperAgents retains the driver's existing natural stage behavior. An operator
change becomes active the next time that operator is invoked:

```text
rollout -> trace analyzer -> meta-agent mutation -> validate -> evaluate -> gate -> record
```

Consequently:

- changed rollout, trace-analyzer, and meta-agent operators affect later
  generations because their current invocations have already completed;
- changed validate, novelty, gate, or record operators may affect the current
  generation when their stages have not yet run;
- canonical evaluation remains external and frozen, so operator mutations
  cannot rewrite the benchmark score;
- all operator mutations remain visible in the inherited patch and archive.

The framework does not add parent-operator snapshots or delayed activation.
The broad HyperAgents design documents and tests must describe this natural
stage behavior rather than claiming that every operator mutation is
descendant-only.

## Framework and Recipe Ownership

The large implementation belongs mainly in reusable framework and library
capabilities:

- shared strategy/runner dispatch;
- shared evidence loading;
- nested runner/support asset vendoring;
- Harbor installed-agent configuration;
- editable-bundle construction;
- multi-root validation, transactional application, and failure reporting;
- consistent runner provenance and usage artifacts;
- migration away from `agent_command` and `feedback_guided`.

Method-specific behavior remains outside the generic mechanism:

- AHE diagnosis, hypotheses, reports, and prompts remain in the AHE operators;
- HyperAgents self-referential policy remains in its meta-agent operator;
- AHE trace selection remains in its trace-analyzer operator;
- MiniSWE source installation remains in the frozen evaluator adapter.

Recipes stay declarative. They choose strategy, runner, Harbor agent, editable
roots, evaluator binding, and experiment limits; they do not reimplement
transport or strategy logic.

## Integration History

Implementation will use a fresh local integration branch based on
`origin/main`. PR 5's commits will be replayed first with authorship preserved.
The AHE branch will then be ported semantically in coherent layers.

Conflict resolution follows the approved architecture:

- keep PR 5's runner and support split;
- adapt AHE to shared runner dispatch and evidence loading;
- do not restore the deleted `agent_command` variant;
- preserve AHE's method-specific operators, frozen limits, MiniSWE evaluator,
  and generic-contract cleanup;
- incorporate the broad target-required HyperAgents design with natural stage
  semantics;
- add focused integration commits for editable bundles and combined tests.

No push, PR creation, PR edit, or PR closure is part of the local development
phase.

## Verification

### Runner and transport

Tests cover safe and invalid `editable_roots`, AHE target-only bundles,
HyperAgents target-plus-operators bundles, installed MiniSWE agent command
construction, successful multi-root return, transactional rollback, missing or
unexpected roots, symlinks, special files, malformed manifests, Harbor errors,
timeouts, and diff or surface failures.

### Strategies

AHE tests cover shared evidence input, AHE prompt requirements, optional report
preservation, runner provenance, and ordinary meta-agent results. HyperAgents
tests cover the substantive target-change instruction, broad `operators/**`
permission, history context, shared runner dispatch, and inherited operator
changes.

### Stage behavior

Tests document that mutations to already-run operators take effect later while
mutations to not-yet-run validation, gate, and record operators may affect the
current generation. Canonical evaluation remains independent of those changes.

### Integration

Initialization tests verify the exact AHE and HyperAgents surfaces and runner
configuration. Fake-Harbor end-to-end tests exercise both artifact scopes
without credentials or a live model. Existing MiniSWE source-evaluator,
resource-freezing, AHE trace, AHE gate, recipe migration, and workspace-vending
tests remain covered.

Focused tests run first, followed by Ruff checks, type checking, and the full
test suite.

## Non-Goals

- Publishing or closing a GitHub PR during local development.
- Using Codex as the default AHE or HyperAgents editing agent.
- Using the evolving source-backed MiniSWE evaluator adapter as the default
  meta-agent.
- Making the Harbor runner, canonical evaluator, mechanism, configuration,
  archive authority, credentials, task partitions, or resource limits mutable.
- Adding a generic AHE schema or AHE-specific framework contract.
- Enforcing HyperAgents' substantive target-change instruction with a new hard
  framework validator.
- Adding delayed or parent-snapshot operator activation.
- Sending the complete workspace, evaluator, or archive into Harbor.
