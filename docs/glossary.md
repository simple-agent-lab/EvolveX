# Glossary

Precise meanings for the domain terms this project uses.

> **Note:** the canonical operator set is `select · rollout · meta_agent · gate ·
> record` (`observe` retired). `novelty` and `reflect` are optional operators
> (off unless a recipe configures them). Authority is `DESIGN.md`.

- **Agent** — the thing being improved. Open-source agent (e.g. mini-swe) =
  a code folder; closed-source agent = a model plus an editable context layer.

- **Candidate / target** — one agent version in the lineage. It *is the whole
  agent folder* (`target/`), not an abstract genome. What runs under the
  evaluator is what a candidate edit changes.

- **Mutable surface** — the `surface` include/exclude globs that say which
  files a candidate edit may touch. The single knob that separates evolving an open
  agent (surface includes its code) from a closed agent (surface includes only
  the context layer), and a normal run from self-modification (surface may add
  specific workflow files such as `operators/meta_agent.py` and
  `operators/meta_agent.md`). The evaluator, archive, and vendored mechanism
  are always excluded.

- **Operator** — a swappable step in the loop: select, rollout, meta_agent, gate,
  record. Framework machinery configured per experiment, run as a subprocess;
  not part of the agent being evolved. (`observe` is retired; operators read
  in-loop artifacts directly through `ctx` paths such as `runs/`, rollout
  summaries, and archive rows.)

- **Operator context (`ctx`)** — The per-operator invocation context. In code,
  `ctx` is an `OperatorContext`: workspace root, checkout, run directory,
  generation id, selected parent, optional round, fan-out, operator config, and
  seeded RNG. It tells an operator where it is and which generation it is
  handling.

- **Meta-agent operator** — the loop step that changes the candidate. It is a
  protocol adapter around the `agent_command` variant, which delegates to
  `run_meta_agent`, then the mechanism applies surface enforcement before it
  inspects the result.

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
  The meta-agent can inspect rollout summaries, artifacts, archive rows, and
  run directories directly through `ctx`; the mechanism no longer writes a
  framework-authored feedback bundle.

- **Trace / trajectory** — the step record of a rollout. Harbor writes traces
  under `runs/gen-N/eval/` and `~/.evolve/harbor-jobs`. Subtask-level
  trajectory analysis is not yet modelled.

- **MiniSWE source target** — for MiniSWE source evolution, `target/` is the
  MiniSWE source checkout plus `target/harbor_agent.py`. Harbor imports
  `target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into
  the task container, installs that source, and then reuses Harbor's MiniSWE
  run behavior.

- **`run_meta_agent`** — `run_meta_agent(workspace, prompt, config)` is
  separate from the meta-agent operator interface. It is only the local
  agent runner that receives a checkout and prompt, then runs the
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
