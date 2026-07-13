import json
import os
import sys
from pathlib import Path

from conftest import git_show, rows_by_genid, run_evolve

from evolve.config import operator_blocks
from evolve.operators import operator_timeout


def _dataset(root: Path, count: int = 10) -> Path:
    root.mkdir()
    for index in range(count):
        task = root / f"task-{index}"
        task.mkdir()
        (task / "task.toml").write_text(f'version = "1.0"\nname = "task-{index}"\n')
    return root


def _fake_harbor(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "print('harbor-live-marker', flush=True)\n"
        "args = sys.argv[1:]\n"
        "jobs = Path(args[args.index('--jobs-dir') + 1])\n"
        "jobs.mkdir(parents=True, exist_ok=True)\n"
        "(jobs / 'args.json').write_text(json.dumps(args))\n"
        "names = [args[i + 1] for i, value in enumerate(args) if value == '--include-task-name']\n"
        "for name in names:\n"
        "    trial = jobs / f'{name}-0'\n"
        "    trial.mkdir(parents=True, exist_ok=True)\n"
        "    payload = {\n"
        "        'trial_name': f'{name}-0',\n"
        "        'task_name': name,\n"
        "        'agent_result': {'n_input_tokens': 1, 'n_output_tokens': 1, 'cost_usd': 0},\n"
        "        'verifier_result': {'rewards': {'reward': 0}},\n"
        "        'exception_info': None,\n"
        "    }\n"
        "    (trial / 'result.json').write_text(json.dumps(payload))\n"
    )
    path.chmod(0o755)


def _fake_codex(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "from pathlib import Path\n"
        "prompt = sys.stdin.read()\n"
        "if 'Harbor Rollout Feedback' not in prompt:\n"
        "    raise SystemExit('missing rollout feedback')\n"
        "target = Path('target/prompt.md')\n"
        "target.write_text(target.read_text() + '\\nAHE_GENERATION_1 = true\\n')\n"
        "print('predicted_fixes: []')\n"
    )
    path.chmod(0o755)


def test_ahe_recipe_runs_train_rollout_codex_mutation_and_gate(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "tasks")
    workspace = tmp_path / "ahe-workspace"
    evolve_home = tmp_path / "evolve-home"
    initialized = run_evolve(
        "init",
        str(workspace),
        "--recipe",
        "ahe",
        "--dataset",
        str(dataset),
        env={"EVOLVE_HOME": str(evolve_home)},
    )
    assert initialized.returncode == 0, initialized.stderr
    assert json.loads((workspace / "target" / "UPSTREAM.json").read_text()) == {
        "kind": "builtin",
        "seed": "builtin-codex",
    }
    assert "source=library/rollout/harbor.py" in (workspace / "operators" / "rollout.py").read_text()
    assert "source=library/mutate/agent_command.py" in (workspace / "operators" / "mutate.py").read_text()
    assert "source=library/gate/hillclimb.py" in (workspace / "operators" / "gate.py").read_text()
    eval_env = (workspace / "evaluator" / "eval.env").read_text()
    assert "EVOLVE_HARBOR_N_CONCURRENT=4" in eval_env
    assert "EVOLVE_HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER=3.0" in eval_env
    assert "EVOLVE_HARBOR_MAX_RETRIES=1" in eval_env
    operators = operator_blocks(workspace)
    assert {name: operator_timeout(operators, name) for name in ("select", "rollout", "mutate", "gate", "record")} == {
        "select": 600,
        "rollout": 3600,
        "mutate": 3600,
        "gate": 600,
        "record": 600,
    }

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_harbor(bin_dir / "harbor")
    _fake_codex(bin_dir / "codex")
    result = run_evolve(
        "run",
        str(workspace),
        "--max-generations",
        "1",
        "--verbose",
        env={
            "EVOLVE_HOME": str(evolve_home),
            "EVOLVE_HARBOR_ROLLOUT_JOBS_DIR": str(tmp_path / "rollout-jobs"),
            "EVOLVE_HARBOR_HTTP_PROXY": "http://proxy.example:8118",
            "EVOLVE_HARBOR_HTTPS_PROXY": "http://proxy.example:8118",
            "EVOLVE_HARBOR_NO_PROXY": "localhost,127.0.0.1,.example.test",
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "harbor-live-marker" in result.stdout
    assert "[evolve] gen/0 baseline: evaluating gate split" in result.stdout
    expected_agent_env = {
        "http_proxy=http://proxy.example:8118",
        "HTTP_PROXY=http://proxy.example:8118",
        "https_proxy=http://proxy.example:8118",
        "HTTPS_PROXY=http://proxy.example:8118",
        "no_proxy=localhost,127.0.0.1,.example.test",
        "NO_PROXY=localhost,127.0.0.1,.example.test",
    }
    baseline_args = json.loads(
        (tmp_path / "home" / ".evolve" / "harbor-jobs" / workspace.name / "gen-0-baseline" / "args.json").read_text()
    )
    rollout_summary = json.loads((workspace / "runs" / "gen-1" / "rollout" / "summary.json").read_text())
    rollout_args = json.loads((Path(rollout_summary["jobs_dir"]) / "args.json").read_text())
    for args in (baseline_args, rollout_args):
        for flag in ("--ae", "--ve"):
            assert {args[index + 1] for index, value in enumerate(args) if value == flag} == expected_agent_env
    rows = rows_by_genid(workspace)
    assert rows["0"]["score"] == 0
    row = rows["1"]
    assert row["valid_parent"] is True
    assert row["verdict"] == "keep"
    assert "AHE_GENERATION_1 = true" in git_show(workspace, "gen/1:target/prompt.md").decode()
    rollout = json.loads((workspace / "runs" / "gen-1" / "rollout" / "summary.json").read_text())
    assert rollout["split"] == "train"
    train_count = len(json.loads((workspace / "evaluator" / "splits.json").read_text())["tasks"]["train"])
    assert rollout["tasks_observed"] == rollout["tasks_requested"]
    assert 0 < rollout["tasks_observed"] <= train_count
    events = [json.loads(line) for line in (workspace / "archive.jsonl").read_text().splitlines()]
    assert any(event.get("kind") == "baseline" for event in events)
