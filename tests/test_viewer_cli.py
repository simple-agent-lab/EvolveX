from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from evolve.cli import app


def test_view_defaults(monkeypatch, tmp_path: Path) -> None:
    called = {}

    def capture(workspace: Path, host: str, port_spec: str) -> None:
        called.update(workspace=workspace, host=host, port_spec=port_spec)

    monkeypatch.setattr("evolve.viewer.run_viewer", capture)

    result = CliRunner().invoke(app, ["view", str(tmp_path)])

    assert result.exit_code == 0
    assert called == {"workspace": tmp_path, "host": "127.0.0.1", "port_spec": "8080-8089"}


def test_view_forwards_explicit_host_and_port(monkeypatch, tmp_path: Path) -> None:
    called = {}
    monkeypatch.setattr(
        "evolve.viewer.run_viewer",
        lambda workspace, host, port_spec: called.update(
            workspace=workspace, host=host, port_spec=port_spec
        ),
    )

    result = CliRunner().invoke(
        app,
        ["view", str(tmp_path), "--host", "0.0.0.0", "--port", "9001"],
    )

    assert result.exit_code == 0
    assert called["host"] == "0.0.0.0"
    assert called["port_spec"] == "9001"
