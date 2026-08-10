# EvolveX arXiv Report Design

## Purpose

Create a concise systems report that introduces EvolveX as a composable
framework for self-improving agents. The report serves researchers who design
and compare self-improvement methods and practitioners who want to run those
methods against real agent systems.

The manuscript describes one coherent EvolveX system. Implementation planning,
readiness, and unresolved experiment choices are tracked outside the paper and
must not appear as a current-versus-target narrative in the manuscript.

## Working Title

> **EvolveX: A Composable Framework for Self-Improving Agents**

The title is provisional, but the phrase "self-improving agents" is the public
term for the paper. Recursive self-improvement may appear in the motivation and
related work without becoming the title's terminology.

## Central Problem

Self-improving-agent methods repeatedly implement similar machinery:
evaluation, rollout analysis, mutation, selection, validation, promotion, and
experiment tracking. Existing systems often package those elements into
isolated implementations. This makes methods difficult to reproduce, combine,
ablate, and compare, and forces practitioners to rebuild experiment
infrastructure for each method.

## Thesis

EvolveX factorizes self-improvement into a shared experimental lifecycle and
interchangeable operators. Researchers can reproduce, modify, ablate, and
combine methods like Lego pieces, while practitioners can run them through one
consistent framework.

Trustworthy execution, frozen evaluation, and durable evidence support this
claim. They are enabling properties of the composable framework rather than the
paper's headline contribution.

## Audience and Scope

The report gives equal weight to two audiences:

- researchers designing, reproducing, comparing, and combining
  self-improvement methods; and
- agent developers applying those methods to prompts, skills, tools, harnesses,
  and selected evolution operators.

The report is a project and systems introduction rather than a conference paper
optimized around one algorithmic novelty claim. The main body should aim for
approximately six to seven pages. That target is a writing budget, not a hard
limit. References and optional appendices are outside the main-body budget.

The paper uses "diverse" or "representative" methods where it discusses method
coverage. It does not claim to implement every possible self-improvement method
or guarantee that evolution improves every target.

## Contributions

The introduction presents four system contributions and one evidence role:

1. **A compositional model.** A fixed lifecycle with well-defined, replaceable
   operators expresses diverse self-improvement methods.
2. **A reusable framework.** Common infrastructure owns targets, recipes,
   evaluation, execution, lineage, and artifacts instead of recreating them for
   each method.
3. **A research workbench.** Operator replacement and configuration enable
   controlled ablations, hybrid methods, and rapid exploration.
4. **A reliable experimental foundation.** Frozen evaluation and durable
   evidence make comparisons between compositions meaningful.
5. **Empirical illustrations.** Compact experiments demonstrate selected
   framework capabilities without turning the report into a benchmark paper.

## Narrative

The report follows a composable "Lego" architecture narrative:

1. Explain how fragmented, monolithic method implementations impede both
   research and use.
2. Identify the recurring lifecycle beneath apparently different methods.
3. Present recipes as declarative compositions of reusable operators.
4. Show the fixed framework mechanism that executes those compositions and
   preserves comparable evidence.
5. Demonstrate the same abstraction from a researcher's and a practitioner's
   perspective.
6. Close with compact empirical illustrations and the role EvolveX can play as
   shared infrastructure for self-improving agents.

This borrows the design-principles-to-architecture-to-evaluation logic of the
PyTorch systems paper without copying its section structure.

## Main-Body Structure

### 1. Introduction

Budget: approximately three quarters to one page.

- Establish the fragmentation problem.
- Introduce the Lego analogy and EvolveX.
- State the thesis and contributions.
- Preview the researcher and practitioner value.

### 2. Self-Improvement as Composition

Budget: approximately one half to three quarters of a page.

- Identify recurring stages across representative methods.
- Explain why monolithic implementations obstruct reproduction, ablation, and
  hybridization.
- Include the compact method-to-operator mapping table.

### 3. Design Principles

Budget: approximately one half page.

State three principles:

1. fixed lifecycle, replaceable policy;
2. simple and explicit composition; and
3. trustworthy experiments by construction.

### 4. EvolveX Architecture

Budget: approximately two to two and one half pages.

This is the technical center of the report. It covers:

- the shared evolution lifecycle;
- operator contracts and the reusable library;
- recipes as declarative compositions;
- mutable agent surfaces;
- framework-owned evaluation, lineage, and evidence; and
- isolation and failure boundaries.

### 5. Using and Extending EvolveX

Budget: approximately three quarters to one page.

- Show one concise end-to-end practitioner workflow.
- Show how a researcher replaces an operator while holding the remaining
  experiment fixed.
- Use one small recipe excerpt and approximately four commands.
- Leave complete API and command references to the project documentation.

### 6. Experimental Illustrations

Budget: approximately three quarters to one page.

The section's stable purpose is to illustrate that EvolveX can express
different self-improvement methods, support controlled recomposition, and
produce measurable agent improvements. Candidate evidence is managed in the
private readiness file and selected through partner review before the final
manuscript is written.

### 7. Related Work and Conclusion

Budget: approximately one half to three quarters of a page.

- Position EvolveX by ideas rather than through a paper-by-paper catalog.
- Relate it to self-improving agents, evaluator-guided optimization, agent
  evaluation infrastructure, and composable systems such as PyTorch and veRL.
- Conclude with EvolveX's intended role as shared research and application
  infrastructure.

## Conceptual Architecture

The architecture is presented in four bands.

### Compose

A declarative recipe specifies the target, evaluator, budgets, mutable surface,
and selected operator for every enabled stage. The recipe describes a method
without embedding executable method logic.

### Run

The framework executes one fixed lifecycle:

```text
select
  -> rollout
  -> analyze?
  -> mutate
  -> validate?
  -> novelty?
  -> evaluate
  -> gate
  -> record
  -> reflect?
```

`select`, `rollout`, `mutate`, `gate`, and `record` are required operator
stages. `analyze`, `validate`, `novelty`, and `reflect` are optional operator
stages. `evaluate` is fixed in the sequence and owned by the framework rather
than selected from the operator library.

Changing an operator changes method policy while preserving stage meaning and
experiment structure.

### Trust

The shared framework substrate provides:

- operator subprocess isolation and clean candidate snapshots;
- declared mutation surfaces and protected evaluation; and
- Git lineage, artifacts, scores, and archive records.

Failures remain attached to the stage and candidate that produced them.
Incomplete or invalid evidence cannot silently promote a new generation.

### Improve

Each generation connects an agent change to a frozen evaluator and produces a
candidate, comparable score, and reproducible lineage. Mutable agent artifacts
may include prompts, skills, tools, harness code, and selected evolution
operators as declared by the recipe.

## Researcher and Practitioner Views

### Researcher view

The paper includes a matrix with representative methods as rows and lifecycle
stages as columns:

```text
select | rollout | analyze | mutate | validate | novelty | gate | reflect
```

The initial row set is AHE, A-Evolve, GEPA, HyperAgents, and hill climbing. A
cell names the selected operator or indicates that the stage is unused. The
table makes differences explicit without suggesting that the methods are
algorithmically identical.

A running example starts from a supported recipe, replaces one analysis or
mutation operator, retains the evaluator and remaining composition, and
compares the resulting lineage. This demonstrates ablation and hybridization
without requiring a second experiment framework.

### Practitioner view

The report shows a four-step workflow:

1. choose a recipe and target agent;
2. initialize an isolated evolution workspace;
3. run generations under the shared evaluator; and
4. inspect the champion, lineage, scores, and artifacts.

The same recipe is both a runnable method for practitioners and an editable
composition for researchers.

## Main-Body Assets

The main body contains at most four primary assets:

1. **Figure 1 - EvolveX architecture.** Recipes, replaceable operators, fixed
   lifecycle, trusted runtime, and evidence flow.
2. **Table 1 - Method composition.** Representative methods mapped onto
   lifecycle stages.
3. **Listing 1 - Minimal recipe excerpt.** A small example showing that method
   composition is declarative and readable.
4. **Figure or Table 2 - Experimental illustration.** Selected through partner
   review from the candidate evidence recorded in the readiness file.

The visual companion diagram produced during design is a conceptual draft for
Figure 1. The manuscript figure should be redrawn as a publication-quality
vector graphic rather than copied from the browser view.

## Experimental Evidence Strategy

The experimental section reserves three evidence roles:

1. **Method coverage:** show that representative methods have explicit operator
   compositions.
2. **Outcome evidence:** show selected Terminal-Bench 2, Tau3 Banking, or skill
   evolution results in one compact comparison.
3. **Composability evidence:** optionally show an operator replacement,
   ablation, or hybrid-method example.

The exact outcome and composability studies are intentionally selected through
partner review. The final report includes only studies with complete artifacts,
clear denominators, and claims supported by the retained evidence.

## Private Readiness File

Create `arxiv/notes/report-readiness.md` as a manuscript-external planning file.
It is synchronized for partner discussion but excluded from the compiled
paper. It tracks:

- each proposed paper claim and its required evidence;
- candidate experiments and figures;
- implementation or measurement work needed for a claim;
- unresolved partner decisions and ownership; and
- final inclusion or exclusion decisions.

The paper does not refer to this file or expose implementation readiness as a
manuscript narrative.

## Presentation Style

- Write as a concise systems report, not project documentation or marketing.
- Lead each section with the problem or design decision it resolves.
- Explain abstractions through one running example.
- Prefer concrete boundaries and trade-offs over feature inventories.
- Use "composable framework for self-improving agents" consistently.
- Avoid claims that EvolveX supports every method or guarantees improvement.
- Keep commands, schemas, and exhaustive component inventories in external
  documentation or appendices.

## Related-Work Organization

Group related work by ideas:

1. self-improving-agent methods;
2. evolutionary and evaluator-guided optimization;
3. agent evaluation and experiment infrastructure; and
4. composable research systems, including PyTorch and veRL.

The method-composition section cites original method papers when it describes
their goals or maps them into EvolveX. The report must distinguish a faithful
reproduction from an adaptation or inspired recipe.

## Optional Appendices

Appendices may contain:

- detailed operator contracts;
- expanded method mappings;
- extended experiment results; and
- reproducibility and environment information.

Appendices do not compensate for missing explanation in the main body.

## Authoring and Quality Gates

Manuscript implementation follows these gates:

1. Create the readiness file and manuscript structure from this approved
   design.
2. Draft the architectural argument before writing experimental claims.
3. Select experiments through partner review and bind every quantitative claim
   to retained evidence.
4. Compile after each meaningful LaTeX change and resolve warnings that affect
   content or layout.
5. Render the complete PDF and inspect every page for overflows, broken
   references, illegible figures, and inconsistent terminology.
6. Scan the final source for drafting markers and unsupported claims before
   release.

The final report has no unresolved drafting markers, broken citations, or
claims whose implementation and evidence are absent from the readiness record.
