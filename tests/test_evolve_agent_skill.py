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

    assert metadata == {
        "name": "evolve-agent",
        "description": (
            "Design, initialize, or operate an evolution workspace for agents, prompts, skills, and agent "
            "harnesses. Use when asked to turn requirements into an RSIHub recipe, choose or author reusable "
            "operators, deploy a frozen workspace, run generations, inspect lineage, recover state, or report an "
            "evidence-backed champion."
        ),
    }

    interface = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text())["interface"]
    assert interface == {
        "display_name": "RSIHub Agent",
        "short_description": "Design and run evidence-backed agent evolution",
        "default_prompt": (
            "Use $evolve-agent to design or operate this evolution experiment through informed, evidence-backed "
            "decisions."
        ),
    }


def test_manifest_exposes_one_unified_skill() -> None:
    manifest = json.loads((ROOT / "skills" / "manifest.json").read_text())

    assert [item["name"] for item in manifest["skills"]] == ["evolve-agent"]
    assert manifest["skills"][0]["role"] == "outer-and-workspace"
    assert manifest["skills"][0]["summary"] == "Design and operate evidence-driven evolution experiments."
    assert not (ROOT / "skills" / "evolve-workspace" / "SKILL.md").exists()


def test_repository_platform_adapters_delegate_to_one_canonical_skill() -> None:
    adapters = (
        ROOT / ".agents" / "skills" / "evolve-agent",
        ROOT / ".claude" / "skills" / "evolve-agent",
    )
    wrapper_texts: list[str] = []
    wrapper_metadata: list[dict[str, object]] = []
    canonical_metadata = _metadata(SKILL / "SKILL.md")

    for adapter in adapters:
        assert adapter.is_dir() and not adapter.is_symlink(), adapter
        assert [path.name for path in adapter.iterdir()] == ["SKILL.md"]
        wrapper = adapter / "SKILL.md"
        assert wrapper.is_file() and not wrapper.is_symlink()

        text = wrapper.read_text()
        wrapper_texts.append(text)
        wrapper_metadata.append(_metadata(wrapper))
        assert len(text.encode()) < 900
        assert "[canonical skill](../../../skills/evolve-agent/SKILL.md)" in text
        assert "../../../skills/evolve-agent/" in text
        assert (adapter / "../../../skills/evolve-agent/SKILL.md").resolve(strict=True) == (SKILL / "SKILL.md").resolve(
            strict=True
        )
        assert (adapter / "../../../skills/evolve-agent").resolve(strict=True) == SKILL.resolve(strict=True)
        assert len(text) < len((SKILL / "SKILL.md").read_text()) // 10

    assert wrapper_texts[0] == wrapper_texts[1]
    assert wrapper_metadata[0] == wrapper_metadata[1] == canonical_metadata

    assert not (ROOT / ".codex" / "skills" / "evolve-agent").exists()


def test_evolve_agent_progressive_references_resolve() -> None:
    body = (SKILL / "SKILL.md").read_text()
    links = REFERENCE_LINK.findall(body)
    expected_links = {
        "references/decision-protocol.md",
        "references/experiment-design.md",
        "references/recipe-authoring.md",
        "references/operator-authoring.md",
        "references/deployment.md",
        "references/workspace-contract.md",
        "references/hill-climb.md",
        "references/a-evolve.md",
        "references/gepa.md",
        "references/ahe.md",
        "references/hyperagents.md",
        "references/scientific-foundations.md",
    }
    assert set(links) == expected_links
    assert all((SKILL / link).is_file() for link in links)
    authoring_links = [
        "references/decision-protocol.md",
        "references/experiment-design.md",
        "references/operator-authoring.md",
        "references/recipe-authoring.md",
        "references/deployment.md",
    ]
    positions = [body.index(f"]({link})") for link in authoring_links]
    assert positions == sorted(positions)
    assert not (SKILL / "scripts").exists()


def test_wheel_includes_skill_resources() -> None:
    build = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
    included = build["force-include"]
    assert included["skills"] == "evolve/skills"
