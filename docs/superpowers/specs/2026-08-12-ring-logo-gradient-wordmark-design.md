# Ring logo and gradient wordmark design

## Goal

Adopt the approved RSIHub identity from the linked design study without changing
the project name, tagline, documentation structure, or any runtime behavior.
The repository should use the Ring as its shared mark and treatment B, “Hub in
the ramp,” as artwork in the README masthead.

## Selected identity

### Ring mark

Replace `docs/rsihub-mark.svg` with the primary Ring treatment from the design
study, not either named variant. The mark consists of four equal arc segments
around an open center. It uses the primary geometry shown in the study: 34°
gaps, a 6-unit round-capped stroke in a `0 0 40 40` view box, and one segment
for each organization ramp color:

1. `#3c8cff`
2. `#0095fd`
3. `#00cbd4`
4. `#78e85c`

The SVG remains transparent so it works in the README and as the MkDocs logo
and favicon on both light and dark surfaces. Its accessible title and
description must identify it as the RSIHub ring mark and describe the four
separated arcs; they must not retain the old selected-lineage description.

### Wordmark

Add `docs/rsihub-wordmark.svg` for treatment B. The artwork renders `RSI` in
the surrounding interface ink and `Hub` in the organization ramp. It must be a
self-contained SVG with stable glyph outlines rather than a dependency on an
installed font.

The artwork supports both GitHub color schemes inside the SVG:

- Light: `RSI` uses `#1f2328`; `Hub` runs from `#3c8cff` at 0%, through
  `#0095fd` at 32% and `#00a3b0` at 66%, to `#2fa844` at 100%.
- Dark: `RSI` uses `#e6edf3`; `Hub` runs from `#3c8cff` at 0%, through
  `#0095fd` at 32% and `#00cbd4` at 66%, to `#78e85c` at 100%.

Those contrast-adjusted light colors and full-ramp dark colors match the
approved artifact. The accessible name remains “RSIHub.”

## Integration

The README keeps the mark and wordmark as separate centered elements. The ring
continues to render at the current 112-pixel masthead size. The wordmark image
replaces only the centered `<h1>RSIHub</h1>` and receives an explicit width that
preserves the visual scale of the approved treatment.

All semantic project-name text remains unchanged. In particular, `site_name`
in `mkdocs.yml`, document headings, package metadata, links, and prose remain
searchable text. The existing MkDocs `logo` and `favicon` paths require no
configuration change because they already point to `rsihub-mark.svg`.

Update `docs/development/documentation.md` so its maintained-asset table names
the Ring mark correctly and includes the new wordmark artwork.

## Validation

Focused tests should verify:

- the Ring SVG has the approved view box, four arc paths, four colors, and no
  stale selected-lineage language;
- the wordmark SVG has an accessible name, stable outlined glyph geometry,
  both light and dark ink/gradient values, and no external font or asset;
- the README references both assets and no longer uses the centered textual
  `<h1>` wordmark;
- MkDocs still points its logo and favicon at the shared Ring asset; and
- the documentation inventory lists both maintained branding assets.

Run the focused public-repository or documentation tests while iterating, then
run `uv run --frozen pytest -q` before handoff. Slow and external checks are not
related to this static branding change.

## Out of scope

- Combining the mark and wordmark into one lockup.
- Replacing searchable RSIHub text outside the README masthead.
- Changing the tagline, descriptive copy, badges, palette, or repository name.
- Redesigning the architecture, benchmark, or lineage illustrations.
