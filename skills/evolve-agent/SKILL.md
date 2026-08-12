---
name: evolve-agent
description: "Design, initialize, or operate an evolution workspace for agents, prompts, skills, and agent harnesses. Use when asked to turn requirements into an EvolveX recipe, choose or author reusable operators, deploy a frozen workspace, run generations, inspect lineage, recover state, or report an evidence-backed champion."
---

# Design and operate an evidence chain

Treat evolution as:

```text
requirements → contract → baseline → evidence → hypothesis
             → candidate → evaluation → lineage
```

## 1. Route from filesystem evidence

Starting at the current directory, inspect it and each ancestor nearest-first.
Evaluate each directory as one root; never combine markers from different
directories to manufacture a match. Collect the two complete marker sets:

- **Initialized workspace:** `evolve.yaml`, `.evolve-components.json`,
  `archive.jsonl`, and the workspace-local `./evolve` launcher all exist. Read
  `AGENTS.md`, `evolve.yaml`, and `program.md`; run `./evolve status .`,
  `./evolve verify .`, and `./evolve operator active . --json`; then read
  [the workspace contract](references/workspace-contract.md).
- **EvolveX source checkout:** `.git`, `pyproject.toml`, `src/evolve/`,
  `library/`, and `recipes/` all exist. Read
  [the decision protocol](references/decision-protocol.md) and
  [experiment design](references/experiment-design.md) before source work.
- **Partial or ambiguous EvolveX markers:** neither set is complete, but at
  least one EvolveX-specific marker exists: `evolve.yaml`, `src/evolve/`,
  `library/`, `recipes/`, `.evolve-components.json`, `archive.jsonl`, or
  `./evolve`.
  Report the markers that are present and missing, then ask one focused
  question for the authoritative target, EvolveX checkout, or initialized-
  workspace root. An importable or installed EvolveX package is not evidence
  of a writable source checkout. Do not guess a context or begin source or
  workspace actions until the location is clear.
- **External target project:** candidate source exists, neither complete set
  matches, and no EvolveX-specific marker exists. Generic `.git` and
  `pyproject.toml` files are ordinary target-project evidence and do not make
  the context ambiguous. Treat it as the candidate. Before the user
  decides, present both entry choices and their consequences:
  - **Repository-local entry:** use a thin target-repository platform adapter
    that routes to this canonical skill. It is portable and pinned with the
    target, but adds adapter metadata to maintain.
  - **Global-skill bootstrap:** use the user's global skill to locate or, with
    explicit approval, acquire a writable authoritative EvolveX source
    checkout. It requires no target-repository adapter, but depends on global
    installation and discovery plus trustworthy checkout provenance.
  Both entries converge on the same decision and experiment-design workflow.
  Neither entry choice authorizes cloning, editing, or credential access;
  obtain separate explicit approval for each required action. This repository
  exposes the same canonical skill through the implemented thin wrappers at
  `.agents/skills/evolve-agent` for Codex and `.claude/skills/evolve-agent` for
  Claude. Each wrapper delegates here and resolves references from this
  canonical directory. Do not invent a `.codex/skills` adapter or copy these
  instructions.
- **Insufficient context:** no recognizable candidate source and no complete or
  partial EvolveX marker set exists. Ask one focused question for the target,
  source-checkout, or initialized-workspace location and do not guess.

Choose the nearest complete candidate when it unambiguously owns the requested
work. If filesystem evidence or a user-supplied path identifies distinct
competing candidates, or the relationship between the nearest candidate and
the requested target is unclear, report the candidate roots and ask one focused
question. State the evidence for every classification.

**Completion check:** Name the context, target, authoritative checkout or
workspace, and next playbook.

## 2. Design before implementation

Define target, mutable surface, evaluator, partitions, budget, execution
boundary, and proof required for acceptance. Evaluation precedes method
selection. For every material choice, present the options and use
[the decision protocol](references/decision-protocol.md).

Use [experiment design](references/experiment-design.md) for a new experiment.
Read [scientific foundations](references/scientific-foundations.md) when
measurement semantics or research claims change. Do not use the method table
until experiment design has qualified evaluator coverage, determinism, leakage,
runtime compatibility, score direction and domain, aggregation, failure and
missing-result handling, thresholds, ties, acceptance semantics, calibration,
limitations, and supported claims. During design, catalog listing is
filesystem-only. Invoke a verified direct `evolve` executable from an
already-existing pre-provisioned environment. If it is absent, stop and request
a separate environment-remediation decision; inspection may not create a
`.venv`, synchronize, download, or provision anything. Before a needed
operator description, read
[operator inspection safety](references/operator-authoring.md) and use its
static review and credential-free read-only isolation procedure. Do not execute
authored source from a writable checkout. Do not scaffold or edit source before
architecture approval. Then read only the method cards whose evidence
requirements fit the experiment:

| Observable condition | Method | Read |
| --- | --- | --- |
| A minimal attributable control is enough | Hill Climb | [hill-climb.md](references/hill-climb.md) |
| Behavioral traces or generated-artifact rubrics should guide prompt or skill mutation | A-Evolve | [a-evolve.md](references/a-evolve.md) |
| The evaluator returns per-task results and the target splits into components | GEPA | [gepa.md](references/gepa.md) |
| Failures are execution-shaped and justify harness changes | AHE | [ahe.md](references/ahe.md) |
| The evolution process itself may also change | HyperAgents | [hyperagents.md](references/hyperagents.md) |

End design with architecture approval bound to the recorded experiment brief.
Do not write source or deploy before approval.

**Completion check:** The task-record rationale names the evaluator-first
contract, selected composition, rejected alternatives, custom capability gaps,
risks, unknowns, and architecture approval; an approved custom recipe later
preserves it in `README.md`.

## 3. Author and review source

Inspect catalog identities through the verified direct pre-provisioned
`evolve operator list --json`. When the approved composition needs a custom
recipe, read
[recipe authoring](references/recipe-authoring.md). Before executing
`evolve operator describe <stage>/<name> --json`, an operator check, a recipe
check, prospective preflight, or newly authored code, read
[operator authoring](references/operator-authoring.md) and use its static
import-safety review and credential-free environment with the exact reviewed
source mounted read-only. Configure an existing operator when it fits; author
reusable source only for an approved capability gap.

Guided authoring permits only named `operator:` bindings. Reject `script:`
bindings even when the user labels the task expert. This repository supplies no
named external script-review playbook, so guided authoring must stop on
`script:` rather than invent checks or an exception. Offer a named `operator:`
binding or deferral. Only a future named external playbook could define another
flow; none is supplied here.

Run direct operator checks, focused tests, and
`evolve recipe check <recipe-path> --json` inside that read-only boundary.
Treat recipe-check output only as operator resolution, normalization, and
composition evidence; rerun it after the target, evaluator, and operator
phases. Name static target/surface review, operator config/schema checks,
evaluator configuration checks, and focused behavior tests separately. Bind
target/surface evidence to the exact target digest. Present source approval
bound to either a clean commit or a complete source-tree manifest/digest with
explicit base, staged, unstaged, untracked, ignored, and exclusion coverage,
plus a digest of the whole packet. Prospective preflight remains deployment.

**Completion check:** Every custom operator has a named catalog identity,
declarative config, focused behavior test, valid recipe binding, limitations,
and source approval.

## 4. Prepare and deploy

Read [deployment](references/deployment.md). This repository supplies no
trusted preflight containment launcher or allowlist sanitizer, so guided
preflight stops unless a separate remediation decision supplies verified
pre-provisioned named tools and schema; do not improvise them. Only then gather
prospective evidence and obtain deployment approval before initialization. Ask
separately before live model or evaluation spend.

Keep a remote Git URL plus full revision in the source-approved recipe and
never override it with remote `--seed`. A guided local override names only the
approved content-addressed read-only snapshot of the exact framework vendoring
closure. Revalidate built-in resource digests and require the copied target
manifest and frozen remote revision to match before accepting generation zero.

Freeze the recipe rationale with the approved source and packet identities.
Record approval in an authoritative immutable or append-only hash-chained event
with approver identity, timestamp/event id, predecessor, and source and packet
digests. Store later preflight evidence, remediation authority, and deployment
approval in the same external chain without changing the approved source tree.
An ordinary Git note is only a convenience pointer or mirror unless externally
anchored; it is not approval authority by itself.

**Completion check:** The preflighted inputs match the initialized workspace,
provenance and integrity verify, and any baseline spend was authorized.

## 5. Operate the frozen experiment

Orient with `./evolve status .`, `./evolve verify .`, and
`./evolve operator active . --json`. Treat active bindings—not file
presence—as capability authority.

Choose exactly one control path for the next generation:

- Use `./evolve run . --max-generations 1` when the configured mutate stage
  should own the edit.
- Use `./evolve operator run . <stage> --genid <id>` and the mechanism-owned
  fork, commit, eval, and finalize transitions when the outer Agent owns the
  hypothesis and edit.

Do not run both paths for one generation. Tune a configured capability before
reading source; read active operator source only to diagnose or explicitly
change the running process.

**Completion check:** The chosen control path, parent, active direct stages,
retained evidence, mutable surface, and interrupted state are all explicit.

## 6. Close the loop

A parent artifact may be replayed only when the selected parent candidate
identity (candidate commit, generation id, and immutable tag resolution),
task-set identity, evaluator `contract_id`, runtime identity, artifact
manifest/digest, evaluation purpose and partition, and matching certified
result all agree with the current request. Any mismatch requires fresh parent
execution. Every child candidate executes fresh regardless of method or valid
parent evidence.

1. Establish and inspect the certified baseline.
2. Select a parent through the configured select stage.
3. Retain rollout and configured analysis evidence.
4. State one evidence-linked hypothesis and predicted effect.
5. Produce one candidate inside the declared mutable surface.
6. Run surface and every configured final-tree admission check.
7. Commit, evaluate, finalize, and verify through mechanism-owned transitions.

**Completion check:** The candidate has an exact lineage identity; admission
and evaluator-stamped results exist; verification passes; accepted and rejected
outcomes remain auditable; no child worktree is unaccounted for.

## 7. Report only what the chain proves

Start from `./evolve report .`. Report baseline, champion, parent-child change,
accepted and rejected mutations, evaluation partition, runtime identity,
retained evidence, and limitations. Resolve conflicts in favor of verified
evaluator-stamped lineage rather than generated summaries.

**Completion check:** Every score and champion identity derives from trusted
lineage, and every generalization claim names its partition and evidence.

## Guard the chain

- Keep one evaluator and runtime identity within an experiment.
- Keep optimization, gate, and sealed task identities disjoint.
- Change only the declared mutable surface.
- Match the execution boundary to candidate trust.
- Preserve linked worktrees outside `runs/worktrees/` unless their owner
  explicitly authorizes a change.
- Keep credentials out of prompts, artifacts, recipes, and reports.
- Spend live model or evaluation budget only when explicitly authorized.

## Historical-workspace note

Older initialized workspaces retain the mechanism, configuration, stage names,
and source frozen at creation time. Operate them through their vendored
`./evolve` and local skill; start a new workspace to use the current authoring
model.
