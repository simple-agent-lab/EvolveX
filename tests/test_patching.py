import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from evolve.candidate.snapshot import CandidateSnapshotError
from evolve.patching import SurfacePolicy, create_candidate_patch, load_surface_policy, patch_parent_ref
from evolve.surface import check_paths


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / "target").mkdir()
    (root / "target" / "agent.py").write_text("print('parent')\n")
    (root / "README.md").write_text("parent\n")
    (root / "evolve.yaml").write_text(
        "experiment:\n  id: test\n"
        "target:\n  seed: builtin-dummy\n"
        "surface:\n  include:\n    - target/**\n  exclude:\n    - target/tmp/**\n"
        "operators:\n  meta_agent: {timeout_s: 30}\n"
        "evaluator:\n  engine: harbor\n  dataset: pass@k\n"
        "  agent: evolve.integrations.harbor.miniswe_candidate:MiniSweSourceAgent\n"
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "parent")
    _git(root, "tag", "gen/0")
    return root


def test_create_candidate_patch_reports_changed_paths_and_diff(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "+print('child')" in patch.diff
    assert patch.notes == []


def test_create_candidate_patch_includes_new_in_surface_files_in_diff(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "new_file.py").write_text("print('new')\n")

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/new_file.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/new_file.py"], "violations": []}
    assert "diff --git a/target/new_file.py b/target/new_file.py" in patch.diff
    assert "+print('new')" in patch.diff
    assert _git(root, "status", "--porcelain", "--", "target/new_file.py") == "?? target/new_file.py"


def test_create_candidate_patch_repairs_out_of_surface_paths(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")
    (root / "README.md").write_text("leak\n")

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "README.md" not in patch.diff
    assert (root / "README.md").read_text() == "parent\n"
    assert patch.notes == ["repaired surface violations by reverted: README.md"]


def test_create_candidate_patch_reports_remaining_violation_when_repair_disabled(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "README.md").write_text("leak\n")

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
        repair=False,
    )

    assert patch.changed_paths == ["README.md"]
    assert patch.surface_report == {"ok": False, "mutated": ["README.md"], "violations": ["README.md"]}
    assert patch.notes == []


def test_create_candidate_patch_ignores_unchanged_injected_live_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = _repo(tmp_path)
    live_archive = '{"genid":"0","score":0.5}\n'
    (workspace / "archive.jsonl").write_text(live_archive)
    (root / "archive.jsonl").write_text(live_archive)
    (root / "target" / "agent.py").write_text("print('child')\n")
    monkeypatch.setenv("EVOLVE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EVOLVE_CHECKOUT", str(root))

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
        repair=False,
    )

    assert patch.changed_paths == ["target/agent.py"]
    assert patch.surface_report == {"ok": True, "mutated": ["target/agent.py"], "violations": []}
    assert "archive.jsonl" not in patch.diff
    assert not (root / "archive.jsonl").exists()


def test_create_candidate_patch_keeps_agent_modified_injected_archive_as_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = _repo(tmp_path)
    (workspace / "archive.jsonl").write_text('{"genid":"0","score":0.5}\n')
    (root / "archive.jsonl").write_text('{"genid":"0","score":0.9}\n')
    monkeypatch.setenv("EVOLVE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EVOLVE_CHECKOUT", str(root))

    patch = create_candidate_patch(
        checkout=root,
        parent_ref="gen/0",
        surface=SurfacePolicy(include=["target/**"], exclude=[]),
        repair=False,
    )

    assert patch.changed_paths == ["archive.jsonl"]
    assert patch.surface_report == {
        "ok": False,
        "mutated": ["archive.jsonl"],
        "violations": ["archive.jsonl"],
    }
    assert (root / "archive.jsonl").exists()


def test_create_candidate_patch_rejects_already_staged_path(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "target" / "agent.py").write_text("print('child')\n")
    _git(root, "add", "target/agent.py")

    with pytest.raises(CandidateSnapshotError, match="^candidate index is not clean$"):
        create_candidate_patch(
            checkout=root,
            parent_ref="gen/0",
            surface=SurfacePolicy(include=["target/**"], exclude=[]),
        )


def test_load_surface_policy_reads_workspace_surface_lists(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    policy = load_surface_policy(root)

    assert policy == SurfacePolicy(include=["target/**"], exclude=["target/tmp/**"])


def test_harbor_agent_file_is_no_longer_implicitly_protected() -> None:
    assert check_paths(["target/harbor_agent.py"], ["target/**"], []) == []


def test_patch_parent_ref_prefers_context_parent(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    assert patch_parent_ref(root, SimpleNamespace(parent="7")) == "gen/7"


def test_patch_parent_ref_falls_back_to_head_tag(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    assert patch_parent_ref(root, SimpleNamespace(parent=None)) == "gen/0"
