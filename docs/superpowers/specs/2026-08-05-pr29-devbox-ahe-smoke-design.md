# PR 29 DevBox AHE 3x3 Smoke Design

## Goal

Validate PR #29 on DevBox with a real AHE experiment over three tasks and three
evolved generations (`gen/1` through `gen/3`), after the genesis evaluation.

## Isolation and inputs

The experiment script creates a new timestamped directory under
`/data00/home/zimuwang`, checks out the PR head into a fresh clone, and creates a
fresh workspace. It does not modify or delete existing experiments. It uses an
existing immutable three-task DevBox dataset and DevBox's private environment
files. Secret values are copied into the generated workspace's Git-ignored root
`.env`; they are never printed or committed.

The script keeps the editable settings near the top: PR branch, base directory,
dataset, private environment inputs, task count, and generation count. The
defaults are three tasks and three evolved generations.

## Execution

The script:

1. verifies required tools and private inputs;
2. clones and checks out `codex/runtime-profiles-phase3`;
3. installs the locked framework environment;
4. initializes an AHE workspace using exactly three tasks;
5. writes the single workspace-root `.env` with private permissions;
6. runs ordinary preflight and model smoke preflight;
7. runs the experiment through `gen/3`;
8. runs framework verification and explicit evidence assertions.

## Success criteria

Success requires all of the following:

- the checked-out commit equals the PR head captured at launch;
- preflight and model smoke preflight pass;
- tags `gen/0`, `gen/1`, `gen/2`, and `gen/3` exist;
- the archive contains successful genesis and candidate evaluation records;
- each evaluated generation records exactly three expected trials;
- strict contract/runtime evidence is present and certified;
- `evolve verify` succeeds;
- the script exits zero only after every assertion passes.

On failure, the script exits nonzero and preserves the checkout, workspace,
logs, preflight receipts, and evaluation artifacts for diagnosis.

## Scope

This is one AHE smoke experiment. It does not run HyperAgents, alter production
defaults, expose private runtime data, resolve GitHub review threads, or clean up
older DevBox runs.
