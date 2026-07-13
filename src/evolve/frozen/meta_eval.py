from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

OPERATOR_PATHS = ("operators", "program.md")


def operator_surface_changed(mutated: list[str]) -> bool:
    return any(p == "program.md" or p.startswith("operators/") for p in mutated)


def _sh(cmd: list[str], cwd: Path, *, check: bool = True, env: dict | None = None, timeout: float = 600):
    merged = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", EVOLVE_IN_META_EVAL="1")
    if env:
        merged.update(env)
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=merged,
                            start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except BaseException as exc:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except BaseException:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            while True:
                try:
                    stdout, stderr = proc.communicate()
                    break
                except KeyboardInterrupt:
                    continue
        if isinstance(exc, subprocess.TimeoutExpired):
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout or exc.output, stderr=stderr or exc.stderr) from exc
        raise
    completed = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if check:
        completed.check_returncode()
    return completed


def _extract(workspace: Path, rev: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    blob = subprocess.run(["git", "-C", str(workspace), "archive", rev], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=blob, check=True)


def _write_genesis(tree: Path) -> None:
    splits = tree / "evaluator" / "splits.json"
    task_hash = hashlib.sha256(splits.read_bytes()).hexdigest() if splits.exists() else ""
    ev_tree = _sh(["git", "rev-parse", "HEAD:evaluator"], tree, check=False).stdout.strip()
    row = {
        "genid": "0", "parent": None,
        "tag": "gen/0", "score": 1.0,
        "status": "complete", "task_set_hash": task_hash,
        "evaluator_tree": ev_tree,
        "valid_parent": True,
        "verdict": "keep",
        "reason": "meta-eval replay genesis",
        "mutated": [],
        "surface_violations": [],
        "predicted_fixes": [],
        "note": "replay", "cost": {"usd": 0, "wall_s": 0},
    }
    (tree / "archive.jsonl").write_text(json.dumps(row) + "\n")


def _replay(tree: Path, k: int, seed: str, *, timeout_s: float = 600) -> float:
    git = ["git", "-c", "user.name=meta-eval", "-c", "user.email=meta@local"]
    _sh(["git", "init", "-q", "-b", "main"], tree)
    _sh(git + ["add", "-A"], tree)
    _sh(git + ["commit", "-qm", "replay-genesis"], tree)
    _sh(["git", "tag", "gen/0"], tree)
    _write_genesis(tree)
    cmd = [sys.executable, "-m", "evolve", "run", ".", "--max-generations", str(k)]
    env = {"EVOLVE_HOME": str(tree / ".meta-home"), "EVOLVE_SEED": str(seed)}
    result = _sh(cmd, tree, check=False, env=env, timeout=timeout_s)
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


def admit(workspace: Path, parent_tag: str, child_checkout: Path, *, k: int = 2, margin: float = 0.05,
          seed: str = "meta-eval", timeout_s: float = 600) -> dict:
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
        verdict["old_best"] = _replay(old_tree, k, seed, timeout_s=timeout_s)
        verdict["new_best"] = _replay(new_tree, k, seed, timeout_s=timeout_s)
        verdict["admitted"] = verdict["new_best"] >= verdict["old_best"] - margin
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        verdict["error"] = str(exc)[:300]  # fail-closed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return verdict
