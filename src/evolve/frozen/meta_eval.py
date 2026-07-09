"""Self-modification admission gate (mechanism 1, DESIGN §2/§7).

When a mutation edits the operator surface (operators/, program.md) it must not
be trusted just because it ran — the thing being evaluated must not own its
evaluator. This runs a confound-free replay: both sides start from the PARENT
tree and differ only in the operator surface (old = parent's, new = the child's
uncommitted version). Each side replays K micro-generations on the stub harness
in a disposable git repo; the new operators are admitted only if they are
non-inferior (`new_best >= old_best - margin`). Fail-closed: any operational
error rejects the change.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The operator surface — scripts + per-verb strategy prose under operators/,
# plus whole-loop orchestration at program.md.
OPERATOR_PATHS = ("operators", "program.md")


def operator_surface_changed(mutated: list[str]) -> bool:
    return any(p == "program.md" or p.startswith("operators/") for p in mutated)


def _sh(cmd: list[str], cwd: Path, *, check: bool = True, env: dict | None = None, timeout: int = 600):
    merged = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", EVOLVE_IN_META_EVAL="1")
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=merged, check=check)


def _extract(workspace: Path, rev: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    blob = subprocess.run(["git", "-C", str(workspace), "archive", rev], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=blob, check=True)


def _write_genesis(tree: Path) -> None:
    splits = tree / "evaluator" / "splits.json"
    task_hash = hashlib.sha256(splits.read_bytes()).hexdigest() if splits.exists() else ""
    ev_tree = _sh(["git", "rev-parse", "HEAD:evaluator"], tree, check=False).stdout.strip()
    row = {
        "genid": "0",
        "parent": None,
        "tag": "gen/0",
        "score": 1.0,
        "status": "complete",
        "task_set_hash": task_hash,
        "evaluator_tree": ev_tree,
        "valid_parent": True,
        "verdict": "keep",
        "reason": "meta-eval replay genesis",
        "mutated": [],
        "surface_violations": [],
        "predicted_fixes": [],
        "note": "replay",
        "cost": {"usd": 0, "wall_s": 0},
    }
    (tree / "archive.jsonl").write_text(json.dumps(row) + "\n")


def _replay(tree: Path, k: int, seed: str) -> float:
    """Fresh repo plus K micro-generations; return the best score."""
    git = ["git", "-c", "user.name=meta-eval", "-c", "user.email=meta@local"]
    _sh(["git", "init", "-q", "-b", "main"], tree)
    _sh(git + ["add", "-A"], tree)
    _sh(git + ["commit", "-qm", "replay-genesis"], tree)
    _sh(["git", "tag", "gen/0"], tree)
    _write_genesis(tree)
    result = _sh(
        [sys.executable, "-m", "evolve", "run", ".", "--max-generations", str(k)],
        tree,
        check=False,
        env={"EVOLVE_HOME": str(tree / ".meta-home"), "EVOLVE_SEED": str(seed)},
    )
    if result.returncode != 0:
        raise RuntimeError(f"replay run failed: {result.stderr.strip()[:300]}")
    scores = [
        float(row["score"])
        for line in (tree / "archive.jsonl").read_text().splitlines()
        if line.strip()
        for row in [json.loads(line)]
        if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)
    ]
    if not scores:
        raise RuntimeError("replay produced an empty ledger")
    return max(scores)


def admit(
    workspace: Path, parent_tag: str, child_checkout: Path, *, k: int = 2, margin: float = 0.05, seed: str = "meta-eval"
) -> dict:
    """Propose-evaluate-accept for an operator-surface change. Returns a verdict
    dict with `admitted` (fail-closed to False on any error)."""
    tmp = Path(tempfile.mkdtemp(prefix="meta-eval-"))
    verdict: dict = {"admitted": False, "k": k, "margin": margin}
    try:
        old_tree, new_tree = tmp / "old", tmp / "new"
        _extract(workspace, parent_tag, old_tree)
        _extract(workspace, parent_tag, new_tree)
        for rel in OPERATOR_PATHS:  # new side keeps parent's tree, swaps only the operator surface
            src, dst = Path(child_checkout) / rel, new_tree / rel
            if dst.is_dir():
                shutil.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            elif src.exists():
                shutil.copy2(src, dst)
        verdict["old_best"] = _replay(old_tree, k, seed)
        verdict["new_best"] = _replay(new_tree, k, seed)
        verdict["admitted"] = verdict["new_best"] >= verdict["old_best"] - margin
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        verdict["error"] = str(exc)[:300]  # fail-closed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return verdict
