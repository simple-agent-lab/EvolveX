"""Enforces ARCHITECTURE.md and coding-style constraints.

When a rot pattern is caught in review, add an assertion here so the
suite accumulates immune memory.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from evolve.frozen import interfaces

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "evolve"
TOTAL_BUDGET = 4500  # simplified integrated framework with certificates and runtime identity
ROW = re.compile(r"^\| `([^`]+\.py)` \| (\d+) \|")
APPROVED_MODULES = {
    "__init__.py",
    "__main__.py",
    "agent.py",
    "archive.py",
    "asset_discovery.py",
    "cli.py",
    "config.py",
    "driver.py",
    "evaluation.py",
    "evaluator.py",
    "git.py",
    "operators.py",
    "patching.py",
    "population.py",
    "report.py",
    "runtime.py",
    "surface.py",
    "task_sets.py",
    "task_vectors.py",
    "workspace.py",
    # the frozen ring — the invariant-enforcers, grouped under frozen/
    "frozen/__init__.py",
    "frozen/interfaces.py",
    "frozen/sdk.py",
}


def _module_paths() -> list[Path]:
    """Every mechanism module — top-level plus the frozen ring."""
    return [*sorted(SRC.glob("*.py")), *sorted((SRC / "frozen").glob("*.py"))]


def _module_relpaths() -> set[str]:
    return {path.relative_to(SRC).as_posix() for path in _module_paths()}


def _budgets() -> dict[str, int]:
    budgets: dict[str, int] = {}
    for line in (ROOT / "ARCHITECTURE.md").read_text().splitlines():
        match = ROW.match(line)
        if match:
            budgets[match.group(1)] = int(match.group(2))
    assert budgets, "ARCHITECTURE.md module table not found"
    return budgets


def test_every_module_is_mapped_and_every_mapped_module_exists() -> None:
    budgets = _budgets()
    actual = _module_relpaths()
    assert actual == APPROVED_MODULES, (
        f"unexpected module set: actual={sorted(actual)}; "
        f"approved={sorted(APPROVED_MODULES)} - "
        "adding or removing a mechanism module requires updating "
        "tests/test_coherence.py and ARCHITECTURE.md in the same commit"
    )
    assert set(budgets) == APPROVED_MODULES, (
        f"ARCHITECTURE.md module set drifted: mapped={sorted(budgets)}; "
        f"approved={sorted(APPROVED_MODULES)} - "
        "keep the architecture map and pinned module set in lockstep"
    )
    assert actual == set(budgets), (
        f"unmapped modules: {sorted(actual - set(budgets))}; "
        f"mapped but missing: {sorted(set(budgets) - actual)} - "
        "a module needs a row and a one-line meaning in ARCHITECTURE.md "
        "in the same commit that creates it"
    )


def test_line_budgets_hold() -> None:
    budgets = _budgets()
    over: dict[str, tuple[int, int]] = {}
    total = 0
    for name, budget in budgets.items():
        lines = len((SRC / name).read_text().splitlines())
        total += lines
        if lines > budget:
            over[name] = (lines, budget)
    assert not over, (
        f"over budget: {over} - run a demolition pass or raise the "
        "budget in ARCHITECTURE.md with the reason in the commit message"
    )
    assert total <= TOTAL_BUDGET, (
        f"mechanism total {total} > {TOTAL_BUDGET} - something belongs in a workspace operator instead (spec rule)"
    )


def test_no_test_hooks_in_mechanism() -> None:
    for path in _module_paths():
        text = path.read_text()
        for pattern in ("EVOLVE_FAKE", "MUTATE_FAKE"):
            assert pattern not in text, f"test hook {pattern!r} in {path}"


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


def test_docs_do_not_describe_real_recipes_as_smoke_or_checkout_fallback() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "DESIGN.md",
        ROOT / "docs" / "glossary.md",
        ROOT / "recipes" / "README.md",
    ]
    text = "\n".join(path.read_text() for path in docs if path.exists())
    assert "solve.sh" not in text
    assert "run.sh" not in text
    assert "CheckoutTargetAgent" not in text
    assert "hyperagents-smoke" in text
    assert "target.harbor_agent:MiniSweSourceAgent" in text
