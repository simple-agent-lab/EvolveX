# Glossary

Precise meanings for the domain terms this project uses.

> **Note:** the canonical required operator set is
> `select · rollout · trace_analyzer · mutate · gate · record` (`observe`
> retired). `novelty` and `reflect` are optional operators
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

- **Operator** — a swappable step in the loop: select, rollout, trace analysis, mutate, gate,
  record. Framework machinery configured per experiment, run as a subprocess;
  not part of the agent being evolved. (`observe` is retired — the mechanism
  writes the feedback bundle itself; see `src/evolve/feedback.py`.)

- **Mutate / meta-agent** — the operator that changes the candidate. The
  `agent_command` variant spawns a coding agent that edits the folder in
  place; agent-agnostic via a configured command. Out-of-surface edits are
  auto-repaired before the mechanism sees them.

- **Evaluator / ruler** — the frozen scorer, wired to **Harbor**. Runs a
  candidate through a standard entry (`checkout_agent.py`) and returns a score.
  Frozen: its tree must match `gen/0` on every eval.

- **Split** — `train / gate / sealed` (`evaluator/splits.json`): train feeds
  rollout, gate scores the canonical eval, sealed is never selected on and
  only human-triggered. (Task-level enforcement lands with Harbor
  partitioning; today the shape is honored by convention.)

- **Rollout** — runs the candidate on the train split and writes method-neutral
  cases and trajectories.

- **Trace analyzer** — independently transforms rollout cases into raw,
  structured, and bounded selected evidence. The mechanism (`feedback.py`)
  then writes the ledger-derived feedback bundle the mutator reads.

- **Trace / trajectory** — the ordered message/tool-call/tool-result record of
  a rollout. Harbor writes raw jobs under `~/.evolve`; normalized and analyzed
  traces live under `runs/gen-N/rollout/` and `trace_analyzer/`.

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
