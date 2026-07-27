import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)#]+)")


def test_license_metadata_and_notice_are_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["license"] == "Apache-2.0"
    assert "Apache License" in (ROOT / "LICENSE").read_text()
    assert (ROOT / "NOTICE").read_text().startswith("Evolve Framework\n")


def test_required_public_repository_files_exist() -> None:
    required = (
        "LICENSE",
        "NOTICE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "SUPPORT.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/pull_request_template.md",
    )
    assert [path for path in required if not (ROOT / path).is_file()] == []


def _issue_form(name: str) -> dict[str, object]:
    value = yaml.safe_load(
        (ROOT / ".github" / "ISSUE_TEMPLATE" / name).read_text()
    )
    assert isinstance(value, dict)
    return value


def test_issue_forms_require_the_information_maintainers_need() -> None:
    bug = _issue_form("bug_report.yml")
    feature = _issue_form("feature_request.yml")
    bug_ids = [entry["id"] for entry in bug["body"] if "id" in entry]
    feature_ids = [entry["id"] for entry in feature["body"] if "id" in entry]
    assert bug_ids == [
        "summary",
        "version",
        "environment",
        "recipe",
        "reproduction",
        "expected",
        "actual",
        "logs",
    ]
    assert feature_ids == [
        "problem",
        "proposal",
        "component",
        "alternatives",
        "scope",
    ]
    for form in (bug, feature):
        required = {
            entry["id"]
            for entry in form["body"]
            if entry.get("validations", {}).get("required") is True
        }
        assert required == set(
            entry["id"] for entry in form["body"] if entry["id"] != "logs"
        )


def test_issue_template_config_routes_security_reports_privately() -> None:
    config = _issue_form("config.yml")
    assert config == {
        "blank_issues_enabled": False,
        "contact_links": [
            {
                "name": "Security report",
                "url": "https://github.com/simple-agent-lab/simple-evolve-agent/security/advisories/new",
                "about": "Report vulnerabilities privately.",
            }
        ],
    }


def test_public_markdown_relative_links_resolve() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "recipes" / "README.md",
        ROOT / "SECURITY.md",
        ROOT / "CODE_OF_CONDUCT.md",
        ROOT / "SUPPORT.md",
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
