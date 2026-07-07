#!/usr/bin/env python3
"""FROZEN — self-reference admission gate (credit-assignment Tier 2, design
§06-C): propose-evaluate-accept for operator changes.

The confound-free replay: both sides start from the PARENT's tree (same
candidate, same everything), differing only in operators/ + meta/ +
program.md — old side keeps the parent's, new side takes this commit's.
Each side replays K micro-generations in a disposable copy (fresh git, stub
harness, fixed seed); the new operator set must be non-inferior
(best score >= old best - margin) to be admitted.

Fail-closed: any operational failure on either side rejects the change.
The protocol lives here because the thing being evaluated must not own its
evaluator. Operators/agents have no write access to this file.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]

OPERATOR_PATHS = ("operators", "meta", "program.md")


def sh(cmd, cwd, env=None, timeout=600):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=e)


def extract(rev: str, dest: Path, paths=()) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    p1 = subprocess.Popen(["git", "archive", rev, *paths], cwd=WS, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["tar", "-x", "-C", str(dest)], stdin=p1.stdout)
    p1.stdout.close()
    p2.communicate()
    if p1.wait() != 0 or p2.returncode != 0:
        raise RuntimeError(f"git archive {rev} failed")


def replay(tree: Path, k: int) -> float:
    """Fresh repo + K micro-generations on the stub harness; returns best score."""
    git = ["git", "-c", "user.name=meta-eval", "-c", "user.email=meta@local"]
    sh(["git", "init", "-q", "-b", "main"], tree)
    sh(git + ["add", "-A"], tree)
    r = sh(git + ["commit", "-qm", "replay-genesis"], tree)
    if r.returncode != 0:
        raise RuntimeError(f"replay init failed: {r.stderr}")
    sh(["git", "tag", "gen/0"], tree)
    for d in ("runs", "insights", "manifests", "ckpts"):
        (tree / d).mkdir(exist_ok=True)

    r = sh([sys.executable, "driver.py", str(k)], tree,
           env={"HARNESS_STUB": "1", "EVOLVE_SEED": "meta-eval",
                "EVOLVE_IN_META_EVAL": "1"})
    if r.returncode != 0:
        raise RuntimeError(f"replay driver failed: {r.stderr.strip()[:300]}")
    arc = tree / "archive.jsonl"
    scores = [json.loads(l)["score"] for l in arc.read_text().splitlines() if l.strip()]
    if not scores:
        raise RuntimeError("replay produced an empty ledger")
    return max(scores)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="parent rev (old operators)")
    ap.add_argument("--new", required=True, help="candidate rev (new operators)")
    ap.add_argument("--k", type=int, default=int(os.environ.get("META_EVAL_K", "2")))
    ap.add_argument("--margin", type=float,
                    default=float(os.environ.get("META_EVAL_MARGIN", "0.05")))
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="meta-eval-"))
    verdict = {"admitted": False, "k": a.k, "margin": a.margin,
               "old": a.old, "new": a.new}
    try:
        old_tree, new_tree = tmp / "old", tmp / "new"
        # both sides = parent tree; new side swaps in the new operator set only
        extract(a.old, old_tree)
        extract(a.old, new_tree)
        for path in OPERATOR_PATHS:
            target = new_tree / path
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        extract(a.new, new_tree, paths=OPERATOR_PATHS)

        verdict["old_best"] = replay(old_tree, a.k)
        verdict["new_best"] = replay(new_tree, a.k)
        verdict["admitted"] = verdict["new_best"] >= verdict["old_best"] - a.margin
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        verdict["error"] = str(e)[:300]  # fail-closed: admitted stays False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
