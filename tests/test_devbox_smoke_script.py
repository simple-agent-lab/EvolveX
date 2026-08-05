import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "devbox_pr29_ahe_smoke_3x3.sh"


def test_devbox_ahe_smoke_script_is_safe_and_self_verifying() -> None:
    text = SCRIPT.read_text()

    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert syntax.returncode == 0, syntax.stderr
    assert "TASKS=3" in text
    assert "GENERATIONS=3" in text
    assert "pr29-runtime-profiles-phase3.bundle" in text
    assert "git bundle list-heads" in text
    assert "--recipe ahe" in text
    assert '"$WORKSPACE/.env"' in text
    assert "preflight" in text
    assert "--smoke" in text
    assert "--max-generations" in text
    assert 'record.get("expected_trials") == tasks' in text
    assert 'record.get("contract_certified") is True' in text
    assert "import json" in text
    assert "import tomllib" in text
    assert 'uv --directory "$REPO" run python - "$DATASET"' in text
    assert 'task["environment"]["docker_image"]' in text
    assert "EVOLVE_RUNTIME_DIGEST=%s" in text
    assert " jq" not in text
    assert "rm -rf" not in text
