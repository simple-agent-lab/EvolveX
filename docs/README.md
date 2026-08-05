# Documentation

The maintained public documentation has distinct roles:

| Document | Role |
| --- | --- |
| [`../README.md`](../README.md) | installation and supported workflows |
| [`../DESIGN.md`](../DESIGN.md) | framework model and ownership boundaries |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | enforced `src/evolve/` module map and budgets |
| [`glossary.md`](glossary.md) | concise domain definitions |
| [`coding-style.md`](coding-style.md) | coding conventions |
| [`architecture.svg`](architecture.svg) | generated README architecture diagram |
| [`../src/evolve/frozen/interfaces.py`](../src/evolve/frozen/interfaces.py) | machine-readable operator contract |

Put dated proposals in `docs/designs/` and implementation plans in
`docs/plans/`. Update the maintained document that describes a behavior in the
same change as that behavior.

Current proposals:

- [`designs/2026-08-05-harbor-evaluation-contracts-design.md`](designs/2026-08-05-harbor-evaluation-contracts-design.md)
  defines deterministic task limiting and runtime-user-owned candidate source
  transport for Harbor evaluations.

Current implementation plans:

- [`plans/2026-08-05-harbor-evaluation-contracts.md`](plans/2026-08-05-harbor-evaluation-contracts.md)
  implements the Harbor evaluation contracts test-first and verifies them on
  DevBox.

Regenerate the README architecture diagram after changing its content or style:

```bash
uv run python tools/generate_architecture_svg.py
uv run python tools/generate_architecture_svg.py --check
```
