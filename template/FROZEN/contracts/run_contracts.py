#!/usr/bin/env python3
"""FROZEN — operator contract tests (credit-assignment Tier 0, design v0.4 §06-C).

Validates every operator's interface against a disposable copy of the
workspace, and verifies FROZEN write-protection. A self-modified operator must
pass these before it may even reach the meta_eval admission gate (M3) — this is
the cheap first gate that catches the most common self-reference death:
shipping a broken operator that kills the whole lineage.

Usage: run_contracts.py [--workspace <dir>]   (default: the workspace this file lives in)
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

SCHEMA_V2_KEYS = [
    "genid", "parent", "tag",
    "score", "score_ci", "task_vector", "harness_version", "audit",
    "cost", "mutated", "operator_diff", "operator_reverted",
    "weights_ref", "train",
    "status", "valid_parent", "used_insights", "predicted_fixes",
    "verified_fixes", "novelty", "note",
]

OPERATORS = ["select.py", "rollout.py", "mutate.py", "novelty.py",
             "gate.py", "record.py", "reflect.py"]

MUTABLE_PREFIXES = ("candidate/", "operators/", "meta/", "program.md")

FAILURES = []


def fail(name: str, msg: str) -> None:
    FAILURES.append(f"{name}: {msg}")
    print(f"  FAIL  {name}: {msg}")


def ok(name: str) -> None:
    print(f"  ok    {name}")


def run(cmd, cwd, timeout=60):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def frozen_digest(ws: str) -> str:
    h = hashlib.sha256()
    froot = os.path.join(ws, "FROZEN")
    for root, dirs, files in os.walk(froot):
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(root, name)
            h.update(os.path.relpath(p, froot).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def build_fixture(src_ws: str, tmp: str) -> str:
    """Copy the workspace (code only) and seed a minimal 3-gen evolution state."""
    ws = os.path.join(tmp, "ws")
    shutil.copytree(
        src_ws, ws,
        ignore=shutil.ignore_patterns(".git", "runs", "ckpts", "manifests", "__pycache__"),
    )
    for d in ("runs", "insights", "manifests", "ckpts"):
        os.makedirs(os.path.join(ws, d), exist_ok=True)

    git = ["git", "-c", "user.name=contracts", "-c", "user.email=contracts@local"]
    run(["git", "init", "-q", "-b", "main"], ws)
    run(git + ["add", "-A"], ws)
    run(git + ["commit", "-qm", "fixture"], ws)
    for g in (0, 1, 2):
        run(["git", "tag", f"gen/{g}"], ws)

    nodes = [
        {"genid": 0, "parent": None, "score": 0.40, "valid_parent": True},
        {"genid": 1, "parent": 0, "score": 0.55, "valid_parent": True},
        {"genid": 2, "parent": 0, "score": 0.35, "valid_parent": False},
    ]
    with open(os.path.join(ws, "archive.jsonl"), "w") as f:
        for n in nodes:
            f.write(json.dumps(n) + "\n")

    for g in (1, 2):
        d = os.path.join(ws, "runs", f"gen-{g}")
        os.makedirs(d, exist_ok=True)
        json.dump(
            {"genid": g, "score": 0.5 + g / 10, "score_ci": [0.3, 0.7],
             "task_vector": "10110", "harness_version": "stub-v1", "audit": "clean"},
            open(os.path.join(d, "stamp.json"), "w"),
        )
        json.dump(
            {"note": "fixture", "predicted_fixes": [], "used_insights": [],
             "cost": {"tokens": 0, "eval_minutes": 0}},
            open(os.path.join(d, "mutate.json"), "w"),
        )
        json.dump({"novelty": 1.0, "accept": True}, open(os.path.join(d, "novelty.json"), "w"))
        json.dump({"status": "keep", "valid_parent": True}, open(os.path.join(d, "gate.json"), "w"))
    return ws


def parse_json_stdout(name: str, proc) -> dict:
    if proc.returncode != 0:
        fail(name, f"exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return {}
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        fail(name, f"stdout is not JSON: {proc.stdout.strip()[:120]!r}")
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    default_ws = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--workspace", default=default_ws)
    a = ap.parse_args()
    src = os.path.abspath(a.workspace)
    print(f"contracts: workspace={src}")

    # -- presence & executability ------------------------------------------
    for f in OPERATORS:
        p = os.path.join(src, "operators", f)
        if not os.path.exists(p):
            fail("presence", f"operators/{f} missing")
    for f in ("eval.sh", "stamp.sh"):
        if not os.path.exists(os.path.join(src, "FROZEN", f)):
            fail("presence", f"FROZEN/{f} missing")
    if FAILURES:
        print(f"contracts: {len(FAILURES)} violation(s)")
        return 1
    ok("presence")

    tmp = tempfile.mkdtemp(prefix="contracts-")
    try:
        ws = build_fixture(src, tmp)
        fz_before = frozen_digest(ws)
        py = sys.executable

        # -- select: must return a valid_parent genid that exists ----------
        j = parse_json_stdout("select", run([py, "operators/select.py"], ws))
        if j:
            if j.get("parent") not in (0, 1):
                fail("select", f"parent={j.get('parent')!r} is not a valid_parent genid from the archive")
            else:
                ok("select")

        # -- gate: legal status/valid_parent over a frozen stamp -----------
        j = parse_json_stdout("gate", run([py, "operators/gate.py", "--gen", "2"], ws))
        if j:
            if j.get("status") not in ("keep", "discard") or not isinstance(j.get("valid_parent"), bool):
                fail("gate", f"illegal output {j}")
            else:
                ok("gate")

        # -- rollout / novelty / reflect: schema-shaped JSON ---------------
        j = parse_json_stdout("rollout", run([py, "operators/rollout.py", "--gen", "1", "--parent", "0"], ws))
        if j and j.get("ok") is not True:
            fail("rollout", f"missing ok=true: {j}")
        elif j:
            ok("rollout")

        j = parse_json_stdout("novelty", run([py, "operators/novelty.py", "--gen", "1", "--parent", "0"], ws))
        if j and not isinstance(j.get("accept"), bool):
            fail("novelty", f"accept must be bool: {j}")
        elif j:
            ok("novelty")

        j = parse_json_stdout("reflect", run([py, "operators/reflect.py", "--gen", "1"], ws))
        if j and not isinstance(j.get("ops"), list):
            fail("reflect", f"ops must be a list: {j}")
        elif j:
            ok("reflect")

        # -- mutate: only mutable paths, never FROZEN -----------------------
        proc = run([py, "operators/mutate.py", "--gen", "3", "--parent", "1"], ws)
        j = parse_json_stdout("mutate", proc)
        if j and "note" not in j:
            fail("mutate", f"missing note: {j}")
        touched = run(["git", "status", "--porcelain"], ws).stdout.splitlines()
        bad = []
        for line in touched:
            path = line[3:].strip().strip('"')
            if path.startswith("FROZEN/"):
                bad.append(path)
            elif path and not path.startswith(MUTABLE_PREFIXES):
                bad.append(path)
        if bad:
            fail("mutate", f"touched non-mutable paths: {bad}")
        elif j:
            ok("mutate")

        # -- record: schema v2, frozen fields only from the stamp ----------
        proc = run([py, "operators/record.py", "--gen", "2", "--parent", "0"], ws)
        j = parse_json_stdout("record", proc)
        if j:
            missing = [k for k in SCHEMA_V2_KEYS if k not in j]
            stamp = json.load(open(os.path.join(ws, "runs", "gen-2", "stamp.json")))
            if missing:
                fail("record", f"schema v2 keys missing: {missing}")
            elif j["score"] != stamp["score"] or j["task_vector"] != stamp["task_vector"]:
                fail("record", "frozen fields do not match the stamp")
            else:
                ok("record")
        # forging must fail: no score argument may exist
        proc = run([py, "operators/record.py", "--gen", "2", "--parent", "0", "--score", "0.99"], ws)
        if proc.returncode == 0:
            fail("record-forge", "record.py accepted a --score argument (invariant #2 violation)")
        else:
            ok("record-forge (rejected as required)")

        # -- FROZEN write-protection across everything above ----------------
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
