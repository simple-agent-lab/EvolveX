import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _fetch_module():
    path = ROOT / "scripts" / "fetch_repository_stats.py"
    spec = importlib.util.spec_from_file_location("fetch_repository_stats", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_stats_fallback_files_are_wired_into_mkdocs() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
    assert config["theme"]["custom_dir"] == "docs/overrides"
    assert "javascripts/repository-stats.js" in config["extra_javascript"]

    source = (ROOT / "docs" / "overrides" / "partials" / "source.html").read_text()
    assert "data-evolvex-repository-stats" in source
    assert 'data-md-component="source"' not in source

    javascript = (ROOT / "docs" / "javascripts" / "repository-stats.js").read_text()
    assert "https://api.github.com/repos/" in javascript
    assert "evolvexRepositoryStats" in javascript
    assert "md-source__fact--${kind}" in javascript


def test_docs_workflow_refreshes_repository_stats_twice_daily() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "docs.yml").read_text())
    triggers = workflow[True]
    assert triggers["schedule"] == [{"cron": "17 0,12 * * *"}]
    assert "scripts/fetch_repository_stats.py" in triggers["push"]["paths"]
    assert "scripts/fetch_repository_stats.py" in triggers["pull_request"]["paths"]

    steps = workflow["jobs"]["build"]["steps"]
    refresh = next(step for step in steps if step.get("name") == "Refresh repository statistics")
    assert refresh["run"] == "python scripts/fetch_repository_stats.py"
    assert refresh["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert steps.index(refresh) < next(
        index for index, step in enumerate(steps) if step.get("name") == "Build documentation"
    )


def test_repository_stats_json_has_valid_counts() -> None:
    payload = json.loads((ROOT / "docs" / "assets" / "repository-stats.json").read_text())
    assert payload["schema_version"] == 1
    assert payload["repository"] == "simple-agent-lab/EvolveX"
    assert isinstance(payload["stars"], int) and payload["stars"] >= 0
    assert isinstance(payload["forks"], int) and payload["forks"] >= 0


def test_repository_stats_writer_is_atomic(tmp_path: Path) -> None:
    module = _fetch_module()
    output = tmp_path / "nested" / "repository-stats.json"
    stats = {
        "schema_version": 1,
        "repository": "example/project",
        "stars": 12,
        "forks": 3,
        "fetched_at": "2026-08-10T00:00:00Z",
    }
    module.write_repository_stats(output, stats)
    assert json.loads(output.read_text()) == stats
    assert not output.with_suffix(".json.tmp").exists()
    assert module.has_usable_fallback(output)
