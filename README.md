# simple-evolve-agent

A self-evolve **and** auto-train agent framework: an inner loop evolves the
harness (operators / prompts / candidate code) and produces trajectories; an
outer loop distills those trajectories into weight updates. Both loops share
one lineage, one frozen ruler, and five hard invariants.

Design doc (v0.4, 中文): [架构 Review artifact](https://claude.ai/code/artifact/7375cbaa-768a-4265-88e2-43d26a2032bf)

## Core ideas

- **Evolvable operators, orthogonal orchestration**: the loop is a chain of
  operator scripts (`select / rollout / mutate / novelty / gate / record /
  reflect / distill`), each shipping a default implementation + variants.
  A ~100-line `loop.sh` drives them (driver mode); an orchestrating agent
  reading `program.md` can replace it (agent mode).
- **Weight updates are just mutations**: a checkpoint is a candidate, training
  is a variation operator, and the same frozen ruler scores it
  (`mutated: ["weights"]` in the ledger).
- **Five hard invariants** (everything else is open to self-modification):
  1. `FROZEN/eval.sh` (the Harness) never changes inside the loop — one ruler, all gens.
  2. Scores enter the ledger only via the frozen stamp; agents never pass them.
  3. `best-ever` is recomputed from true scores by a fixed rule; champion changes require a replication re-eval.
  4. Training data never contains gate/sealed-test tasks and never comes from audit-flagged gens (`FROZEN/decontam.py`).
  5. Checkpoints enter the lineage only through canonical eval.

## Quickstart (M0: stub harness)

```bash
bin/init-workspace.sh ws          # instantiate a workspace with its own git archive
cd ws
HARNESS_STUB=1 ./loop.sh 5        # idle-run 5 generations
cat archive.jsonl                 # the lineage (ledger schema v2)
git tag -l 'gen/*'                # commit = candidate, tag = generation
python3 FROZEN/contracts/run_contracts.py   # Tier-0 operator contract tests
```

Tests (M0 acceptance):

```bash
tests/smoke_m0.sh          # 5 idle gens -> lineage grows; git reset keeps history; contracts hold
tests/contracts_reject.sh  # broken operators (garbage output / FROZEN writes / score forgery) get rejected
```

## Layout

```
bin/init-workspace.sh   instantiate template/ into a workspace (own git repo, tag gen/0)
template/               the meta-workspace template
├─ loop.sh              driver-mode conductor (10-step inner loop)
├─ program.md           loop rules (agent-mode orchestration prose)
├─ operators/           evolvable operators (defaults + variants) + engine adapters
├─ meta/                paired strategy prose per operator
├─ candidate/           Layer 2 genome: code + model_ref (weights slot)
├─ FROZEN/              frozen core: eval/stamp/splits/decontam/meta_eval/contracts/audit
└─ .gitignore           runs/, archive.jsonl, insights/, ckpts/… stay untracked (reset-proof)
tests/                  M0 acceptance scripts
```

Workspace state that must survive `git reset` (ledger, runs, playbook,
manifests, checkpoints) is deliberately untracked; everything that travels
with the lineage (candidate, operators, meta, program.md) is committed and
tagged `gen/<id>` per generation.

## Milestones

| # | Goal | Status |
|---|------|--------|
| M0 | pipeline (driver + stub) + ledger schema v2 + contract tests | **done** |
| M1 | real harness (harbor), 3-way splits, parent-balancing on real scores | next |
| M2 | llm mutate + reflect/playbook (insight pool + credit backfill) | |
| M3 | population + self-reference (novelty, meta_eval admission gate, islands) | |
| M4 | presets (autoresearch / AHE / HyperAgents / MetaAgent) | |
| M5 | data pipeline (distill + frozen decontam) | |
| M6 | weights into the lineage (open model + vLLM, LoRA SFT) | |
| M7 | auto-train closed loop (plateau trigger, async train jobs) | |
| M8 | recipe evolution + online RL exploration | |
