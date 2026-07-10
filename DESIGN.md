# DESIGN.md — the unified design

This is the authoritative design of the framework. It is one system, not a
merge of an old and a new one: every capability has exactly one home. On any
conflict with other prose under `docs/`, this file wins; on any conflict about
an operator *interface*, `src/evolve/frozen/interfaces.py` wins (it is the
machine-readable authority, this file is its prose).

Coding conventions live in [`docs/coding-style.md`](docs/coding-style.md).
Docs layout: [`docs/README.md`](docs/README.md).

> **Implementation status** (this doc describes the whole design; not all of it
> is built). **Built & green today:** the honest core loop, the operator
> contract + single-source `OPERATORS` registry, the frozen ring
> (`interfaces`/`sdk`/`meta_eval`), Harbor-backed evaluation, optional
> research operators (novelty, reflect) and the self-modification gate,
> falsification → `verified_fixes`, and observability (`verify` / `doctor`;
> audit quarantine via `EVOLVE_AUDIT_JUMP`). **Planned, not yet built:**
> islands, auto-train (distill/decontam/train — DESIGN level 4, needs weights
> infra), and interactive `gen begin` / `gen finish` as a CLI surface.

---

## 1. The one idea

Evolve a **candidate** (code / prompts / config / weights-ref) under a
**frozen ruler**, keep a **lineage**, drive it with **one command**. Git is
the lineage archive (commit = candidate, tag `gen/<id>`), `archive.jsonl` is
the ledger, and a fixed set of invariants (§3) keeps the fitness signal honest
no matter what the loop — or the agent driving it — does.

RSI has no settled paradigm, so this framework isn't a bet on one. The
irreducible core is tiny; every research layer on top (insight pools,
self-modifying operators, islands, auto-train) is **opt-in, off by default**.
A user who only runs level 0 still has a complete, honest loop.

Harbor is the only real benchmark execution path. Real recipes call Harbor with
an explicit `evaluator.agent` value. Smoke recipes are named `*-smoke` and are
the only recipes intended for deterministic `EVAL_STUB=1` mechanism tests.

## 2. Three rings, ordered by who may change what

Everything in a workspace sits in exactly one ring. The boundary between rings
is not a convention — it is **physically enforced** by three separate
mechanisms, so evolution cannot cross a ring even if it tries to.

```
Ring 0 · frozen      the ruler (`evaluator/`) + the invariant-enforcers + the contract
                     enforced by: outside the mutable surface (evolution can't target it) +
                     every eval asserts the evaluator tree still == gen/0 (a changed ruler fails the eval)
Ring 1 · mechanism   the engine that runs the loop (driver, console)
                     enforced by: not in the mutable surface — evolution never targets it
Ring 2 · surface     the evolvable genome (target, operators, program, config)
                     enforced by: the mutable-surface globs; runs/ archive.jsonl are .gitignored
```

The governing rule for placing anything new:

> **Mechanism owns the primitives; policy is evolvable.**

The novelty *threshold and accept decision* are policy (Ring 2
`operators/novelty.py`); *what to remember and when to retire it* is policy
(Ring 2 `operators/reflect.py`). When unsure which ring something belongs in,
ask: "if evolution rewrote this to cheat, would a score become a lie?" If yes,
it is Ring 0 (frozen).

**Frozen is small, and it is NOT the evolution logic.** The seed operators and
algorithms — `library/` (the reference catalog) and a workspace's `operators/`
— are the *evolvable genome* (Ring 2): the whole ambition is that the evolution
logic can itself be evolved (self-reference, gated by `meta_eval`). What must
stay frozen is only the irreducible honesty core — the **ruler** (the evaluator:
workspace-side, excluded from the surface and pinned by the `tree == gen/0`
assertion), the **stamp** (scores enter only via the frozen side), the
**operator contract** (`frozen/interfaces.py` + `frozen/sdk.py`), and the
**admission gate** (`frozen/meta_eval.py`) that keeps self-modification honest.
Evolve the operators; never the ruler that judges them.

## 3. The five invariants (the part that is NOT optional)

Enforced, not documented-and-hoped. Everything else is open to evolution.

1. **The ruler never moves.** `evaluator/eval.sh` (and the engine it calls) never
   changes inside the loop — one ruler, all generations.
2. **Scores enter only via the frozen stamp.** Agents and operators never pass
   a score; `record` has no score argument. `score`/`task_vector` come only
   from `runs/gen-<id>/stamp.json`, written by the frozen side.
3. **`best-ever` is recomputed by a frozen rule**, and a champion change
   requires a replication re-eval. However loose a gate is, it cannot touch
   this.
4. **Training data never contains gate/sealed tasks** and never comes from
   audit-flagged generations. (To be enforced by a frozen decontam guard when
   auto-train is enabled — **planned, not yet built**; dormant until weights land.)
5. **Checkpoints enter the lineage only through canonical eval.** A checkpoint
   is a candidate; training is a variation operator; the same ruler scores it.

## 4. `template = skill`: two levels

The product *is* a skill. Two distinct skills, do not conflate them:

- **Outer skill** `skills/evolve-agent/SKILL.md` — globally discovered by
  Claude Code. Thin router: "no workspace yet → `evolve init`; else
  `cd` in and follow the workspace's own SKILL.md; everything through
  `./evolve`."
- **Inner skill** `skills/evolve-workspace/SKILL.md` — the operating manual
  that travels into every workspace, copied into a **unified, tool-agnostic
  `skills/` folder** (not `.claude/skills/`) so Claude Code, codex, and other
  tools can all find it; the workspace `AGENTS.md` points at it. This is where
  "you are the meta-agent" lives.

Intelligence lives in these markdown skills and in `operators/*.md` (per-verb
strategy prose beside the scripts), never in the harness. Thin harness, fat
skills. Skills are plain markdown in a plain `skills/` folder — no
tool-specific binding.

## 5. Directory tree

One system, no provenance tags. What runs, where.

```
simple-evolve-agent/
├─ README.md  DESIGN.md  ARCHITECTURE.md  CONTRIBUTING.md
│
├─ src/evolve/                    Ring 1 — the one thin harness (engine + contract source)
│   ├─ cli.py                     console dispatch — parsing only, no logic
│   ├─ driver.py                  the generation sequencer (the 10-step loop)
│   ├─ operators.py               subprocess runner for workspace operators
│   ├─ archive.py  population.py  ledger store · lineage bookkeeping
│   ├─ evaluator.py  git.py  surface.py  report.py  config.py
│   └─ frozen/                    Ring 0 — the invariant-enforcers, vendored into each workspace
│       ├─ interfaces.py          THE single source of truth: operator ABCs + result types +
│       │                         the OPERATORS registry + payload validation
│       ├─ sdk.py                 operator SDK (self-validation) + file-contract IO
│       └─ meta_eval.py           self-modification admission gate (confound-free replay)
│   (planned, not yet built: decontam.py — training-data guard for invariant #4, dormant until weights)
│   (the frozen *ruler* — eval.sh · stub_eval.py · splits.json · stamp — lives workspace-side
│    under evaluator/, since it must travel with the lineage and be digest-guarded there;
│    the harbor engine adapter that feeds the ruler is a workspace-side eval template)
│
├─ skills/                        fat skills as recipes (where `template = skill` lives)
│   ├─ evolve-agent/SKILL.md      outer: create + enter
│   ├─ evolve-workspace/SKILL.md  inner: the meta-agent's manual (travels into workspaces)
│   ├─ _conventions.md  _invariants.md  manifest.json
│
├─ templates/workspace/           Ring 2 static skeleton — the browsable shape init copies in
│   ├─ README.md                  the workspace map (also lands at the workspace root)
│   ├─ AGENTS.md  program.md      agent entry + loop orchestration prose
│   ├─ .gitignore
│   └─ operators/                 per-verb strategy prose seeds (`<verb>.md` + meta_agent_brief.md)
│       (init overlays the per-recipe/generated parts: evolve.yaml · operators/<verb>.py +
│        operators/README.md · library/<verb>/ palette · evaluator/… · target/ seed · skills/ · PROTOCOL.md)
│
├─ library/                       the framework's operator catalog (consult & adapt)
│   ├─ select/ rollout/ meta_agent/ validate/ novelty/ gate/ record/ reflect/   variants, each with a _skeleton.py
│   └─ README.md                  how the meta-agent draws from here (surfaced via the skill)
│       init vendors a per-recipe subset into the workspace's OWN library/
│
├─ recipes/                       a paradigm = a config (hill_climb, dgm, ahe, autoresearch, hyperagents, metaagent)
├─ tests/                         flat test_m<N>_<topic>.py + test_coherence.py (the enforced map guard)
└─ docs/coding-style.md     coding conventions
```

### The workspace at runtime (created by init; `.gitignore`d, reset-proof)

```
<workspace>/                       an independent git repo (its own gen/0 tag)
├─ README.md                       the workspace map (from templates/workspace/)
├─ target/                         the candidate being evolved (Ring 2, mutable per the surface)
├─ operators/                      ACTIVE set (Ring 2): `<verb>.py` + `<verb>.md` + README.md index
├─ library/                        vendored variant palette — swap-in alternatives per verb
├─ program.md                      loop orchestration prose (Ring 2)
├─ evolve.yaml                     experiment config (recipe, operator selection, mutable surface)
├─ evaluator/                      the FROZEN ruler (pinned to gen/0; outside the mutable surface)
├─ .evolve/                        vendored harness (stdlib-only) → the workspace self-drives (meta_eval replay needs this)
├─ evolve                          console → .evolve
├─ skills/evolve-workspace/        the meta-agent's manual (tool-agnostic: Claude Code + codex)
├─ PROTOCOL.md                     the operator contract in prose
├─ archive.jsonl                   the ledger (append-only, via record; frozen fields only from stamp)
├─ runs/gen-<id>/                  per-gen scratch: rollout/ · meta_agent/ · validate/ · gate.json · novelty.json
└─ insights/playbook.jsonl         the insight pool (written only by reflect)
```

## 6. One of each — the anti-duplication rule

There is never a v1 and a v2 of the same thing living side by side. Each
capability has one home; if a change needs a different interface, it goes
through the front door (bump `PROTOCOL_VERSION`), it does not fork.

| Capability | The one home |
|---|---|
| Interfaces / types / registry / ledger schema | `src/evolve/frozen/interfaces.py` |
| Operator SDK + playbook/novelty primitives | `src/evolve/frozen/sdk.py` |
| The loop engine | `src/evolve/driver.py` (vendored, not re-authored per workspace) |
| Canonical scoring | workspace `evaluator/eval.sh` → stamp (tree pinned to `gen/0`) |
| The ledger | one `archive.jsonl`, schema = `protocol.LedgerEntry` (version 1, born at 1) |
| Human-readable protocol | one `PROTOCOL.md`, authority = `frozen/interfaces.py` |
| Operator implementations | active set in `templates/workspace/operators/`; alternatives in `library/` |

**Vendoring is not a second version.** `src/evolve/` is the single source;
the copy inside a workspace is a *deployment*, stamped `MECHANISM_VERSION`.
`evolve upgrade` re-syncs it; `evolve verify` reports drift. One source, one
deploy — never two lineages.

## 7. Operators

Canonical verb set — this supersedes any earlier "six-verb" list:

```
select · rollout · meta_agent · validate · novelty · gate · record · reflect     (+ distill, deferred with weights)
```

`observe` is retired. The rollout summary is passed directly to `meta_agent` as
its observation, and other run artifacts remain available through the workspace
file contract. The mechanism does not synthesize a framework feedback bundle.

For MiniSWE source evolution, `target/` is the MiniSWE source checkout plus
`target/harbor_agent.py`. Harbor imports
`target.harbor_agent:MiniSweSourceAgent`, uploads the candidate source into the
task container, installs that source, and then reuses Harbor's MiniSWE run
behavior.

`run_meta_agent(workspace, prompt, config)` is the local meta-agent runner.
It receives a checkout and prompt, then runs the configured command in that
checkout. It does not know about generation IDs, archive rows, Harbor, or
surface policy.

Each operator is a standalone subprocess script (crash isolation), invoked with
`--config <json>` and an `EVOLVE_*` env contract, writing its result under
`runs/gen-<id>/` (the file contract). The driver validates that result at the
seam and the operator self-validates via the SDK — both derive from the one
contract module. Adding an operator is **one registry entry** — no parallel
table to drift. That registry *is* the coherence wall that replaces per-file
line budgets. (The contract lives in `interfaces.py`+`sdk.py` today and
now lives in `frozen/interfaces.py`+`frozen/sdk.py` (migration step S4, done).)

### The variant catalog (`library/`) is reference, not runtime

Variants are **operators to consult during evolution**, not a palette switched
at runtime. So they are neither harness (`src/`) nor per-workspace genome
(`templates/`) — they are a **top-level, framework-versioned catalog**:

- The meta-agent (an agent) reads `library/<verb>/*.py`, then **adapts a variant
  into** the workspace's active `operators/<verb>.py`. Only that adapted-in,
  committed copy ever runs — so meta_eval replay and the self-reference gate
  always act on in-tree code, and the catalog needs no digest, no freeze, no
  gate. It can grow freely without bloating a workspace.
- The catalog is surfaced through the skill (`operators/meta_agent.md` points at
  it), not copied in — fat-skills, again.
- It is also the sink for **harvest**: operators that evolve well in real runs
  get promoted back into `library/`, closing the loop
  `framework seeds → workspace evolves → good variants flow back` (M8).

HyperAgents uses a bounded atomic genome: `target/**`,
`operators/meta_agent.py`, and `operators/meta_agent.md`. A changed meta-agent
workflow affects later children forked from the accepted generation; fixed
selection, validation, gate, record, evaluator, and archive code remain outside
the V1 mutable surface. The driver checks the mutable surface immediately after
the proposal, runs optional candidate validation, and rejects a failed
self-modification admission atomically: no part of the child is committed.

## 8. The learning ladder (every rung above 0 is opt-in)

| Level | You get | Turn it on |
|---|---|---|
| 0 · run the loop | generations, lineage, champion tracking | `./evolve run N` |
| 1 · be the meta-agent | your agent edits the candidate; the machine keeps the books | edit within surface, then `./evolve run` (interactive `gen begin`/`finish` planned) |
| 2 · shape the search | select/gate/meta_agent behaviors; paradigms as recipes | edit `evolve.yaml` / `evolve init --recipe <name>` |
| 3 · self-modify | `operators/` (scripts + strategy prose) and `program.md` become mutable, behind surface checks + optional validation + the atomic meta_eval admission gate + novelty rejection; islands | a candidate edit touches `operators/` (gated automatically) |
| 4 · auto-train | plateau → distill → decontam-stamped data → train engine → checkpoint re-enters as a candidate | `EVOLVE_TRAIN_PLATEAU=K` (weights infra required) |

## 9. Versioning

One `VERSION` for the framework. One `PROTOCOL_VERSION` (an integer in
`PROTOCOL_VERSION` in `frozen/interfaces.py`, born at 1 — not "v2 migrating from v1"). Each workspace pins the
`PROTOCOL_VERSION` and `MECHANISM_VERSION` it was born with; `evolve upgrade`
moves a workspace forward deliberately, `evolve verify` flags any drift between
the vendored copy and its stamp. Changing a *required* interface key is the one
thing that bumps `PROTOCOL_VERSION`, and it happens outside the loop — the same
front door as bumping the harness version.
