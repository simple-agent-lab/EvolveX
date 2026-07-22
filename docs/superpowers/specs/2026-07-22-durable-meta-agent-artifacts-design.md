# Durable Meta-Agent Artifacts Design

## Purpose

Give users and meta-agents a general, durable place to exchange arbitrary files
across evolution generations without treating each new file type as part of the
Harbor runner protocol. A free-form handoff is one convention built on this
primitive, not a special framework-owned schema.

The design also makes evidence references portable between the host workspace
and the disposable meta-agent environment by storing workspace-relative paths.

## Goals

- Preserve arbitrary user-provided files across every meta-agent run.
- Let each meta-agent persist arbitrary files for later generations.
- Preserve generation provenance under branching, rejection, and retries.
- Keep durable artifacts outside candidate patches and benchmark runtime code.
- Make handoffs free-form, optional, and explicitly identified in prompts.
- Make history evidence paths usable on both the host and in Harbor.
- Retain the existing Harbor isolation and editable-surface checks.

## Non-goals

- Define the contents or format of `handoff.md`.
- Make a missing handoff fail a generation.
- Let a meta-agent overwrite user files or artifacts from earlier generations.
- Include durable artifacts in candidate Git commits or evaluation snapshots.
- Retain nested Harbor jobs, caches, worktrees, or other recursive runtime data.

## Workspace Layout

Each evolution workspace may contain this mechanism-owned top-level directory:

```text
artifacts/
├── user/
└── generations/
    ├── 1/
    │   ├── handoff.md
    │   └── arbitrary-file.json
    └── 2/
```

`artifacts/user/` is host-authoritative persistent material supplied by users.
The framework does not interpret its contents.

`artifacts/generations/<genid>/` is the durable output namespace for one
generation. The meta-agent may create any regular files and directories within
its current generation namespace. The framework does not interpret files other
than using `handoff.md` as an optional prompt convention.

The top-level `artifacts/` directory is not part of the mutable candidate
surface. It is excluded from candidate commits, patches, surface checks, and
evaluation snapshots.

## Harbor Data Flow

Before a Harbor meta-agent starts, the runner copies the complete host
`artifacts/` tree into the disposable experiment workspace at:

```text
/app/task/workspace/artifacts/
```

The meta-agent may read the complete tree. Its prompt explicitly identifies:

- the artifact root: `artifacts/`;
- its writable directory: `artifacts/generations/<current-genid>/`;
- the selected parent's directory, when one exists:
  `artifacts/generations/<parent-genid>/`;
- the selected parent's optional handoff:
  `artifacts/generations/<parent-genid>/handoff.md`.

The prompt describes the handoff as context written by the selected parent's
meta-agent and tells the current meta-agent to verify its claims against the
available evidence. If the selected parent has no handoff, the prompt says so
explicitly.

Before submission, the prompt asks the meta-agent to write a free-form handoff
to its current generation directory. This is best-effort: absence does not make
the operator fail.

After Harbor returns the disposable workspace, the runner validates and
transactionally imports only:

```text
artifacts/generations/<current-genid>/
```

The imported namespace may contain arbitrary regular files and directories.
Symlinks, special files, and paths escaping the namespace are rejected. The
host tree is unchanged if validation or installation fails.

Returned changes to `artifacts/user/` or any other generation namespace are
discarded. The authoritative host copies remain unchanged. Candidate editable
roots continue to be imported through the existing transactional surface gate.

For a non-Harbor runner, the same logical paths apply directly under the host
workspace. The operator prompt and artifact helper use workspace-relative
references so the contract does not depend on the runner.

## Retry and Failure Semantics

The current generation namespace may already exist when an interrupted
generation resumes. The staged workspace begins with that existing content.
On a successful meta-agent return, the returned current-generation namespace
atomically replaces the host namespace. This permits the meta-agent to refine
files during a resumed attempt without affecting prior generations.

If the meta-agent or Harbor run fails before a valid workspace is returned, the
host artifact tree remains unchanged. A missing `handoff.md` is valid and is
reported as unavailable to the next meta-agent.

## Relative Evidence Paths

All paths stored in feedback history that refer to files within the evolution
workspace use normalized POSIX paths relative to the workspace root. For
example:

```json
{
  "raw_evidence_dir": "runs/gen-3/trace_analyzer/evidence"
}
```

Stored workspace paths must not be absolute, contain `..`, or escape the
workspace after resolution. Prompt renderers may display the relative path
directly because meta-agents work from the experiment workspace. Code that
needs an absolute path resolves it against `ctx.workspace` on the host or
`/app/task/workspace` in Harbor.

This change applies to newly written feedback. Existing experiment artifacts
remain readable; no migration rewrites completed experiment history.

## Shared Framework Interface

A small shared meta-agent support module owns the durable-artifact conventions:

- compute the artifact root and current/parent generation directories;
- render prompt guidance for the selected parent's handoff;
- provide the canonical current-generation write path.

Meta-agent strategies decide where that guidance appears in their prompts but
do not define separate storage behavior. Initially AHE and HyperAgents use the
shared helper. Future strategies may opt in without adding new Harbor transport
rules.

The Harbor runner remains responsible for staging, validating, and importing
the generic current-generation namespace. It does not inspect or enumerate the
files stored there.

## Testing

Tests must demonstrate:

1. Feedback history stores workspace-relative evidence paths.
2. Relative evidence paths resolve to real files in a staged Harbor workspace.
3. The complete artifact tree is readable in the disposable workspace.
4. Arbitrary files under the current generation namespace return to the host.
5. Nested directories and empty current-generation directories are supported.
6. Returned edits to `artifacts/user/` and prior generation namespaces do not
   modify their host-authoritative copies.
7. Symlinks and special files in the returned current-generation namespace are
   rejected without partially changing the host.
8. Failed Harbor execution leaves host artifacts unchanged.
9. AHE and HyperAgents prompts identify the artifact root, writable generation
   directory, selected parent directory, and handoff semantics.
10. A missing parent handoff is explicitly acknowledged and remains non-fatal.
11. The handoff and other artifact files never appear in the candidate patch or
    changed-path result.
12. Existing candidate editable-root import and protected-file rejection tests
    continue to pass.

## Documentation

`META_AGENTS.md` will document the durable artifact layout, write boundaries,
best-effort handoff convention, and relative-path contract. The operator
protocol will state that `artifacts/` is persistent workspace state rather than
an operator result or candidate mutation.
