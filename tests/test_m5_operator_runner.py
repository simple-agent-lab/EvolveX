import subprocess
import textwrap
from pathlib import Path

from evolve.driver import _run_operator_guarded
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


def test_harbor_meta_agent_outer_timeout_budgets_every_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkout = tmp_path / "checkout"
    _write_operator(checkout, "meta_agent", "pass\n")
    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        observed["env_timeout"] = kwargs["env"]["EVOLVE_OPERATOR_TIMEOUT_S"]
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr("evolve.operators.subprocess.run", fake_run)

    result = run_operator(
        name="meta_agent",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent=None,
        run_dir=tmp_path / "r",
        config_block={"runner": "harbor", "max_retries": 1, "timeout_s": 3600},
        timeout_s=3600,
    )

    assert result.returncode == 0
    assert observed == {
        "timeout": 7215.0,
        "env_timeout": "7215.0",
    }


def test_guarded_operator_restores_archive_in_child_checkout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs" / "gen-1"
    workspace.mkdir()
    checkout.mkdir()
    live_archive = '{"genid":"0","score":0.5}\n'
    (workspace / "archive.jsonl").write_text(live_archive)
    (checkout / "archive.jsonl").write_text("")
    _write_operator(checkout, "probe", "pass\n")

    result = _run_operator_guarded(
        name="probe",
        checkout=checkout,
        workspace=workspace,
        exp_id="experiment",
        genid="1",
        parent="0",
        run_dir=run_dir,
        config_block={},
        timeout_s=30,
    )

    assert result.returncode == 0
    assert (workspace / "archive.jsonl").read_text() == live_archive
    assert (checkout / "archive.jsonl").read_text() == ""
