# Runtime Profiles and Preflight: Phase 3 Design

## Purpose

Move runtime preparation, endpoint authentication, dependency handling, proxy
normalization, and launch checks out of experiment scripts and into one
framework-owned path for future experiments.

This phase implements the runtime-profile and preflight portion of the
approved future experiment framework. It does not add the external
click-to-start specification or lifecycle service; those remain Phase 4.

Existing and historical experiment workspaces, scripts, commits, artifacts,
and reports are not modified or migrated. Their vendored mechanisms continue
to run as they do today.

## Approved direction

Future model-backed execution uses the ByteDance GPT-5.4 OpenAI-compatible
endpoint through environment-provided `OPENAI_API_KEY` and
`OPENAI_BASE_URL`. Codex `auth.json` is unavailable and is neither required,
inspected, synthesized, nor used as a fallback.

AEvolve and GEPA retain their Codex agent semantics. They use Harbor's existing
API-key authentication mode instead of the repository's current forced
`auth.json` behavior. AHE and HyperAgents retain their MiniSWE agent semantics.
Replacing Codex with MiniSWE would change partner-method behavior and is out of
scope.

## Design principles

1. Runtime behavior is selected by one versioned profile, not assembled in an
   experiment launcher.
2. Profile names describe capabilities, not experiment methods.
3. Profile resolution, validation, hashing, and receipt writing are single
   framework operations.
4. Future strict profiles fail closed; legacy compatibility is explicit and
   cannot be mistaken for certification.
5. Ordinary preflight is read-only and makes no network request. Smoke is a
   separate, non-mutating operation and may perform a minimal live request.
6. Secrets never enter contracts, profile files, receipts, diagnostics,
   command records, or hashes. Raw endpoint and proxy values never appear in
   persisted artifacts; the normalized endpoint is used only to calculate a
   non-secret model-route digest and is then discarded.
7. Python owns policy and typed data. Shell remains a thin process boundary.
8. Shared code never branches on `aevolve`, `ahe`, `gepa`, or `hyperagents`.

## Options considered

### 1. Typed framework profiles with generated resolved profile (selected)

Define a small typed profile registry in framework code. Recipes select one
profile name. Workspace initialization resolves the profile and immutable
runtime pin into canonical JSON. Evaluation, preflight, the Harbor evaluator,
and Harbor meta-agent runners consume the same resolved policy.

This approach gives one source of truth, stable hashing, simple recipe input,
and direct unit-test boundaries. It also lets old vendored workspaces remain
unchanged.

### 2. External YAML profile files

Store profiles as independent YAML resources and copy them into workspaces.
This looks data-driven, but adds another parser and validation surface while
the initial profile set contains only two small variants. It also makes it
easier for profile schema and execution behavior to drift.

### 3. Infer policy from agent and `candidate_runtime`

Keep the existing configuration and infer a profile from the selected agent
class and presence of `candidate_runtime`. This minimizes visible recipe
changes but hides launch-critical behavior, prevents explicit immutable
identity, and perpetuates the current duplication.

## Configuration

Future recipes select exactly one profile:

```yaml
evaluator:
  runtime:
    profile: harbor-bytedance-v1
```

or:

```yaml
evaluator:
  runtime:
    profile: harbor-bytedance-uv-v1
```

The two Phase 3 profiles are:

| Profile | Candidate dependencies | Model route | Intended capability |
|---|---|---|---|
| `harbor-bytedance-v1` | None | ByteDance OpenAI-compatible API | Agent owns its task runtime |
| `harbor-bytedance-uv-v1` | Frozen `uv` project at `target`, Python 3.12 | ByteDance OpenAI-compatible API | Candidate is a Python project |

AEvolve and GEPA select `harbor-bytedance-v1`. AHE, HyperAgents, and the
supported hill-climb recipe select `harbor-bytedance-uv-v1`.

The profile replaces future recipe-level `candidate_runtime` declarations.
`evaluator.candidate_runtime` remains a compatibility input for old recipes
and workspaces. New generated configurations never write both forms.

Unknown profile names, unknown runtime fields, or contradictory legacy fields
are configuration errors.

## Components

### `RuntimeProfileV1`

A frozen typed value defines framework policy:

```text
schema_version
name
engine
model_route
required_credentials_by_role
forbidden_credentials
required_tools
candidate_runtime (optional)
dependency_policy
cache_policy
network_policy
proxy_policy
model_bypass_policy
preflight_capabilities
smoke_capabilities
```

Profile definitions contain no host paths, credential values, endpoint values,
proxy values, or runtime image tags. Versioned profile names are immutable:
changing policy requires a new name.

The initial registry contains only the two profiles above. A registry is
preferable to a plugin system in this phase because there is no demonstrated
need for third-party runtime profiles.

### `ResolvedRuntimeProfileV1`

Workspace initialization combines the selected definition with the immutable
evaluator runtime digest supplied through the existing
`EVOLVE_RUNTIME_DIGEST` interface and a digest of the normalized model route
derived from `OPENAI_BASE_URL`. It writes:

```text
evaluator/runtime-profile.json
```

The generated file contains the complete non-secret profile payload,
`runtime_digest`, `model_route_digest`, and `profile_digest`. The normalized
model URL itself is discarded after hashing. `profile_digest` is the SHA-256
of canonical JSON containing the policy, runtime digest, and model-route
digest. The existing `evaluator/runtime.pin` is retained for compatibility and
must equal the resolved profile's `runtime_digest`.

Generation zero commits both files. Contract resolution reads the trusted
generation-zero resolved profile and verifies its digest instead of
reconstructing policy from the caller's environment.

### Runtime environment resolver

One pure framework function accepts a resolved profile and the current process
environment and returns a role-specific runtime environment plan. It owns:

- Uppercase/lowercase proxy normalization.
- Removal of public dependency hosts from proxy bypass lists.
- Addition of the configured model endpoint hostname to the bypass list.
- Credential-name requirements by agent and verifier role.
- Candidate-runtime cache mounts and offline-trial flags.
- Removal of forbidden file-auth variables.
- A redacted evidence view containing names and decisions but not values.

The evaluator and meta-agent runner consume this function. They do not each
reimplement proxy and credential policy.

For both strict profiles, `CODEX_FORCE_AUTH_JSON` and
`CODEX_AUTH_JSON_PATH` are forbidden and removed from child environments. A
present forbidden variable causes preflight to fail with a clear migration
message; it is never silently honored.

### `PreflightResultV1`

Preflight returns and atomically writes a predefined typed receipt:

```text
schema_version
status
profile_name
profile_digest
runtime_digest
mode
checks
required_credential_names_by_role
failure_category (optional)
failure_message (optional, bounded and redacted)
```

Each check has a stable name, status, failure category, and bounded redacted
message. Receipts contain only credential names, route policy names, and the
expected route digest, never credential, endpoint, or proxy values.

The receipt is written under a run-owned preflight attempt directory. It is
operational evidence and is not committed to generation zero.

### Preflight service

The Phase 3 service exposes:

```text
preflight(workspace, mode="ordinary") -> PreflightResultV1
preflight(workspace, mode="smoke") -> PreflightResultV1
```

The initial CLI adapter is:

```bash
evolve preflight WORKSPACE
evolve preflight WORKSPACE --smoke
```

Phase 4's `validate` and `start --smoke` operations will call the same service;
they will not duplicate its checks.

The generated `operators/preflight.sh` becomes a small wrapper around the
vendored framework command. It contains no proxy manipulation, dependency
installation, credential discovery, or method-specific logic.

## Authentication migration

The installed Harbor Codex agent already defaults to `OPENAI_API_KEY`
authentication when `CODEX_FORCE_AUTH_JSON` and `CODEX_AUTH_JSON_PATH` are
absent. Phase 3 uses that supported path.

For future source templates:

- The built-in Codex target wrapper stops overriding
  `_resolve_auth_json_path`.
- The Harbor meta-agent runner stops forcing `CODEX_FORCE_AUTH_JSON`.
- The Harbor meta-agent runner stops stripping `OPENAI_API_KEY`,
  `OPENAI_BASE_URL`, and `OPENAI_API_BASE` for Codex agents.
- The shared runtime environment resolver provides the same endpoint policy
  to Codex and MiniSWE adapters.

No auth file is copied, mounted, generated, searched for, or recorded. Existing
workspaces already containing the old vendored wrapper are not rewritten.

## Ordinary preflight behavior

Ordinary preflight is read-only. It performs these checks in order:

1. Parse and validate the trusted configuration.
2. Resolve and verify `runtime-profile.json`, its digest, and `runtime.pin`.
3. Verify target, evaluator, dataset members, split identity, and evaluation
   contract prerequisites.
4. Check required host executables and exact versions where the profile pins a
   version.
5. Check that the immutable evaluator image is available locally without
   pulling it.
6. For the `uv` profile, run lock validation without syncing, installing, or
   warming a cache.
7. Check presence of required credential names and absence of forbidden
   credential names.
8. Normalize the configured endpoint, verify that its digest matches the
   resolved profile, and calculate the in-memory proxy plan.

It does not call the model endpoint, install dependencies, pull images, mutate
the target, create a candidate environment, or warm shared state.

Every strict evaluation calls ordinary preflight before creating trial work.
A user cannot bypass the checks by invoking `eval` directly.

## Smoke behavior

Smoke first runs ordinary preflight. It then uses a detached candidate snapshot
and a run-owned temporary overlay to perform the profile's heavier checks:

- Prepare candidate dependencies for the `uv` profile using the existing
  frozen-lock runtime adapter.
- Launch the real selected agent adapter in its evaluator image.
- Make one minimal GPT-5.4 request through the configured ByteDance endpoint.
- Verify the agent can initialize, receive a response, and write its expected
  runtime evidence.
- Tear down the temporary environment while retaining redacted logs and the
  preflight receipt.

The smoke prompt performs no repository task and has no editable mount of the
experiment workspace. Smoke never rewrites `evolve.yaml`, amends `gen/0`, moves
tags, appends evaluation rows, or selects a champion.

One live smoke is run for each distinct profile after local unit and integration
gates pass. It uses the ByteDance endpoint only. Four-method end-to-end smoke
belongs to Phase 5 after the shared profile behavior is proven.

## Dependency and cache policy

`harbor-bytedance-v1` has no framework-managed candidate project.

`harbor-bytedance-uv-v1` requires:

- `target/pyproject.toml`.
- `target/uv.lock`.
- Python 3.12.
- Frozen lock validation.
- Explicit preparation before trials.
- Offline trial execution with `UV_OFFLINE=1`.
- Content-addressed shared download and managed-Python caches.
- Per-attempt writable environments so trials cannot mutate shared inputs.

Preparation may use the dependency proxy. Trial execution must use the prepared
offline inputs. A missing or inconsistent candidate lock is
`candidate_invalid`; a network, registry, disk, or tool failure while preparing
a valid lock is `infrastructure_failed`.

The current `EVAL_STUB=1` compatibility shortcut remains available only to
legacy/unverified test paths. It cannot produce a certified strict runtime
receipt. Strict integration tests use an explicit fake runtime adapter rather
than claiming an unprepared runtime was observed.

## Proxy and network policy

The environment resolver treats dependency and model traffic separately:

- Dependency installation inherits the configured HTTP/HTTPS proxy.
- Public package hosts are removed from inherited bypass lists.
- The model endpoint hostname is added to the bypass list when the profile's
  model-bypass policy requires direct routing.
- Lowercase and uppercase proxy variables receive identical normalized values.
- Trial execution uses the narrowest network behavior supported by the
  evaluator image and prepared dependencies.

The profile records the policy and normalized endpoint digest, not the actual
proxy or endpoint. The endpoint host is derived at runtime and is not written
to disk. Redaction covers literal environment values and common credential
forms before logs or receipts are persisted.

## Evaluation-contract integration

Contract v1 keeps its existing top-level schema. Phase 3 changes the source and
meaning of these fields:

- `runtime_profile` is the resolved profile name.
- `runtime_profile_digest` is the verified digest of the complete resolved
  non-secret profile payload and immutable runtime digest.
- `runtime_digest` must match both `runtime-profile.json` and `runtime.pin`.
- `candidate_dependency_digest` is derived from the resolved profile's
  candidate runtime adapter and candidate lock files.
- `model_identity` includes the non-secret model-route policy name and route
  digest in addition to agent and model.

A missing profile, mismatched digest, forbidden auth variable, or failed
ordinary preflight prevents strict contract execution. Legacy workspaces
without a generated resolved profile keep their existing `legacy-pin` contract
mode and remain uncertified rather than being silently upgraded.

## Error model

Preflight failures use stable categories:

```text
configuration_invalid
runtime_profile_invalid
runtime_unavailable
dependency_lock_invalid
dependency_tool_unavailable
credential_missing
credential_forbidden
endpoint_invalid
container_image_unavailable
network_unavailable
model_smoke_failed
```

Configuration, lock, and candidate-project defects are actionable before a run.
Host tool, image, credential, endpoint, and network defects are infrastructure
failures. None becomes a benchmark reward or a candidate score.

Messages are bounded and redacted. Detailed logs remain in the run-owned smoke
attempt and are referenced safely by the receipt.

## Compatibility

- Current and historical experiment directories and scripts are untouched.
- Existing vendored workspaces keep their vendored auth and runtime behavior.
- Existing `evolve init` and `evolve run` commands remain supported.
- Existing `evaluator.candidate_runtime` is accepted only through explicit
  compatibility resolution.
- Future built-in recipes write `evaluator.runtime.profile` and no longer write
  `candidate_runtime`.
- There are no method-name branches and no new experiment-specific scripts.
- The source framework no longer depends on Codex `auth.json` for future
  generated workspaces.

## Testing strategy

Implementation follows test-driven development in these gates.

### Unit tests

- Profile lookup, schema validation, and immutable name behavior.
- Canonical resolved-profile hashing and runtime-pin matching.
- Model-route normalization, digest matching, and raw-URL non-persistence.
- Recipe normalization and legacy `candidate_runtime` compatibility.
- Role-specific credential requirements and forbidden auth variables.
- Proxy normalization, dependency-host removal, and model-host bypass.
- Redacted preflight serialization with secret-leak canaries.
- Stable failure-category mapping.

### Integration tests

- Initialize each built-in recipe and verify its generated resolved profile.
- Run ordinary preflight with fake tools, images, and credentials.
- Prove ordinary preflight does not mutate the workspace or caches.
- Prove strict evaluation cannot bypass a failed preflight.
- Prove the evaluator and meta-agent runners consume the same environment
  resolver.
- Prove Codex API-key mode receives ByteDance endpoint variables and never
  searches for an auth file.
- Prove the `uv` profile validates locks and preserves offline trial behavior.
- Prove legacy workspaces continue through named unverified compatibility.

### Template and security tests

- Generated `preflight.sh` is a thin wrapper.
- Harbor shell contains no independent credential or proxy policy engine.
- Contracts, profiles, receipts, logs, and command records contain no secret or
  raw endpoint values.
- No `auth.json` path, file content, or fallback appears in strict future
  runtime artifacts.

### Non-mutating live smoke

After all local tests pass:

1. Run one `harbor-bytedance-v1` smoke with the Codex adapter.
2. Run one `harbor-bytedance-uv-v1` smoke with the MiniSWE adapter.
3. Confirm both use the ByteDance GPT-5.4 route, preserve the workspace tree,
   and produce redacted certified receipts.

No broader experiment is started in Phase 3.

## Implementation boundaries

Expected cohesive source boundaries are:

```text
src/evolve/runtime_profiles.py   profile types, registry, resolution, hashing
src/evolve/runtime_environment.py role-specific environment planning
src/evolve/preflight.py          checks, result schema, receipt writing
```

Existing `uv_runtime.py`, `workspace.py`, evaluation-contract code, Harbor
evaluator scaffolds, built-in Codex seed, and Harbor meta-agent runner call
these components. They are changed only where required to remove duplicated
policy or consume the resolved profile.

If implementation reveals that Harbor does not propagate the supported
API-key environment into a real Codex trial, work stops at that external
boundary. It must not generate an auth file or add an experiment-specific
launcher workaround.

## Acceptance criteria

Phase 3 is complete when:

- Every future built-in recipe selects one versioned runtime profile.
- Initialization automatically generates and commits a canonical resolved
  profile with a verified digest.
- A changed model endpoint fails route-digest verification before trial work.
- Contract v1 hashes the complete resolved runtime policy.
- Ordinary preflight is read-only, typed, mandatory, and fail-closed.
- Smoke is isolated, non-mutating, and performs one real ByteDance GPT-5.4
  request per profile.
- Codex and MiniSWE agents use the ByteDance endpoint through API-key
  authentication.
- Strict future paths neither inspect nor use Codex `auth.json`.
- Evaluator and meta-agent execution share one proxy and credential policy.
- Candidate dependency preparation is explicit and trials use frozen offline
  inputs.
- Unit, integration, template, security, and two live profile smoke gates pass.
- AEvolve, AHE, GEPA, HyperAgents, and hill-climb recipe initialization and
  ordinary preflight conform without method-name branches.
- Existing and historical experiments remain untouched.
