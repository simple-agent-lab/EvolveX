---
name: make-paper-poster
description: Create a visual poster from an academic paper as a self-contained SVG. Use when asked to summarize or present a paper as an SVG research poster.
---

# Make a paper poster

Read the source paper and identify its central problem, method, evidence, and
takeaway.

Create one self-contained SVG poster that communicates the paper visually.
Preserve the paper's technical meaning and do not invent claims or results.

When `EVOLVE_SVG_RENDERER` is available, render previews only through that
command so your preview matches the evaluator. For example:

```sh
"$EVOLVE_SVG_RENDERER" poster.svg --width 1600
```

The command prints the content-addressed PNG path. Inspect that PNG, revise
obvious problems, and render at most once more after revision. Do not probe for
or switch to another SVG renderer. Return the final SVG path.
