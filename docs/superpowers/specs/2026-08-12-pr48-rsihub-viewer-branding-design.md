# PR48 RSIHub Viewer Branding Design

## Goal

Bring PR48's experiment viewer onto the repository's RSIHub identity without
changing viewer behavior, experiment data interpretation, or public CLI command
names.

## Integration

Merge the completed RSIHub branding branch into the PR48 branch. Resolve the
five overlapping files (`README.md`, `mkdocs.yml`, `pyproject.toml`,
`src/evolve/cli.py`, and `uv.lock`) by retaining the branding branch's RSIHub
identity while preserving PR48's viewer documentation, command, dependencies,
and entry points.

## Viewer identity

- Replace the viewer's copied EvolveX lineage mark with the canonical RSIHub
  ring mark.
- Display `RSIHub` in the navigation brand and browser/API titles.
- Use `RSIHub` in viewer-facing prose, diagnostics, and documentation while
  retaining the lowercase `evolve` CLI command and existing `EVOLVE_*`
  configuration protocol.
- Rename new viewer-only `X-Evolve-*` HTTP headers to `X-RSIHub-*`; PR48 has not
  shipped, so these headers have no compatibility contract yet.
- Keep the sidebar layout unchanged: ring icon, textual project name, and the
  existing `Experiment viewer` subtitle.

## Assets and tests

The viewer will package its own `rsihub-mark.svg`, byte-identical to the
canonical documentation asset, so installed distributions remain self-contained.
Tests will assert the RSIHub name, canonical asset, titles, and response headers,
and will reject stale viewer references to the retired identity.

## Verification

Run the focused viewer Python and frontend tests, the repository identity guard,
and the default non-slow test suite. Finally, serve the same full flagship
experiment through the updated PR48 viewer and visually confirm the branding and
champion diff remain correct.
