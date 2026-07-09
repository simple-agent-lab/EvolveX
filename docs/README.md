# docs/

Live authority for the system is **not** under this folder:

| Doc | Role |
| --- | --- |
| [`../DESIGN.md`](../DESIGN.md) | architecture + rationale |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | mechanism module map (enforced) |
| [`coding-style.md`](coding-style.md) | how we write (style / ethos) |
| [`../src/evolve/frozen/interfaces.py`](../src/evolve/frozen/interfaces.py) | operator contract (machine authority) |

Also here:

- [`glossary.md`](glossary.md) — domain terms (non-binding; DESIGN wins on conflict)

## Where new writing goes

Do **not** recreate `docs/superpowers/`. Place by role:

| Kind | Path |
| --- | --- |
| Design / spec | `docs/designs/YYYY-MM-DD-<topic>.md` |
| Implementation plan | `docs/plans/YYYY-MM-DD-<topic>.md` |
| Kickoff / how-to | `docs/guides/YYYY-MM-DD-<topic>.md` |
| Small implementation call | append `docs/decisions/implementation-log.md` |
| Load-bearing decision | `docs/decisions/README.md` or fold into `DESIGN.md` |

When a design or plan is finished, `git mv` it into the matching `archive/`
folder with a one-line archived banner. Behavior changes that update the live
design edit `DESIGN.md` in the same commit.
