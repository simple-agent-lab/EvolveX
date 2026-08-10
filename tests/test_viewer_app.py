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


def test_artifact_metadata_and_bounded_headers(viewer_workspace: Path) -> None:
    patch = viewer_workspace / "runs/gen-1/meta_agent/model_patch.diff"
    patch.write_text("diff --git a/a.py b/a.py\n" + "+x\n" * 350_000)

    with TestClient(create_viewer_app(viewer_workspace)) as client:
        detail = client.get("/api/evolve/generations/1").json()
        rationale = next(item for item in detail["artifacts"] if item["label"] == "rationale.md")
        model_patch = next(item for item in detail["artifacts"] if item["label"] == "model_patch.diff")
        metadata = client.get(f"/api/evolve/artifacts/{rationale['id']}/metadata")
        patch_metadata = client.get(f"/api/evolve/artifacts/{model_patch['id']}/metadata")
        content = client.get(f"/api/evolve/artifacts/{model_patch['id']}")

    assert metadata.json()["relative_path"] == "runs/gen-1/meta_agent/rationale.md"
    assert metadata.json()["content_url"] == f"/api/evolve/artifacts/{rationale['id']}"
    assert metadata.json()["truncated"] is False
    assert patch_metadata.json()["truncated"] is True
    assert content.headers["x-evolve-artifact-truncated"] == "true"
    assert len(content.content) == 1024 * 1024


def test_artifact_shell_and_metadata_preserve_registered_id_boundary(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        shell = client.get("/artifacts/example")
        missing = client.get("/api/evolve/artifacts/missing/metadata")

    assert shell.status_code == 200
    assert 'id="evolve-viewer"' in shell.text
    assert missing.status_code == 404


def test_composed_app_blocks_mutating_and_get_shaped_actions(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        assert client.post("/api/run", json={}).status_code == 405
        assert client.delete("/api/jobs/example").status_code == 405
        assert client.get("/api/jobs/example/upload").status_code == 405
        assert client.get("/api/run/options").status_code == 405
        assert client.get("/api/auth/status").status_code == 405
        assert client.get("/api/jobs").status_code == 200


def test_frontend_routes_serve_evolve_shell(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        for path in ("/", "/generations", "/generations/1", "/trials", "/artifacts/example"):
            response = client.get(path)
            assert response.status_code == 200
            assert 'id="evolve-viewer"' in response.text


def test_frontend_shell_and_assets_are_not_cached_across_deployments(viewer_workspace: Path) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        shell = client.get("/")
        javascript = client.get("/evolve-assets/app.js")

    assert shell.headers["cache-control"] == "no-store"
    assert javascript.headers["cache-control"] == "no-store"


def test_frontend_has_required_navigation_and_refresh_contract() -> None:
    static = Path(__file__).parents[1] / "src/evolve/viewer/static"
    html = (static / "index.html").read_text()
    javascript = (static / "app.js").read_text()

    assert all(label in html for label in ("Overview", "Generations", "Trials"))
    assert "3000" in javascript
    assert "/api/evolve/snapshot" in javascript
    assert "Full Harbor inspection" in javascript
    assert all(label in javascript for label in ("← Overview", "← Generations", "← Generation"))
    assert all(
        label in javascript
        for label in ("Previous performance page", "Next performance page", "GEPA train score change")
    )
    assert "Global final result" in javascript
    assert "Global champion from canonical evaluation" in javascript
    assert "Champion agent ·" in javascript
    assert "hasTrainScore && !globalResult" in javascript
    assert "overviewPlaceholderCard" in javascript


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("diff2html.min.js", "javascript"),
        ("diff2html.min.css", "text/css"),
        ("highlight.min.js", "javascript"),
        ("highlight-github.min.css", "text/css"),
    ],
)
def test_vendored_preview_assets_are_served(viewer_workspace: Path, path: str, media_type: str) -> None:
    with TestClient(create_viewer_app(viewer_workspace)) as client:
        response = client.get(f"/evolve-assets/vendor/{path}")

    assert response.status_code == 200
    assert response.content
    assert media_type in response.headers["content-type"]
