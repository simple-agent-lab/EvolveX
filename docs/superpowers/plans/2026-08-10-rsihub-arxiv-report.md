# RSIHub arXiv Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a concise, publication-quality arXiv systems report that introduces RSIHub as a composable framework for self-improving agents.

**Architecture:** Keep the manuscript in the nested `arxiv/` Overleaf Git repository and split prose by paper section. Use a two-column LaTeX article, one TikZ architecture figure, one method-composition table, one compact recipe listing, and an evidence section gated by the partner readiness record. Treat the root RSIHub repository as the source of truth for architecture, recipe mappings, commands, and retained results.

**Tech Stack:** LaTeX (`article`, TikZ, `booktabs`, `tabularx`, `listings`, `natbib`, `hyperref`, `cleveref`), BibTeX, `latexmk`, Poppler (`pdfinfo`, `pdftoppm`), Markdown readiness tracking, Git/Overleaf.

## Global Constraints

- Work in `/Users/bytedance/Desktop/simple-agent-lab/RSIHub/arxiv` for manuscript changes; it is an independent Git repository.
- Preserve the root repository's unrelated untracked `.codex/` and `arxiv/` entries and do not stage them from the root repository.
- Use **RSIHub: A Composable Framework for Self-Improving Agents** as the working title.
- Use “self-improving agents” as the main public term; use recursive self-improvement only in motivation or related work.
- Give researchers and practitioners equal emphasis.
- Aim for six to seven pages of main content; treat this as a writing budget rather than a hard limit.
- Describe one coherent RSIHub system. Do not put implementation-readiness or current-versus-target language in the paper.
- Present the fixed lifecycle as `select -> rollout -> analyze? -> mutate -> validate? -> novelty? -> evaluate -> gate -> record -> reflect?`.
- Keep `evaluate` framework-owned and treat other enabled stages as replaceable policy operators.
- Use “diverse” or “representative” methods; do not claim support for every method or guaranteed improvement.
- Cite original papers and primary project sources for technical claims. Mark RSIHub mappings as adaptations when fidelity is not demonstrated.
- Keep experiment selection and claim readiness in `notes/report-readiness.md`, which must not be included in the compiled manuscript.
- Do not introduce quantitative claims until the readiness record names the source artifact, denominator, aggregation, and approved wording.
- Compile after every manuscript task. Render and inspect the affected pages after every meaningful layout change.
- Do not commit LaTeX build products or rendered QA images.

---

## File Structure

The finished paper repository uses these responsibilities:

```text
arxiv/
├── .gitignore                       # LaTeX build products only
├── main.tex                         # document class, packages, metadata, section order
├── references.bib                   # verified primary-source BibTeX records
├── figures/
│   └── architecture.tex             # publication-quality TikZ system figure
├── sections/
│   ├── 01-introduction.tex          # problem, thesis, contributions
│   ├── 02-composition.tex           # recurring lifecycle and method matrix
│   ├── 03-design-principles.tex     # three design principles
│   ├── 04-architecture.tex          # system components, flow, boundaries
│   ├── 05-usage.tex                 # practitioner workflow and researcher swap
│   ├── 06-experiments.tex           # partner-approved empirical illustrations
│   ├── 07-related-work.tex          # grouped research context
│   └── 08-conclusion.tex            # concise role, limits, conclusion
└── notes/
    └── report-readiness.md           # private claim, evidence, and decision register
```

Stable LaTeX identifiers used across tasks:

```text
sec:introduction
sec:composition
sec:principles
sec:architecture
sec:usage
sec:experiments
sec:related-work
sec:conclusion
fig:architecture
tab:method-composition
lst:recipe
tab:results
```

---

### Task 1: Establish the manuscript substrate and readiness register

**Files:**
- Create: `arxiv/.gitignore`
- Modify: `arxiv/main.tex`
- Create: `arxiv/sections/01-introduction.tex`
- Create: `arxiv/sections/02-composition.tex`
- Create: `arxiv/sections/03-design-principles.tex`
- Create: `arxiv/sections/04-architecture.tex`
- Create: `arxiv/sections/05-usage.tex`
- Create: `arxiv/sections/07-related-work.tex`
- Create: `arxiv/sections/08-conclusion.tex`
- Create: `arxiv/notes/report-readiness.md`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-08-10-rsihub-arxiv-report-design.md`.
- Produces: a compiling two-column manuscript shell, stable section labels, and the decision gate consumed by Task 7.

- [ ] **Step 1: Verify the nested paper repository baseline**

Run from `arxiv/`:

```bash
git status --short
git branch --show-current
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Expected: branch `main`, no tracked modifications, and the existing 14-line paper skeleton compiles successfully. Record any pre-existing untracked files before changing the repository.

- [ ] **Step 2: Ignore only generated LaTeX products**

Create `.gitignore` with:

```gitignore
*.aux
*.bbl
*.blg
*.fdb_latexmk
*.fls
*.log
*.out
*.synctex.gz
main.pdf
```

- [ ] **Step 3: Replace `main.tex` with the stable paper shell**

Use this document structure and retain the existing author until the partner record approves a different author list:

```tex
\documentclass[10pt,twocolumn]{article}

\usepackage[T1]{fontenc}
\usepackage[margin=0.72in,columnsep=0.24in]{geometry}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,backgrounds,fit,positioning}
\usepackage{listings}
\usepackage[numbers,sort&compress]{natbib}
\usepackage[hidelinks]{hyperref}
\usepackage[nameinlink,capitalise]{cleveref}

\definecolor{rsihubblue}{HTML}{2563EB}
\definecolor{rsihubgreen}{HTML}{0F766E}
\definecolor{rsihubgold}{HTML}{B45309}
\definecolor{rsihubgray}{HTML}{F3F4F6}

\lstset{
  basicstyle=\ttfamily\footnotesize,
  breaklines=true,
  columns=fullflexible,
  frame=single,
  rulecolor=\color{black!20},
  showstringspaces=false
}

\title{RSIHub: A Composable Framework for Self-Improving Agents}
\author{Zimu Wang}
\date{}

\begin{document}
\maketitle

\begin{abstract}
RSIHub is a composable framework for building and studying self-improving
agents. It separates a fixed experimental lifecycle from replaceable method
operators, allowing researchers to reproduce, ablate, and combine improvement
strategies while practitioners reuse one execution and evidence substrate. This
report presents the abstraction, architecture, and workflow of RSIHub.
\end{abstract}

\input{sections/01-introduction}
\input{sections/02-composition}
\input{sections/03-design-principles}
\input{sections/04-architecture}
\input{sections/05-usage}
\input{sections/07-related-work}
\input{sections/08-conclusion}

\bibliographystyle{plainnat}
\bibliography{references}
\end{document}
```

Task 3 creates `references.bib`; until then, omit the final two bibliography lines so Task 1 compiles without an empty bibliography warning.

- [ ] **Step 4: Create the section files with stable headings and labels**

Create each section file with only its exact heading and label. For example:

```tex
\section{Introduction}
\label{sec:introduction}
```

Use these heading/label pairs:

```text
Self-Improvement as Composition / sec:composition
Design Principles / sec:principles
RSIHub Architecture / sec:architecture
Using and Extending RSIHub / sec:usage
Related Work / sec:related-work
Conclusion / sec:conclusion
```

- [ ] **Step 5: Create the private readiness register**

Create `notes/report-readiness.md` with the following sections and initial decisions:

```markdown
# RSIHub Report Readiness

## Approved framing

- Working title: RSIHub: A Composable Framework for Self-Improving Agents
- Primary contribution: composable infrastructure for self-improving agents
- Audience: researchers and practitioners with equal emphasis
- Main-body writing budget: six to seven pages
- Experiment role: compact illustrations rather than a benchmark paper

## Decision register

| Decision | State | Owner | Completion condition |
| --- | --- | --- | --- |
| Final author list and affiliations | Open | Zimu Wang and partners | Names, order, affiliations, and contact author are approved |
| Method-fidelity wording | Open | Zimu Wang and partners | Each method row is labeled faithful, adapted, or inspired |
| Outcome evidence | Open | Zimu Wang and partners | One retained result source and exact claim wording are approved |
| Composability evidence | Open | Zimu Wang and partners | Operator swap, ablation, hybrid example, or explicit omission is approved |
| Appendix scope | Open | Zimu Wang and partners | Included appendix material or no-appendix decision is approved |

## Claim evidence

| Claim | Required evidence | Source | State |
| --- | --- | --- | --- |
| Recipes compose reusable operators | Recipe schema, operator library, generated workspace | RSIHub repository | Ready for manuscript verification |
| Evaluation is framework-owned | Interface and architecture source | RSIHub repository | Ready for manuscript verification |
| Different methods share one lifecycle | Source-backed method/operator matrix | Original papers and RSIHub recipes | Requires fidelity review |
| RSIHub improves agent outcomes | Complete result artifact with denominator | Partner-selected artifact | Requires evidence selection |
| Operator replacement enables controlled research | Reproducible swap or ablation record | Partner-selected artifact | Requires evidence selection |

## Candidate evidence

- Terminal-Bench 2 recipe results
- Tau3 Banking recipe results
- Paper-to-poster skill-evolution result
- Focused operator replacement or ablation

## Review log

Record dated partner decisions here. Each entry names the decision, approved wording, evidence path, and reviewer.
```

- [ ] **Step 6: Compile and inspect the shell**

Run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
pdfinfo main.pdf | rg '^(Pages|Page size):'
rg -n 'LaTeX Warning:|Overfull \\hbox|Undefined control sequence' main.log
```

Expected: compilation succeeds; no undefined controls, missing inputs, or overfull boxes. Empty sections are acceptable only in this scaffold commit.

- [ ] **Step 7: Commit the substrate**

```bash
git add .gitignore main.tex sections notes/report-readiness.md
git commit -m "docs: scaffold RSIHub systems report"
```

---

### Task 2: Write the architectural core and publication figure

**Files:**
- Create: `arxiv/figures/architecture.tex`
- Modify: `arxiv/sections/04-architecture.tex`

**Interfaces:**
- Consumes: fixed lifecycle and ownership rules from the approved design and `docs/concepts/design.md`.
- Produces: `fig:architecture` and the canonical prose definitions referenced by Tasks 3–6.

- [ ] **Step 1: Re-verify the architecture sources before drafting**

Read these root-repository sources in full:

```text
docs/superpowers/specs/2026-08-10-rsihub-arxiv-report-design.md
docs/superpowers/specs/2026-08-10-lego-operator-library-design.md
docs/concepts/design.md
ARCHITECTURE.md
library/PROTOCOL.md
```

Write down any vocabulary mismatch in `notes/report-readiness.md` and resolve it before the paper uses a stage name. The manuscript uses `analyze` and `mutate`, not legacy `trace_analyzer` and `meta_agent` terminology.

- [ ] **Step 2: Create the four-band TikZ figure**

Create `figures/architecture.tex` as a `figure*` with four labeled bands: Compose, Run, Trust, and Improve. Use the following node vocabulary and relationships:

```tex
\begin{figure*}[t]
  \centering
  \begin{tikzpicture}[
    font=\scriptsize,
    >=Latex,
    box/.style={draw=black!35, rounded corners=2pt, align=center,
      minimum height=6mm, inner xsep=4pt, fill=white},
    policy/.style={box, draw=rsihubblue!65, fill=rsihubblue!7},
    fixed/.style={box, draw=rsihubgreen!70, fill=rsihubgreen!8,
      line width=0.8pt},
    evidence/.style={box, draw=rsihubgold!65, fill=rsihubgold!8},
    flow/.style={->, draw=black!55, line width=0.6pt}
  ]
    \node[box, text width=18mm] (recipe) {Recipe};
    \node[policy, right=5mm of recipe] (select) {select};
    \node[policy, right=2mm of select] (rollout) {rollout};
    \node[policy, right=2mm of rollout] (analyze) {analyze?};
    \node[policy, right=2mm of analyze] (mutate) {mutate};
    \node[policy, right=2mm of mutate] (validate) {validate?};
    \node[policy, right=2mm of validate] (novelty) {novelty?};
    \node[fixed, right=2mm of novelty] (evaluate) {evaluate};
    \node[policy, right=2mm of evaluate] (gate) {gate};
    \node[policy, right=2mm of gate] (record) {record};
    \node[policy, right=2mm of record] (reflect) {reflect?};

    \draw[flow] (recipe) -- (select);
    \foreach \a/\b in {select/rollout,rollout/analyze,analyze/mutate,
      mutate/validate,validate/novelty,novelty/evaluate,evaluate/gate,
      gate/record,record/reflect}
      \draw[flow] (\a) -- (\b);

    \node[fixed, below=9mm of mutate, text width=30mm] (execution)
      {isolated execution\\clean candidate snapshots};
    \node[fixed, right=5mm of execution, text width=30mm] (surface)
      {declared mutable surface\\protected evaluator};
    \node[evidence, right=5mm of surface, text width=30mm] (lineage)
      {Git lineage\\artifacts and archive};

    \node[box, below=9mm of execution, text width=25mm] (agent)
      {agent generation $n$};
    \node[fixed, right=8mm of agent, text width=25mm] (evaluator)
      {frozen evaluator};
    \node[evidence, right=8mm of evaluator, text width=31mm] (output)
      {generation $n{+}1$\\score and evidence};
    \draw[flow] (agent) -- (evaluator);
    \draw[flow] (evaluator) -- (output);
  \end{tikzpicture}
  \caption{RSIHub separates declarative method composition and replaceable
  policy operators from framework-owned evaluation and evidence. Optional
  stages are marked with question marks.}
  \label{fig:architecture}
\end{figure*}
```

Adjust spacing rather than shrinking text below `\scriptsize`. Keep policy, fixed mechanism, and evidence visually distinct in both color and labels.

- [ ] **Step 3: Write the architecture section around the figure**

Write `sections/04-architecture.tex` in this order:

1. One paragraph defining recipes, operators, framework mechanism, target, and evaluator.
2. `\subsection{Fixed Lifecycle}` explaining required, optional, and framework-owned stages.
3. `\subsection{Operator Boundary}` explaining file contracts and subprocess isolation.
4. `\subsection{Controlled Mutation}` explaining mutable surfaces and clean snapshots.
5. `\subsection{Lineage and Evidence}` explaining Git tags, artifacts, scores, and archive records.
6. One short failure-semantics paragraph: invalid operator output or incomplete evidence cannot promote a generation.

Reference `\cref{fig:architecture}` from the opening paragraph and place
`\input{figures/architecture}` immediately after that paragraph. Keep low-level
module names out of the main body.

- [ ] **Step 4: Compile, render, and inspect the figure pages**

Run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
mkdir -p /tmp/rsihub-paper-pages
pdftoppm -png -r 144 main.pdf /tmp/rsihub-paper-pages/page
rg -n 'Overfull \\hbox|Underfull \\hbox|LaTeX Warning: Reference|Undefined control sequence' main.log
```

Expected: the figure fits across both columns, stage labels remain legible, arrows do not cross labels, and the three ownership categories are clear without relying only on color.

- [ ] **Step 5: Commit the architecture core**

```bash
git add figures/architecture.tex sections/04-architecture.tex
git commit -m "docs: explain RSIHub architecture"
```

---

### Task 3: Add primary citations and the method-composition argument

**Files:**
- Create: `arxiv/references.bib`
- Modify: `arxiv/main.tex`
- Modify: `arxiv/sections/02-composition.tex`
- Modify: `arxiv/notes/report-readiness.md`

**Interfaces:**
- Consumes: target stage vocabulary from Task 2 and recipe configurations under `recipes/*/evolve.yaml`.
- Produces: `tab:method-composition`, verified citation keys, and fidelity labels consumed by the introduction and related work.

- [ ] **Step 1: Retrieve BibTeX from primary sources**

Add verified records with these stable keys and sources:

```text
paszke2019pytorch       arXiv:1912.01703
sheng2025hybridflow     HybridFlow/veRL paper and official veRL repository
lin2026ahe              arXiv:2604.25850
lin2026aevolve          arXiv:2602.00359
agrawal2025gepa         arXiv:2507.19457
zhang2026hyperagents    arXiv:2603.19461
```

Copy author lists, titles, year, venue or archive, identifier, and URL from the original paper page or official repository citation block. Do not copy BibTeX from aggregators.

- [ ] **Step 2: Derive the RSIHub method mapping from repository evidence**

Inspect:

```text
recipes/ahe/evolve.yaml
recipes/aevolve/evolve.yaml
recipes/gepa/evolve.yaml
recipes/hyperagents/evolve.yaml
recipes/hill_climb/evolve.yaml
library/
```

For the target vocabulary, map `trace_analyzer` to `analyze` and `meta_agent` to `mutate`. Use the selected `variant` value as the operator name. Mark stages not selected by a recipe with an em dash. Record one of these exact fidelity labels for each row in `notes/report-readiness.md`: `faithful`, `adapted`, or `inspired`. Use `adapted` unless the implementation has been checked against the original method's required semantics.

- [ ] **Step 3: Write the composition section and table**

Structure `sections/02-composition.tex` as:

1. Shared-problem paragraph: methods repeatedly implement selection, rollout, feedback analysis, mutation, validation, and promotion.
2. Fragmentation paragraph: monolithic implementations frustrate reproduction, ablation, and hybridization.
3. `table*` with rows AHE, A-Evolve, GEPA, HyperAgents, and hill climbing; columns `select`, `rollout`, `analyze`, `mutate`, `validate`, `novelty`, `gate`, and `reflect`.
4. Interpretation paragraph: the table localizes differences without claiming the algorithms are identical.
5. One sentence distinguishing faithful reproduction from RSIHub adaptation, using the readiness labels.

Use `\footnotesize`, `\tabcolsep` adjustment, `booktabs`, and abbreviated operator names only when the caption defines them. Label the table `tab:method-composition` and cite original method papers in the method-name cells or adjacent prose.

- [ ] **Step 4: Enable the bibliography and verify citations**

Restore in `main.tex`:

```tex
\bibliographystyle{plainnat}
\bibliography{references}
```

Run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
rg -n 'Citation.*undefined|There were undefined citations|I couldn.t open database file' main.log
```

Expected: no undefined citations and every bibliography record is cited from the manuscript.

- [ ] **Step 5: Render and inspect the method table**

```bash
pdftoppm -png -r 144 main.pdf /tmp/rsihub-paper-pages/page
rg -n 'Overfull \\hbox' main.log
```

Expected: the table fits across two columns, cells remain readable, and no operator name touches a column boundary.

- [ ] **Step 6: Commit the composition argument**

```bash
git add references.bib main.tex sections/02-composition.tex notes/report-readiness.md
git commit -m "docs: map self-improvement methods to operators"
```

---

### Task 4: Write the introduction and design principles

**Files:**
- Modify: `arxiv/sections/01-introduction.tex`
- Modify: `arxiv/sections/03-design-principles.tex`

**Interfaces:**
- Consumes: architecture definitions from Task 2 and source-backed method framing from Task 3.
- Produces: the paper's problem statement, thesis, contribution list, and principle names referenced by later sections.

- [ ] **Step 1: Write the introduction as five short moves**

Use this paragraph structure:

1. Self-improving agents are increasingly built through evaluator-guided changes to prompts, skills, tools, harness code, and improvement policy.
2. Existing methods repeatedly rebuild the same experiment mechanics inside method-specific systems.
3. State the thesis: RSIHub factorizes a shared lifecycle from replaceable operators so methods can be reproduced, ablated, and combined like Lego pieces.
4. Explain the dual value: researchers edit compositions; practitioners run recipes on one substrate.
5. Present a compact contribution list covering the compositional model, reusable framework, research workbench, and reliable experimental foundation.

Keep the contribution list to four bullets. Do not include benchmark numbers in the introduction until Task 7 approves them.

- [ ] **Step 2: Write the three design principles**

Use exactly these subsection headings:

```tex
\subsection{Fixed Lifecycle, Replaceable Policy}
\subsection{Simple and Explicit Composition}
\subsection{Trustworthy Experiments by Construction}
```

For each principle, give one rationale, one architectural consequence, and one rejected alternative:

- fixed lifecycle rejects a general user-defined workflow DAG;
- explicit composition rejects method logic embedded in recipe files; and
- trustworthy experiments reject candidate-owned evaluation and unbound scores.

Keep this section near one half page by moving implementation detail to `\cref{sec:architecture}`.

- [ ] **Step 3: Verify terminology and claim discipline**

Run from `arxiv/`:

```bash
rg -n 'recursive self-improvement|all methods|guarantee|current implementation|target architecture|trace_analyzer|meta_agent' sections/01-introduction.tex sections/03-design-principles.tex
```

Expected: no `all methods`, guarantee, readiness, or legacy-stage language. Any use of recursive self-improvement is motivational and immediately connected to self-improving agents.

- [ ] **Step 4: Compile and check the writing budget**

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
pdfinfo main.pdf | rg '^Pages:'
rg -n 'Overfull \\hbox|LaTeX Warning: Reference' main.log
```

Expected: introduction occupies no more than one page of the two-column main body and design principles remain close to one half page.

- [ ] **Step 5: Commit the framing**

```bash
git add sections/01-introduction.tex sections/03-design-principles.tex
git commit -m "docs: frame RSIHub composability principles"
```

---

### Task 5: Add the practitioner workflow and researcher extension example

**Files:**
- Modify: `arxiv/sections/05-usage.tex`

**Interfaces:**
- Consumes: target recipe syntax and stable CLI behavior from the RSIHub repository.
- Produces: `lst:recipe`, the four-step practitioner flow, and the one-operator research example.

- [ ] **Step 1: Verify the final recipe and CLI syntax**

Compare the manuscript example against:

```text
docs/guides/recipe-to-experiment.md
docs/guides/custom-recipes.md
recipes/hill_climb/evolve.yaml
docs/superpowers/specs/2026-08-10-lego-operator-library-design.md
```

Use the target `operator:` key and canonical `analyze`/`mutate` stage names. Keep command examples consistent with the final CLI even if target operator vocabulary differs from legacy recipe files.

- [ ] **Step 2: Add the minimal recipe listing**

Use this six-stage example and label it `lst:recipe`:

```yaml
operators:
  select:  {operator: greedy}
  rollout: {operator: harbor}
  analyze: {operator: failure_patterns}
  mutate:  {operator: hyperagents}
  gate:    {operator: hillclimb}
  record:  {operator: jsonl}
```

The accompanying prose explains that target, evaluator, budgets, and mutable surface are also declared by the recipe but omitted from the listing for space.

- [ ] **Step 3: Write the four-step practitioner workflow**

Present exactly four actions:

```bash
uv run --frozen evolve preflight /path/to/experiment --recipe hill_climb --dataset /path/to/tasks
uv run --frozen evolve init /path/to/experiment --recipe hill_climb --dataset /path/to/tasks
/path/to/experiment/evolve run /path/to/experiment --max-generations 5
/path/to/experiment/evolve status /path/to/experiment
```

Explain what each action establishes: readiness, frozen workspace, iterative evolution, and evidence inspection. Do not turn the section into an installation guide.

- [ ] **Step 4: Write the researcher swap example**

Describe a controlled comparison that changes `analyze.operator` from `failure_patterns` to another registered analysis operator while retaining target, evaluator, split, seed, budgets, and other operators. State that the two runs produce separate Git lineages and archive evidence under the same evaluation contract.

Do not report an outcome for this example unless Task 7 approves a matching artifact.

- [ ] **Step 5: Compile and inspect the listing and commands**

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
pdftoppm -png -r 144 main.pdf /tmp/rsihub-paper-pages/page
rg -n 'Overfull \\hbox|Undefined control sequence' main.log
```

Expected: YAML and shell commands wrap without clipping, remain legible, and the complete section stays within approximately one page.

- [ ] **Step 6: Commit the usage section**

```bash
git add sections/05-usage.tex
git commit -m "docs: show RSIHub composition workflow"
```

---

### Task 6: Complete related work, conclusion, and abstract

**Files:**
- Modify: `arxiv/sections/07-related-work.tex`
- Modify: `arxiv/sections/08-conclusion.tex`
- Modify: `arxiv/main.tex`
- Modify: `arxiv/references.bib`

**Interfaces:**
- Consumes: stable thesis, terminology, and citation inventory from Tasks 2–5.
- Produces: a complete non-experimental narrative and an abstract that makes no unsupported quantitative claim.

- [ ] **Step 1: Add only primary related-work sources**

Organize citations into four idea groups:

1. self-improving-agent methods, using AHE, A-Evolve, GEPA, and HyperAgents;
2. evaluator-guided and evolutionary optimization, using original method papers rather than surveys when making method claims;
3. agent evaluation and experiment infrastructure, using official benchmark or framework papers; and
4. composable systems, using PyTorch and HybridFlow/veRL.

Add a BibTeX record only after verifying its title, authors, identifier, and URL against the original publication page.

- [ ] **Step 2: Write related work by contrast, not catalog**

Use one paragraph per idea group. Each paragraph answers:

- what abstraction the prior work provides;
- what RSIHub reuses or learns from it; and
- what RSIHub adds at the cross-method infrastructure level.

Avoid novelty claims based only on the absence of a cited paper. Phrase broad positioning as scope, not priority.

- [ ] **Step 3: Write the conclusion**

Use three short paragraphs:

1. Restate the fragmentation problem and compositional answer.
2. Summarize the shared lifecycle, operator library, and evidence substrate.
3. State the intended role: a common workbench for building, applying, and studying self-improving agents.

Include one compact limitation sentence: the abstraction makes operator boundaries explicit but does not remove the need to validate method fidelity or generalization.

- [ ] **Step 4: Rewrite the abstract from the completed narrative**

The final abstract is 120–170 words and contains, in order:

1. the fragmented-infrastructure problem;
2. RSIHub's fixed-lifecycle/replaceable-operator idea;
3. the researcher and practitioner capabilities;
4. the trustworthy experiment substrate; and
5. one evidence sentence only if Task 7 has already approved a quantitative result.

Do not use citations in the abstract.

- [ ] **Step 5: Compile and verify references**

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
rg -n 'Citation.*undefined|Reference.*undefined|There were undefined|Overfull \\hbox' main.log
pdfinfo main.pdf | rg '^Pages:'
```

Expected: all citations and cross-references resolve; the non-experimental main body remains within the page budget needed to add up to one page of empirical evidence.

- [ ] **Step 6: Commit the complete non-experimental draft**

```bash
git add main.tex references.bib sections/07-related-work.tex sections/08-conclusion.tex
git commit -m "docs: complete RSIHub report narrative"
```

---

### Task 7: Pass the partner evidence gate and write experimental illustrations

**Files:**
- Create: `arxiv/sections/06-experiments.tex`
- Modify: `arxiv/main.tex`
- Modify: `arxiv/notes/report-readiness.md`
- Modify: `arxiv/references.bib` only when an approved benchmark requires a primary citation

**Interfaces:**
- Consumes: partner-approved outcome and composability decisions in `notes/report-readiness.md`, each bound to retained evidence.
- Produces: `sec:experiments`, optional `tab:results`, and the only quantitative claims permitted in the report.

- [ ] **Step 1: Enforce the evidence decision gate**

Read the `Outcome evidence` and `Composability evidence` rows. Continue only when each is either `Approved` with evidence details in the review log or `Omitted by decision`. If either remains `Open`, stop execution after Task 6 and ask the user to complete the partner review. Do not create an empty experiments section or drafting marker in the manuscript.

- [ ] **Step 2: Audit every approved result artifact**

For each approved study, record in the review log:

```text
artifact path or immutable URL
source commit or generation tag
benchmark and split
numerator and denominator
aggregation rule
model and evaluator identity
approved claim sentence
```

Recompute displayed percentages from the numerator and denominator. If only an aggregate percentage exists, label it as reported and do not infer counts.

- [ ] **Step 3: Write the section around research questions**

Use these research questions, dropping any question whose evidence was explicitly omitted:

```text
RQ1: Can representative self-improvement methods be expressed through one lifecycle?
RQ2: Does RSIHub support controlled operator replacement while holding the evaluation contract fixed?
RQ3: Do selected RSIHub recipes produce measurable improvements on agent benchmarks?
```

Answer RQ1 with `\cref{tab:method-composition}` rather than duplicating the table. Use one compact `table*` labeled `tab:results` for approved quantitative results. Put task-level detail, costs, and extended configurations in an appendix only if the partner record approves an appendix.

- [ ] **Step 4: Insert the section in manuscript order**

Add:

```tex
\input{sections/06-experiments}
```

between `05-usage` and `07-related-work` in `main.tex`. Update the abstract with at most one approved evidence sentence.

- [ ] **Step 5: Verify every number and citation**

Run the artifact-specific aggregation command recorded in the readiness review log, then run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
rg -n 'Citation.*undefined|Reference.*undefined|There were undefined|Overfull \\hbox' main.log
pdftoppm -png -r 144 main.pdf /tmp/rsihub-paper-pages/page
```

Expected: every number matches the audited artifact, captions name denominators and splits, and the results asset is legible without exceeding the main-body writing budget.

- [ ] **Step 6: Commit the approved evidence section**

```bash
git add main.tex references.bib sections/06-experiments.tex notes/report-readiness.md
git commit -m "docs: add RSIHub experimental illustrations"
```

---

### Task 8: Perform the full manuscript quality gate

**Files:**
- Modify: any `arxiv/*.tex`, `arxiv/sections/*.tex`, `arxiv/figures/*.tex`, or `arxiv/references.bib` file with a verified defect
- Modify: `arxiv/notes/report-readiness.md`

**Interfaces:**
- Consumes: the complete manuscript and approved readiness record.
- Produces: a submission-ready PDF source tree with resolved references, inspected pages, and no unsupported claims.

- [ ] **Step 1: Check source completeness and prohibited drafting language**

Run:

```bash
rg -n 'TBD|TODO|FIXME|PLACEHOLDER|fill in|current implementation|target architecture|all methods|guarantee improvement' . -g '*.tex' -g '*.bib'
```

Expected: no matches. Review every use of “first,” “novel,” “state of the art,” or “outperform” and retain it only when a cited source or approved artifact directly supports it.

- [ ] **Step 2: Build the complete document from source**

Run:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
rg -n 'Citation.*undefined|Reference.*undefined|There were undefined|Undefined control sequence|Overfull \\hbox' main.log
pdfinfo main.pdf | rg '^(Pages|Page size|File size):'
```

Expected: successful build, no unresolved citations/references, no undefined controls, and no overfull boxes.

- [ ] **Step 3: Render and inspect every page**

Run:

```bash
mkdir -p /tmp/rsihub-paper-final-pages
pdftoppm -png -r 168 main.pdf /tmp/rsihub-paper-final-pages/page
```

Inspect every rendered page for:

- clipped or overlapping text;
- illegible table or figure labels;
- awkward float placement or large unexplained gaps;
- inconsistent section hierarchy;
- broken URLs, citations, and cross-references;
- widows, orphan headings, and unbalanced final columns; and
- main-body length materially above seven pages without an explicit editorial reason.

Fix discovered defects and repeat Steps 2–3 from a fresh build.

- [ ] **Step 4: Perform the claim-to-evidence audit**

For every quantitative or method-fidelity claim in the paper, locate its row or review-log entry in `notes/report-readiness.md`. Change any unsupported claim to a precise qualitative statement or remove it. Mark the corresponding readiness row `Verified for draft` with the source commit and manuscript location.

- [ ] **Step 5: Review the exact Git scope**

```bash
git status --short
git diff --check
git diff --stat
```

Expected: only intended source, bibliography, figure, and readiness files are modified; no PDF, PNG, log, or auxiliary build file is tracked.

- [ ] **Step 6: Commit final manuscript QA fixes**

```bash
git add main.tex references.bib sections figures notes/report-readiness.md .gitignore
git commit -m "docs: finalize RSIHub arXiv report draft"
```

- [ ] **Step 7: Hand the rendered draft to the authors**

Report the commit, page count, included experiments, unresolved partner decisions, and exact PDF build command. Ask the authors to review title, author order, claims, and figures before any arXiv submission or Overleaf push.
