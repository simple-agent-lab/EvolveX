#!/usr/bin/env python3
"""FROZEN — thin operator SDK.

Removes the per-operator boilerplate (argparse, path resolution, JSON
emission, exit codes) while keeping operators as isolated subprocess scripts:
crash isolation stays, mutation diffs stay small, and a git checkout still
swaps a generation's whole behavior. Operators import exactly two things:
this module and their output type from protocol.py.

Usage:
    @operator_main("select")
    def main(args):
        ...
        return SelectOutput(parent=..., extras={"strategy": "..."})

    if __name__ == "__main__":
        main()
"""
import argparse
import json
import os
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))

from FROZEN.contracts import protocol  # noqa: E402


class OperatorError(Exception):
    """Raise inside an operator to fail this generation (exit EXIT_FAIL)."""


def ws_path(*parts) -> Path:
    return WS.joinpath(*parts)


def run_dir(gen: int) -> Path:
    d = ws_path("runs", f"gen-{gen}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text())


def write_json(path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def read_archive() -> list:
    p = ws_path("archive.jsonl")
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def append_ledger(entry: dict) -> None:
    """Ledger is append-only; record.py is its only sanctioned writer."""
    with open(ws_path("archive.jsonl"), "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def env_seed(salt: str = ""):
    """Honor EVOLVE_SEED (public env interface) for reproducible runs."""
    seed = os.environ.get("EVOLVE_SEED")
    return f"{seed}:{salt}" if seed else None


def operator_main(name: str):
    """Wire an operator function to the protocol CLI contract.

    Handles: argparse from the registry spec (unknown flags -> EXIT_USAGE, so
    forged arguments like --score die at the boundary), OperatorError ->
    EXIT_FAIL, output validation against the spec's type (an operator that
    violates its own protocol fails rather than feeding the driver garbage),
    JSON emission on stdout.
    """
    spec = protocol.OPERATORS[name]

    def deco(fn):
        def run(argv=None):
            ap = argparse.ArgumentParser(prog=spec.name, allow_abbrev=False)
            for a in spec.cli:
                if a.kind == "flag":
                    ap.add_argument(a.flag, action="store_true")
                else:
                    ap.add_argument(a.flag, type=int if a.kind == "int" else str,
                                    required=a.required, default=None)
            args = ap.parse_args(argv)
            try:
                out = fn(args)
            except OperatorError as e:
                print(f"{spec.name}: {e}", file=sys.stderr)
                sys.exit(protocol.EXIT_FAIL)
            data = protocol.payload(out)
            errs = protocol.validate(data, spec.output)
            if errs:
                print(f"{spec.name}: output violates protocol: {errs}", file=sys.stderr)
                sys.exit(protocol.EXIT_FAIL)
            print(json.dumps(data, ensure_ascii=False))
            return data

        return run

    return deco
