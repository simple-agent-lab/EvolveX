from __future__ import annotations

import math
import re
import socket
import threading
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from harbor import viewer as harbor_viewer
from harbor.viewer.server import create_app as create_harbor_app

from .harbor_bridge import HarborBridge
from .models import ArtifactPreviewMetadata, PaginatedTrials, SnapshotBundle, ViewerWarning, WorkspaceSources
from .reader import WorkspaceReader
from .snapshot import add_snapshot_warning, build_snapshot

MAX_ARTIFACT_PREVIEW_BYTES = 1024 * 1024
_ACTION_PATH = re.compile(r"^/api/jobs/[^/]+/upload/?$")


class SnapshotStore:
    def __init__(self, reader: WorkspaceReader, bridge: HarborBridge):
        self.reader = reader
        self.bridge = bridge
        self._last: SnapshotBundle | None = None
        self._lock = threading.RLock()

    def refresh(self) -> SnapshotBundle:
        with self._lock:
            try:
                sources = self.reader.refresh()
                tasks = _canonical_tasks(sources)
                federation = self.bridge.refresh(sources.job_roots, canonical_tasks=tasks)
                self._last = build_snapshot(sources, harbor_links=federation.trial_links)
            except Exception as exc:
                if self._last is None:
                    raise
                warning = ViewerWarning(code="refresh_failed", message=str(exc), scope="experiment")
                self._last = add_snapshot_warning(self._last, warning)
            return self._last


def create_viewer_app(workspace: Path, *, bridge: HarborBridge | None = None) -> FastAPI:
    workspace = workspace.resolve()
    active_bridge = (bridge or HarborBridge(workspace)).__enter__()
    store = SnapshotStore(WorkspaceReader(workspace), active_bridge)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            active_bridge.__exit__(None, None, None)

    app = FastAPI(title="Evolve Experiment Viewer", version="0.1.0", lifespan=lifespan)
    app.state.snapshot_store = store

    @app.middleware("http")
    async def enforce_read_only(request: Request, call_next):
        path = request.url.path
        if request.method not in {"GET", "HEAD", "OPTIONS"} or _is_action_path(path):
            return Response(status_code=405, headers={"Allow": "GET, HEAD, OPTIONS"})
        response = await call_next(request)
        if path.startswith(("/evolve-assets/", "/generations", "/trials", "/artifacts")) or path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/evolve/snapshot")
    def snapshot() -> Any:
        return store.refresh().snapshot

    @app.get("/api/evolve/generations")
    def generations() -> Any:
        return store.refresh().snapshot.generations

    @app.get("/api/evolve/generations/{genid}")
    def generation(genid: str) -> Any:
        detail = store.refresh().generation_details.get(genid)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"generation {genid!r} not found")
        return detail

    @app.get("/api/evolve/trials", response_model=PaginatedTrials)
    def trials(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        generation: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        task: str | None = None,
    ) -> PaginatedTrials:
        items = list(store.refresh().trials)
        items = _filter_trials(
            items,
            generation=generation,
            purpose=purpose,
            status=status,
            task=task,
        )
        total = len(items)
        start = (page - 1) * page_size
        return PaginatedTrials(
            items=items[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    @app.get("/api/evolve/artifacts/{artifact_id}")
    def artifact(artifact_id: str) -> Response:
        target = store.refresh().artifact_targets.get(artifact_id)
        if target is None or not target.path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        try:
            with target.path.open("rb") as handle:
                content = handle.read(MAX_ARTIFACT_PREVIEW_BYTES)
        except OSError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=target.media_type,
            headers={"X-Evolve-Artifact-Truncated": str(target.size > MAX_ARTIFACT_PREVIEW_BYTES).lower()},
        )

    @app.get("/api/evolve/artifacts/{artifact_id}/metadata", response_model=ArtifactPreviewMetadata)
    def artifact_metadata(artifact_id: str) -> ArtifactPreviewMetadata:
        bundle = store.refresh()
        reference = bundle.artifact_references.get(artifact_id)
        if reference is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return ArtifactPreviewMetadata(
            **reference.model_dump(),
            truncated=reference.size > MAX_ARTIFACT_PREVIEW_BYTES,
            content_url=f"/api/evolve/artifacts/{artifact_id}",
        )

    evolve_static = Path(__file__).parent / "static"
    app.mount("/evolve-assets", StaticFiles(directory=evolve_static), name="evolve-assets")

    @app.get("/", include_in_schema=False)
    @app.get("/generations", include_in_schema=False)
    @app.get("/generations/{genid}", include_in_schema=False)
    @app.get("/trials", include_in_schema=False)
    @app.get("/artifacts/{artifact_id}", include_in_schema=False)
    def evolve_shell(genid: str | None = None, artifact_id: str | None = None) -> FileResponse:
        del genid, artifact_id
        return FileResponse(evolve_static / "index.html")

    harbor_static = Path(next(iter(harbor_viewer.__path__))) / "static"
    harbor_app = create_harbor_app(active_bridge._require_root(), static_dir=harbor_static)
    app.router.routes.extend(harbor_app.router.routes[4:])
    return app


def run_viewer(workspace: Path, host: str, port_spec: str) -> None:
    port = _select_bindable_port(host, _ports(port_spec))
    print(f"Evolve viewer: http://127.0.0.1:{port}")
    print(f"DevBox tunnel: ssh -N -L {port}:127.0.0.1:{port} DevBox")
    uvicorn.run(create_viewer_app(workspace), host=host, port=port)


def _ports(port_spec: str) -> tuple[int, ...]:
    parts = port_spec.split("-", 1)
    try:
        start = int(parts[0])
        end = int(parts[1]) if len(parts) == 2 else start
    except ValueError as exc:
        raise ValueError("port must be an integer or ascending range such as 8080-8089") from exc
    if not (1 <= start <= end <= 65535):
        raise ValueError("port must be between 1 and 65535 and ranges must be ascending")
    return tuple(range(start, end + 1))


def _select_bindable_port(host: str, ports: Iterable[int]) -> int:
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
                candidate.bind((host, port))
        except OSError:
            continue
        return port
    raise RuntimeError("no available port in requested range")


def _is_action_path(path: str) -> bool:
    return (
        path == "/auth/callback"
        or path.startswith("/api/run")
        or path.startswith("/api/auth")
        or _ACTION_PATH.fullmatch(path) is not None
    )


def _filter_trials(items: list[Any], **filters: str | None) -> list[Any]:
    return [
        item
        for item in items
        if all(value is None or str(getattr(item, field)) == value for field, value in filters.items())
    ]


def _canonical_tasks(
    sources: WorkspaceSources,
) -> Mapping[tuple[str, str], tuple[str, ...]]:
    result: dict[tuple[str, str], set[str]] = {}
    for row in sources.rows:
        generation = str(row.get("genid"))
        purpose = str(row.get("purpose") or ("genesis" if generation == "0" else "candidate"))
        vector = row.get("task_vector")
        tasks = vector.get("tasks") if isinstance(vector, dict) else None
        if isinstance(tasks, dict):
            result.setdefault((generation, purpose), set()).update(str(task) for task in tasks)
    for relative, document in sources.documents.items():
        if not relative.endswith("/rollout/cases.json") or not isinstance(document.value, list):
            continue
        generation = Path(relative).parts[1].removeprefix("gen-")
        names = {
            str(item.get("task") or item.get("task_name"))
            for item in document.value
            if isinstance(item, dict) and (item.get("task") or item.get("task_name"))
        }
        result.setdefault((generation, "rollout"), set()).update(names)
    return {key: tuple(sorted(values)) for key, values in result.items()}
