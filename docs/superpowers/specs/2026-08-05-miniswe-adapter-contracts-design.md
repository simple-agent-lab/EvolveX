# MiniSWE Adapter Contracts Design

## Goal

Make the MiniSWE integrations clear and durable without introducing a general
agent capability framework. Preserve the separate trust roles of the installed
evolution agent and the evolved candidate runtime, make session metadata
optional, remove MiniSWE assumptions from AHE, and eliminate class-name suffix
inference.

## Scope

This change covers:

- optional `EVOLVE_SESSION_ID` handling in both MiniSWE execution paths;
- target-neutral AHE meta-agent instructions;
- clearer names for the installed and candidate MiniSWE adapters;
- removal of `endswith(":MiniSweSourceAgent")` and
  `endswith(":FileTaskMiniSweAgent")` behavior selection;
- removal of legacy support for running the candidate-source adapter as a
  meta-agent; and
- focused compatibility aliases for existing adapter import paths.

It does not redesign recipes, experiment scripts, Harbor's agent registry, or
the general evaluator configuration model. Recipe edits are limited to using
the clearer canonical adapter names.

## Adapter Roles and Names

The two adapters remain separate because they enforce different trust and
installation contracts.

### `InstalledMiniSweAgent`

This is the canonical replacement for `FileTaskMiniSweAgent`. It runs the
fixed MiniSWE installation supplied by the meta-agent runtime image. It is used
for mutation, debugging, and read-only judging. Transporting instructions
through a mounted file is an implementation detail, not part of its public
name.

### `CandidateMiniSweAgent`

This is the canonical replacement for `MiniSweSourceAgent`. It is an evaluator
adapter for evolved MiniSWE source under `target/`. It validates the candidate
project and lockfile, uploads the source, installs it in an isolated runtime,
and invokes the candidate's Python API.

The candidate adapter is evaluator-only. The Harbor meta-agent runner will no
longer select candidate-source installation or config-command behavior for it.
This removes a legacy self-referential execution path that no supported recipe
uses.

The old class names remain importable aliases during migration. First-party
recipes use the canonical names. Compatibility recognizes only the exact old
and new first-party identifiers; arbitrary classes with matching suffixes gain
no special behavior.

## Shared and Separate Implementation

Common MiniSWE response-model configuration may be factored into small pure
helpers where both adapters can consume it without crossing the container
boundary. The adapters themselves remain separate:

- installed-agent setup and file instruction transport stay with
  `InstalledMiniSweAgent`;
- candidate validation, frozen installation, preflight, and source execution
  stay with `CandidateMiniSweAgent`; and
- candidate failures remain distinguishable from runtime infrastructure
  failures.

No environment-variable switch chooses between trusted installed code and
untrusted candidate source inside one adapter.

## Session Identifier Contract

`EVOLVE_SESSION_ID` is optional and is used literally when supplied.

For both MiniSWE adapters:

1. If `EVOLVE_SESSION_ID` is non-empty, use its exact value as
   `prompt_cache_key` and emit the endpoint-specific header
   `extra: {"session_id": <value>}`.
2. If it is absent or empty, retain a generated per-agent `prompt_cache_key`
   and omit the `extra` header entirely.
3. The framework does not modify, suffix, validate for uniqueness, or rotate a
   configured identifier. Avoiding reuse across unrelated sessions is the
   user's responsibility.

The candidate adapter explicitly forwards `EVOLVE_SESSION_ID` into its
embedded source runtime. Other custom endpoint headers remain outside this
change.

## AHE Prompt Contract

The permanent AHE prompt describes improving the configured candidate harness
through its declared mutable surface. It must not mention MiniSWE,
`DefaultAgent`, the `mini` configuration, or a fixed `target/**` execution
path.

The prompt uses the existing workspace contract to expose editable roots,
detected runtime prompt/configuration, skills, memory, tools, and evidence. AHE
continues to require one coherent, evidence-supported harness change and its
change manifest. Target-specific execution facts belong to target adapters or
recipe documentation, not the reusable AHE operator prompt.

## Harbor Runner Dispatch

Evolve does not describe every Harbor-supported agent. Ordinary Harbor agents
use the generic runner path.

Special handling is restricted to exact first-party installed-MiniSWE
identifiers and centralized behind clearly named helper functions or constants.
Those helpers control only Evolve-owned behavior:

- mounted-file instruction transport;
- MiniSWE submission-status validation;
- read-only report artifact handling; and
- the config-command timeout path required by the installed MiniSWE adapter.

The candidate MiniSWE identifier is used by evaluator workspace preparation,
not meta-agent runner dispatch. Suffix matching is removed from the runner,
trace analyzers, and timeout-budget code.

## Compatibility and Migration

- Existing workspaces using the exact legacy adapter identifiers continue to
  resolve through aliases.
- Supported recipes switch only their adapter identifier strings; benchmark,
  model, image, concurrency, and timeout choices remain unchanged.
- Custom Harbor agents default to the generic path. A custom class named
  `MiniSweSourceAgent` or `FileTaskMiniSweAgent` receives no implicit behavior.
- No experiment orchestration scripts are changed.

## Testing

Tests will establish the following contracts before implementation:

1. Each MiniSWE adapter uses a configured `EVOLVE_SESSION_ID` literally for
   the cache key and optional header.
2. Without the variable, each adapter generates a cache key and omits the
   custom `extra` header.
3. The candidate adapter forwards the variable into its embedded runtime.
4. The AHE prompt contains target-neutral language and none of the removed
   MiniSWE-specific assumptions.
5. Canonical and exact legacy installed-agent identifiers retain file
   transport, timeout, artifact, and submission behavior.
6. Suffix-sharing custom identifiers remain generic.
7. The candidate adapter remains supported by evaluator initialization and
   execution but no longer selects a meta-agent runner branch.
8. Existing AHE, HyperAgents, and hill-climb recipe assertions continue to pass
   after their identifier-only migration.

## Non-Goals

- A public plugin capability registry.
- A universal description of Harbor agents.
- Combining trusted installed execution and untrusted candidate execution in
  one adapter.
- Broader recipe/profile composition work.
- Changes to remote experiment workspaces or scripts.
