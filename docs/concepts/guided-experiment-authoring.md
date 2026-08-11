# Guided Experiment Authoring Design

## Purpose

Make EvolveX usable through one conversational skill. A user should be able to
ask Codex, Claude, or another compatible coding agent to improve a target; the
agent should learn the user's requirements, explain the meaningful choices,
author the recipe, operators, and evaluation assets that are needed, validate
them, and deploy a frozen experiment only after explicit approval.

This design builds on the Lego Operator Library introduced by PR #47. That
change supplies the machine-facing primitives for operator discovery,
declarative configuration, scaffolding, validation, recipe resolution, and
workspace provenance. Guided authoring is an agent experience over those
contracts, not a second composition framework.

## Goals

1. Give users one public skill and one continuous conversation from target
   discovery through experiment operation.
2. Make every material decision informed: show realistic options, explain
   their consequences, recommend one, and let the user decide.
3. Reuse the current `skills/evolve-agent/` package, method cards, scientific
   guidance, workspace contract, skill evaluations, and PR #47 commands.
4. Compose existing recipes and operators before creating new ones.
5. Let the user's agent co-design, implement, and test reusable custom
   operators in a writable EvolveX source checkout.
6. Support both configuring existing evaluations and authoring new
   evaluations.
7. Present Harbor-compatible evaluation and new evaluator-engine development
   as explicit alternatives with different cost, risk, and review levels.
8. Separate architecture, source, and deployment approval so design
   conversations cannot silently trigger external work or create experiment
   lineage.
9. Keep the workflow resumable from durable repository artifacts rather than
   hidden conversational state.
10. Make Codex, Claude, repository-local, and global entry paths converge on
    the same canonical workflow.

## Non-goals

- Replacing the PR #47 operator catalog, declarative `Config` contract, or
  recipe resolver.
- Adding a second operator registry or allowing reusable recipe-local operator
  implementations.
- Turning recipes into executable workflow graphs or allowing user-defined
  lifecycle stages.
- Making canonical evaluation, archive stamping, or lineage integrity
  user-replaceable.
- Hiding framework development behind the same risk language as Harbor task
  authoring.
- Automatically installing tools, cloning repositories, building images,
  using credentials, calling models, or spending evaluation budget without
  user authority.
- Encoding every possible user conversation as a rigid CLI wizard.

## Governing principles

### One front door, progressive playbooks

The user invokes one public skill, retaining the existing
`evolve-agent` identity. The skill detects the current context and loads only
the relevant playbook. The distinction between experiment architecture and
experiment operation remains an internal responsibility boundary rather than
two user-facing commands.

### Informed user control

The agent may recommend strongly, but it must not hide realistic alternatives
or silently make material scientific, security, cost, or irreversible choices.
Low-risk mechanical defaults may be applied without interrupting the user only
when they are disclosed in the next review summary.

### Evaluation precedes optimization

The measurement contract, protected data, and supported claims must be
understood before selecting the evolution policy. Operators are chosen against
the evidence that the evaluator can actually produce.

### Existing capability before new code

The agent inspects supported methods and the live PR #47 catalog before
proposing a new operator. A custom implementation must correspond to a named
capability gap, not mere stylistic preference.

### Durable state over conversational memory

Decisions, assumptions, source, tests, normalized configuration, preflight
results, and frozen workspace receipts are the resumable state. Another agent
must be able to continue without reconstructing an earlier chat.

## Architecture

### Canonical skill package

The existing skill remains the canonical package:

```text
skills/evolve-agent/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    ├── decision-protocol.md          # new
    ├── experiment-design.md          # new
    ├── operator-authoring.md         # new
    ├── evaluation-authoring.md       # new
    ├── evaluator-engine-authoring.md # new
    ├── deployment.md                 # new
    ├── workspace-contract.md         # existing
    ├── scientific-foundations.md     # existing
    ├── hill-climb.md                 # existing
    ├── a-evolve.md                   # existing
    ├── gepa.md                       # existing
    ├── ahe.md                        # existing
    └── hyperagents.md                # existing
```

`SKILL.md` is a compact router and evidence-chain overview. Detailed authoring
procedures live in progressively loaded references. Public documentation and
code remain authoritative for framework contracts; skill references describe
how an agent uses those contracts and must not duplicate catalogs or schemas.

When PR #47 is merged, the skill's operator-authoring prose must use the final
declarative `Config` and `sdk.main(..., config_schema=CONFIG)` contract. It must
not retain the earlier procedural `validate_config` example as a parallel API.

### Context routing

The router recognizes four contexts from filesystem evidence:

| Context | Evidence | Next playbook |
| --- | --- | --- |
| External target project | candidate source but no EvolveX source or workspace markers | bootstrap and experiment design |
| EvolveX source checkout | `.git`, `pyproject.toml`, `src/evolve/`, `library/`, and `recipes/` | source authoring |
| Initialized workspace | `evolve.yaml`, `.evolve-components.json`, archive and workspace launcher | experiment operation |
| Insufficient context | none of the above is conclusive | ask one focused location question |

The router reports the evidence for its classification. It does not infer a
writable source checkout merely because an installed Python package is
available.

### Platform and installation adapters

`.codex` and `.claude` contain thin discovery adapters that direct each
platform to the canonical skill. They do not copy its workflow, safety rules,
method guidance, or framework contracts. Exact adapter formats follow the
supported conventions of each platform at implementation time.

A globally installed skill is another entry point, not another implementation.
When invoked outside EvolveX, it identifies the candidate target and locates or,
with approval, acquires a writable EvolveX checkout. PR #47 requires named
custom operators to live in such a checkout; the global path must not edit an
installed package or conceal reusable code beside a recipe.

## Decision protocol

Every material choice is presented as a compact decision packet:

1. **Decision:** what must be chosen and why it matters.
2. **Options:** realistic supported choices, including deferral when valid.
3. **Recommendation:** the preferred option and concrete reasons.
4. **Trade-offs:** quality, cost, time, complexity, security, and
   reproducibility.
5. **Consequences:** files, framework boundaries, services, credentials, or
   experiment state affected.
6. **Reversibility:** whether the choice can change later or requires a new
   frozen workspace.
7. **Unknowns:** missing evidence and explicit assumptions.
8. **Selection:** the user's confirmation before the agent proceeds.

A choice is material when it changes the measurement contract or supported
claims, trust or credential boundary, external spend, source implementation,
or content frozen into an initialized workspace.

Material decisions include at least:

- existing recipe versus custom composition;
- existing operator versus new operator;
- existing evaluation versus new evaluation;
- Harbor-compatible evaluation versus a new evaluator engine;
- deterministic checks versus rubric or model judging;
- local versus isolated execution;
- dataset partitions and sealed-data exposure;
- authentication and external services;
- source approval, deployment approval, and live budget use.

Selections and rationale are recorded in the custom recipe's `README.md` or,
for framework-wide evaluator-engine work, the maintained design documentation.

## End-to-end workflow

### 1. Establish the target

The agent identifies the target project, prompt, skill, or harness; desired
behavior and known failures; mutable and protected paths; external
dependencies; budget; credentials; and execution environment. Ambiguities that
change the experiment contract become decision packets.

### 2. Design the evaluation

The agent determines whether the user already has evaluation assets and
inspects their coverage, determinism, leakage risk, runtime, and compatibility.
When a new evaluation is required, it presents two options.

#### Harbor-compatible evaluation

This is the default recommendation when the desired behavior can be expressed
as isolated benchmark tasks. The agent may create or adapt:

- task instructions and input fixtures;
- deterministic test scripts;
- rubrics and judge schemas;
- artifact validators;
- Docker environments;
- candidate adapters;
- positive and negative calibration candidates;
- train, gate, and sealed partitions.

The path preserves the supported evaluator engine and normally has lower
framework risk and implementation cost.

#### New evaluator engine

The agent presents this when it can name an execution or scoring requirement
that Harbor cannot satisfy, or when the user chooses it after reviewing both
options. This path changes trusted framework mechanics and therefore requires a
separate framework architecture review, threat analysis, engine scaffold,
runtime and preflight integration, deterministic contract tests, maintained
documentation, and recipe integration.

The skill must explain that a new engine is a framework feature: users need the
EvolveX version containing it, and its failures can affect score trust rather
than only benchmark quality.

Selecting this option branches into the evaluator-engine authoring project. An
engine-specific design and threat review must be approved before engine source
implementation begins; the general experiment architecture approval does not
substitute for that review.

Before optimization design begins, the user reviews scoring semantics,
partitions, calibration evidence, limitations, and the claims the evaluator can
support.

### 3. Design the evolution method

The agent reads only the relevant method cards, then queries the live PR #47
surface:

```bash
evolve operator list --json
evolve operator describe <stage>/<name> --json
```

It explains whether a supported recipe fits, proposes a code-free custom
composition when necessary, and identifies gaps that require new operators.
The fixed lifecycle and framework-owned evaluation boundary remain unchanged.

This phase ends with the **architecture approval** packet covering target,
evaluation, recipe, operators, mutable surface, runtime, budget, risks, and
known unknowns.

### 4. Implement approved source

After architecture approval, the agent works on an isolated branch or worktree
and preserves unrelated changes. It may:

- write the custom recipe and rationale;
- author Harbor tasks and evaluator assets;
- run `evolve operator new <stage> <name>` and implement the resulting named
  operator;
- declare its configuration with `evolve.frozen.config.Config`;
- add focused behavioral tests;
- implement an evaluator engine and its trusted-boundary tests only after its
  separate engine-specific design is approved;
- update maintained documentation required by the changed boundary.

Reusable named operator source stays at `library/<stage>/<name>.py`. Recipes
contain selection and configuration, not reusable Python implementations.

### 5. Verify authoring artifacts

Verification proceeds from inexpensive contracts to broader behavior:

```text
operator describe/check
→ recipe check
→ focused operator tests
→ evaluator positive and negative controls
→ model-free evaluator smoke
→ relevant framework tests
→ normalized composition and provenance review
```

The agent then presents the **source approval** packet: the exact diff,
normalized configuration, test and calibration evidence, limitations, expected
runtime and cost, and the bytes initialization will freeze.

### 6. Prepare and deploy

After source approval, the agent runs read-only preflight and reports failures
with their resolution choices. It does not silently install dependencies,
download assets, build images, use credentials, or call models.

Once prerequisites pass, the agent presents the **deployment approval** packet.
On approval it initializes the workspace, verifies its frozen contract and
provenance, and may run inexpensive candidate smoke checks. Material model or
evaluation spend, including baseline certification, receives explicit
authorization. The initialized workspace then enters the existing
evidence-chain operating workflow.

## Approval semantics

Approvals bind to exact artifacts and assumptions:

- changing scoring semantics invalidates evaluation and downstream approvals;
- changing operator behavior invalidates source approval;
- changing the dataset, runtime identity, or recipe after preflight invalidates
  deployment approval;
- changing a frozen workspace contract requires a new workspace.

Architecture approval binds to the recorded decision set. Source approval
binds to the reviewed Git diff or commit plus normalized operator and recipe
checks. Deployment approval binds to the selected recipe, operator, evaluator,
dataset, runtime identities and their recorded digests, together with the
current preflight result.

The agent names which approval became stale and why. It never treats a general
statement of intent as authorization for unrelated external or costly work.

## Durable artifacts and data flow

A typical custom recipe is the resumable design record:

```text
my-recipe/
├── evolve.yaml
├── README.md          # goal, decisions, assumptions, evidence, limitations
└── evaluator/         # permitted evaluator assets when needed
```

Reusable operator source lives in `library/`; focused tests live in `tests/`.
Framework-wide engine work also updates `src/evolve/`, evaluator scaffolds,
`ARCHITECTURE.md`, and maintained public design documentation as required.

The complete flow is:

```text
user requirements
→ decision packets and recipe rationale
→ catalog and schema inspection
→ approved source implementation
→ focused tests and PR #47 checks
→ source review
→ environment preflight
→ deployment approval
→ frozen workspace and provenance
→ evidence-backed experiment operation
```

## Failure, safety, and recovery model

Failures are classified rather than blurred:

| Category | Meaning |
| --- | --- |
| Requirement ambiguity | a material choice lacks sufficient information |
| Authoring failure | invalid operator schema, recipe, evaluator asset, test, or framework contract |
| Environment failure | missing tools, images, credentials, disk, or connectivity |
| Evaluation-design failure | calibration exposes wrong incentives, leakage, or inadequate discrimination |
| Live execution failure | an authorized model, container, or benchmark run fails |
| Integrity failure | frozen files, provenance, lineage, or stamped evidence do not verify |

The agent does not weaken an evaluator because the environment is unavailable,
silently replace a failing custom operator, or reinterpret infrastructure
failure as candidate quality.

Credentials remain outside recipes, prompts, retained artifacts, and reports.
External installations, network downloads, image builds, model calls, and paid
evaluation require explicit authority. New operator code retains PR #47's
subprocess boundary. New evaluator-engine work receives additional scrutiny and
cannot make canonical stamping or lineage user-replaceable.

Recovery begins from durable artifacts. Another agent reruns inexpensive checks
rather than trusting an old conversational claim. Failed live actions retain
safe diagnostic evidence, while retries that consume money or evaluation
budget require renewed authorization.

## Testing strategy

### Skill behavior evaluations

Extend `evals/skills/evolve-agent/` with cases that verify context routing,
focused interviewing, complete decision packets, option transparency, method
and catalog inspection, approval gates, external-action refusal, approval
invalidation, and artifact-based recovery. Rubrics score decision quality and
scientific correctness rather than demanding one exact conversation.

### Model-free integration fixtures

Cover at least:

1. existing operators with an existing Harbor task set;
2. a custom recipe composed from the PR #47 catalog;
3. a new named operator with declarative configuration and focused tests;
4. a newly authored Harbor evaluation with known-good and known-bad controls;
5. a simulated evaluator-engine integration without live services;
6. interrupted authoring resumed from source artifacts;
7. an assumption change that invalidates prior approval.

Fixtures must not require credentials, network access, model calls, or live
services.

### Platform parity

Codex and Claude adapters must discover the same canonical skill, avoid copied
workflow instructions, point to maintained project files, and preserve the
same approval and safety rules. A lightweight repository test should detect
substantial duplicated canonical instructions.

### Repository verification

Follow the repository test tiers: focused checks while iterating, relevant
composition/resource/coherence tests for changed boundaries, and
`uv run --frozen pytest -q` before handoff. Run slow generated-workspace tests
only when their workflow is affected. Docker, Harbor, model, and live-campaign
checks remain explicitly authorized manual validation.

## Delivery decomposition

The complete experience spans independent boundaries and is too broad for one
implementation plan. Deliver it as four reviewed projects that preserve this
umbrella architecture:

1. **Guided recipe and operator authoring:** compact skill router, decision
   protocol, experiment-design and operator-authoring playbooks, PR #47
   alignment, approval records, and skill behavior evaluations.
2. **Harbor evaluation authoring:** evaluation playbook, deterministic task and
   rubric patterns, calibration workflow, fixtures, and focused evaluations.
3. **Evaluator-engine authoring:** a separate framework design for engine
   extensibility and one model-free reference path; this project receives its
   own spec before implementation because it changes trusted mechanics.
4. **Distribution adapters:** verified `.codex` and `.claude` discovery,
   globally installed bootstrap behavior, and parity tests based on the
   platform conventions current at implementation time.

Each project receives its own spec, implementation plan, focused tests, and
review. The first implementation project should be guided recipe and operator
authoring because PR #47 already supplies its stable machine-facing substrate.

## Acceptance criteria

The umbrella design is realized when:

1. A user can invoke one public skill from Codex or Claude.
2. The agent can guide a target from requirements to an initialized workspace.
3. Current method cards, scientific guidance, workspace contract, skill
   evaluations, and PR #47 primitives are reused.
4. Existing and new named operators are both supported.
5. Existing Harbor tasks and newly authored Harbor evaluations are supported.
6. Harbor-compatible evaluation and evaluator-engine development are both
   presented with their differences before the user chooses.
7. Every material choice includes options, recommendation, trade-offs,
   consequences, reversibility, and unknowns.
8. Architecture, source, and deployment approvals are enforced and invalidated
   when their inputs change.
9. The workflow resumes from repository artifacts rather than hidden chat
   state.
10. Codex, Claude, repository-local, and global entry paths converge on the
    same canonical skill workflow.
