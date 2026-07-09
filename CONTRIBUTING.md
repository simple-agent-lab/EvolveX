# Contributing

This project is built to stay coherent while many people (and agents) work on
it. The rule that makes that possible: **don't trust discipline — build the
constraint.** Most of the "rules" below are enforced by tests, so you'll find
out fast if you cross one.

Read [`DESIGN.md`](DESIGN.md) (the architecture + rationale) and
[`docs/coding-style.md`](docs/coding-style.md) (how code is written)
before a non-trivial change. Those plus [`ARCHITECTURE.md`](ARCHITECTURE.md)
are the maintained set — keep them current rather than adding new ones.
See [`docs/README.md`](docs/README.md) for where new writing goes.

## Setup

Requires `uv` and `git` (Python 3.11+ is provided by uv).

```bash
uv sync --dev
uv run pytest -q          # the full suite (~4 min)
uv run ruff check .       # lint
uv run ty check           # type check (must be zero)
```

## What CI enforces (green before merge)

Two workflows gate every PR:

- **`test`** — `uv run pytest` (the suite *is* the coherence guard) + a
  self-driving smoke (`init → run → verify`).
- **`lint`** — `ruff check` and `ty check`, both blocking.

If CI is red, the PR doesn't merge. Locally, run all three before pushing.

## The constraints you'll hit (and why)

- **The architecture map is enforced.** `ARCHITECTURE.md` lists every
  `src/evolve/` module with a one-line meaning and a line budget;
  `tests/test_coherence.py` fails on drift. A new module needs a row *and* a
  budget in the same commit. Over a budget → do a demolition pass, or raise the
  budget with the reason in the commit message. Budgets are speed bumps that
  force a conscious decision, not walls.
- **Tests are spec, not scar tissue.** When behavior changes, update or delete
  the test in the same commit — never shim production code to keep a stale test
  green. Every rot pattern caught in review becomes a new assertion in
  `test_coherence.py`.
- **Three rings, one rule** (DESIGN §2): *mechanism owns the primitives; policy
  is evolvable.* Ask "if evolution rewrote this to cheat, would a score become a
  lie?" — if yes, it belongs in the frozen ring (`src/evolve/frozen/`), not an
  operator.
- **The mechanism never imports workspace operator code in-process.** Operators
  run only as subprocesses via `operators.run_operator`.
- **Runtime is stdlib-only** for the driver, operators, and frozen tools (they
  run as bare subprocesses and inside meta_eval replay). Only the CLI layer
  (`cli.py`) may use Typer.

## Adding an operator

Operators are defined **once** in the registry — `interfaces.OPERATORS`
(`src/evolve/frozen/interfaces.py`). Add one `OperatorSpec` entry (kind, ABC,
result type, method, required?) and the kind lists in `config.py` and the
contract tests derive from it automatically (`test_coherence` asserts every
`*Operator` is registered and dispatched). Then:

1. add the ABC + `Result` dataclass + a `validate_*` payload check next to the
   others in `interfaces.py`;
2. add a dispatch branch in `frozen/sdk.py` (writes the operator's output file);
3. add reference implementations under `library/<kind>/` (a `_skeleton.py` plus
   at least one real variant) — these are consulted-and-adapted, not vendored
   wholesale (`library/README.md`);
4. wire it into the driver if it runs in the loop (required kinds run in the
   sequence; optional kinds run only when a recipe configures them);
5. add tests named by milestone (`test_m<N>_<topic>.py`).

## Commits & docs

- Any behavior change that extends or contradicts the design edits `DESIGN.md`
  **in the same commit**. `README`/`ARCHITECTURE` must never overstate what's
  built.
- Don't add new prose docs casually. Prefer editing `DESIGN.md`,
  `ARCHITECTURE.md`, or `docs/coding-style.md`; otherwise follow
  `docs/README.md`. Or put a comment next to the code it explains.
- Keep commits logically scoped and individually green.
- `DESIGN.md`'s status callout marks what's built vs planned — keep it honest.
