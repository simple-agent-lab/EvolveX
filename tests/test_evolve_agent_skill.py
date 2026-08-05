import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "evolve-agent"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
REFERENCE_LINK = re.compile(r"\]\((references/[^)]+)\)")


def _metadata(path: Path) -> dict[str, object]:
    match = FRONTMATTER.match(path.read_text())
    assert match is not None
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict)
    return metadata


def test_evolve_skill_has_valid_discovery_metadata() -> None:
    metadata = _metadata(SKILL / "SKILL.md")

    assert metadata.keys() == {"name", "description"}
    assert metadata["name"] == "evolve-agent"
    description = str(metadata["description"])
    assert "prompts, skills, and agent harnesses" in description
    assert "operate an evolution workspace" in description

    interface = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text())["interface"]
    assert 25 <= len(interface["short_description"]) <= 64
    assert "$evolve-agent" in interface["default_prompt"]


def test_manifest_exposes_one_unified_skill() -> None:
    manifest = json.loads((ROOT / "skills" / "manifest.json").read_text())

    assert [item["name"] for item in manifest["skills"]] == ["evolve-agent"]
    assert manifest["skills"][0]["role"] == "outer-and-workspace"
    assert not (ROOT / "skills" / "evolve-workspace" / "SKILL.md").exists()


def test_evolve_agent_progressive_references_resolve() -> None:
    body = (SKILL / "SKILL.md").read_text()
    links = REFERENCE_LINK.findall(body)
    assert links == [
        "references/workspace-contract.md",
        "references/hill-climb.md",
        "references/a-evolve.md",
        "references/gepa.md",
        "references/ahe.md",
        "references/hyperagents.md",
        "references/scientific-foundations.md",
    ]
    assert all((SKILL / link).is_file() for link in links)


def test_top_level_skill_is_backend_neutral_and_operator_first() -> None:
    body = (SKILL / "SKILL.md").read_text().lower()
    forbidden = ("harbor", "docker", "recipes/", "src/evolve/", "evolve_runtime_digest")

    assert [term for term in forbidden if term in body] == []
    assert "./evolve operator list . --json" in body
    assert "./evolve operator run . <stage>" in body
    assert body.index("./evolve operator list . --json") < body.index("operators/<stage>.py")
    assert body.index("operators/<stage>.py") < body.index("library/<stage>/")
    assert "do not read implementation source merely to invoke" in body
    assert not (SKILL / "scripts").exists()


def test_method_cards_route_to_shipped_capabilities() -> None:
    expected = {
        "hill-climb.md": ("operator list . --json", "library/select/", "library/gate/"),
        "a-evolve.md": (
            "operator list . --json",
            "library/trace_analyzer/trajectory_only.py",
            "library/meta_agent/aevolve.py",
        ),
        "gepa.md": (
            "operator list . --json",
            "library/select/pareto.py",
            "library/trace_analyzer/gepa.py",
            "library/validate/minibatch_improvement.py",
        ),
        "ahe.md": (
            "operator list . --json",
            "operators/trace_analyzer.py",
            "library/trace_analyzer/ahe.py",
        ),
        "hyperagents.md": (
            "operator list . --json",
            "library/meta_agent/hyperagents.py",
            "library/validate/hyperagents.py",
        ),
    }
    for filename, terms in expected.items():
        body = (SKILL / "references" / filename).read_text()
        assert "## Use the shipped capabilities" in body
        assert all(term in body for term in terms)

    concrete_paths = {
        term for terms in expected.values() for term in terms if term.startswith("library/") and term.endswith(".py")
    }
    assert all((ROOT / path).is_file() for path in concrete_paths)


def test_evolve_skill_uses_checkable_completion_criteria() -> None:
    outer = (SKILL / "SKILL.md").read_text()
    contract = (SKILL / "references" / "workspace-contract.md").read_text()

    assert outer.count("**Completion check:**") >= 5
    assert "evidence chain" in outer.lower()
    assert "## Completion contract" in contract


def test_workspace_contract_is_shared_across_methods() -> None:
    body = (SKILL / "references" / "workspace-contract.md").read_text()
    for path in (
        "target/",
        "evaluator/",
        "operators/",
        "library/",
        "runs/",
        "artifacts/",
        "skills/evolve-agent/",
        "evolve.yaml",
        "archive.jsonl",
        "best_ever.json",
    ):
        assert path in body
    assert "do not require new top-level layouts" in body


def test_workspace_contract_exposes_both_real_control_paths() -> None:
    body = (SKILL / "references" / "workspace-contract.md").read_text()

    assert "./evolve run . --max-generations 1" in body
    commands = (
        "./evolve operator run . select",
        "./evolve fork .",
        "./evolve operator run . rollout",
        "./evolve surface-check",
        "./evolve commit .",
        "./evolve eval .",
        "./evolve finalize .",
        "./evolve verify .",
    )
    positions = [
        body.rindex(command) if command == "./evolve verify ." else body.index(command) for command in commands
    ]
    assert positions == sorted(positions)
    assert 'parent_id="<selected numeric id>"' in body
    assert "`finalize` alone applies gate and record" in body


def test_workspace_contract_preserves_user_owned_external_worktrees() -> None:
    outer = (SKILL / "SKILL.md").read_text()
    contract = (SKILL / "references" / "workspace-contract.md").read_text()

    assert "never remove or modify them without explicit authorization" in outer
    assert "never remove, commit, or modify it merely to unblock the" in contract
    assert "the driver remains blocked" in contract


def test_wheel_includes_skill_resources() -> None:
    build = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
    included = build["force-include"]
    assert included["skills"] == "evolve/skills"
