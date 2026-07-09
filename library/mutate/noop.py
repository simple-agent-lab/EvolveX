"""No-op mutate writes valid artifacts without editing the checkout.

It is the baseline recipe for mutation-disabled runs.
"""

# ruff: noqa: E402

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != os.path.dirname(os.path.abspath(__file__))]

from evolve.frozen import sdk
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.git import head_tag, working_tree_changed_paths
from evolve.surface import check_paths, surface_patterns


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _safe_usage(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {"usd": 0}
    normalized = dict(usage)
    usd = normalized.get("usd", 0)
    normalized["usd"] = usd if isinstance(usd, (int, float)) and not isinstance(usd, bool) else 0
    return normalized


def _surface_rule_lists(checkout: Path | str) -> tuple[list[str], list[str]]:
    try:
        return surface_patterns(Path(checkout))
    except Exception:
        return ["target/**"], []


def _surface_check(checkout: Path | str = ".", parent: str | None = None) -> dict[str, Any]:
    root = Path(checkout).resolve()
    include, exclude = _surface_rule_lists(root)
    base = parent or head_tag(root) or "gen/0"
    mutated = working_tree_changed_paths(root, base)
    violations = check_paths(mutated, include, exclude)
    return {"ok": not violations, "mutated": mutated, "violations": violations}


def _repair_surface_path(path: str, checkout: Path | str = ".") -> str | None:
    candidate = Path(checkout) / path
    rel = Path(path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return None
    subprocess.run(["git", "checkout", "--", path], cwd=checkout, text=True, capture_output=True, check=False)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", path], cwd=checkout, text=True, capture_output=True, check=False
    )
    if status.stdout.startswith("??"):
        if candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
        return "removed"
    return "reverted" if candidate.exists() else None


def _fallback_surface_check(checkout: Path | str = ".") -> dict[str, Any]:
    root = Path(checkout)
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--"], cwd=root, text=True, capture_output=True, check=False
    )
    changed = [line for line in tracked.stdout.splitlines() if line]
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False)
    for line in status.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if path not in changed:
            changed.append(path)
    include, exclude = _surface_rule_lists(root)
    violations = check_paths(changed, include, exclude)
    return {"ok": not violations, "mutated": changed, "violations": violations}


def _checked_surface(
    mutate_dir: Path, notes: list[str], changed: list[str], checkout: Path | str = "."
) -> dict[str, Any]:
    try:
        result = _surface_check(checkout)
    except Exception:
        try:
            result = _fallback_surface_check(checkout)
        except Exception as exc:
            result = {"ok": False, "mutated": changed, "violations": [], "error": "surface-check failed: %s" % exc}
            _write_json(mutate_dir / "surface-check.json", result)
            return result
    if result.get("violations"):
        reverted: list[str] = []
        removed: list[str] = []
        for path in result["violations"]:
            action = _repair_surface_path(path, checkout)
            if action == "reverted":
                reverted.append(path)
            elif action == "removed":
                removed.append(path)
        if reverted or removed:
            details = []
            if reverted:
                details.append("reverted: %s" % ", ".join(reverted))
            if removed:
                details.append("removed untracked: %s" % ", ".join(removed))
            notes.append("repaired surface violations by %s" % "; ".join(details))
        try:
            result = _surface_check(checkout)
        except Exception:
            try:
                result = _fallback_surface_check(checkout)
            except Exception as exc:
                result = {"ok": False, "mutated": changed, "violations": [], "error": "surface-check failed: %s" % exc}
    _write_json(mutate_dir / "surface-check.json", result)
    return result


def _write_mutate_artifacts(
    *,
    run_dir: Path,
    notes: list[str],
    usage: dict[str, Any] | None = None,
    variant: str,
    surface: dict[str, Any] | None = None,
    changed: list[str] | None = None,
) -> dict[str, Any]:
    mutate_dir = run_dir / "mutate"
    mutate_dir.mkdir(parents=True, exist_ok=True)
    notes.extend(["written-by: operators/mutate.py", "variant: %s" % variant])
    if surface is None:
        surface = {"ok": True, "mutated": changed or [], "violations": []}
    _write_json(mutate_dir / "surface-check.json", surface)
    usage_payload = _safe_usage(usage or {"usd": 0})
    (mutate_dir / "rationale.md").write_text("\n".join(notes) + "\n")
    (mutate_dir / "predicted_fixes.json").write_text("[]\n")
    _write_json(mutate_dir / "usage.json", usage_payload)
    return usage_payload


class NoopMutate(MutateOperator):
    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        changed: list[str] = []
        notes: list[str] = []
        surface = _checked_surface(ctx.run_dir / "mutate", notes, changed, checkout)
        usage = _write_mutate_artifacts(
            run_dir=ctx.run_dir,
            notes=notes,
            usage={"usd": 0},
            variant="noop",
            surface=surface,
            changed=changed,
        )
        if not surface.get("ok"):
            raise SystemExit(1)
        return MutateResult(changed=changed, notes=notes, usage=usage)


if __name__ == "__main__":
    sdk.main(NoopMutate)
