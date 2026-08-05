# README identity and narrative design

**Date:** 2026-08-05

**Status:** Approved for implementation planning

**Ground truth reviewed:** remote `main` at `ebb00de125244b6a416006524fcdfd2dccdb17bb`

## Objective

Redesign the public README and its visual identity so Evolve feels memorable and
approachable while retaining the rigor expected of an agent-evolution research
framework. The README must serve both developers who want to improve an agent
and researchers who want controlled, reproducible evolution experiments.

The design uses progressive disclosure: begin with the outcome in ordinary
language, introduce the evolution loop and its practical uses, then reveal the
evaluation and lineage guarantees that make the results credible.

## Positioning

The approved primary message is:

> **Build agents that improve — and keep the evidence.**

The supporting description is:

> A file-based framework for evaluator-driven evolution, reproducible candidate
> lineage, and controlled self-modification.

This positioning balances the two audiences:

- Agent builders first encounter the practical promise: improve prompts,
  skills, harnesses, or agent code.
- Researchers immediately afterward encounter the discipline behind it:
  frozen evaluators, controlled mutable surfaces, canonical evaluation, Git
  lineage, and stamped outcomes.

The README must not claim benchmark superiority or imply production maturity.
The project remains described as an active prototype for research and
controlled experimentation.

## Visual identity

### Selected Lineage concept

The approved identity is a rising candidate lineage:

- A dark green selected path ascends from a baseline through several candidate
  generations.
- Muted side branches represent candidates that were explored but not selected.
- A brighter terminal node with a check mark represents a verified generation.
- Rounded paths and nodes give the identity an organic quality without using a
  literal tree, leaf, DNA helix, or biological mascot.

The concept communicates four properties at once: evolution, branching search,
Git lineage, and evidence-based selection.

The identity must remain a single metaphor. It must not be combined with a
robot face, agent mascot, brain, spark, or other evolution symbol.

### Palette

The visual system uses five functional colors:

| Role | Reference color | Meaning |
| --- | --- | --- |
| core | `#10372e` | stable mechanism and icon background |
| lineage | `#19785a` | selected candidate path |
| verified | `#65ce9f` | canonical improvement |
| explored | `#b5d3c7` | evaluated but unselected candidates |
| surface | `#f2fbf7` | light backgrounds and mutable regions |

Exact colors may receive minor contrast adjustments during asset production,
but their semantic roles must remain stable.

### Asset roles

The visual system contains three related assets, each with one job:

1. **Identity mark:** a square-safe reduction of the Selected Lineage. It has no
   labels or explanatory text and remains legible at 32 pixels. Intended uses
   include the repository avatar, favicon, and social card.
2. **README hero figure:** an expanded lineage showing the baseline, explored
   candidates, selected path, and verified generation. It communicates the
   project idea before readers encounter framework vocabulary.
3. **Architecture figure:** a technical diagram showing the
   select → rollout/evaluate → analyze → mutate → gate → record loop, the
   declared mutable surface, and the frozen evaluator/runtime/evidence layer.
   It inherits the palette but remains informational rather than decorative.

The hero and architecture figures must not duplicate one another. The hero
answers “what outcome does Evolve create?” The architecture figure answers “how
does the framework control that process?”

## Above-the-fold design

The README begins with a centered, restrained hero:

1. Selected Lineage identity mark.
2. `Evolve Framework` title.
3. Primary message: “Build agents that improve — and keep the evidence.”
4. Supporting description.
5. Test, Python, and license badges.
6. Compact navigation links.
7. Expanded Selected Lineage hero figure.
8. Three short value statements:
   - for agent builders;
   - for researchers;
   - evidence built in.

The visual character should be scientific and modern, with an organic edge.
It must avoid excessive gradients, neon effects, emoji-heavy headings, and
large badge collections.

## README information architecture

### 1. Identity and promise

Use the approved hero to explain the project outcome before describing
implementation mechanics.

### 2. The mental model

Explain one composable evolution loop in plain language:

`select → evaluate → analyze → mutate → gate → record`

Then explain that recipes choose the operators and determine what is allowed to
evolve. Introduce the protected evaluator, runtime, surface check, and stamped
evidence only after the reader understands the loop.

The existing implementation may use “rollout” as a distinct operator term.
README prose should use “evaluate” for the reader-facing step and explain the
rollout/evaluation relationship where precision is required.

### 3. What can evolve

Organize examples around user intent rather than source layout:

- prompts and skills;
- harnesses and target code;
- selected evolution operators in advanced co-evolution recipes.

This section should help readers recognize their own project before asking them
to learn recipe names.

### 4. Practical and research value

Present two adjacent depths:

- **Agent builders:** reusable experiment workspaces, inspectable candidates,
  multiple improvement strategies, and durable artifacts.
- **Researchers:** frozen evaluation contracts, declared mutable surfaces,
  canonical evaluation, and reproducible lineage.

This is one framework serving two levels of use, not two separate products.

### 5. Recipes

Preserve the five supported recipes on remote `main`: `hill_climb`, `aevolve`,
`ahe`, `gepa`, and `hyperagents`.

Lead each row with the behavior or intent a reader would choose, followed by the
method name and mutable surface. Keep detailed configuration in
`recipes/README.md`.

### 6. Getting started

Reserve this position in the README, but redesign its commands and demonstration
in a separate onboarding effort. The current deterministic smoke test and real
Harbor run remain valid ground truth until that work occurs.

The README redesign must not invent a demo, installation path, package release,
or runtime capability.

### 7. Status and deeper documentation

State the prototype status plainly, then route readers to the existing design,
architecture, recipes, meta-agent, trace-analysis, local-execution, and
contributing documents.

Remove the current empty Results section. A results section should return only
when reproducible results and supporting artifacts are available.

## Content rules

- Lead with outcomes, then name mechanisms.
- Define framework-specific terms before relying on them.
- Prefer one strong sentence over parallel lists of overlapping features.
- Keep claims verifiable against repository behavior on remote `main`.
- Keep low-level contracts and invariants in `DESIGN.md`; summarize only the
  reader-relevant guarantees in the README.
- Use emoji sparingly or not at all; personality comes from the identity and
  writing, not decorative headings.
- Do not imitate Arbor’s literal tree metaphor or benchmark-first presentation.
- Do not add a mascot to make the project feel approachable.

## Rendering and accessibility requirements

- Store final visual assets in the repository; do not depend on remote image
  hosting or remote fonts.
- Prefer SVG for the identity, hero, and architecture assets.
- Verify the identity mark at 32, 64, and 128 pixels.
- Verify figures on GitHub light and dark themes.
- Provide useful alt text describing the information conveyed by each figure.
- Maintain sufficient contrast between selected, explored, and verified states.
- Ensure the README remains understandable when images fail to render.
- Avoid important labels that become unreadable on narrow screens.

## Verification

Implementation is complete only after all of the following checks pass:

1. Render the README at desktop and narrow widths on GitHub-compatible Markdown.
2. Inspect all SVG assets visually in light and dark contexts.
3. Confirm internal navigation anchors and documentation links resolve.
4. Run the repository’s Markdown or documentation checks if present.
5. Run the existing test suite proportionally to any asset-generation or source
   changes; a README-only edit does not require unrelated integration tests.
6. Compare all capability statements with the current CLI, recipes, and
   `DESIGN.md` to prevent documentation drift.
7. Confirm the diff does not include local brainstorming artifacts or unrelated
   workspace files.

## Scope boundaries

This design covers the README identity, visual asset system, positioning, and
information hierarchy.

The following are separate follow-on efforts:

- designing a fast first-run demo;
- changing CLI behavior or packaging;
- producing or publishing benchmark results;
- building a project website;
- creating a character mascot;
- changing framework architecture or recipe contracts.

These boundaries allow the identity and narrative work to proceed without
making unsupported usability or performance claims.
