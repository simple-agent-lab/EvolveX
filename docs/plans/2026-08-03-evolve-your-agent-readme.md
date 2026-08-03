# Evolve Your Agent README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the public README so a reader can first evolve the built-in Codex or MiniSWE target and then adapt the workflow to an installable Harbor-compatible agent.

**Architecture:** Keep the README as the single user-facing entry point and organize it by reader journey rather than framework internals. Add a small repository test that protects the four-role mental model and the three supported entry paths from disappearing in later copy edits; retain the existing relative-link test for documentation integrity.

**Tech Stack:** Markdown, Python 3.12, pytest, Typer CLI, YAML recipes, Harbor 0.18, `uv`

## Global Constraints

- Do not change runtime behavior, recipe semantics, evaluator boundaries, or CLI interfaces.
- The first runnable path uses the built-in Codex target; the second uses the recipe-pinned MiniSWE target.
- Define target, evaluated Harbor agent, evaluator, and meta-agent as distinct roles before using recipe internals.
- State that a custom Harbor adapter must execute candidate state from the current checkout's `target/`.
- Keep the introductory mutable surface at `target/**`; operator self-evolution remains an advanced option.
- Do not imply that a placeholder digest or an unexecuted live Docker/model command was verified.
- Preserve links to security, support, license, design, architecture, recipe, meta-agent, trace-analysis, local-environment, and contributor documentation.

---

### Task 1: Protect the user journey with a README contract test

**Files:**
- Modify: `tests/test_public_repository.py`

**Interfaces:**
- Consumes: repository-root `README.md` as UTF-8 Markdown text.
- Produces: `test_readme_explains_how_to_evolve_builtin_and_custom_agents()`, a content-level regression test for the role definitions and entry-point commands.

- [ ] **Step 1: Add the failing README contract test**

Add this test after `test_required_public_repository_files_exist`:

```python
def test_readme_explains_how_to_evolve_builtin_and_custom_agents() -> None:
    readme = (ROOT / "README.md").read_text()
    required = (
        "## How the pieces fit together",
        "| Target |",
        "| Evaluated Harbor agent |",
        "| Evaluator |",
        "| Meta-agent |",
        "## Choose your starting point",
        "--recipe aevolve",
        "--seed builtin-codex",
        "--recipe hill_climb",
        "## Bring your own Harbor-compatible agent",
        "--recipe-path",
        "surface.include",
        "target/**",
        "package.module:ClassName",
    )
    assert [text for text in required if text not in readme] == []
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
uv run pytest -q tests/test_public_repository.py::test_readme_explains_how_to_evolve_builtin_and_custom_agents
```

Expected: FAIL with a non-empty list beginning with `## How the pieces fit together` because the current README does not contain the new journey.

- [ ] **Step 3: Commit the failing contract test**

```bash
git add tests/test_public_repository.py
git commit -m "test: define evolve-your-agent README contract"
```

### Task 2: Rewrite the README around built-in and custom targets

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: current CLI flags from `src/evolve/cli.py`; recipe defaults from `recipes/aevolve/evolve.yaml` and `recipes/hill_climb/evolve.yaml`; adapter/dependency contract from `META_AGENTS.md` and `src/evolve/workspace.py`.
- Produces: the public onboarding document satisfying the strings and semantics enforced by Task 1.

- [ ] **Step 1: Replace the overview-first body with the reader journey**

Keep the title, badges, architecture image, project information links, and license. Replace the navigation and body between them with these sections in order:

```text
What Evolve does
How the pieces fit together
Choose your starting point
Install
Evolve the built-in Codex target
Evolve the MiniSWE harness
Bring your own Harbor-compatible agent
What one generation does
Inspect the result
Recipes
Trust boundaries
Current limitations
Documentation
Project information
```

The four-role table must use these meanings:

```markdown
| Part | Role | Example |
| --- | --- | --- |
| Target | Candidate-owned files that may change between generations. | `target/prompt.md`, `target/skills/**`, or MiniSWE source under `target/`. |
| Evaluated Harbor agent | Runs one candidate on one Harbor task. It must load behavior from that candidate's `target/`. | `target.agent:HarborAgent` or `evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent`. |
| Evaluator | Frozen tasks and verifiers that produce the trusted score. | A local Harbor task directory plus its verifier. |
| Meta-agent | Reads training evidence and edits the next candidate. | Codex or MiniSWE running through the configured meta-agent operator. |
```

State immediately after the table that the evaluated Harbor agent and the meta-agent are different roles even when both happen to use Codex.

- [ ] **Step 2: Add a three-row starting-point decision table**

Document these exact choices:

```markdown
| Goal | Start with | Evolves |
| --- | --- | --- |
| Improve a Codex prompt and skills | `aevolve` with `builtin-codex` | `target/prompt.md` and `target/skills/**` |
| Improve the MiniSWE harness/source | `hill_climb` | the pinned MiniSWE repository under `target/**` |
| Improve your own Harbor-compatible agent | a copied recipe passed with `--recipe-path` | the seed repository vendored under `target/**` |
```

Explain that readers should complete one built-in path before adapting the custom path.

- [ ] **Step 3: Add the complete Codex path**

Use this command flow, with prose that says it is a real Harbor run requiring Docker or another configured Harbor environment, model credentials, a host `codex login`, and an immutable evaluator image digest:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable-evaluator-image-digest>"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"

uv run evolve init /tmp/evolve-codex \
  --recipe aevolve \
  --seed builtin-codex \
  --dataset "$HARBOR_TASKS"

cd /tmp/evolve-codex
./evolve run . --max-generations 1 --verbose
./evolve status .
./evolve report .
```

Explain that the candidate initially contains `target/agent.py`, `target/prompt.md`, `target/codex.toml`, and `target/skills/`; credentials stay outside `target/`.

- [ ] **Step 4: Add the complete MiniSWE path**

Use this command flow and state that `hill_climb` pins the MiniSWE Git revision, generates its lock, uses the framework-owned `MiniSweSourceAgent` adapter, and evolves `target/**`:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:<immutable-evaluator-image-digest>"
export HARBOR_TASKS="/absolute/path/to/harbor/tasks"

uv run evolve init /tmp/evolve-miniswe \
  --recipe hill_climb \
  --dataset "$HARBOR_TASKS"

cd /tmp/evolve-miniswe
./evolve run . --max-generations 1 --verbose
./evolve status .
```

Warn that the Harbor tasks must be compatible with the chosen agent and evaluator; a successful workspace initialization does not prove task compatibility.

- [ ] **Step 5: Add the custom Harbor-agent contract and adaptation procedure**

Document this sequence:

1. Copy `recipes/aevolve/` when evolving prompt/skills or `recipes/hill_climb/` when evolving a source harness.
2. Set `target.seed` to an absolute local directory or Git URL.
3. Set `surface.include` to `target/**`.
4. Set `evaluator.agent` to an importable `package.module:ClassName` Harbor `BaseAgent` implementation.
5. Ensure the adapter loads the candidate from the current checkout's `target/` rather than a fixed host installation.
6. Initialize with `uv run evolve init /tmp/evolve-custom --recipe-path /absolute/path/to/my-recipe --dataset "$HARBOR_TASKS"`.
7. If the adapter is an external package, run `uv add /absolute/path/to/my-harbor-adapter-package` inside the generated workspace and commit both `pyproject.toml` and `uv.lock` before running.
8. Launch with `./evolve run . --max-generations 1 --verbose`.

Include this minimal configuration excerpt and clearly label it as the fields to change in a copied, complete recipe—not a standalone complete recipe:

```yaml
target:
  seed: /absolute/path/to/my-agent-repository

surface:
  include:
    - target/**
  exclude: []

evaluator:
  engine: harbor
  dataset: /absolute/path/to/harbor/tasks
  agent: package.module:ClassName
```

Explain that `operators.meta_agent` configures the editor, while `evaluator.agent` configures the candidate executor.

- [ ] **Step 6: Preserve concise operational and safety reference**

Retain or add:

- the deterministic `EVAL_STUB=1` baseline smoke, explicitly labeled as mechanism-only and not a mutation-quality result;
- `archive.jsonl`, `gen/*`, `runs/gen-N/`, `./evolve status .`, `./evolve report .`, and `./evolve verify .` inspection pointers;
- the five-recipe comparison table;
- the three trust-boundary guarantees;
- limitations covering prototype status, real-run Docker/Linux preference, local dataset materialization, credentials, and the absence of published benchmark results;
- all public documentation and project-information links present in the current README.

- [ ] **Step 7: Run the README contract and relative-link tests**

Run:

```bash
uv run pytest -q \
  tests/test_public_repository.py::test_readme_explains_how_to_evolve_builtin_and_custom_agents \
  tests/test_public_repository.py::test_public_markdown_relative_links_resolve
```

Expected: `2 passed`.

- [ ] **Step 8: Commit the README rewrite**

```bash
git add README.md
git commit -m "docs: explain how to evolve an agent"
```

### Task 3: Verify commands, repository checks, and final scope

**Files:**
- Verify: `README.md`
- Verify: `tests/test_public_repository.py`

**Interfaces:**
- Consumes: final documentation diff and the installed project CLI.
- Produces: evidence that documented flags parse, the deterministic scaffold works, public links resolve, and only intended documentation/test files changed.

- [ ] **Step 1: Verify documented CLI flags**

Run:

```bash
uv run evolve init --help
uv run evolve run --help
```

Expected: init help lists `--recipe`, `--recipe-path`, `--seed`, and `--dataset`; run help lists `--max-generations` and `--verbose`.

- [ ] **Step 2: Run the deterministic mechanism smoke**

Run in a fresh temporary path:

```bash
export EVOLVE_RUNTIME_DIGEST="sha256:local-smoke-runtime"
export EVOLVE_HOME="/tmp/evolve-readme-home"
uv run evolve init /tmp/evolve-readme-smoke --recipe hill_climb
EVAL_STUB=1 /tmp/evolve-readme-smoke/evolve run /tmp/evolve-readme-smoke --max-generations 0
/tmp/evolve-readme-smoke/evolve status /tmp/evolve-readme-smoke
/tmp/evolve-readme-smoke/evolve verify /tmp/evolve-readme-smoke
```

Expected: initialization succeeds, generation 0 is evaluated by the stub, status reports the baseline population, and verify reports integrity `ok`. If the MiniSWE seed cannot be cloned because network access is unavailable, record that limitation and rely on the existing workspace-init tests rather than claiming the smoke ran.

- [ ] **Step 3: Run the complete public-repository test file**

```bash
uv run pytest -q tests/test_public_repository.py
```

Expected: all tests pass.

- [ ] **Step 4: Run formatting and diff checks**

```bash
uvx ruff check tests/test_public_repository.py
git diff --check origin/main...HEAD
git status --short
```

Expected: Ruff and diff checks pass; status is clean; the branch contains only the design, plan, README, and README contract test commits.

- [ ] **Step 5: Review final diff for preserved public information**

```bash
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- README.md tests/test_public_repository.py
```

Confirm from the displayed diff that security, support, license, limitations,
trust boundaries, and deeper documentation links remain present and that no
runtime or recipe file changed.

- [ ] **Step 6: Commit any verification-only copy corrections**

If verification exposed a wording or link correction, edit only `README.md`,
rerun Steps 3–5, then commit:

```bash
git add README.md
git commit -m "docs: polish agent evolution quickstart"
```

If no correction was needed, do not create an empty commit.
