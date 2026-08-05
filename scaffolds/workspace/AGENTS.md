# Evolve Workspace

This repository is a self-driving evolvable workspace. The operating manual
is **`skills/evolve-agent/SKILL.md`** — read it first. It works for any
agent tool (Claude Code, codex, …); the skill lives in a plain `skills/`
folder, not a tool-specific one.

Everything goes through the vendored console **`./evolve`** (the mechanism is
under `.evolve/`, so no install is needed): `./evolve status .` to see where
things stand, `./evolve run . --resume` to run the driver, and
`./evolve operator list .` to discover capabilities for an agent-orchestrated
generation.

Hard rules (enforced — do not fight them): never hand-edit scores or archive
status fields; the frozen evaluator side stamps those. To edit a candidate as
the outer agent, read `program.md`, invoke configured operators for evidence,
and finish through commit → eval → finalize. Before committing manual candidate
edits, run `./evolve surface-check <child-worktree>`, then every configured
`validate` and `novelty` operator. Commit refuses missing or stale results.

Any newly introduced Python package must be added to the workspace root
`pyproject.toml` with `uv add`, and the resulting `uv.lock` must be committed.
Harbor trials run from the locked workspace environment: never rely on a package
installed globally, injected through `PYTHONPATH`, or installed ad hoc during a
trial.

Workspace-local `.env` values are loaded automatically for run, eval, and
candidate smoke commands and supply live meta-agent/evaluator keys and
endpoints. The caller repository's `.env` is used as a fallback for a separate
workspace. Exported environment variables take precedence; never commit secrets.
