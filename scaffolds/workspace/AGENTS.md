# Evolve Workspace

This repository is a self-driving evolvable workspace. The operating manual
is **`skills/evolve-workspace/SKILL.md`** — read it first. It works for any
agent tool (Claude Code, codex, …); the skill lives in a plain `skills/`
folder, not a tool-specific one.

Everything goes through the vendored console **`./evolve`** (the mechanism is
under `.evolve/`, so no install is needed): `./evolve status` to see where
things stand, `./evolve run . --resume` to drive the loop, `./evolve report .`
to prepare claims.

Hard rules (enforced — do not fight them): never hand-edit scores or archive
status fields; the frozen evaluator side stamps those. If `evolve.yaml` says
`mode: agent`, read `program.md` and sequence the verbs yourself; the console
still enforces the honesty invariants. Before finishing manual candidate edits, run
`./evolve surface-check .` and repair any violations.

Any newly introduced Python package must be added to the workspace root
`pyproject.toml` with `uv add`, and the resulting `uv.lock` must be committed.
Harbor trials run from the locked workspace environment: never rely on a package
installed globally, injected through `PYTHONPATH`, or installed ad hoc during a
trial.

Project-root `.env` values are loaded automatically for run, eval, preflight,
and candidate-smoke commands. Exported environment variables take precedence;
caller and parent `.env` files are not loaded. Use API credentials by default,
or an explicit `CODEX_AUTH_JSON_PATH` for Codex. Never commit secrets or invoke
the internal `evaluator/eval.sh` directly.
