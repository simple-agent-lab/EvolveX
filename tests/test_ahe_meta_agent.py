import copy
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from evolve.frozen.interfaces import OperatorContext

ROOT = Path(__file__).resolve().parents[1]


def _editor_module():
    spec = importlib.util.spec_from_file_location(
        "ahe_evidence_editor",
        ROOT / "library" / "meta_agent" / "ahe_evidence_editor.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    checkout = tmp_path / "checkout"
    run_dir = tmp_path / "runs" / "gen-1"
    (checkout / "target").mkdir(parents=True)
    (checkout / "target" / "agent.py").write_text("print('parent')\n")
    (checkout / "target" / "harbor_agent.py").write_text("print('protected')\n")
    (checkout / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n  exclude: []\n"
        "operators:\n  meta_agent: {timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n  agent: target.harbor_agent:MiniSweSourceAgent\n"
    )
    evidence = run_dir / "rollout" / "analysis" / "detail" / "task-1.md"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("Task task-1 fails because the tool call is malformed.\n")
    (evidence.parent / "unselected.md").write_text("UNSELECTED DETAIL MUST NOT APPEAR\n")
    (run_dir / "rollout" / "analysis" / "selection.json").write_text(
        json.dumps({"generation": "1", "tasks": {"task-1": ["failure"]}}) + "\n"
    )
    (run_dir / "rollout" / "analysis" / "overview.md").write_text("Normalize tool calls.\n")
    (run_dir / "rollout" / "attribution.json").write_text('{"changes": []}\n')
    (run_dir / "feedback").mkdir()
    (run_dir / "feedback" / "attempts.md").write_text("# Attempts\n\n- baseline\n")
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.name", "test")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-qm", "parent")
    _git(checkout, "tag", "gen/0")
    return checkout, run_dir


def _ctx(checkout: Path, run_dir: Path, command: str) -> OperatorContext:
    return OperatorContext(
        workspace=checkout,
        checkout=checkout,
        run_dir=run_dir,
        genid="1",
        parent="0",
        round=None,
        fan_out=1,
        config={
            "command": command,
            "timeout_s": 30,
            "evidence": {"max_detail_reports": 4, "max_report_chars": 2000, "max_total_chars": 4000},
            "rollback": {"allow_partial": True, "pivot_after_revert": True},
        },
        rng=random.Random(0),
    )


def _manifest(files: list[str], report: str = "rollout/analysis/detail/task-1.md") -> dict[str, object]:
    return {
        "schema_version": 1,
        "generation": "1",
        "parent": "0",
        "decision": "revise",
        "changes": [
            {
                "id": "change-1",
                "type": "improvement",
                "files": files,
                "failure_evidence": [{"task_id": "task-1", "report": report}],
                "root_cause": "The tool call is malformed.",
                "targeted_fix": "Normalize the tool arguments.",
                "predicted_fixes": ["task-1", "task-2"],
                "risk_tasks": ["task-3"],
                "component_level": "tool",
            }
        ],
        "validation": {"status": "passed", "commands": ["pytest -q"]},
    }


def _write_command(tmp_path: Path, *, edits: dict[str, str], manifest: object | None) -> Path:
    script = tmp_path / "evolution_agent.py"
    lines = [
        "import json",
        "import os",
        "from pathlib import Path",
        "assert os.environ['EVOLVE_SOURCE_AGENT_ROLE'] == 'evolution'",
        "assert all(name not in os.environ for name in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY'))",
        "Path(os.environ['EVOLVE_SOURCE_AGENT_OUTPUT_PATH']).write_text('trajectory\\n')",
    ]
    lines.extend("Path(%r).write_text(%r)" % (path, content) for path, content in edits.items())
    if manifest is not None:
        lines.append("Path(os.environ['EVOLVE_AHE_MANIFEST_PATH']).write_text(%r)" % (json.dumps(manifest) + "\n"))
    script.write_text("\n".join(lines) + "\n")
    return script


def _assert_failure_artifacts(run_dir: Path) -> None:
    meta_agent = run_dir / "meta_agent"
    assert (meta_agent / "changed.json").is_file()
    assert (meta_agent / "surface-check.json").is_file()
    assert (meta_agent / "patch.diff").is_file()
    assert "error:" in (meta_agent / "rationale.md").read_text()
    assert json.loads((meta_agent / "predicted_fixes.json").read_text()) == []
    assert json.loads((meta_agent / "risk_tasks.json").read_text()) == []
    assert json.loads((meta_agent / "usage.json").read_text())["usd"] == 0


def test_ahe_evidence_editor_writes_evidence_backed_artifacts(tmp_path: Path, monkeypatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    command = _write_command(
        tmp_path,
        edits={"target/agent.py": "print('child')\n"},
        manifest=_manifest(["target/agent.py"]),
    )
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.example:8118")

    result = _editor_module().AheEvidenceEditor().run(checkout, "ignored", _ctx(checkout, run_dir, f"{sys.executable} {command}"))

    meta_agent = run_dir / "meta_agent"
    assert result.changed == ["target/agent.py"]
    assert json.loads((meta_agent / "changed.json").read_text()) == ["target/agent.py"]
    assert json.loads((meta_agent / "predicted_fixes.json").read_text()) == ["task-1", "task-2"]
    assert json.loads((meta_agent / "risk_tasks.json").read_text()) == ["task-3"]
    assert json.loads((meta_agent / "surface-check.json").read_text()) == {
        "mutated": ["target/agent.py"],
        "ok": True,
        "violations": [],
    }
    assert (meta_agent / "change_manifest.json").is_file()
    assert not (checkout / ".evolve-ahe-change-manifest.json").exists()
    assert (meta_agent / "evolution.trajectory.json").read_text() == "trajectory\n"
    assert "variant: ahe_evidence_editor" in (meta_agent / "rationale.md").read_text()


@pytest.mark.parametrize(
    ("edits", "manifest", "message"),
    [
        ({"target/agent.py": "print('child')\n"}, None, "manifest"),
        ({"target/agent.py": "print('child')\n"}, _manifest(["target/agent.py"], "rollout/analysis/detail/missing.md"), "evidence"),
        (
            {"target/agent.py": "print('child')\n", "target/extra.py": "print('extra')\n"},
            _manifest(["target/agent.py"]),
            "cover",
        ),
        ({"target/agent.py": "print('child')\n"}, _manifest(["target/agent.py"], "../outside.md"), "unsafe path"),
        ({"target/harbor_agent.py": "print('edited')\n"}, _manifest(["target/harbor_agent.py"]), "surface"),
    ],
    ids=["missing-manifest", "missing-evidence", "uncovered-file", "unsafe-evidence", "protected-harbor-agent"],
)
def test_ahe_evidence_editor_blocks_invalid_pre_evaluation_proposals(
    tmp_path: Path,
    edits: dict[str, str],
    manifest: object | None,
    message: str,
) -> None:
    checkout, run_dir = _checkout(tmp_path)
    command = _write_command(tmp_path, edits=edits, manifest=manifest)

    with pytest.raises(SystemExit, match=message):
        _editor_module().AheEvidenceEditor().run(checkout, "", _ctx(checkout, run_dir, f"{sys.executable} {command}"))

    _assert_failure_artifacts(run_dir)


def test_build_ahe_prompt_reads_only_explicit_ahe_artifacts(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    prompt = _editor_module().build_ahe_prompt(checkout, _ctx(checkout, run_dir, f"{sys.executable} -c 'pass'"))

    assert "# Experiment Config" in prompt
    assert "# Analysis Overview\n\nNormalize tool calls." in prompt
    assert "# Previous Change Attribution" in prompt
    assert "# Selected Detail Reports" in prompt
    assert "Task task-1 fails because the tool call is malformed." in prompt
    assert "UNSELECTED DETAIL MUST NOT APPEAR" not in prompt
    assert "# Evolution History\n\n# Attempts" in prompt
    assert "target/harbor_agent.py" in prompt
    assert ".evolve-ahe-change-manifest.json" in prompt
    assert str(run_dir) not in prompt
    assert "Do not `cd` to experiment or run-artifact directories" in prompt
    assert "KEEP" in prompt
    assert "ROLLBACK + PIVOT" in prompt
    assert "Partial rollback is allowed" in prompt
    assert "A distinct pivot after every revert is required" in prompt


def test_build_ahe_prompt_sanitizes_and_bounds_selected_detail_reports(tmp_path: Path, monkeypatch) -> None:
    checkout, run_dir = _checkout(tmp_path)
    secret = "opaque-editor-secret"
    credential_url = "https://user:password@llm.example/v1"
    report = run_dir / "rollout" / "analysis" / "detail" / "task-1.md"
    report.write_text("useful debugger diagnosis\n" + secret + "\n" + credential_url + "\n" + ("x" * 5000))
    (run_dir / "feedback" / "attempts.md").write_text(f"prior secret: {secret}\nprior proxy: {credential_url}\n")
    config = (checkout / "evolve.yaml").read_text().replace(
        "  agent: target.harbor_agent:MiniSweSourceAgent\n",
        f"  agent: target.harbor_agent:MiniSweSourceAgent\n  proxy_url: {credential_url}\n  api_key: {secret}\n",
    )
    (checkout / "evolve.yaml").write_text(config)
    monkeypatch.setenv("EVOLVE_EDITOR_TOKEN", secret)

    prompt = _editor_module().build_ahe_prompt(checkout, _ctx(checkout, run_dir, "unused"))

    assert "useful debugger diagnosis" in prompt
    assert secret not in prompt
    assert credential_url not in prompt
    assert "[REDACTED]" in prompt
    detail_section = prompt.split("# Selected Detail Reports", 1)[1].split("# Evolution History", 1)[0]
    assert len(detail_section) < 4500


def test_build_ahe_prompt_renders_disabled_rollback_policy(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    ctx = _ctx(checkout, run_dir, "unused")
    ctx.config["rollback"] = {"allow_partial": False, "pivot_after_revert": False}

    prompt = _editor_module().build_ahe_prompt(checkout, ctx)

    assert "Partial rollback is prohibited" in prompt
    assert "A pivot after revert is optional" in prompt


@pytest.mark.parametrize(
    "path",
    [
        "target/.env",
        "target/.env.local",
        "target/config/.env.test",
        "target/model.env",
        "target/proxy.env",
        "target/eval.env",
        "target/config/runtime.env",
        "target/config/model-config.yaml",
        "target/config/proxy-config.json",
        "target/config/model_config.yaml",
        "target/config/proxy_config.json",
    ],
)
def test_ahe_effective_surface_excludes_operational_paths(tmp_path: Path, path: str) -> None:
    from evolve.surface import check_paths

    checkout, _run_dir = _checkout(tmp_path)
    surface = _editor_module()._ahe_surface(checkout)

    assert check_paths([path], surface.include, surface.exclude) == [path]


def test_build_ahe_prompt_binds_immutable_manifest_identity(tmp_path: Path) -> None:
    checkout, run_dir = _checkout(tmp_path)
    module = _editor_module()
    ctx = _ctx(checkout, run_dir, f"{sys.executable} -c 'pass'")
    parent_ref = module.patch_parent_ref(checkout, ctx)

    prompt = module.build_ahe_prompt(checkout, ctx, parent_ref)

    assert "# Immutable Manifest Identity" in prompt
    assert "Generation ID: `1`" in prompt
    assert "Parent generation ID: `0`" in prompt
    assert f"Parent git ref: `{parent_ref}`" in prompt
    assert 'Copy exactly `"generation": "1"` and `"parent": "0"` into `change_manifest.json`.' in prompt


def test_installed_editor_imports_support_and_reads_copied_prompt(tmp_path: Path, monkeypatch) -> None:
    from evolve import workspace as workspace_module

    config = workspace_module.default_config("ahe-smoke", "installed-ahe")
    config["operators"]["meta_agent"] = {"variant": "ahe_evidence_editor"}
    monkeypatch.setattr(workspace_module, "default_config", lambda _recipe, _experiment: copy.deepcopy(config))
    workspace = tmp_path / "installed-ahe"
    workspace_module.init_workspace(workspace_module.InitOptions(workspace=workspace, recipe="ahe-smoke"))

    installed_editor = workspace / "operators" / "meta_agent.py"
    code = (
        "import importlib.util\n"
        f"path = {str(installed_editor)!r}\n"
        "spec = importlib.util.spec_from_file_location('installed_ahe_editor', path)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(module._read_prompt('ahe_evolve.md').splitlines()[0])\n"
    )
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=False, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "# AHE Evidence Editor\n"
    assert (workspace / "library" / "ahe_support.py").is_file()
    assert (workspace / "library" / "meta_agent" / "prompts" / "ahe_evolve.md").is_file()
