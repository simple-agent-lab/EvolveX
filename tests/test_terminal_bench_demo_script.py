from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_terminal_bench_demo.sh"


def test_public_terminal_bench_demo_is_short_and_portable() -> None:
    text = SCRIPT.read_text()

    assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
    assert "terminal-bench@2.0" in text
    assert "--tasks" in text
    for command in ("evolve init", "preflight", 'evolve" run', "status", "verify"):
        assert command in text
    for private in ("DevBox", "/data00", "proxy.env", "REPO_BUNDLE", "python -"):
        assert private not in text
    assert len(text.splitlines()) <= 30
