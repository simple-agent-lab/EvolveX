# RSIHub Project Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RSIHub/rsihub the sole Git-tracked project identity while preserving every established `evolve` technical interface.

**Architecture:** Treat the rename as three independently testable identity boundaries: generated-workspace branding, distribution/public-entry branding, and an exhaustive tracked-source sweep. Existing behavior tests change first and must fail against the former identity; implementation then updates only brand-derived strings and paths. A tracked-file guard prevents the retired identity from returning without rejecting the stable evolution vocabulary.

**Tech Stack:** Python 3.12, pytest, Typer, Hatchling, uv, MkDocs Material, GitHub Actions, Markdown, SVG.

## Global Constraints

- Display name: `RSIHub`.
- Python distribution name: `rsihub`.
- GitHub repository: `simple-agent-lab/RSIHub`.
- Documentation site: `https://simple-agent-lab.github.io/RSIHub/`.
- Branded asset stem and generated legal suffix: `rsihub` and `.rsihub`.
- Preserve `evolve`, `src/evolve/`, `python -m evolve`, `evolve.yaml`, `.evolve/`, `.evolve-components.json`, `EVOLVE_*`, and `evolve-agent`.
- Preserve generic evolution language and external method names such as A-Evolve.
- Edit Git-tracked content only; preserve `.codex/`, `arxiv/`, local archives, caches, Git history, the checkout directory, and configured remotes.
- Do not add former-brand compatibility aliases or transitional copy.
- Do not run slow or live integration checks; this change does not affect experiment execution.

## File Structure

- `tests/test_m0_init.py`: generated-workspace and initialization brand contract.
- `src/evolve/cli.py`, `src/evolve/workspace.py`: CLI copy and generated legal/Git identity values.
- `scaffolds/workspace/{README.md,AGENTS.md}`: generated-workspace documentation.
- `tests/test_public_repository.py`: canonical public identity, branded assets, and tracked-file stale-identity guard.
- `tests/test_release_artifact.py`: built distribution name, README payload, and project URL contract.
- `pyproject.toml`, `uv.lock`, `NOTICE`: distribution and legal identity sources.
- `README.md`, `mkdocs.yml`, `docs/**`: public copy, repository links, navigation, accessible asset metadata, and historical tracked records.
- `.github/**`, root policy files, recipes, seeds, skills, evals, library, and `src/evolve/**`: remaining project-owned display strings and derived identifiers.
- `docs/rsihub-mark.svg`: renamed existing project mark; no visual redesign.

---

### Task 1: Generated Workspace Identity

**Files:**
- Modify: `tests/test_m0_init.py`
- Modify: `src/evolve/cli.py`
- Modify: `src/evolve/workspace.py`
- Modify: `scaffolds/workspace/README.md`
- Modify: `scaffolds/workspace/AGENTS.md`
- Modify: `.github/workflows/test.yml`

**Interfaces:**
- Consumes: the existing `evolve init` command and `init_fixture_workspace(...)` test helper.
- Produces: initialization output containing `RSIHub`; generated `LICENSE.rsihub` and `NOTICE.rsihub`; unchanged `.evolve/`, `evolve.yaml`, and `evolve` launcher paths.

- [ ] **Step 1: Change the initialization expectations to the canonical brand**

Update the existing assertions in `tests/test_m0_init.py` to express the new contract:

```python
assert f"Initialized RSIHub workspace at {tmp_path / '.evolve-workspace'}" in result.output
```

In `test_init_scaffolds_hill_climb_workspace`, replace the generated legal-file entries and assertions with:

```python
"LICENSE.rsihub",
"NOTICE.rsihub",
```

```python
assert "Apache License" in (workspace / "LICENSE.rsihub").read_text()
assert "GEPA" in (workspace / "NOTICE.rsihub").read_text()
```

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_m0_init.py::test_init_defaults_to_home_workspace \
  tests/test_m0_init.py::test_init_scaffolds_hill_climb_workspace
```

Expected: both nodes fail because the CLI still prints the former display name and generated workspaces still contain the former legal suffix.

- [ ] **Step 3: Update the generated-workspace implementation**

Apply these exact identity mappings without changing technical paths:

| Location | New value |
| --- | --- |
| `src/evolve/cli.py` Typer help, init docstring, success output | `RSIHub` |
| `src/evolve/workspace.py` legal copy keys | `LICENSE.rsihub`, `NOTICE.rsihub` |
| `src/evolve/workspace.py` generated Git user/email | `RSIHub Mechanism`, `rsihub@example.invalid` |
| `scaffolds/workspace/AGENTS.md` heading | `RSIHub Workspace` |
| `scaffolds/workspace/README.md` display copy | `RSIHub` |
| `scaffolds/workspace/README.md` legal filenames | `LICENSE.rsihub`, `NOTICE.rsihub` |
| `.github/workflows/test.yml` wheel smoke files | `LICENSE.rsihub`, `NOTICE.rsihub` |

Keep `.evolve`, `evolve.yaml`, `.evolve-components.json`, and the `evolve` command unchanged.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_m0_init.py::test_init_defaults_to_home_workspace \
  tests/test_m0_init.py::test_init_scaffolds_hill_climb_workspace
```

Expected: 2 passed.

- [ ] **Step 5: Commit the generated-workspace boundary**

```bash
git add tests/test_m0_init.py src/evolve/cli.py src/evolve/workspace.py \
  scaffolds/workspace/README.md scaffolds/workspace/AGENTS.md .github/workflows/test.yml
git commit -m "refactor: rename generated workspaces to RSIHub"
```

---

### Task 2: Distribution and Public Entry Identity

**Files:**
- Modify: `tests/test_public_repository.py`
- Modify: `tests/test_coherence.py`
- Modify: `tests/test_release_artifact.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `NOTICE`
- Modify: `README.md`
- Modify: `mkdocs.yml`
- Move: the pre-rename branded-mark asset to `docs/rsihub-mark.svg`

**Interfaces:**
- Consumes: Hatchling metadata from `pyproject.toml`, README long description, MkDocs theme assets, and the existing release-artifact test harness.
- Produces: distribution `rsihub`; canonical GitHub/docs URLs; `RSIHub` legal and README identity; branded mark at `docs/rsihub-mark.svg`; unchanged `evolve` console script and `evolve` wheel package.

- [ ] **Step 1: Change public and release expectations first**

In `test_license_metadata_and_notice_are_consistent`, add the canonical package and URL assertions and change the notice assertion:

```python
assert project["name"] == "rsihub"
assert project["urls"] == {
    "Homepage": "https://github.com/simple-agent-lab/RSIHub",
    "Documentation": "https://simple-agent-lab.github.io/RSIHub/",
    "Repository": "https://github.com/simple-agent-lab/RSIHub",
    "Issues": "https://github.com/simple-agent-lab/RSIHub/issues",
}
assert (ROOT / "NOTICE").read_text().startswith("RSIHub\n")
```

Change the public visual tests to use `docs/rsihub-mark.svg` in both the asset tuple and the expected state-count mapping.

In `test_release_wheel_has_one_resource_owner_and_complete_metadata`, use:

```python
assert metadata["Name"] == "rsihub"
assert "RSIHub" in metadata.get_payload()
project_urls = metadata.get_all("Project-URL") or []
assert "Repository, https://github.com/simple-agent-lab/RSIHub" in project_urls
assert "Issues, https://github.com/simple-agent-lab/RSIHub/issues" in project_urls
```

- [ ] **Step 2: Run the public identity tests and verify they fail**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_public_repository.py::test_readme_visual_assets_have_accessible_svg_metadata \
  tests/test_public_repository.py::test_selected_and_explored_graphics_have_three_to_one_contrast \
  tests/test_public_repository.py::test_license_metadata_and_notice_are_consistent
```

Expected: failures report the missing `docs/rsihub-mark.svg`, former package name/URLs, and former notice heading.

- [ ] **Step 3: Update the canonical package, legal, README, and documentation entry points**

Make these exact changes:

```toml
[project]
name = "rsihub"

[project.urls]
Homepage = "https://github.com/simple-agent-lab/RSIHub"
Documentation = "https://simple-agent-lab.github.io/RSIHub/"
Repository = "https://github.com/simple-agent-lab/RSIHub"
Issues = "https://github.com/simple-agent-lab/RSIHub/issues"

[project.scripts]
evolve = "evolve.cli:main"
```

Change the root package entry in `uv.lock` to `name = "rsihub"`. Change the
first two `NOTICE` lines to:

```text
RSIHub
Copyright 2026 Simple Agent Lab and the RSIHub authors
```

Rename the existing SVG file to `docs/rsihub-mark.svg` without changing its
geometry. Replace its README and MkDocs references. Update every README display
name, heading anchor, badge alt label, and project-owned URL to RSIHub while
leaving example `evolve` commands untouched. Set these MkDocs values:

```yaml
site_name: RSIHub
site_url: https://simple-agent-lab.github.io/RSIHub/
repo_url: https://github.com/simple-agent-lab/RSIHub
repo_name: simple-agent-lab/RSIHub
```

Keep `theme.logo` and `theme.favicon` pointed at `rsihub-mark.svg`.

- [ ] **Step 4: Run the public identity tests and verify they pass**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_public_repository.py::test_readme_visual_assets_have_accessible_svg_metadata \
  tests/test_public_repository.py::test_selected_and_explored_graphics_have_three_to_one_contrast \
  tests/test_public_repository.py::test_license_metadata_and_notice_are_consistent
```

Expected: 3 passed.

- [ ] **Step 5: Build and test the renamed release artifacts**

Run:

```bash
RSIHUB_RELEASE_DIR="$(mktemp -d /tmp/rsihub-release.XXXXXX)"
uv build --out-dir "$RSIHUB_RELEASE_DIR"
EVOLVE_RELEASE_DIST="$RSIHUB_RELEASE_DIR" uv run --frozen pytest -q -n 0 \
  tests/test_release_artifact.py -p no:cacheprovider
```

Expected: build exits 0 and both release-artifact tests pass. The distribution
filename contains `rsihub`, while archived Python resources remain under
`evolve/`.

- [ ] **Step 6: Commit the distribution/public-entry boundary**

```bash
git add tests/test_public_repository.py tests/test_release_artifact.py pyproject.toml \
  uv.lock NOTICE README.md mkdocs.yml docs/rsihub-mark.svg
git commit -m "refactor: rename project identity to RSIHub"
```

---

### Task 3: Exhaustive Tracked-Source Migration and Regression Guard

**Files:**
- Modify: `tests/test_public_repository.py`
- Modify: `.github/ISSUE_TEMPLATE/{bug_report.yml,config.yml,feature_request.yml}`
- Modify: `.github/workflows/test.yml`
- Modify: `.gitignore`
- Modify: `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `QUICKSTART.md`, `SECURITY.md`, `SUPPORT.md`
- Modify: `docs/assets/{architecture.svg,benchmark-results.svg}`
- Modify: `docs/concepts/design.md`
- Modify: `docs/development/{coding-style.md,documentation.md}`
- Modify: `docs/getting-started.md`, `docs/guides/operations.md`, `docs/index.md`
- Modify: `docs/reference/{environment-variables.md,operators.md,terminology.md}`
- Move: the pre-rename historical arXiv-report plan filename to `docs/superpowers/plans/2026-08-10-rsihub-arxiv-report.md`
- Move: the pre-rename historical logo-exploration plan filename to `docs/superpowers/plans/2026-08-10-rsihub-logo-exploration.md`
- Move: the pre-rename historical arXiv-report design filename to `docs/superpowers/specs/2026-08-10-rsihub-arxiv-report-design.md`
- Move: the pre-rename historical logo-exploration design filename to `docs/superpowers/specs/2026-08-10-rsihub-logo-exploration-design.md`
- Modify: all tracked `docs/superpowers/{plans,specs}/*.md` files reported by the guard
- Modify: `evals/README.md`
- Modify: `evals/skills/make-paper-poster/{prepare_dataset.py,recipe/evaluator/prepare_poster_runtime.py}`
- Modify: `library/PROTOCOL.md`, `library/meta_agent/runners/harbor.py`
- Modify: `recipes/aevolve/README.md`, `recipes/ahe/README.md`, `seeds/codex/README.md`
- Modify: `skills/evolve-agent/agents/openai.yaml`
- Modify: project-brand strings under `src/evolve/**` reported by the guard
- Modify: `tests/conftest.py`, `tests/fixtures/seeds/dummy/agent.py`

**Interfaces:**
- Consumes: Git's tracked-file inventory and all project-owned textual identity surfaces.
- Produces: no retired project identity in any tracked path or decodable tracked file; project-owned derived values use `rsihub`; stable `evolve` technical names continue to be accepted.

- [ ] **Step 1: Add a tracked-file stale-identity guard**

Add `subprocess` to the imports in `tests/test_public_repository.py`, then add:

```python
def test_tracked_files_use_only_current_project_identity() -> None:
    retired = ("evolve" + "x", "simple-" + "evolve-agent")
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]
    stale: list[str] = []
    for relative in paths:
        folded_path = relative.as_posix().casefold()
        for identity in retired:
            if identity in folded_path:
                stale.append(f"path:{relative}")
        try:
            text = (ROOT / relative).read_text()
        except UnicodeDecodeError:
            continue
        folded_text = text.casefold()
        for identity in retired:
            if identity in folded_text:
                stale.append(f"text:{relative}")
    assert sorted(set(stale)) == []
```

This assembles the denylist from fragments so the test itself does not retain a
forbidden identity. It intentionally uses `git ls-files`, excluding `.codex/`,
`arxiv/`, caches, local archives that are untracked, and Git history.

- [ ] **Step 2: Run the guard and verify that it fails for the remaining tracked surfaces**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_public_repository.py::test_tracked_files_use_only_current_project_identity
```

Expected: failure lists tracked paths that still carry the retired display,
distribution, or repository-slug identity.

- [ ] **Step 3: Migrate every guard-reported text occurrence and branded path**

For every guard-reported project-owned value, apply these exact semantic
mappings:

| Former context | Canonical replacement |
| --- | --- |
| Display-name references | `RSIHub` |
| Distribution-derived lowercase identifiers | `rsihub` |
| Repository URLs and slugs | `simple-agent-lab/RSIHub` |
| Documentation URLs | `https://simple-agent-lab.github.io/RSIHub/` |
| CI Git identity | `rsihub-ci`, `rsihub-ci@example.invalid` |
| Meta-agent Git identity | `RSIHub Meta-Agent`, `meta-agent@rsihub.invalid` |
| Experiment-smoke Git identity | `RSIHub Experiment Smoke`, `smoke@rsihub.invalid` |
| HTTP provider display label | `RSIHub HTTP Responses` |
| Paper-poster HTTP user-agent | `rsihub-paper-poster/1` |
| Test uv cache | `/tmp/rsihub-test-uv` |
| Skill display name | `RSIHub Agent` |

Rename the four historical files listed in this task and update their content,
along with old-brand content in all other tracked historical specs/plans. Update
SVG `<title>`, `<desc>`, and accessible copy while preserving SVG geometry.

Do not replace the standalone verb/package/config/interface forms listed in
Global Constraints. In particular, retain `src/evolve`, `evolve init`,
`evolve.yaml`, `.evolve`, `EVOLVE_*`, `evolve-agent`, and A-Evolve.

Resolve the approved repository-policy conflict in `tests/test_coherence.py`:
rename `test_local_superpowers_artifacts_are_not_tracked` to
`test_local_superpowers_runtime_artifacts_are_not_tracked`, make its
`git ls-files` command inspect only `.superpowers`, and keep the assertion that
runtime scratch must be untracked. Deliberately committed design and plan
records under `docs/superpowers` are now allowed and remain covered by the
tracked-source identity guard.

- [ ] **Step 4: Re-run the guard until it passes**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_public_repository.py::test_tracked_files_use_only_current_project_identity
```

Expected: 1 passed.

- [ ] **Step 5: Verify public links, assets, generated workspaces, and release metadata together**

Run:

```bash
uv run --frozen pytest -q -n 0 \
  tests/test_public_repository.py \
  tests/test_m0_init.py::test_init_defaults_to_home_workspace \
  tests/test_m0_init.py::test_init_scaffolds_hill_climb_workspace
```

Expected: all selected tests pass.

Then run a direct tracked-path and tracked-text audit using the same fragmented
denylist logic:

```bash
uv run --frozen python -c 'import pathlib, subprocess; root=pathlib.Path.cwd(); retired=("evolve"+"x", "simple-"+"evolve-agent"); raw=subprocess.run(["git","ls-files","-z"],check=True,capture_output=True).stdout; paths=[pathlib.Path(p.decode()) for p in raw.split(b"\0") if p]; hits=[]; [(hits.append(str(p)) if any(x in p.as_posix().casefold() or x in ((root/p).read_text(errors="ignore").casefold()) for x in retired) else None) for p in paths]; print("\n".join(hits)); raise SystemExit(bool(hits))'
```

Expected: no output and exit 0.

- [ ] **Step 6: Commit the exhaustive migration and regression guard**

Review `git status --short` and ensure `.codex/` and `arxiv/` remain untracked
and unstaged. Then stage only tracked changes and the four explicit renamed
historical files:

```bash
git add -u
git add -f \
  docs/superpowers/plans/2026-08-10-rsihub-arxiv-report.md \
  docs/superpowers/plans/2026-08-10-rsihub-logo-exploration.md \
  docs/superpowers/specs/2026-08-10-rsihub-arxiv-report-design.md \
  docs/superpowers/specs/2026-08-10-rsihub-logo-exploration-design.md
git commit -m "refactor: complete RSIHub branding migration"
```

---

### Task 4: Repository-Wide Verification

**Files:**
- Verify only: all files changed by Tasks 1–3

**Interfaces:**
- Consumes: the completed branding migration.
- Produces: fresh evidence that documentation, default tests, lint, formatting, types, and tracked identity constraints all pass without slow/live integration.

- [ ] **Step 1: Validate lock consistency and strict documentation rendering**

Run:

```bash
uv lock --check
uv run --frozen mkdocs build --strict
```

Expected: both commands exit 0; the docs build reports no missing renamed asset,
broken anchor, or strict-mode warning.

- [ ] **Step 2: Run the default repository suite**

Run:

```bash
uv run --frozen pytest -q
```

Expected: exit 0 with zero failures; slow tests remain skipped by default.

- [ ] **Step 3: Run standard static checks**

Run:

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen ty check
```

Expected: all three commands exit 0 with no lint, formatting, or type errors.

- [ ] **Step 4: Recheck scope and final diff**

Run:

```bash
git status --short
git diff HEAD~3 --check
git diff HEAD~3 --stat
```

Confirm that the diff implements every acceptance criterion, contains no
changes to stable technical interfaces, and does not include `.codex/`,
`arxiv/`, local archives, caches, generated site output, or unrelated files.

If verification requires a corrective edit, write or select the smallest
focused failing test, make the correction, rerun that focused test, rerun every
command in Tasks 4.1–4.3, and commit with:

```bash
git add -u
git commit -m "fix: correct RSIHub rename verification"
```
