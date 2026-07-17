from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_contains_only_supported_recipes() -> None:
    recipe_names = {
        path.name for path in (ROOT / "recipes").iterdir() if path.is_dir() and not path.name.startswith(".")
    }

    assert recipe_names == {
        "ahe",
        "hill_climb",
        "hill_climb-smoke",
        "hyperagents",
        "hyperagents-smoke",
    }
