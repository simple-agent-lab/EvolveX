#!/usr/bin/env python3
"""driver — mechanism-side conductor for the 10-step inner loop (design §02).

Replaces the bash driver: operators still run as isolated subprocesses (crash
isolation, small mutation diffs), but orchestration, exit-code semantics,
output validation, and the FROZEN guard live here in one readable place.
Agent mode replaces this file with an orchestrating agent reading program.md.

Usage: driver.py [N]   (default 5 generations; loop.sh is a thin wrapper)
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent
sys.path.insert(0, str(WS))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # keep FROZEN digests byte-stable

from FROZEN.contracts import protocol  # noqa: E402

GIT = ["git", "-c", "advice.detachedHead=false"]


class NotWired(RuntimeError):
    """A capability from a later milestone was hit — abort loudly, don't loop."""


class GenDiscard(RuntimeError):
    """This generation is bad (operator failure / guard trip) — discard, continue."""


def log(msg: str) -> None:
    print(f"[driver] {msg}", file=sys.stderr)


def sh(cmd, check=True, capture=False) -> str:
    p = subprocess.run(cmd, cwd=WS, capture_output=capture, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}"
                           + (f"\n{p.stderr}" if capture else ""))
    return p.stdout if capture else ""


def frozen_digest() -> str:
    h = hashlib.sha256()
    root = WS / "FROZEN"
    for p in sorted(root.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def next_id() -> int:
    arc = WS / "archive.jsonl"
    if not arc.exists():
        return 0
    ids = [json.loads(l)["genid"] for l in arc.read_text().splitlines() if l.strip()]
    return max(ids, default=-1) + 1


def run_operator(name: str, **cli) -> dict:
    """Run one operator as a subprocess, enforce the protocol at the boundary,
    persist its output to runs/gen-<id>/<name>.json for inspectability."""
    spec = protocol.OPERATORS[name]
    cmd = [sys.executable, str(WS / spec.script)]
    for key, value in cli.items():
        if value is True:
            cmd.append(f"--{key}")
        elif value is not None and value is not False:
            cmd += [f"--{key}", str(value)]
    p = subprocess.run(cmd, cwd=WS, capture_output=True, text=True)
    if p.returncode == protocol.EXIT_NOT_WIRED:
        raise NotWired(f"{name}: {p.stderr.strip()}")
    if p.returncode != protocol.EXIT_OK:
        raise GenDiscard(f"{name} failed (exit {p.returncode}): {p.stderr.strip()[:300]}")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise GenDiscard(f"{name}: stdout is not JSON: {p.stdout.strip()[:120]!r}")
    errs = protocol.validate(data, spec.output)
    if errs:
        raise GenDiscard(f"{name}: output violates protocol: {errs}")
    gen = cli.get("gen")
    if gen is not None:
        out = WS / "runs" / f"gen-{gen}" / f"{name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return data


def frozen_step(script: str, gen: int) -> None:
    p = subprocess.run(["bash", str(WS / "FROZEN" / script), str(gen)],
                       cwd=WS, capture_output=True, text=True)
    if p.returncode == protocol.EXIT_NOT_WIRED:
        raise NotWired(f"FROZEN/{script}: {p.stderr.strip()}")
    if p.returncode != 0:
        raise GenDiscard(f"FROZEN/{script} failed: {p.stderr.strip()[:300]}")


def cleanup_worktree() -> None:
    sh(GIT + ["checkout", "-q", "--", "."])
    sh(["git", "clean", "-qfd", "candidate", "operators", "meta"], check=False)


def bootstrap() -> None:
    log("bootstrap: eval + record gen 0")
    sh(GIT + ["checkout", "-q", "gen/0"])
    (WS / "runs" / "gen-0").mkdir(parents=True, exist_ok=True)
    frozen_step("eval.sh", 0)
    frozen_step("stamp.sh", 0)
    run_operator("gate", gen=0)
    run_operator("record", gen=0, genesis=True, note="genesis")


def generation() -> None:
    parent = run_operator("select")["parent"]                       # (1)
    gen = next_id()
    log(f"gen {gen} <- parent {parent}")

    sh(GIT + ["checkout", "-q", f"gen/{parent}"])                   # (2)
    (WS / "runs" / f"gen-{gen}").mkdir(parents=True, exist_ok=True)
    fz_before = frozen_digest()

    try:
        run_operator("rollout", gen=gen, parent=parent)             # (3)
        mutate = run_operator("mutate", gen=gen, parent=parent)     # (4)
        novelty = run_operator("novelty", gen=gen, parent=parent)   # (5)

        if frozen_digest() != fz_before:
            raise GenDiscard("mutation touched FROZEN/ — reverting")
        if not novelty["accept"]:
            raise GenDiscard("novelty reject (re-mutate retries land at M3)")
    except GenDiscard:
        cleanup_worktree()
        raise

    sh(["git", "add", "-A"])                                        # (6)
    sh(["git", "commit", "-qm", f"gen {gen} (parent {parent}): {mutate['note']}"])
    sh(["git", "tag", f"gen/{gen}"])

    # (self-reference admission: FROZEN/contracts + meta_eval gate lands at M3)

    frozen_step("eval.sh", gen)                                     # (7)
    frozen_step("stamp.sh", gen)
    run_operator("gate", gen=gen)                                   # (8)
    run_operator("record", gen=gen, parent=parent)                  # (9)
    run_operator("reflect", gen=gen)                                # (10)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    p = subprocess.run(["bash", str(WS / "operators" / "preflight.sh")],
                       cwd=WS, capture_output=True, text=True)
    if p.returncode != 0:
        log(p.stderr.strip())
        return 1

    if next_id() == 0:
        bootstrap()

    done = discarded = 0
    for _ in range(n):
        try:
            generation()
            done += 1
        except GenDiscard as e:
            log(f"discard: {e}")
            discarded += 1
        except NotWired as e:
            log(f"abort: {e}")
            return protocol.EXIT_NOT_WIRED

    best = "n/a"
    best_path = WS / "best_ever.json"
    if best_path.exists():
        best = json.loads(best_path.read_text())["score"]
    total = len((WS / "archive.jsonl").read_text().splitlines())
    log(f"done: {done} gens ({discarded} discarded), {total} ledger entries, best-ever={best}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
