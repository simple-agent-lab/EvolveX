"""Enforces ARCHITECTURE.md and coding-style constraints.

When a rot pattern is caught in review, add an assertion here so the
suite accumulates immune memory.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path

from evolve.frozen import interfaces

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "evolve"
APPROVED_MODULES = {
    "__init__.py",
    "__main__.py",
    "agent.py",
    "archive.py",
    "branching.py",
    "candidate/__init__.py",
    "candidate/smoke.py",
    "candidate/snapshot.py",
    "cli.py",
    "config.py",
    "driver.py",
    "evaluation/__init__.py",
    "evaluation/evidence.py",
    "evaluation/execution.py",
    "evaluation/identity.py",
    "evaluation/repair.py",
    "evaluation/results.py",
    "feedback.py",
    "git.py",
    "harbor_local.py",
    "host_runtime.py",
    "integrations/__init__.py",
    "integrations/harbor/__init__.py",
    "integrations/harbor/miniswe_candidate.py",
    "integrations/harbor/miniswe_task_file.py",
    "meta_agent_budget.py",
    "operators.py",
    "patching.py",
    "population.py",
    "report.py",
    "runtime.py",
    "splits.py",
    "surface.py",
    "trace_analysis.py",
    "uv_runtime.py",
    "workspace.py",
    # the frozen ring — the invariant-enforcers, grouped under frozen/
    "frozen/__init__.py",
    "frozen/interfaces.py",
    "frozen/sdk.py",
}


def _module_paths() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _module_relpaths() -> set[str]:
    return {path.relative_to(SRC).as_posix() for path in _module_paths()}


def test_every_module_is_approved_and_every_approved_module_exists() -> None:
    actual = _module_relpaths()
    assert actual == APPROVED_MODULES, (
        f"unexpected module set: actual={sorted(actual)}; "
        f"approved={sorted(APPROVED_MODULES)} - "
        "adding or removing a mechanism module requires updating the pinned set"
    )


def test_population_delegates_evaluation_identity() -> None:
    source = (SRC / "population.py").read_text()
    assert "hashlib" not in source
    assert "json.dumps" not in source


def test_no_test_hooks_in_mechanism() -> None:
    for path in _module_paths():
        text = path.read_text()
        for pattern in ("EVOLVE_FAKE", "MUTATE_FAKE"):
            assert pattern not in text, f"test hook {pattern!r} in {path}"


def _is_versioned_superpowers_document(path: str) -> bool:
    return path.startswith(("docs/superpowers/specs/", "docs/superpowers/plans/"))


def test_only_versioned_superpowers_specs_and_plans_are_allowed() -> None:
    assert _is_versioned_superpowers_document(
        "docs/superpowers/specs/approved-design.md"
    )
    assert _is_versioned_superpowers_document(
        "docs/superpowers/plans/approved-plan.md"
    )
    assert not _is_versioned_superpowers_document(
        "docs/superpowers/worktrees/temporary-copy.md"
    )
    assert not _is_versioned_superpowers_document(
        "docs/superpowers/sdd/2026-07-28-task/report.md"
    )


def test_local_superpowers_artifacts_are_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--", "docs/superpowers"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_artifacts = [
        path
        for path in result.stdout.splitlines()
        if not _is_versioned_superpowers_document(path)
    ]
    assert not tracked_artifacts, (
        "transient Superpowers artifacts must not be tracked: "
        f"{tracked_artifacts}"
    )


def test_stamped_fields_defined_once() -> None:
    defining = [
        path.relative_to(SRC).as_posix()
        for path in _module_paths()
        if re.search(r"^STAMPED_FIELDS\s*=", path.read_text(), re.M)
    ]
    assert defining == ["archive.py"], (
        f"STAMPED_FIELDS defined in {defining}; single source of truth is archive.py - import it"
    )


def test_operator_registry_is_the_single_source() -> None:
    # Every *Operator ABC is registered exactly once, and sdk.py dispatches each —
    # so adding an operator is one registry entry that everything else derives from.
    defined = {
        name
        for name, obj in vars(interfaces).items()
        if inspect.isclass(obj) and name.endswith("Operator") and obj is not object
    }
    registered = {spec.abc.__name__ for spec in interfaces.OPERATORS}
    assert defined == registered, f"unregistered operator ABCs: {defined ^ registered}"
    assert len(registered) == len(interfaces.OPERATORS), "duplicate operator in the registry"

    sdk_source = (SRC / "frozen" / "sdk.py").read_text()
    for spec in interfaces.OPERATORS:
        assert spec.abc.__name__ in sdk_source, f"sdk.py must dispatch {spec.abc.__name__}"
    # config's kind lists are derived, not hand-kept
    from evolve import config

    assert set(config.OPERATOR_KINDS) | set(config.OPTIONAL_OPERATOR_KINDS) == {s.kind for s in interfaces.OPERATORS}
