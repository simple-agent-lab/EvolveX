# Runtime Configuration Redesign

## Status

Approved conversational design for revising PR #29 before implementation.

## Goals

- Give users one predictable, project-root `.env` for local credentials, endpoints, and optional proxy settings.
- Support Codex with either API authentication or an explicitly configured `auth.json` file.
- Keep runtime profiles reproducible while making them provider-neutral, declarative, and extensible without editing framework source.
- Keep organization-specific routing and proxy behavior out of the public framework.
- Preserve strict evaluation contracts, content-backed dataset identity, safe artifact handling, and role-isolated Harbor secret transport.
- Reduce the size and coupling of preflight and runtime-environment code without performing unrelated refactors.

## Non-goals

- Implicitly discovering `~/.codex/auth.json`.
- Supporting `auth.json` for agents that do not understand Codex authentication.
- Persisting credentials, authentication paths, literal endpoints, or proxy values in Git or evaluation artifacts.
- Supporting direct user invocation of generated `evaluator/eval.sh`.
- Reorganizing evaluation diagnostics solely to reduce its line count.
- Adding a general plugin framework for runtime profiles.

## Public configuration

The generated experiment project has one user-facing environment file at its root:

```text
my-experiment/
├── .env
├── evolve.yaml
├── target/
├── evaluator/
├── operators/
└── runs/
```

The project-root `.env` is ignored by Git. Explicit process environment variables override values loaded from it. The CLI does not load a caller-directory or parent-directory `.env`.

Supported local settings include:

```dotenv
# API authentication
OPENAI_API_KEY=...
OPENAI_BASE_URL=...  # optional; unset means the official OpenAI endpoint

# Explicit Codex file authentication
CODEX_AUTH_JSON_PATH=/absolute/path/to/auth.json

# Optional infrastructure passthrough
HTTP_PROXY=...
HTTPS_PROXY=...
ALL_PROXY=...
NO_PROXY=...

# Optional private runtime-profile directories
EVOLVE_RUNTIME_PROFILE_PATH=/private/profiles:/shared/profiles
```

The framework may generate private, per-role Harbor environment files at runtime. These files are internal implementation artifacts, use restrictive permissions, and are never edited by users.

## Authentication

Authentication is resolved for the actual agent implementation.

For Codex:

1. If `CODEX_AUTH_JSON_PATH` is set, validate that it names a readable regular file and use it.
2. Otherwise, if `OPENAI_API_KEY` is set, use API authentication.
3. Otherwise, preflight fails with a typed missing-credential error.

There is no implicit lookup of `~/.codex/auth.json`. When both methods are configured, the explicit auth-json path wins. `OPENAI_BASE_URL` is optional in API mode; an unset value identifies the official OpenAI endpoint.

Non-Codex agents require their supported API credential mechanism. Supplying only `CODEX_AUTH_JSON_PATH` for such an agent fails preflight with an `auth_json_unsupported` category.

Authentication paths and credential values are local execution data. They are excluded from runtime profiles, contracts, receipts, logs, and persisted environment evidence.

## Endpoint identity

Changing the model endpoint after initialization invalidates strict evaluation certification. The framework normalizes the effective endpoint and freezes only its SHA-256 digest in the resolved evaluation inputs. It never persists the literal custom endpoint URL.

An unset `OPENAI_BASE_URL` maps to a stable built-in identity for the official OpenAI endpoint. The evaluator's configured model name remains part of the evaluation contract.

## Proxy behavior

Proxy support is infrastructure passthrough, not core experiment policy. When configured, standard `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` values are forwarded unchanged to the roles that launch networked processes.

The public framework does not:

- maintain a hardcoded dependency-host list;
- rewrite `NO_PROXY`;
- add the model host automatically;
- define ByteDance-specific proxy variables;
- persist proxy values or incorporate them into the evaluation contract.

Organization-specific proxy setup belongs in the ignored project-root `.env`, deployment scripts, or private runtime-profile distribution. A profile may declare that standard proxy passthrough is supported, but not contain proxy values or private routing details.

## Declarative runtime profiles

Runtime profiles describe provider-neutral, reproducible execution policy:

- evaluator engine;
- immutable runtime image requirements;
- required host tools;
- candidate runtime variant, project, and Python version;
- dependency, cache, and network execution modes;
- supported preflight and smoke capabilities.

Profiles do not describe credentials, auth paths, endpoint URLs, proxy values, organization-specific hosts, or ByteDance-specific routes.

Neutral built-in profiles are shipped as YAML or JSON data, for example `harbor-v1` and `harbor-uv-v1`. Recipes continue to select profiles by portable name:

```yaml
evaluator:
  engine: harbor
  runtime:
    profile: harbor-uv-v1
```

Profile resolution searches directories listed in `EVOLVE_RUNTIME_PROFILE_PATH` and the packaged built-in profile directory. A name must resolve exactly once; duplicate definitions are rejected rather than resolved by implicit precedence. All definitions pass the same schema validation.

Initialization freezes the safe resolved profile and its digest into `gen/0`. Runtime image references must be validated as immutable rather than merely nonempty. Existing `harbor-bytedance-*` definitions and public aliases are removed because this feature has not shipped on `main`; branch recipes migrate directly to neutral profile names.

## Evaluator configuration

`evaluator_config.py` remains the shared normalization boundary:

- `repetitions` is the canonical field;
- legacy `k` remains accepted;
- specifying both requires equal values;
- normalized generated configuration omits `k`;
- runtime profile syntax is checked before workspace generation.

The normalizer validates the profile reference shape but delegates full name lookup and schema validation to the runtime-profile loader. This avoids coupling generic evaluator parsing to a Python constant registry.

## Runtime environment boundaries

Runtime environment handling is divided into focused operations:

1. Load explicit process values over the project-root `.env`.
2. Resolve authentication for the selected agent or meta-agent.
3. Build role-specific agent, verifier, and meta-agent environments.
4. Convert sensitive values into Harbor-resolvable templates backed by private process variables.
5. Persist only templates and non-secret evidence about forwarded variable names.

`runtime_environment.py` retains generic role isolation, validation, Harbor templating, atomic private-file writing, and unchanged standard proxy passthrough. Authentication selection moves to a focused authentication module. ByteDance policy, dependency-host tables, automatic bypass rewriting, and the misleading legacy rejection of file authentication are removed.

No user manages `runtime-agent.env`, `runtime-verifier.env`, or equivalent generated files.

## Preflight

Preflight continues to answer whether an exact strict evaluation can run. Ordinary mode checks frozen configuration, profile and image identity, evaluation contract resolution, required tools, candidate dependency locks, authentication, and endpoint consistency. Smoke mode additionally performs one minimal real model request.

The implementation is split by responsibility:

```text
preflight/
├── models.py     # receipt and check data models
├── checks.py     # typed individual checks and host probes
└── runner.py     # ordering, short-circuiting, and receipt construction
```

Failures use typed categories instead of classifying runtime errors by searching error-message strings. Supplying a restricted environment to a check does not merge unspecified ambient host variables back into the subprocess.

Receipts contain bounded, redacted messages and hashed relative artifact references. They never contain credentials, auth paths, literal custom endpoints, or proxy values.

## Evaluation contract

`evaluation/contract.py` remains one cohesive module. It receives a module-level trust-model explanation and clear internal sections for data models, resolution, receipt verification, serialization, and helpers.

Strict contract resolution continues to read evaluator inputs from trusted `gen/0` Git objects rather than mutable working-tree files. The contract binds candidate and evaluator trees, evaluator semantics, selected task contents, repetitions and expected trials, immutable runtime policy, endpoint digest, model name, retry policy, and framework version.

Credential values, auth paths, literal endpoints, and proxy configuration are excluded.

## Dataset and split identity

Version 2 split manifests remain content-backed. Local dataset identity covers selected task names, file contents, relevant modes, directory structure, and safe internal symlinks. Manifest construction computes each task digest once and reuses those digests for both per-task entries and the aggregate dataset identity.

Registry datasets are resolved during initialization. The registry must provide immutable dataset metadata and immutable task references such as Git commit IDs or SHA-256 package references. The resolved metadata, per-task identities, selected membership, and aggregate digest are frozen into the split manifest and dataset pin.

Initialization fails clearly when a registry dataset cannot provide immutable identity. It does not silently label such a dataset verified. Version 1 manifests remain readable as `legacy_unverified` for existing workspaces.

## Generated evaluator and test utilities

Generated `evaluator/eval.sh` is an internal framework entrypoint. It consumes prepared runtime inputs and fails clearly when they are missing. Direct standalone invocation is not supported, preventing credential and runtime policy from being duplicated in shell.

`stub_eval.py` receives documentation explaining that it runs only under `EVAL_STUB=1`. `# FAIL` creates an observed failing task, while `# MISSING` intentionally omits a task to test missing-trial materialization.

`candidate/smoke.py` receives documentation explaining that it supports explicit candidate smoke and preflight smoke, not normal recipe evaluation. Its private logs, relative hashed artifact references, mode field, redaction, and bounded structured failure propagation remain.

Evaluation diagnostics retain their current behavior and module boundary. They materialize absent expected trials, distinguish ownership and actionability, bound failure categories, determine retry eligibility, and expose only safe artifact references. Reorganizing diagnostics is deferred because it does not improve the runtime redesign.

## Compatibility and migration

- Legacy `evaluator.k` remains supported.
- Version 1 split manifests remain readable but unverified.
- Workspaces without a runtime profile retain a documented legacy evaluation path where currently required.
- The unmerged `harbor-bytedance-*` profile names are not retained as aliases.
- Host-home Codex authentication is not discovered implicitly; users must configure `CODEX_AUTH_JSON_PATH`.
- The caller-directory `.env` fallback is removed.
- Direct `evaluator/eval.sh` invocation is declared unsupported.

README and recipe documentation list the neutral profiles, project-root `.env` rules, authentication precedence, optional endpoint behavior, profile search path, proxy passthrough, and strict-versus-legacy dataset guarantees.

## Verification

Tests cover:

- API-key authentication with the official endpoint;
- API-key authentication with a custom endpoint;
- explicit Codex auth-json authentication;
- auth-json precedence when both methods are configured;
- absence of implicit home-directory auth discovery;
- rejection of auth-json for non-Codex agents;
- one project-root `.env`, explicit-environment precedence, and removal of caller fallback;
- unchanged proxy passthrough with no host rewriting;
- built-in and private declarative profile lookup;
- duplicate and invalid profile rejection;
- immutable image-reference validation;
- custom endpoint changes invalidating strict certification;
- absence of secrets, auth paths, literal endpoints, and proxy values in persisted artifacts;
- local and registry content identity, including immutable-reference rejection;
- single-pass local task hashing;
- internal evaluator entrypoint failure when prepared runtime inputs are absent;
- ordinary and smoke preflight receipts with typed failures;
- `k` compatibility and `repetitions` normalization;
- existing deterministic stub and candidate-smoke behavior.

The earlier minimal fixes to deterministic README/CI smoke setup and bounded Harbor candidate error codes remain part of the branch and are verified with their focused tests.

## Acceptance criteria

- A standard OpenAI Codex user can run with only `OPENAI_API_KEY` in the project-root `.env`.
- A Codex user can instead configure an explicit `CODEX_AUTH_JSON_PATH`.
- A private endpoint user can add `OPENAI_BASE_URL` without exposing it in Git or receipts.
- Proxy users can set standard variables without framework rewriting.
- A user can add a provider-neutral runtime profile without editing Python source.
- No public runtime profile or core module contains ByteDance-specific policy.
- Default local and registry-backed recipes can produce content-certified evaluation contracts when their sources provide immutable identities.
- Runtime and preflight modules expose focused, documented responsibilities while preserving secret isolation and reproducibility.
