# RSIHub Project Rename Design

## Objective

Adopt RSIHub as the sole project identity throughout every Git-tracked part of
the repository. The migration covers public copy, package
metadata, repository links, continuous-integration labels, generated-workspace
branding, legal notices, branded assets, tests, and historical tracked design
records.

The rename is deliberately limited to project identity. Existing technical
interfaces built around the verb `evolve` remain stable so current commands,
configuration, imports, environment variables, skills, and workspaces do not
break solely because the project has a new name.

## Canonical Identity

After the migration, the canonical forms are:

| Context | Canonical value |
| --- | --- |
| Display name | `RSIHub` |
| Python distribution name | `rsihub` |
| GitHub repository | `simple-agent-lab/RSIHub` |
| Documentation site | `https://simple-agent-lab.github.io/RSIHub/` |
| Branded asset stem | `rsihub` |
| Branded generated legal suffix | `.rsihub` |

Project-owned identifiers derived from the old distribution name, including
CI identities, invalid example email domains, user-agent strings, cache paths,
and wheel smoke-test filenames, use the lowercase `rsihub` form.

## Stable Technical Interfaces

The following names describe the framework's evolution mechanism rather than
the project brand and therefore remain unchanged:

- the `evolve` command and `[project.scripts]` entry;
- the `evolve` Python import package and `src/evolve/` tree;
- `python -m evolve`;
- `evolve.yaml`, `.evolve/`, `.evolve-components.json`, and related workspace
  paths;
- `EVOLVE_*` environment variables;
- the `evolve-agent` skill and evaluation directory names;
- generic domain language such as “evolve,” “evolution,” and “evolving”; and
- names of external methods or projects such as A-Evolve.

No compatibility aliases or transitional former-brand copy will be added. The
repository should present one unambiguous project identity.

## Migration Surface

### Public documentation and repository metadata

Update the root documentation, MkDocs content and configuration, contributor
and support policies, issue templates, package metadata, lockfile, and all
tracked GitHub and documentation URLs. Headings, link anchors, image alt text,
and navigation labels must use RSIHub consistently.

Historical specs and implementation plans under `docs/superpowers/` are part
of the tracked repository and must also use the current project name. Files
whose names contain the retired brand stem are renamed to use `rsihub`, and
references to those paths are updated.

### Code, scaffolds, and generated workspaces

Update user-visible CLI messages, docstrings, diagnostic errors, generated Git
identity labels, provider display names, and other project-owned strings.
Generated workspaces use `LICENSE.rsihub` and `NOTICE.rsihub`; scaffold
documentation and generation tests must agree with those names. This is a
branding filename migration, not a change to workspace execution semantics.

### Visual assets

Rename the project mark from `docs/evolve-mark.svg` to
`docs/rsihub-mark.svg` and update every reference. Update embedded titles and
accessible descriptions in other tracked SVGs to RSIHub. The lineage
illustration `docs/evolve-lineage.svg` keeps its filename because it
describes the evolution concept rather than the old brand.

This task does not redesign the logo. It only migrates the existing asset and
its accessible branding.

### Tests and enforcement

Update existing assertions for package metadata, CLI output, generated legal
files, and notices. Strengthen the public-repository checks so a future tracked
source file or path cannot reintroduce any retired project identity in display,
distribution, or repository-slug form. The guard must exclude Git metadata and
untracked local artifacts by operating on the repository's tracked-file set;
its denylist literals should be assembled from fragments so the test does not
itself retain a forbidden identity.

The guard should not reject preserved technical-interface terms such as
`evolve`, `EVOLVE_*`, `.evolve`, or `evolve-agent`.

## Repository Boundaries

The migration edits Git-tracked repository content only. It does not rewrite:

- untracked `.codex/` state, local archives, generated LaTeX outputs, caches,
  or experiment artifacts;
- Git history, Git metadata, existing commit messages, or archived bundles;
- the local checkout directory name;
- the configured Git remote or the external GitHub repository itself; or
- external infrastructure that must be renamed outside this checkout.

Tracked links will target the intended `simple-agent-lab/RSIHub` repository.
Those links may become live only after the repository owner performs the
corresponding external rename.

## Error Handling and Compatibility

The migration introduces no runtime fallback or compatibility layer because
runtime technical interfaces remain unchanged. Tests that fail due to stale
branding are corrected to the new canonical identity. Tests that fail because
an `evolve` technical interface changed indicate an unintended breaking change
and must be resolved by restoring that interface.

## Verification

Verification proceeds in layers:

1. Run the focused public-repository, initialization, and release-artifact
   tests that enforce identity, generated filenames, CLI output, and package
   metadata.
2. Search all Git-tracked paths and text for the retired identities and confirm
   there are no matches.
3. Build the documentation in strict mode so renamed assets, anchors, and links
   resolve.
4. Run the default repository suite with `uv run --frozen pytest -q`.
5. Run the repository's standard static checks for lint, format, and types.

Slow integration and live external checks are not required because the rename
does not change experiment execution behavior or external services.

## Acceptance Criteria

The rename is complete when:

- every Git-tracked project-brand reference uses `RSIHub` or `rsihub` as
  appropriate;
- no Git-tracked path or text contains a retired project identity in display,
  distribution, or repository-slug form;
- package metadata identifies the distribution as `rsihub`;
- repository and documentation links target `simple-agent-lab/RSIHub`;
- generated workspaces contain `LICENSE.rsihub` and `NOTICE.rsihub`;
- the `evolve` technical interfaces listed above remain unchanged;
- focused tests, documentation build, default tests, and static checks pass;
  and
- unrelated tracked and untracked work remains untouched.
