from pathlib import Path

from evolve.config import scaffold_root, seed_root

ROOT = Path(__file__).resolve().parents[1]


def test_source_resources_have_one_owner() -> None:
    assert (scaffold_root() / "workspace" / "pyproject.toml").is_file()
    assert (scaffold_root() / "evaluators" / "harbor" / "engine.sh").is_file()
    assert (seed_root() / "codex" / "agent.py").is_file()
    assert not (ROOT / "templates").exists()


def test_obsolete_miniswe_template_is_absent() -> None:
    assert not (ROOT / "templates" / "target" / "harbor" / "miniswe_source_agent.py").exists()
