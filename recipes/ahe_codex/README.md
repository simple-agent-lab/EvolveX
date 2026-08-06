# AHE on Codex with Terminal-Bench 2.0

This recipe evolves a Codex harness rather than MiniSWE source. The candidate
surface includes `prompt.md`, `skills/**`, `codex.toml`, and the local plugin
under `plugins/evolve-target/**`. Its initial `SessionStart` hook injects
candidate-owned context, and every canonical evaluation installs the candidate
plugin into an isolated temporary `CODEX_HOME` before invoking Codex CLI.

Authentication uses the host Codex login. Run `codex login` once; a ChatGPT
subscription login is sufficient and no `OPENAI_API_KEY` is required. The
credential remains runtime state and is not copied into the candidate genome.

The recipe uses a versioned 30-task subset derived from the official
`terminal-bench@2.0` dataset. Task names and content digests are checked into
`dataset-manifest.json`; this prevents a missing local directory from silently
turning into a different experiment.

Prepare the dataset and pinned image, then run:

```bash
./scripts/setup_terminal_bench.sh ahe_codex
./scripts/run_recipe_demo.sh ahe_codex
```

Generation 0 and subsequent generations use the same frozen 30 tasks. This is
an optimization curve over the selected set, not a held-out generalization
claim. To compare another task set, create a new manifest and experiment ID.

When Harbor uses Docker through Colima or Docker Desktop, keep the workspace,
dataset, and `EVOLVE_UV_CACHE_DIR` on a host path shared with the VM. Colima
shares `/Users` by default; macOS `/private/tmp` is not the same directory in
the VM, so verifier rewards written through a bind mount will not appear in a
workspace created there.
