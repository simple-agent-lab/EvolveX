# Python Import and Runtime Cleanup Design

**Date:** 2026-07-17

**Status:** Approved for implementation planning

## Objective

Remove repository-wide dependence on `sys.path` mutation and `PYTHONPATH`
injection without introducing a second runtime-management system. Generated
Evolve workspaces become ordinary `uv` projects, and that one project manages
the host Python environment, Harbor, and Harbor adapters.

This is an intentionally breaking migration. The legacy `agent_pythonpath`
setting is removed rather than deprecated.

## Supported Platforms

The supported host platforms are macOS and Linux. Existing POSIX shell,
process-group, and signal behavior remains supported on both hosts. Native
Windows is explicitly unsupported.

## Core Rule

Each generated Evolve workspace is one `uv` project:

```text
workspace/
├── pyproject.toml
├── uv.lock
├── .venv/                     # ignored
├── .evolve/evolve/            # protected vendored mechanism
├── evolve_harbor_adapter/     # protected host adapter package
├── target/                    # mutable candidate project
├── operators/
└── evaluator/
```

The execution contract is:

- `uv` and `uv.lock` select host Python dependencies and executables;
- the workspace working directory exposes first-party `library.*` modules to
  operator subprocesses;
- explicit filesystem paths identify candidate source;
- production code never mutates `sys.path` or sets `PYTHONPATH`.

There is no nested runtime project, runtime-project resolver, digest-keyed
environment manager, or fallback Harbor installation.

## Workspace Project

`evolve init` copies a pre-locked root `pyproject.toml` and `uv.lock` from the
framework resources; initialization does not resolve dependencies or require
network access. The root project declares the host dependencies needed by
generated workspaces, including the supported Harbor version, and installs the
protected adapter package. The candidate under `target/` may remain its own
nested project with its own declaration and lock; the two projects have
different responsibilities.

The root `.venv/` is ignored by Git and the Evolve mutable surface. All host
commands use the original experiment workspace as their `uv --project` path.
The evaluator passes that path explicitly to commands operating on temporary
candidate checkouts. This prevents a separate environment from being created
for every worktree.

The protected project declaration, lockfile, adapter, evaluator, and vendored
mechanism cannot be changed by candidate evolution. Existing surface and
evaluator-integrity checks enforce that boundary.

## Command Boundaries

The generated `./evolve` entry point runs the protected vendored mechanism with:

```text
uv run --project <workspace> --frozen python <protected-launcher> ...
```

A small launcher adjacent to `.evolve/evolve` imports the vendored package by
normal Python script rules. It preserves the caller's working directory and
relative CLI arguments.

Harbor evaluator, rollout, and meta-agent commands use:

```text
uv run --project <workspace> --frozen harbor ...
```

The `uv` executable is resolved from `EVOLVE_UV_BINARY` first and then `PATH`.
The Harbor executable is never resolved separately from ambient `PATH`.

Operator subprocesses continue to execute trusted operator source with the
candidate checkout as their working directory. This existing launcher contract
provides deterministic access to first-party workspace modules without any
module-level path repair.

## Harbor Adapter Boundary

The current `target/harbor_agent.py` is host infrastructure even though it lives
inside candidate source. It is already excluded from mutation. The implementation
moves it into the protected `evolve_harbor_adapter` package installed by the
workspace project.

The adapter receives candidate source as an explicit host filesystem path. It
validates the candidate `pyproject.toml`, `uv.lock`, and MiniSWE package before
uploading that source into the task environment. The candidate project remains
mutable while the host adapter and Harbor environment remain locked.

Custom Harbor adapters must be ordinary dependencies of the workspace root
project before an experiment begins. Users update `pyproject.toml` and `uv.lock`
instead of configuring import directories. `agent_pythonpath` produces a clear
removed-setting error.

## Environment Handling

Python and Harbor child environments are copied from the parent and stripped of
`PYTHONPATH`, `PYTHONHOME`, and `VIRTUAL_ENV`; `uv --project` remains the sole
environment selector. Required credentials, proxy settings, Docker
configuration, cache paths, and Evolve variables remain available.

Paths are passed as individual subprocess arguments or environment values. Code
does not join import roots with `os.pathsep`, assume `:` as a separator, or
interpolate executable commands through a shell.

## Failure Handling

Failures are early and do not fall back to ambient Python behavior:

- missing `uv` identifies `EVOLVE_UV_BINARY` and the installation requirement;
- missing workspace `pyproject.toml` or `uv.lock` identifies the workspace;
- legacy `agent_pythonpath` explains that adapters must be locked dependencies;
- `uv` synchronization or command failures preserve useful diagnostics and are
  classified as infrastructure failures;
- malformed candidate source remains candidate-invalid;
- Harbor logs and recorded commands continue redacting credentials and bearer
  tokens.

## Existing Workspaces

Existing generated workspaces are not rewritten silently because their
protected mechanism and evaluator trees are experiment history. This breaking
release requires affected experiments to be regenerated or migrated explicitly.
An old workspace missing the root `uv` project receives a clear error.

## Verification

Implementation follows test-driven development. Each behavior change begins
with a focused failing test and is verified before the next boundary changes.

Static checks prevent runtime Python files from mutating `sys.path` and prevent
production Python or shell code from assigning `PYTHONPATH`. Obsolete library
and template Ruff `E402` exemptions are removed.

Unit and integration tests cover:

- generation of the root project, lockfile, ignored `.venv`, and protected
  adapter package;
- exact `uv run --project ... --frozen` command construction;
- `EVOLVE_UV_BINARY`, missing `uv`, missing project files, and legacy-setting
  errors;
- removal of inherited Python import variables without parent mutation;
- preservation of credentials, proxies, Docker settings, and Evolve variables;
- paths containing whitespace and shell metacharacters valid on macOS/Linux;
- operator imports and trusted-source execution without path mutation;
- generated console behavior inside and outside the workspace;
- explicit candidate-source delivery to the protected adapter;
- fake Harbor evaluator, rollout, and meta-agent executions;
- unchanged candidate-invalid and infrastructure-failure ownership.

Repository completion requires Ruff lint, Ruff format checking, `ty`, the full
pytest suite, a wheel build/install resource smoke test, and the init → run →
verify self-driving smoke. GitHub Actions runs the test suite on
`ubuntu-latest` and `macos-latest`. Harbor command/import smoke tests use the
locked workspace project but do not require Docker or model credentials.

## Documentation

Documentation will explain:

- the single-workspace `uv` project model;
- how to add and lock a custom Harbor adapter before initialization;
- the removal of `agent_pythonpath`;
- the macOS/Linux support boundary;
- first-run `uv` synchronization and actionable failures;
- regeneration or explicit migration of existing workspaces;
- why `PYTHONPATH` is not a supported extension mechanism.

## Non-goals

This cleanup does not add Windows support, redesign candidate dependency
management, change benchmark semantics, or automatically migrate historical
workspaces.
