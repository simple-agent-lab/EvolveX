# Glossary

Precise meanings for the domain terms this project uses.

> **Note:** the canonical operator set is `select · rollout · mutate · gate ·
> record` (`observe` retired). `novelty` and `reflect` are optional operators
> (off unless a recipe configures them). Authority is `DESIGN.md`.

- **Agent** — the thing being improved. Open-source agent (e.g. mini-swe) =
  a code folder; closed-source agent = a model plus an editable context layer.

- **Candidate / target** — one agent version in the lineage. It *is the whole
  agent folder* (`target/`), not an abstract genome. What runs under the
  evaluator is what a mutation edits.

- **Mutable surface** — the `surface` include/exclude globs that say which
  files a mutation may edit. The single knob that separates evolving an open
  agent (surface includes its code) from a closed agent (surface includes only
  the context layer), and a normal run from self-modification (surface adds
  `operators/**`). The evaluator, archive, and vendored mechanism are always
  excluded.

- **Operator** — a swappable step in the loop: select, rollout, mutate, gate,
  record. Framework machinery configured per experiment, run as a subprocess;
  not part of the agent being evolved. (`observe` is retired — the mechanism
  writes the feedback bundle itself; see `src/evolve/feedback.py`.)

- **Mutate / meta-agent** — the operator that changes the candidate. The
  `agent_command` variant spawns a coding agent that edits the folder in
  place; agent-agnostic via a configured command. Out-of-surface edits are
  auto-repaired before the mechanism sees them.

- **Evaluator / ruler** — the frozen scorer, wired to **Harbor**. Runs a
  candidate through the configured Harbor agent and returns a score. Harbor is
  the only real benchmark execution path. Real recipes call Harbor with an
  explicit `evaluator.agent` value. Smoke recipes are named `*-smoke` and are
  the only recipes intended for deterministic `EVAL_STUB=1` mechanism tests.
  Frozen: its tree must match `gen/0` on every eval.

- **Split** — `train / gate / sealed` (`evaluator/splits.json`): train feeds
  rollout, gate scores the canonical eval, sealed is never selected on and
  only human-triggered. (Task-level enforcement lands with Harbor
  partitioning; today the shape is honored by convention.)

- **Rollout** — runs the candidate on the train split to produce trajectories.
  The mechanism (`feedback.py`) then writes the ledger-derived feedback bundle
  the mutator reads (the retired `observe` operator's former job).

- **Trace / trajectory** — the step record of a rollout. Harbor writes traces
  under `runs/gen-N/eval/` and `~/.evolve/harbor-jobs`. Subtask-level
  trajectory analysis is not yet modelled.

- **MiniSWE source target** — for MiniSWE source evolution, `target/` is the
  MiniSWE source checkout plus `target/harbor_agent.py`. Harbor imports
  `target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into
  the task container, installs that source, and then reuses Harbor's MiniSWE
  run behavior.

- **`run_meta_agent`** — `run_meta_agent(workspace, prompt, config)` is the
  local mutation-agent runner. It receives a checkout and prompt, then runs the
  configured command in that checkout. It does not know about generation IDs,
  archive rows, Harbor, or surface policy.

- **Archive / lineage** — every candidate version in git (commit = candidate,
  tag `gen/N`) plus `archive.jsonl`. Keep everything.

- **Select / gate** — select picks the parent (greedy = best; score_weighted /
  random / newest are other variants; DGM-style divergent search fans out).
  gate is the accept/reject verdict; `parent_eligible` = valid children become
  eligible parents.

- **Paradigm** — a published system (AHE, DGM, HyperAgents, MetaAgent,
  autoresearch, hill_climb). A paradigm is a **recipe** (config), not an
  architecture: same fixed operator loop, different operator variants +
  surface + evaluator. There is no separate pipeline/workflow concept.

- **Recipe** — the `evolve.yaml` config that instantiates a paradigm.

- **Workspace** — the generated experiment directory: the agent folder +
  operators + frozen evaluator + archive, with the mechanism vendored under
  `.evolve/` so it self-drives.

- **Mechanism** — the `evolve` code (driver + verbs). Installed as a CLI for
  `evolve init`, and vendored into each generated workspace so it runs from
  inside. Never imports workspace operator code in-process.
