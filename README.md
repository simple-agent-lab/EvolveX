# simple-evolve-agent

Evolve a candidate (code / prompts / config / weights-ref) under a frozen
scoring harness. Git is the lineage archive, `archive.jsonl` is the ledger,
and five hard invariants keep the fitness signal honest no matter what the
loop — or the agent driving it — does.

RSI has no settled paradigm yet, so this framework deliberately isn't a bet
on one. The irreducible core is small — **a candidate, a frozen ruler, a
lineage, one command** — and every research paradigm on top (insight pools,
self-modifying operators, islands, auto-train) is an opt-in layer, off by
default. The repro matrix (four published systems as four config files) is
the proof that paradigms are configs here, not architecture.

Design doc (v0.4, 中文): [架构 Review artifact](https://claude.ai/code/artifact/7375cbaa-768a-4265-88e2-43d26a2032bf)

## 60 seconds

```bash
bin/init-workspace.sh ws && cd ws
export HARNESS_STUB=1        # deterministic stub harness (real harbor = M1-infra)
./evolve run 5               # evolve 5 generations
./evolve status              # who's the champion, how healthy is the population
```

That's the whole product at level 0. Everything below is optional depth.

## The learning ladder

| Level | You get | Turn it on | Read |
|---|---|---|---|
| **0 · run the loop** | generations, lineage, champion tracking | `./evolve run N` | this file |
| **1 · be the mutator** | your agent makes the mutations; the machine keeps the books | `./evolve gen begin` → edit → `gen finish` | workspace `SKILL.md` (~60 lines) |
| **2 · shape the search** | select/gate/mutate variants; four published systems as presets | edit `config.json`, or `bin/apply-preset.sh ws <name>` | `presets/*.json` |
| **3 · let it modify itself** | operators/meta/program.md become mutable, behind contract tests + a replay admission gate; novelty rejection; islands | happens when a mutation touches `operators/` (gated automatically); `bin/islands.sh` | `PROTOCOL.md`, `program.md` |
| **4 · auto-train** | plateau → distill trajectories → decontam-stamped data → train engine → checkpoint re-enters as a candidate | `EVOLVE_TRAIN_PLATEAU=K` (engine backend is M6, infra-blocked) | design doc §03 |

Defaults keep every advanced layer off: no novelty threshold tuning, no
audit quarantine (`EVOLVE_AUDIT_JUMP`), no outer loop, no islands — until
you ask. A user who only ever runs level 0 has a complete, honest
evolution loop.

## The five invariants (the part that is NOT optional)

Everything else is open to evolution and self-modification. These are not:

1. `FROZEN/eval.sh` (the Harness) never changes inside the loop — one ruler, all gens.
2. Scores enter the ledger only via the frozen stamp; agents never pass them.
3. `best-ever` is recomputed from true scores by a fixed rule; champion changes require a replication re-eval.
4. Training data never contains gate/sealed-test tasks and never comes from audit-flagged gens (`FROZEN/decontam.py`, tamper-evident stamps).
5. Checkpoints enter the lineage only through canonical eval.

Weight updates are just mutations: a checkpoint is a candidate, training is
a variation operator, the same frozen ruler scores it.

## Layout

```
bin/init-workspace.sh   instantiate template/ into a workspace (own git repo, tag gen/0)
.claude/skills/         evolve-agent skill (auto-discovered by Claude Code)
template/               the meta-workspace template
├─ evolve               the operating console: run/gen/status/show/doctor/verify/…
├─ SKILL.md             the operating manual for agents (level 1 starts here)
├─ driver.py            mechanism engine (10-step loop, begin/finish slots, outer loop)
├─ program.md           loop rules (agent-mode orchestration prose)
├─ PROTOCOL.md          operator protocol, human/LLM-readable (authority: FROZEN/contracts/protocol.py)
├─ config.json          Layer-1 variant selection (presets are alternative configs)
├─ operators/           evolvable operators (defaults + variants) + engine adapters
├─ meta/                paired strategy prose per operator
├─ candidate/           Layer 2 genome: code + model_ref (weights slot)
├─ FROZEN/              frozen core: eval/stamp/splits/decontam/meta_eval/audit
│   └─ contracts/       protocol.py (typed interfaces) + oplib.py (operator SDK) + run_contracts.py
└─ .gitignore           runs/, archive.jsonl, insights/, ckpts/… stay untracked (reset-proof)
presets/                repro-matrix configs (autoresearch/AHE/HyperAgents/MetaAgent)
tests/                  acceptance suites (tests/run_all.sh)
```

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
| M7 | auto-train trigger mechanics (plateau detect -> distill -> decontam -> engine dispatch) **done to the engine boundary**; checkpoint re-entry needs M6 | mechanics done |
| M8 | recipe evolution + online RL exploration | after M6/M7 |

## Observability & integrity

- `./evolve status` / `show <gen>` — one-screen digest / one-gen deep dive (`--json` for machines)
- `./evolve report` and `bin/lineage-report.py` — population health, task-vector
  diversity (collapse warning), Tier-1 operator-mutation attribution
- `./evolve doctor` — detect + repair interrupted states
- `./evolve verify` — integrity fsck: ledger vs stamps vs eval results vs
  deterministic spot recomputes (hand-edited ledgers are exposed)
- `./evolve audit` / `EVOLVE_AUDIT_JUMP` — quarantine of suspicious score jumps

Tests: `tests/run_all.sh` (9 suites: smoke, contract rejection, insight loop,
self-reference admission, islands, presets, training-data pipeline,
outer-loop trigger, skill CLI).
