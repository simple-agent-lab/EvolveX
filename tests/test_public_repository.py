import re
import shlex
import tomllib
from pathlib import Path

import yaml

from evolve import __version__

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)#]+)")


def test_license_metadata_and_notice_are_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == __version__
    assert project["license"] == "Apache-2.0"
    assert "Apache License" in (ROOT / "LICENSE").read_text()
    assert (ROOT / "NOTICE").read_text().startswith("EvolveX\n")


def test_required_public_repository_files_exist() -> None:
    required = (
        "LICENSE",
        "NOTICE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "SUPPORT.md",
        "RELEASING.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
    )
    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_public_markdown_relative_links_resolve() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "recipes" / "README.md",
        ROOT / "SECURITY.md",
        ROOT / "CODE_OF_CONDUCT.md",
        ROOT / "SUPPORT.md",
        ROOT / "RELEASING.md",
    ]
    broken = []
    for source in files:
        if not source.is_file():
            broken.append(f"missing:{source.relative_to(ROOT)}")
            continue
        for target in RELATIVE_LINK.findall(source.read_text()):
            path = target.strip("<>")
            if not (source.parent / path).resolve().exists():
                broken.append(f"{source.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_lint_ci_checks_lock_lint_format_and_types() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "lint.yml").read_text())
    commands = [step.get("run") for step in workflow["jobs"]["lint"]["steps"] if step.get("run")]
    assert commands == [
        "uv lock --check",
        "uv sync --dev --locked",
        "uv run --frozen ruff check --output-format=github .",
        "uv run --frozen ruff format --check .",
        "uv run --frozen ty check",
    ]


def test_ci_warms_clean_python_312_cache_before_offline_workspace_probes() -> None:
    assert (ROOT / ".python-version").read_text() == "3.12\n"
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())
    job = workflow["jobs"]["test"]
    assert "runner.temp" not in yaml.safe_dump(job.get("env", {}))

    steps = job["steps"]
    setup_uv = next(step for step in steps if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"))
    assert setup_uv["with"]["python-version"] == "3.12"
    assert setup_uv["with"]["enable-cache"] is False

    indexes = {step.get("id"): index for index, step in enumerate(steps)}
    assert (
        indexes["configure-uv-cache"]
        < indexes["install-python-312"]
        < indexes["reset-uv-cache"]
        < indexes["check-root-lock"]
        < indexes["warm-root-runtime"]
        < indexes["offline-workspace-probe"]
    )
    by_id = {step.get("id"): step for step in steps}
    assert by_id["configure-uv-cache"]["run"] == (
        'echo "UV_CACHE_DIR=$RUNNER_TEMP/evolve-clean-uv-cache" >> "$GITHUB_ENV"'
    )
    assert shlex.split(by_id["install-python-312"]["run"]) == [
        "uv",
        "python",
        "install",
        "3.12",
    ]
    assert shlex.split(by_id["reset-uv-cache"]["run"]) == ["rm", "-rf", "$UV_CACHE_DIR"]
    assert shlex.split(by_id["warm-root-runtime"]["run"]) == [
        "uv",
        "sync",
        "--dev",
        "--locked",
        "--python",
        "3.12",
    ]
    assert shlex.split(by_id["warm-scaffold-runtime"]["run"]) == [
        "uv",
        "sync",
        "--project",
        "scaffolds/workspace",
        "--frozen",
        "--no-install-project",
        "--python",
        "3.12",
    ]
    assert by_id["warm-scaffold-runtime"]["env"] == {
        "UV_PROJECT_ENVIRONMENT": "${{ runner.temp }}/evolve-scaffold-venv"
    }
    assert shlex.split(by_id["check-scaffold-lock"]["run"]) == [
        "uv",
        "lock",
        "--project",
        "scaffolds/workspace",
        "--check",
        "--offline",
    ]
    assert by_id["check-scaffold-lock"]["env"]["UV_OFFLINE"] == "1"
    assert shlex.split(by_id["offline-workspace-probe"]["run"]) == [
        "uv",
        "run",
        "--offline",
        "pytest",
        "-q",
        "tests/test_recipe_composition.py",
    ]
    assert by_id["offline-workspace-probe"]["env"]["UV_OFFLINE"] == "1"


def test_ci_self_driving_smoke_requires_real_candidate_progress() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    smoke = next(step for step in steps if step.get("name", "").startswith("deterministic mechanism smoke"))

    assert "tests/fixtures/smoke_agent.py" in smoke["env"]["EVOLVE_AGENT_COMMAND"]
    command = smoke["run"]
    assert 'EVOLVE_HOME="$RUNNER_TEMP/ci-smoke-home" uv run --frozen evolve init' in command
    assert "--recipe-path tests/fixtures/recipes/hill_climb-smoke" in command
    assert "--seed tests/fixtures/seeds/dummy" in command
    assert 'tests/assert_self_driving_smoke.py "$RUNNER_TEMP/ci-smoke" 3' in command
    assert "--recipe hill_climb" not in command


def test_root_lock_warms_every_generated_workspace_runtime_version() -> None:
    def registry_versions(path: Path) -> dict[str, str]:
        lock = tomllib.loads(path.read_text())
        return {
            package["name"]: package["version"]
            for package in lock["package"]
            if "version" in package and package.get("source", {}).get("registry") == "https://pypi.org/simple"
        }

    root = registry_versions(ROOT / "uv.lock")
    generated = registry_versions(ROOT / "scaffolds" / "workspace" / "uv.lock")
    assert {name: (root.get(name), version) for name, version in generated.items() if root.get(name) != version} == {}
