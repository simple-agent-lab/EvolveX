import subprocess
import textwrap
import time
from pathlib import Path

import pytest

import evolve.runtime.process as runtime_module
from evolve import driver as driver_module
from evolve.archive import archive_path, eval_receipt_path, mirror_path
from evolve.config import operator_runtime_config
from evolve.driver import _operator_config_block, _run_operator_guarded
from evolve.operators import OperatorResult, _operator_deadline_s, run_operator


def _ps_process_tree_available() -> bool:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


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
            "opaque": config["opaque"],
            "genid": os.environ["EVOLVE_GENID"],
            "parent": os.environ["EVOLVE_PARENT"],
            "workspace": os.environ["EVOLVE_WORKSPACE"],
            "checkout": os.environ.get("EVOLVE_CHECKOUT"),
            "stage_timeout": os.environ["EVOLVE_STAGE_TIMEOUT_S"],
            "operator_deadline": os.environ["EVOLVE_OPERATOR_TIMEOUT_S"],
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
        config_block={"opaque": {"value": True}},
        timeout_s=30,
    )
    assert isinstance(result, OperatorResult)
    assert result.returncode == 0
    import json

    probe = json.loads((run_dir / "probe.json").read_text())
    assert probe == {
        "opaque": {"value": True},
        "genid": "1",
        "parent": "0",
        "workspace": str(tmp_path.resolve()),
        "checkout": str(checkout.resolve()),
        "stage_timeout": "30",
        "operator_deadline": "30",
    }


def test_operator_runtime_config_returns_only_nested_opaque_mapping() -> None:
    operators = {
        "mutate": {
            "operator": "hyperagents",
            "timeout_s": 17,
            "config": {"runner": "local", "seed": 4},
        }
    }

    assert operator_runtime_config(operators, "mutate") == {"runner": "local", "seed": 4}


def test_driver_extracts_only_nested_operator_runtime_config() -> None:
    operators = {
        "gate": {
            "operator": "hillclimb",
            "timeout_s": 12,
            "config": {"strict": True},
        }
    }

    assert _operator_config_block(operators, "gate") == {"strict": True}


def test_sdk_context_uses_framework_timeout_and_fixed_fan_out(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    (tmp_path / "evolve.yaml").write_text("execution_runtime: {backend: local}\n")
    (checkout / ".evolve-protocol-version").parent.mkdir(parents=True, exist_ok=True)
    (checkout / ".evolve-protocol-version").write_text("1\n")
    _write_operator(
        checkout,
        "select",
        """
        import json
        from evolve.frozen import sdk
        from evolve.frozen.interfaces import SelectOperator, SelectResult

        class Probe(SelectOperator):
            def pick(self, archive, ctx):
                ctx.run_dir.mkdir(parents=True, exist_ok=True)
                (ctx.run_dir / "context.json").write_text(json.dumps({
                    "timeout_s": ctx.timeout_s,
                    "fan_out": ctx.fan_out,
                    "config": ctx.config,
                }))
                return SelectResult(["0"])

        if __name__ == "__main__":
            sdk.main(Probe)
        """,
    )

    result = run_operator(
        name="select",
        checkout=checkout,
        workspace=tmp_path,
        genid="1",
        parent=None,
        run_dir=run_dir,
        config_block={"seed": 4, "fan_out": 9, "timeout_s": 999},
        timeout_s=30,
    )

    assert result.returncode == 0, result.stderr
    assert __import__("json").loads((run_dir / "context.json").read_text()) == {
        "timeout_s": 30.0,
        "fan_out": 1,
        "config": {"seed": 4, "fan_out": 9, "timeout_s": 999},
    }


def test_run_operator_nonzero_and_timeout(tmp_path):
    checkout = tmp_path / "checkout"
    _write_operator(checkout, "mutate", "raise SystemExit(7)\n")
    failed = run_operator(
        name="mutate",
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
        "evolve.integrations.harbor.miniswe_task_file:InstalledMiniSweAgent",
        "evolve.integrations.harbor.miniswe_task_file:FileTaskMiniSweAgent",
    ],
)
def test_installed_miniswe_mutate_outer_timeout_budgets_every_retry(
    agent: str,
) -> None:
    assert (
        _operator_deadline_s(
            "mutate",
            {
                "runner": "harbor",
                "agent": agent,
                "max_retries": 1,
            },
            3600,
        )
        == 14640.0
    )


@pytest.mark.parametrize(
    "agent",
    [
        "evolve.integrations.harbor.miniswe_candidate:CandidateMiniSweAgent",
        "evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent",
        "custom:FileTaskMiniSweAgent",
        "custom:MiniSweSourceAgent",
    ],
)
def test_non_installed_agents_keep_whole_process_timeout(agent: str) -> None:
    assert (
        _operator_deadline_s(
            "mutate",
            {"runner": "harbor", "agent": agent, "max_retries": 1},
            3600,
        )
        == 3600
    )


def test_codex_harbor_mutate_keeps_whole_process_timeout() -> None:
    assert (
        _operator_deadline_s(
            "mutate",
            {
                "runner": "harbor",
                "agent": "codex",
                "max_retries": 1,
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
    live_best = '{"genid":"0","score":0.5}\n'
    (workspace / "archive.jsonl").write_text(live_archive)
    eval_receipt_path(archive_path(workspace)).write_text(live_receipt)
    (workspace / "best_ever.json").write_text(live_best)
    (checkout / "archive.jsonl").write_text("")
    eval_receipt_path(archive_path(checkout)).write_text("checkout-original\n")
    (checkout / "best_ever.json").write_text("")
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
    assert (workspace / "best_ever.json").read_text() == live_best
    assert (checkout / "archive.jsonl").read_text() == ""
    assert eval_receipt_path(archive_path(checkout)).read_text() == "checkout-original\n"
    assert (checkout / "best_ever.json").read_text() == ""


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


@pytest.mark.skipif(not _ps_process_tree_available(), reason="requires permission to enumerate the process tree")
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
        timeout_s=2.0,
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
