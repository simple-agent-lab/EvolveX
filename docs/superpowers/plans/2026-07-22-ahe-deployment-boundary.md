# AHE Deployment Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent AHE evolution instructions from being copied into the deployed MiniSWE benchmark-agent prompt, then validate the correction before launching full experiments.

**Architecture:** Make one recipe-local prompt-contract change in `library/meta_agent/ahe.py`. Prove it with the existing prompt-builder unit test, then run local verification and a clean DevBoxS AHE smoke before starting the unchanged full AHE and HyperAgents recipes.

**Tech Stack:** Python 3.12+, pytest, Ruff, Harbor, Docker, Terminal-Bench 2.0.

## Global Constraints

- Keep the implementation to one prompt paragraph and one focused test change.
- Do not change framework code, validation, gate, selection, model, budgets, task splits, evaluator behavior, or editable surface.
- Do not add a patch-content scanner.
- Preserve AHE's ability to edit legitimate target runtime prompts.
- Use four tasks and four workers for the acceptance smoke.

---

### Task 1: Clarify the AHE deployment boundary

**Files:**
- Modify: `tests/test_ahe_meta_agent.py`
- Modify: `library/meta_agent/ahe.py`

**Interfaces:**
- Consumes: `build_prompt(checkout: Path, observation: str, ctx: OperatorContext) -> str`.
- Produces: an AHE meta-agent prompt that distinguishes evolution-only context from candidate runtime context.

- [ ] **Step 1: Extend the prompt-contract test**

Add these required fragments to `test_ahe_prompt_uses_official_decisions_and_required_manifest`:

```python
        "deployed benchmark-solving harness",
        "not available inside benchmark episodes",
        "Do not copy this evolution workflow",
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest -q tests/test_ahe_meta_agent.py::test_ahe_prompt_uses_official_decisions_and_required_manifest
```

Expected: FAIL because the deployment-boundary wording is absent.

- [ ] **Step 3: Add the minimal recipe prompt paragraph**

Insert this paragraph into `AHE_PROMPT` after the generation workflow:

```text
Files under `target/` become the deployed benchmark-solving harness. Evolution
artifacts and instructions in this prompt are not available inside benchmark
episodes. If you edit a target runtime prompt, include only instructions usable
by the benchmark-solving agent. Do not copy this evolution workflow, evidence
paths, KEEP/REVISE/ROLLBACK decisions, or manifest requirements into target files.
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest -q tests/test_ahe_meta_agent.py
```

Expected: all AHE meta-agent tests pass.

- [ ] **Step 5: Commit the prompt boundary**

```bash
git add library/meta_agent/ahe.py tests/test_ahe_meta_agent.py
git commit -m "fix: separate AHE evolution and runtime prompts"
```

### Task 2: Verify locally and on the four-task smoke

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: the committed recipe prompt boundary and existing DevBoxS runtime configuration.
- Produces: local test evidence and one clean AHE smoke workspace with complete lifecycle artifacts.

- [ ] **Step 1: Run full local verification**

```bash
uv run pytest -q
uv run ruff check .
git diff --check
```

Expected: all tests pass, Ruff reports no errors, and `git diff --check` is silent.

- [ ] **Step 2: Confirm old full experiment process state**

Inspect process IDs and experiment paths without printing credentials or full process environments. Do not stop a process unless it is positively identified as an obsolete full AHE or HyperAgents run and the user authorizes stopping it.

- [ ] **Step 3: Initialize and launch a clean AHE smoke**

Use the existing four-task Terminal-Bench dataset, four workers, two training tasks, one gate task, one sealed task, `k=2`, and the already-authorized OpenAI and managed-uv runtime configuration.

- [ ] **Step 4: Inspect the smoke**

Verify:

- every driver stage exits zero;
- archive integrity is `ok`;
- rollout and analyzer summaries contain real task observations;
- the manifest and changed paths are present;
- any changed target runtime prompt has no references to debugger reports, archive records, evolution decisions, evidence paths, or manifest-writing workflow; and
- record and sealed-anchor artifacts complete.

- [ ] **Step 5: Stop if acceptance fails**

If prompt leakage or another implementation failure appears, do not launch full experiments. Preserve artifacts and return to root-cause analysis.

### Task 3: Launch full experiments after acceptance

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: accepted AHE smoke evidence and the unchanged full recipe configurations.
- Produces: live full AHE and HyperAgents experiment workspaces and recorded process IDs.

- [ ] **Step 1: Resolve old-run ownership**

If obsolete full runs remain live, report their process IDs and paths. Stop them only with explicit user authorization; otherwise choose distinct new workspaces and account for resource contention.

- [ ] **Step 2: Launch full AHE and HyperAgents runs**

Reuse the existing OpenAI configuration without displaying or persisting secret values. Use the recipes' configured task splits, budgets, concurrency, selection, gate, and evaluator behavior unchanged.

- [ ] **Step 3: Verify startup health**

Record each workspace, driver PID, deployed commit, configured task counts, and initial stage. Confirm both drivers remain alive past preflight and produce their first evaluation or rollout artifacts.
