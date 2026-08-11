# RSIHub Logo Exploration Design

## Objective

Create a broad, art-directed logo exploration for RSIHub, then use the
comparison to select a smaller set for production refinement. The exploration
must feel memorable and intentional at GitHub-avatar scale while remaining
credible in research papers, documentation, and developer tooling.

The work replaces the current visual language rather than polishing the
existing selected-lineage mark. The existing mark may inform the project story,
but its dark rounded square, small branches, many nodes, checkmark, and green
palette are not constraints.

## Approved Direction

The exploration combines three visual languages selected by the user:

1. **Minimal original mascots — 18 concepts.** Distinctive silhouettes with
   restrained internal detail. They should feel intelligent and curious without
   becoming childish, derivative of another project's animal, or overly cute.
2. **Playful open-source identities — 16 concepts.** Warm, unconventional marks
   with a community-friendly personality. Color may carry energy, but geometry
   and typography must prevent the designs from feeling like stickers or
   short-lived trends.
3. **Technical editorial identities — 16 concepts.** Precise symbols and
   wordmarks suitable for papers, documentation, and infrastructure. They
   should feel authored rather than corporate, sterile, or indistinguishable
   from a software icon set.

These allocations produce exactly 50 concepts. The three collections are
genuine art directions, not cosmetic recolors of a shared template.

## Design Principles

Every concept must satisfy these rules:

- Lead with one recognizable silhouette and one visual idea.
- Remain recognizable at 32 pixels and legible at 16 pixels where practical.
- Work in one-color black and white before relying on color.
- Use no more than two main brand colors in the primary version.
- Include an intentional RSIHub wordmark treatment; do not use an unmodified
  default system font as the final typographic expression.
- Avoid generic AI and developer-tool imagery: neural-network dots, circuit
  traces, brains, atoms, glowing orbs, chat bubbles, generic trees, and random
  gradient letter marks.
- Avoid literal diagrams of the framework architecture. The logo should become
  meaningful through recognition rather than attempting to explain the system.
- Do not copy or closely imitate the reference projects. Their logos calibrate
  restraint, memorability, and tone only.

## Visual System

The initial exploration may use varied palettes to find the identity, but each
concept must include:

- a primary symbol;
- a horizontal symbol-and-wordmark lockup;
- a monochrome version;
- a light-background presentation;
- a dark-background presentation; and
- a 32-pixel avatar test.

Wordmarks may use modified open-licensed typefaces or custom vector lettering.
Any external font considered for a final candidate must have a documented
license compatible with the repository.

## Comparison Gallery

All 50 concepts will appear in one scrollable local HTML gallery. The gallery
will group concepts by the three approved collections and support multi-select
shortlisting. Each card will show the main lockup, monochrome proof, dark-mode
proof, and avatar-scale preview. Concepts will use stable identifiers so user
feedback can refer to a design unambiguously.

The gallery is an exploration artifact, not the final repository logo. It may
remain under the local brainstorming workspace and should not be treated as a
shipped public asset.

## Refinement Flow

1. Produce all 50 concepts to the same presentation standard.
2. Conduct an internal quality pass and remove any concept that violates the
   design principles, replacing it so the gallery still contains 50.
3. Ask the user to shortlist promising concepts in the gallery.
4. Refine the shortlisted concepts through targeted iterations rather than
   generating another undirected batch.
5. Select one primary identity and, if useful, one alternate direction.
6. Produce final repository-ready SVG assets and update references only after
   explicit approval of the winning design.

## Acceptance Criteria

The exploration is ready for user review when:

- exactly 50 distinct concepts are present in the approved 18/16/16 split;
- the concepts do not share one obvious construction template;
- every concept includes the required lockups and proofs;
- no design depends on details that disappear at avatar scale;
- every concept has a defensible, concise visual idea;
- none rely on the prohibited generic imagery;
- all gallery interactions work in the brainstorming browser; and
- the original repository logo and README remain unchanged until a winner is
  explicitly approved.

## Verification

Verification is visual and structural. Confirm the gallery contains exactly 50
stable concept identifiers, validate the 18/16/16 collection counts, inspect all
light, dark, monochrome, and avatar proofs, and test multi-selection in the
browser. No repository test suite is required until a winning asset changes
tracked documentation or project resources.
