# Documentation

The maintained public documentation has distinct roles:

| Document | Role |
| --- | --- |
| [`../README.md`](../README.md) | installation and supported workflows |
| [`../DESIGN.md`](../DESIGN.md) | framework model and ownership boundaries |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | enforced `src/evolve/` module map and budgets |
| [`glossary.md`](glossary.md) | concise domain definitions |
| [`coding-style.md`](coding-style.md) | coding conventions |
| [`evolve-mark.svg`](evolve-mark.svg) | generated Selected Lineage identity mark |
| [`evolve-lineage.svg`](evolve-lineage.svg) | generated README identity figure |
| [`architecture.svg`](architecture.svg) | generated README architecture diagram |
| [`../src/evolve/frozen/interfaces.py`](../src/evolve/frozen/interfaces.py) | machine-readable operator contract |

Put dated proposals in `docs/designs/` and implementation plans in
`docs/plans/`. Update the maintained document that describes a behavior in the
same change as that behavior.

Regenerate the maintained README visuals after changing their content or style:

```bash
uv run python tools/generate_readme_assets.py
uv run python tools/generate_readme_assets.py --check
uv run python tools/generate_architecture_svg.py
uv run python tools/generate_architecture_svg.py --check
```
