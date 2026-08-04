import textwrap
import time
from pathlib import Path

import pytest

from evolve import driver as driver_module
from evolve import runtime as runtime_module
from evolve.archive import archive_path, eval_receipt_path, mirror_path
from evolve.driver import _run_operator_guarded
from evolve.operators import OperatorResult, _operator_deadline_s, run_operator


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


@pytest.mark.parametrize(
    "agent",
    [
        "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent",
        "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent",
    ],
)
def test_miniswe_source_harbor_meta_agent_outer_timeout_budgets_every_retry(
    agent: str,
) -> None:
    assert (
        _operator_deadline_s(
            "meta_agent",
            {
                "runner": "harbor",
                "agent": agent,
                "max_retries": 1,
                "timeout_s": 3600,
            },
            3600,
        )
        == 14640.0
    )


def test_codex_harbor_meta_agent_keeps_whole_process_timeout() -> None:
    assert (
        _operator_deadline_s(
            "meta_agent",
            {
                "runner": "harbor",
                "agent": "codex",
                "max_retries": 1,
                "timeout_s": 3600,
            },
            3600,
        )
        == 3600
    )


def test_guarded_operator_restores_archive_in_child_checkout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    checkout = tmp_path / "checkout"
    run_dir = workspace / "runs" / "gen-1"
    workspace.mkdir()
    checkout.mkdir()
    live_archive = '{"genid":"0","score":0.5}\n'
    live_receipt = "trusted-receipt\n"
    (workspace / "archive.jsonl").write_text(live_archive)
    eval_receipt_path(archive_path(workspace)).write_text(live_receipt)
    (checkout / "archive.jsonl").write_text("")
    eval_receipt_path(archive_path(checkout)).write_text("checkout-original\n")
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
    assert eval_receipt_path(archive_path(workspace)).read_text() == live_receipt
    assert (checkout / "archive.jsonl").read_text() == ""
    assert eval_receipt_path(archive_path(checkout)).read_text() == "checkout-original\n"


def test_guarded_operator_restores_archive_and_receipts_when_runner_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    local = archive_path(workspace)
    mirror = mirror_path("experiment", workspace)
    originals = {
        local: ['{"genid":"0"}'],
        eval_receipt_path(local): ["local-receipt"],
        mirror: ['{"genid":"0"}'],
        eval_receipt_path(mirror): ["mirror-receipt"],
    }
    for path, lines in originals.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    def crashing_runner(**_kwargs):
        for path in originals:
            path.write_text("corrupted\n")
        raise KeyboardInterrupt

    monkeypatch.setattr(driver_module, "run_operator", crashing_runner)
    with pytest.raises(KeyboardInterrupt):
        _run_operator_guarded(
            name="probe",
            checkout=workspace,
            workspace=workspace,
            exp_id="experiment",
            genid="1",
            parent="0",
            run_dir=workspace / "runs" / "gen-1",
            config_block={},
            timeout_s=30,
        )

    for path, lines in originals.items():
        assert path.read_text().splitlines() == lines


def test_run_operator_timeout_kills_descendant_in_new_session(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    pid_file = tmp_path / "detached.pid"
    monkeypatch.setattr(runtime_module, "_proc_children", lambda: None)
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
