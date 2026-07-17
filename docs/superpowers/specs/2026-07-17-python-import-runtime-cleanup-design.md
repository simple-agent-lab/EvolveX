# Python Import and Runtime Cleanup Design

**Date:** 2026-07-17

**Status:** Approved for implementation planning

## Objective

Remove repository-wide dependence on `sys.path` mutation and `PYTHONPATH`
injection while preserving operator, evaluator, rollout, meta-agent, and
generated-workspace behavior on macOS and Linux. Third-party Python runtimes,
including Harbor and custom Harbor adapters, must be selected and reproduced by
locked `uv` projects rather than ambient interpreter state.

This is an intentionally breaking migration. The legacy `agent_pythonpath`
configuration is removed rather than deprecated.

## Supported Platforms

The supported host platforms are macOS and Linux. The implementation must use
`pathlib`, argument-vector subprocess calls, and platform-aware path handling.
Existing POSIX shell, process-group, and signal behavior remains supported on
both hosts.

Native Windows is explicitly unsupported. Adding it would require a separate
design for shell scripts, signals, process groups, and executable discovery.

## Repository-Wide Invariants

Production Python code must not mutate `sys.path`. Production Python and shell
code must not construct, prepend, append, or export `PYTHONPATH`.

The execution model is:

- the working directory controls access to first-party workspace code;
- adjacent bootstrap scripts load the protected vendored mechanism;
- `uv.lock` controls third-party interpreters and dependencies;
- external commands are invoked with argument vectors rather than shell-built
  command strings;
- child processes do not inherit Python import-environment overrides.

The cleanup covers operator variants and skeletons, Harbor rollout and
meta-agent runners, generated workspace launchers, evaluator templates, test
fixtures, lint configuration, documentation, and examples.

## Runtime Architecture

### First-party operator code

The existing operator launcher remains the single execution boundary. It
executes the selected trusted operator source while setting the candidate
checkout as the subprocess working directory. Workspace-local `library.*`
imports therefore resolve from one documented working-directory contract. No
operator or library module may repair or reorder imports at module load time.

The launcher must sanitize inherited Python import variables before starting
the child. It preserves required Evolve variables, credentials, proxy settings,
Docker configuration, and ordinary host variables.

### Vendored mechanism bootstraps

Generated workspaces contain the protected mechanism under `.evolve/evolve`.
Small bootstrap scripts are placed beside that package:

```text
.evolve/
├── evolve/
├── launch_evolve.py
└── launch_splits.py
```

The workspace `evolve` shell entry point executes `launch_evolve.py` with the
pinned framework interpreter. Because the script is adjacent to the vendored
package, ordinary Python script import rules locate `evolve` without changing
the caller's working directory or import path. `launch_splits.py` provides the
same stable boundary for evaluator split selection.

Relative CLI arguments continue to resolve against the caller's working
directory. Interpreter paths and workspace paths containing spaces, quotes,
backticks, dollar signs, and backslashes remain safe.

### Locked Harbor runtime

Generated workspaces contain a protected Harbor runtime:

```text
.evolve/harbor-runtime/
├── pyproject.toml
├── uv.lock
└── evolve_harbor_adapter.py
```

The project locks Harbor and the built-in MiniSWE source adapter into the same
environment. All Harbor entry points use this command prefix:

```text
uv run --project <runtime-project> --frozen harbor
```

The `uv` executable is resolved from `EVOLVE_UV_BINARY` first and then `PATH`.
The Harbor executable is never resolved independently from ambient `PATH`.

The default runtime project is
`<workspace>/.evolve/harbor-runtime`. A `harbor_project` setting may replace it
for an operator or evaluator that requires a custom adapter. Relative project
paths resolve from the workspace root; absolute paths remain absolute. A custom
runtime must contain both `pyproject.toml` and `uv.lock`, and it must declare
Harbor and the selected adapter in that locked project.

The removed `agent_pythonpath` setting is rejected with an actionable breaking
migration error. There is no compatibility path that translates it into an
environment variable.

## Harbor Adapter Boundary

The built-in `target/harbor_agent.py` file is host infrastructure even though it
currently lives under the candidate source tree. It is already excluded from
the mutable surface. The implementation moves it into the protected Harbor
runtime and changes the configured adapter import to the protected module.

The adapter no longer uses its own `__file__` location as candidate source. The
caller supplies the candidate source directory explicitly. The adapter
validates that directory, including its project declaration, lockfile, and
MiniSWE source package, before uploading it into the task environment. Candidate
source remains mutable; the host adapter, Harbor version, and host dependencies
remain frozen.

Evaluator, rollout, and meta-agent flows use the same runtime-resolution and
environment-sanitization contract. Python implementations share a focused
runtime helper. The evaluator shell constructs the equivalent `uv` argument
prefix without evaluating generated shell text.

## Environment Handling

Before launching Python or Harbor children, the implementation removes
`PYTHONPATH`, `PYTHONHOME`, and unrelated `VIRTUAL_ENV` values from the copied
environment. It does not mutate the parent process environment.

The following classes of values remain available when needed:

- Evolve workspace, generation, timeout, run, and runtime variables;
- API credentials and explicit agent environment entries;
- HTTP, HTTPS, and no-proxy settings;
- Docker and Colima settings;
- cache directories and the explicit `EVOLVE_UV_BINARY` override.

Paths travel as individual subprocess arguments or environment values. No code
joins import roots with `os.pathsep`, assumes `:` as a separator, or constructs
an executable command by interpolating untrusted paths.

## Error Handling

Failures are early, deterministic, and do not trigger an ambient fallback:

- missing `uv` reports the supported override and installation requirement;
- missing runtime directories, `pyproject.toml`, or `uv.lock` report the fully
  resolved path;
- `agent_pythonpath` reports that it was removed and that a locked
  `harbor_project` is required;
- `uv` synchronization or execution failures preserve useful diagnostics and
  are classified as infrastructure failures;
- adapter import failures identify the configured adapter and runtime project;
- malformed candidate source remains classified as candidate-invalid;
- Harbor output and recorded commands continue to redact credentials and bearer
  tokens.

There is no fallback to a separately installed `harbor` command and no retry
with a modified import path.

## Existing Workspaces

Existing generated workspaces are not silently rewritten. Their operator,
evaluator, target-adapter, and protected mechanism trees are part of experiment
history. This breaking release requires affected experiments to be regenerated
or migrated explicitly using the documented new layout.

An old workspace missing the locked runtime receives a clear error rather than
using ambient Harbor or import configuration.

## Verification Strategy

### Static invariants

Tests inspect runtime Python syntax and production shell templates to prevent
reintroduction of `sys.path` mutation or `PYTHONPATH` assignment. Library and
template-wide Ruff `E402` exemptions are removed; imports return to normal
top-of-file order. Test fixtures that currently modify import paths use explicit
module loading or package imports instead.

### Unit tests

Unit coverage includes:

- default, relative, and absolute Harbor project resolution;
- required project and lock files;
- legacy configuration rejection;
- `uv` executable selection and missing-executable errors;
- exact `uv run --project ... --frozen harbor` argument construction;
- removal of inherited Python import variables without parent-environment
  mutation;
- preservation of required credentials, proxies, Docker settings, and Evolve
  variables;
- paths containing macOS/Linux-valid shell metacharacters and whitespace.

### Integration tests

Integration coverage includes:

- every operator family importing and executing without path mutation;
- trusted operator source executing against the intended candidate checkout;
- generated console behavior from inside and outside the workspace;
- preservation of caller working directory and relative CLI arguments;
- evaluator split bootstrapping through the adjacent protected launcher;
- the built-in adapter importing inside its locked `uv` runtime and receiving
  candidate source explicitly;
- fake Harbor executions through evaluator, rollout, and meta-agent paths;
- candidate-invalid and infrastructure-failure ownership remaining unchanged.

### Repository and CI verification

Completion requires:

- Ruff lint;
- Ruff format check for changed Python files;
- `ty` type checking;
- the complete pytest suite;
- a wheel build and isolated install/resource smoke test;
- the init, run, and verify self-driving smoke test;
- a GitHub Actions test matrix using `ubuntu-latest` and `macos-latest`.

The locked Harbor runtime is smoke-tested by importing its adapter and invoking
the Harbor CLI help/version path through `uv run --project ... --frozen`. Tests
that validate orchestration use fake task execution and do not require Docker or
external model credentials.

## Documentation Changes

Repository documentation will:

- replace `agent_pythonpath` examples with locked `harbor_project` examples;
- explain the default protected runtime and custom-adapter packaging contract;
- state the macOS and Linux support boundary;
- document first-run `uv` synchronization and failure behavior;
- provide explicit regeneration or manual migration guidance for old
  workspaces;
- state that setting `PYTHONPATH` is not a supported extension mechanism.

## Non-goals

This cleanup does not add native Windows support, change candidate dependency
policy, redesign Harbor task containers, modify benchmark semantics, or provide
automatic in-place migration of historical workspaces.
