# Contributing

Thank you for improving Evolve Framework. Read [DESIGN.md](DESIGN.md),
[ARCHITECTURE.md](ARCHITECTURE.md), and [docs/coding-style.md](docs/coding-style.md)
before making a non-trivial change.

## Setup and checks

Requires `uv`, Git, and Python 3.12 or later.

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ty check
```

Run all four commands before opening a pull request. Tests enforce the module
inventory, recipe inventory, resource layout, and behavior contracts; do not
keep stale tests green with compatibility shims.

## Source ownership

Keep these categories separate:

- **Recipes** (`recipes/`) are the seven supported, user-facing configurations.
  Recipe YAML selects the target, evaluator, and operator behavior.
- **Scaffolds** (`scaffolds/`) are generated workspace structure. Common files
  live under `scaffolds/workspace/`; evaluator-specific files live under their
  engine directory.
- **Seeds** (`seeds/`) are built-in evolvable target content. They are copied
  only when a recipe selects that seed.
- **Integrations** (`src/evolve/integrations/`) are framework-owned runtime
  behavior. Harbor adapters are vendored inside `.evolve/evolve/`, never
  generated as standalone workspace packages.

Test fixtures under `tests/fixtures/` and experiments under `experiments/` are
not supported recipes. Do not add either to the public recipe inventory.

## Architecture and tests

`ARCHITECTURE.md` is an executable module map: every `src/evolve/**/*.py` file
has one row and a line budget, enforced by `tests/test_coherence.py`. Update its
row and honest budget in the same change as a source-module change.

The mechanism must not import workspace operator code in-process. Operators run
as subprocesses, while frozen evaluator state stays outside the mutable
surface. When behavior changes, update or remove the test that describes the
previous behavior in the same commit.

## Documentation and commits

Keep commits focused and update the maintained documentation with behavior:

- `README.md` explains supported public workflows.
- `DESIGN.md` explains the system model and rationale.
- `ARCHITECTURE.md` maps executable modules.
- [`docs/README.md`](docs/README.md) routes other documentation.

Avoid adding new prose files when one of these documents can be made clearer.
