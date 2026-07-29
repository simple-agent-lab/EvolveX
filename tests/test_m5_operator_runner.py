import textwrap
import time
from pathlib import Path

from evolve.operators import OperatorResult, run_operator


def _write_operator(root: Path, name: str, body: str) -> None:
    path = root / "operators" / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body))


def test_run_operator_success_env_and_config(tmp_path):
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    _write_operator(
        checkout,
        "gate",
        """
        import json, os, sys
        args = sys.argv
        config = json.loads(args[args.index("--config") + 1])
        out = {
            "variant": config["variant"],
            "genid": os.environ["EVOLVE_GENID"],
            "parent": os.environ["EVOLVE_PARENT"],
            "workspace": os.environ["EVOLVE_WORKSPACE"],
            "checkout": os.environ.get("EVOLVE_CHECKOUT"),
        }
        run_dir = os.environ["EVOLVE_RUN_DIR"]
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "probe.json"), "w") as f:
            json.dump(out, f)
        """,
    )
    result = run_operator(
        name="gate",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent="0",
        run_dir=run_dir,
        config_block={"variant": "hillclimb"},
        timeout_s=30,
    )
    assert isinstance(result, OperatorResult)
    assert result.returncode == 0
    import json

    probe = json.loads((run_dir / "probe.json").read_text())
    assert probe == {
        "variant": "hillclimb",
        "genid": "1",
        "parent": "0",
        "workspace": str(tmp_path.resolve()),
        "checkout": str(checkout.resolve()),
    }


def test_run_operator_nonzero_and_timeout(tmp_path):
    checkout = tmp_path / "checkout"
    _write_operator(checkout, "meta_agent", "raise SystemExit(7)\n")
    failed = run_operator(
        name="meta_agent",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent=None,
        run_dir=tmp_path / "r",
        config_block={},
        timeout_s=30,
    )
    assert failed.returncode == 7

    _write_operator(checkout, "rollout", "import time\ntime.sleep(60)\n")
    timed_out = run_operator(
        name="rollout",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent=None,
        run_dir=tmp_path / "r2",
        config_block={},
        timeout_s=0.1,
    )
    assert timed_out.returncode == -1
    assert "timeout" in timed_out.stderr.lower()


def test_run_operator_timeout_kills_descendant_in_new_session(tmp_path):
    checkout = tmp_path / "checkout"
    pid_file = tmp_path / "detached.pid"
    _write_operator(
        checkout,
        "gate",
        f"""
        import pathlib, signal, subprocess, sys
        child = subprocess.Popen(
            [sys.executable, "-c", "import signal; signal.pause()"],
            start_new_session=True,
        )
        pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))
        signal.pause()
        """,
    )

    result = run_operator(
        name="gate",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent="0",
        run_dir=tmp_path / "r3",
        config_block={},
        timeout_s=0.2,
    )

    assert result.returncode == -1
    child_pid = int(pid_file.read_text())
    for _ in range(100):
        try:
            Path(f"/proc/{child_pid}/status").read_text()
        except OSError:
            break
        time.sleep(0.01)
    else:
        raise AssertionError(f"detached child still running: {child_pid}")
