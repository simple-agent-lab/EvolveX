#!/usr/bin/env python3
"""FROZEN — Tier-0 operator contract tests, driven by protocol.py.

There are no hand-written interface assertions here: presence, CLI, output
shape, and write scopes all come from the OPERATORS registry, so protocol.py
is the single place the interface is defined. A self-modified operator must
pass these before it may reach the meta_eval admission gate (M3) — the cheap
first gate that catches the most common self-reference death: a broken
operator killing the whole lineage.

Usage: run_contracts.py [--workspace <dir>]
Exit 0 = all contracts hold; exit 1 = at least one violation (offender named).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))
from FROZEN.contracts import protocol  # noqa: E402

# fixture CLI values per operator (fixture seeds gens 0/1/2; gen 3 is "next")
FIXTURE_CLI = {
    "select": {},
    "rollout": {"gen": 3, "parent": 1},
    "mutate": {"gen": 3, "parent": 1},
    "novelty": {"gen": 3, "parent": 1},
    "gate": {"gen": 2, "parent": 0},
    "record": {"gen": 2, "parent": 0},
    "reflect": {"gen": 2},
    "distill": {},  # fixture has no trajectories -> must succeed with an empty manifest
}

FAILURES = []


def fail(name, msg):
    FAILURES.append(f"{name}: {msg}")
    print(f"  FAIL  {name}: {msg}")


def ok(name):
    print(f"  ok    {name}")


def sh(cmd, cwd, timeout=60):
    # contracts always exercise operators against the stub harness — cheap,
    # deterministic, and independent of live infra
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HARNESS_STUB="1")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def frozen_digest(ws: Path) -> str:
    h = hashlib.sha256()
    root = ws / "FROZEN"
    for p in sorted(root.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def build_fixture(src: Path, tmp: Path) -> Path:
    """Copy the workspace (code only) and seed a minimal 3-gen evolution state."""
    ws = tmp / "ws"
    shutil.copytree(src, ws, ignore=shutil.ignore_patterns(
        ".git", "runs", "ckpts", "manifests", "__pycache__"))
    for d in ("runs", "insights", "manifests", "ckpts"):
        (ws / d).mkdir(exist_ok=True)

    git = ["git", "-c", "user.name=contracts", "-c", "user.email=contracts@local"]
    sh(["git", "init", "-q", "-b", "main"], ws)
    sh(git + ["add", "-A"], ws)
    sh(git + ["commit", "-qm", "fixture"], ws)
    for g in (0, 1, 2):
        sh(["git", "tag", f"gen/{g}"], ws)

    with open(ws / "archive.jsonl", "w") as f:
        for n in ({"genid": 0, "parent": None, "score": 0.40, "valid_parent": True},
                  {"genid": 1, "parent": 0, "score": 0.55, "valid_parent": True},
                  {"genid": 2, "parent": 0, "score": 0.35, "valid_parent": False}):
            f.write(json.dumps(n) + "\n")

    for g in (1, 2):
        d = ws / "runs" / f"gen-{g}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "stamp.json").write_text(json.dumps(
            {"genid": g, "score": 0.5 + g / 10, "score_ci": [0.3, 0.7],
             "task_vector": "10110", "harness_version": "stub-v1", "audit": "clean"}))
        (d / "mutate.json").write_text(json.dumps(
            {"note": "fixture", "predicted_fixes": [], "used_insights": [],
             "cost": {"tokens": 0, "eval_minutes": 0}}))
        (d / "novelty.json").write_text(json.dumps({"novelty": 1.0, "accept": True}))
        (d / "gate.json").write_text(json.dumps({"status": "keep", "valid_parent": True}))
    return ws


def reset_tree(ws: Path) -> None:
    sh(["git", "checkout", "-q", "--", "."], ws)
    sh(["git", "clean", "-qfd"], ws)


def touched_paths(ws: Path) -> list:
    out = sh(["git", "status", "--porcelain"], ws).stdout
    return [line[3:].strip().strip('"') for line in out.splitlines() if line.strip()]


def run_and_validate(ws: Path, name: str) -> dict:
    """Run one operator per its registry spec; validate output + write scope."""
    spec = protocol.OPERATORS[name]
    cmd = [sys.executable, str(ws / spec.script)]
    for key, value in FIXTURE_CLI[name].items():
        cmd += [f"--{key}", str(value)]
    proc = sh(cmd, ws)
    if proc.returncode != protocol.EXIT_OK:
        fail(name, f"exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return {}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        fail(name, f"stdout is not JSON: {proc.stdout.strip()[:120]!r}")
        return {}
    errs = protocol.validate(data, spec.output)
    if errs:
        fail(name, f"output violates protocol: {errs}")
        return {}

    bad = [p for p in touched_paths(ws)
           if p.startswith("FROZEN/") or not p.startswith(spec.write_scope or ("\0",))]
    if bad:
        fail(name, f"touched paths outside write scope {spec.write_scope}: {bad}")
        return {}
    ok(name)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(_HERE.parents[2]))
    a = ap.parse_args()
    src = Path(a.workspace).resolve()
    print(f"contracts: workspace={src} protocol=v{protocol.PROTOCOL_VERSION}")

    # -- presence: everything the registry + frozen core promise ------------
    missing = [s.script for s in protocol.OPERATORS.values() if not (src / s.script).exists()]
    missing += [f"FROZEN/{f}" for f in ("eval.sh", "stamp.sh", "sealed_eval.sh",
                                        "contracts/protocol.py", "contracts/oplib.py")
                if not (src / "FROZEN" / f).exists()]
    if missing:
        fail("presence", f"missing: {missing}")
        print(f"contracts: {len(FAILURES)} violation(s)")
        return 1
    ok("presence")

    tmp = Path(tempfile.mkdtemp(prefix="contracts-"))
    try:
        ws = build_fixture(src, tmp)
        fz_before = frozen_digest(ws)

        results = {}
        for name in protocol.OPERATORS:
            reset_tree(ws)
            results[name] = run_and_validate(ws, name)

        # -- semantic checks beyond shape -----------------------------------
        sel = results.get("select") or {}
        if sel and sel.get("parent") not in (0, 1):
            fail("select-semantic",
                 f"parent={sel.get('parent')!r} is not a valid_parent genid from the archive")
        elif sel:
            ok("select-semantic (parent is a valid_parent)")

        rec = results.get("record") or {}
        if rec:
            stamp = json.loads((ws / "runs" / "gen-2" / "stamp.json").read_text())
            if rec["score"] != stamp["score"] or rec["task_vector"] != stamp["task_vector"]:
                fail("record-semantic", "frozen fields do not match the stamp")
            else:
                ok("record-semantic (frozen fields == stamp)")

        # forging must fail: the protocol CLI has no score flag
        proc = sh([sys.executable, str(ws / "operators" / "record.py"),
                   "--gen", "2", "--parent", "0", "--score", "0.99"], ws)
        if proc.returncode == protocol.EXIT_OK:
            fail("record-forge", "record.py accepted a --score argument (invariant #2 violation)")
        else:
            ok("record-forge (rejected as required)")

        if frozen_digest(ws) != fz_before:
            fail("frozen-guard", "an operator modified FROZEN/ during contract runs")
        else:
            ok("frozen-guard")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"contracts: {len(FAILURES)} violation(s)")
        return 1
    print("contracts: all held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
