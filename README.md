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
  A Python `driver.py` conducts them (driver mode); an orchestrating agent
  reading `program.md` can replace it (agent mode).
- **Typed protocol, JSON only at the wire**: every operator interface (CLI,
  required output keys, write scopes, exit codes) is defined once as types in
  `FROZEN/contracts/protocol.py` — the interface is mechanism, the
  implementation is evolvable. The driver, the operator SDK
  (`FROZEN/contracts/oplib.py`), and the contract tests all validate against
  the same types; `PROTOCOL.md` is the human/LLM-readable rendition injected
  into mutation prompts from M2.
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
├─ driver.py            driver-mode conductor (10-step inner loop; loop.sh is a thin wrapper)
├─ program.md           loop rules (agent-mode orchestration prose)
├─ PROTOCOL.md          operator protocol, human/LLM-readable (authority: FROZEN/contracts/protocol.py)
├─ operators/           evolvable operators (defaults + variants) + engine adapters
├─ meta/                paired strategy prose per operator
├─ candidate/           Layer 2 genome: code + model_ref (weights slot)
├─ FROZEN/              frozen core: eval/stamp/splits/decontam/meta_eval/audit
│   └─ contracts/       protocol.py (typed interfaces) + oplib.py (operator SDK) + run_contracts.py
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
| M1 | real harness (harbor): 3-way splits + adapter **done on stub**; needs a live harbor install (binary, docker, dataset pin, model keys) to finalize | mechanics done |
| M2 | reflect/playbook (insight pool + falsification + credit backfill); llm mutate scaffolded (needs claude CLI/key) | **done** |
| M3 | population + self-reference (real novelty + retries, contracts+meta_eval admission gate, islands w/ migration) | **done** |
| M4 | presets (autoresearch / AHE / HyperAgents / MetaAgent) + operator variants | **done** |
| M5 | data pipeline (distill + frozen decontam, tamper-evident stamps; engine rejects unstamped) | **done** |
| M6 | weights into the lineage — **blocked on infra**: open-weights policy model + vLLM serving + GPU (or fine-tuning API) | blocked |
| M7 | auto-train closed loop (plateau trigger, async train jobs) | after M6 |
| M8 | recipe evolution + online RL exploration | after M7 |

Tests: `tests/run_all.sh` (smoke, contract rejection, insight loop,
self-reference admission, islands, presets, training-data pipeline).
