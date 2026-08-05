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
    assert 'WORKSPACE=$RUN_ROOT/$(basename "$RUN_ROOT")' in text
    assert "pr29-runtime-profiles-phase3.bundle" in text
    assert "git bundle list-heads" in text
    assert "load_tau3_runtime_env.sh" in text
    assert 'source "$TAU3_ENV_LOADER" "$ENV_ROOT"' in text
    assert 'SHARED_UV_CACHE=${EVOLVE_UV_CACHE_DIR:-}' in text
    assert 'PRIVATE_UV_CACHE=$RUN_ROOT/uv-cache' in text
    assert '--reflink=auto --no-preserve=ownership' in text
    assert 'export EVOLVE_UV_CACHE_DIR=$PRIVATE_UV_CACHE' in text
    assert "--recipe ahe" in text
    assert '"$WORKSPACE/.env"' in text
    assert 'chmod 600 "$WORKSPACE/.env"' in text
    assert 'chmod -R go+rX "$WORKSPACE/target"' in text
    assert "umask 022" in text
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
    assert "TAU3_RUNTIME_API_KEY=%s" in text
    assert "NO_PROXY=%s" in text
    assert " jq" not in text
    assert "rm -rf" not in text
