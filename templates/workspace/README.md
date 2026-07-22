# This is an evolve workspace

An evolution run living in a git repo: each generation is a commit tagged
`gen/<id>`, the append-only ledger is `archive.jsonl`, and `evolve report` shows
the lineage. `evolve run` drives the loop; `evolve status` shows where it is.

## Layout

```
target/          the thing being evolved (the candidate). Only paths matched by
                 the mutable surface (see evolve.yaml) may change.
operators/       the ACTIVE evolution logic — one executable script per verb
                 (`<verb>.py`). Generated run artifacts record prompts and output.
  README.md      generated table of the active set + swap-in alternatives
library/         the operator catalog: variants per verb. Copy one over an
                 operators/<verb>.py to change strategy.
evaluator/       the FROZEN ruler — how a candidate is scored. Never changes
                 inside the loop (pinned to gen/0); a harness change is a proposal
                 for a human, not a mutation.
skills/          the mutator's manual (tool-agnostic: Claude Code, codex, …)
evolve.yaml      experiment config: recipe, operator selection, the mutable surface
program.md       loop orchestration prose (agent mode)
PROTOCOL.md      the operator contract in prose (authority: the framework)
archive.jsonl    append-only event ledger (gitignored; the source of truth)
pyproject.toml   declared Python runtime for the mechanism and Harbor adapters
uv.lock          exact cross-platform dependency lock used by every entry point
```

Harbor can run directly against an already installed local agent with
`environment: evolve.harbor_local:LocalEnvironment`. This is useful for fast
Codex iterations on skills or other small behaviors where container isolation
is unnecessary. Use `environment_kwargs: {workdir: /app}` to select the virtual
workspace directory. Harbor maps its fixed absolute task paths into the trial
output directory, so the backend needs neither root access nor Docker.
Inside task scripts, use the current directory for workspace files and
`$HARBOR_LOGS_DIR`, `$HARBOR_TESTS_DIR`, or `$HARBOR_SOLUTION_DIR` instead of
container-only absolute paths.

## Python runtime

This workspace is a Python 3.12 `uv` project. Run it through `./evolve`; the
console uses `uv run --project <workspace> --frozen`, and the operator and
evaluator subprocesses inherit that same locked environment.

Add packaged Python dependencies with `uv add`, then commit both
`pyproject.toml` and `uv.lock`. Do not modify `sys.path` or set `PYTHONPATH`;
undeclared imports should fail clearly instead of depending on the caller's
machine or working directory.

## Run visibility

`evolve run` prints stage-level progress. Use `evolve run . --verbose` to
stream Harbor and operator output while preserving `runs/gen-*/**/harbor.log`.
Set `EVOLVE_PROGRESS=0` to suppress the stage messages.

## The one rule

Evolve `target/` and the `operators/`; never the `evaluator/` that judges them —
if the ruler could change, a score would become a lie. That boundary is what
keeps every number in `archive.jsonl` honest.
