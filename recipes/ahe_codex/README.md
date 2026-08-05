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

Prepare the dataset:

```bash
harbor download terminal-bench@2.0 --export -o /absolute/path/to/raw
python recipes/ahe_codex/prepare_dataset.py \
  /absolute/path/to/raw/terminal-bench \
  /absolute/path/to/terminal-bench-2-ahe-30-v1
```

Then initialize and run:

```bash
export HARBOR_TASKS="/absolute/path/to/terminal-bench-2-ahe-30-v1"
evolve init /absolute/path/to/ahe-codex-run \
  --recipe ahe_codex \
  --dataset "$HARBOR_TASKS"
cd /absolute/path/to/ahe-codex-run
./evolve doctor . --profile experiment --probe-model
./evolve smoke . --profile experiment --task cancel-async-tasks
EVOLVE_HARBOR_N_CONCURRENT_OVERRIDE=5 ./evolve run . --max-generations 1
```

Generation 0 and subsequent generations use the same frozen 30 tasks. This is
an optimization curve over the selected set, not a held-out generalization
claim. To compare another task set, create a new manifest and experiment ID.

When Harbor uses Docker through Colima or Docker Desktop, keep the workspace,
dataset, and `EVOLVE_UV_CACHE_DIR` on a host path shared with the VM. Colima
shares `/Users` by default; macOS `/private/tmp` is not the same directory in
the VM, so verifier rewards written through a bind mount will not appear in a
workspace created there.
