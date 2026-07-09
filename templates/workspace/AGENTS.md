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
still enforces the honesty invariants. Before finishing manual mutations, run
`./evolve surface-check .` and repair any violations.

Repo-local `.env` values supply live mutator/evaluator keys and endpoints;
load them locally, never commit secrets.
