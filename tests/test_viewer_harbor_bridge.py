from __future__ import annotations

import json
from pathlib import Path

from evolve.viewer.harbor_bridge import HarborBridge
from evolve.viewer.models import JobRootReference


def _harbor_jobs(root: Path, job: str, *, task: str = "task-a", trial: str = "trial-0") -> Path:
    trial_dir = root / job / trial
    trial_dir.mkdir(parents=True)
    (root / job / "config.json").write_text("{}")
    (trial_dir / "config.json").write_text(
        json.dumps(
            {
                "task": {"path": task, "source": "local/source"},
                "agent": {"name": "mini agent", "model_name": "openai/model name"},
            }
        )
    )
    return root


def test_bridge_federates_multiple_roots_without_collisions(tmp_path: Path) -> None:
    left = _harbor_jobs(tmp_path / "left", "same-job")
    right = _harbor_jobs(tmp_path / "right", "same-job")

    with HarborBridge(tmp_path / "workspace") as bridge:
        federation = bridge.refresh(
            [
                JobRootReference(generation="1", purpose="rollout", path=left),
                JobRootReference(generation="1", purpose="candidate", path=right),
            ]
        )
        links = sorted(federation.root.iterdir())
        assert len(links) == 2
        assert links[0].name != links[1].name
        assert all(path.is_symlink() for path in links)


def test_bridge_removes_stale_links_and_cleans_up(tmp_path: Path) -> None:
    jobs = _harbor_jobs(tmp_path / "jobs", "job-a")
    bridge = HarborBridge(tmp_path / "workspace")
    root = bridge.__enter__().refresh(
        [JobRootReference(generation="1", purpose="candidate", path=jobs)]
    ).root

    bridge.refresh([])
    assert list(root.iterdir()) == []
    bridge.__exit__(None, None, None)
    assert not root.exists()


def test_bridge_names_are_stable_and_invalid_jobs_are_ignored(tmp_path: Path) -> None:
    jobs = _harbor_jobs(tmp_path / "jobs", "job with spaces")
    (jobs / "not-a-job").mkdir()
    reference = JobRootReference(generation="2", purpose="candidate", path=jobs)

    with HarborBridge(tmp_path / "workspace") as bridge:
        first = bridge.refresh([reference])
        first_names = sorted(path.name for path in first.root.iterdir())
        second_names = sorted(path.name for path in bridge.refresh([reference]).root.iterdir())

    assert first_names == second_names
    assert len(first_names) == 1
    assert first_names[0].startswith("job-with-spaces-")


def test_bridge_builds_full_harbor_trial_route(tmp_path: Path) -> None:
    jobs = _harbor_jobs(tmp_path / "jobs", "job-a", task="task-a", trial="trial one")

    with HarborBridge(tmp_path / "workspace") as bridge:
        federation = bridge.refresh(
            [JobRootReference(generation="3", purpose="candidate", path=jobs)]
        )

    link = federation.trial_links[("3", "candidate", "task-a", 0)]
    assert link.url.startswith("/jobs/job-a-")
    assert link.url.endswith(
        "/tasks/local%2Fsource/mini%20agent/openai/model%20name/task-a/trials/trial%20one"
    )


def test_bridge_maps_only_unique_canonical_suffix(tmp_path: Path) -> None:
    jobs = _harbor_jobs(tmp_path / "jobs", "job-a", task="short")
    reference = JobRootReference(generation="4", purpose="candidate", path=jobs)

    with HarborBridge(tmp_path / "workspace") as bridge:
        unique = bridge.refresh(
            [reference], canonical_tasks={("4", "candidate"): ("suite__short",)}
        )
        assert ("4", "candidate", "suite__short", 0) in unique.trial_links

        ambiguous = bridge.refresh(
            [reference],
            canonical_tasks={("4", "candidate"): ("left__short", "right__short")},
        )
        assert ambiguous.trial_links == {}
