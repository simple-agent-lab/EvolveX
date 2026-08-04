from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evolve.viewer.app import create_viewer_app


@pytest.fixture
def viewer_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "experiment"
    workspace.mkdir()
    (workspace / "evolve.yaml").write_text(
        """
experiment:
  id: viewer-api-test
target: {}
surface: {}
operators:
  select: {}
  rollout: {}
  meta_agent: {}
  gate: {}
  record: {}
evaluator: {}
""".lstrip()
    )
    trials = [
        {"trial": index, "status": "complete" if index < 23 else "error", "reward": float(index % 2)}
        for index in range(25)
    ]
    row = {
        "genid": "1",
        "parent": "0",
        "purpose": "candidate",
        "status": "complete",
        "score": 0.72,
        "task_vector": {"tasks": {"task-a": {"trials": trials}}},
    }
    (workspace / "archive.jsonl").write_text(json.dumps(row) + "\n")
    rationale = workspace / "runs/gen-1/meta_agent/rationale.md"
    rationale.parent.mkdir(parents=True)
    rationale.write_text("Improved retry handling.\n")
    return workspace


def test_snapshot_and_generation_routes(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        assert client.get("/api/evolve/snapshot").status_code == 200
        assert client.get("/api/evolve/generations/1").json()["summary"]["genid"] == "1"
        assert client.get("/api/evolve/generations/missing").status_code == 404


def test_trial_pagination_and_filters(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        response = client.get(
            "/api/evolve/trials",
            params={"page": 2, "page_size": 10, "status": "complete", "purpose": "candidate"},
        )
    body = response.json()
    assert body["page"] == 2
    assert len(body["items"]) == 10
    assert body["total"] == 23
    assert all(item["status"] == "complete" for item in body["items"])


def test_last_valid_snapshot_survives_transient_bad_archive(viewer_workspace: Path) -> None:
    app = create_viewer_app(viewer_workspace)
    with TestClient(app) as client:
        first = client.get("/api/evolve/snapshot").json()
        (viewer_workspace / "archive.jsonl").write_text("not json\n")
        second = client.get("/api/evolve/snapshot").json()
    assert second["generations"] == first["generations"]
    assert any(warning["code"] == "refresh_failed" for warning in second["experiment"]["warnings"])


def test_preview_is_bounded_and_registered(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        detail = client.get("/api/evolve/generations/1").json()
        artifact_id = detail["artifacts"][0]["id"]
        response = client.get(f"/api/evolve/artifacts/{artifact_id}")
        missing = client.get("/api/evolve/artifacts/missing")
    assert response.status_code == 200
    assert len(response.content) <= 1024 * 1024
    assert missing.status_code == 404


def test_composed_app_blocks_mutating_and_get_shaped_actions(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        assert client.post("/api/run", json={}).status_code == 405
        assert client.delete("/api/jobs/example").status_code == 405
        assert client.get("/api/jobs/example/upload").status_code == 405
        assert client.get("/api/run/options").status_code == 405
        assert client.get("/api/auth/status").status_code == 405
        assert client.get("/api/jobs").status_code == 200
