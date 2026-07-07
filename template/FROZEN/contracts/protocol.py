#!/usr/bin/env python3
"""FROZEN — the operator protocol: single source of truth for every interface
in the evolution loop.

Design (v0.4): the interface is mechanism, the implementation is evolvable.
Operators stay isolated subprocess scripts (crash isolation, small mutation
diffs, git-checkout swaps whole behaviors); this module owns everything about
HOW they are called and WHAT they must emit:

  - CLI convention per operator (flags, types)
  - output types (required keys closed, extra keys open — operators may evolve
    richer outputs without breaking the driver)
  - write scopes (which tracked paths an operator may modify; FROZEN/ never)
  - exit-code semantics
  - the ledger schema (v2)

JSON on stdout is only the wire format at the process boundary — never the
protocol itself. The driver and the contract tests both validate against the
types below, so there is exactly one place where the interface can change,
and changing required keys goes through the human front door
(PROTOCOL_VERSION bump, outside the loop), same as harness versioning.
"""
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Union, get_args, get_origin

PROTOCOL_VERSION = 1

# ---------------------------------------------------------------------------
# exit-code semantics (process boundary)
# ---------------------------------------------------------------------------
EXIT_OK = 0         # success; stdout carries one JSON object
EXIT_FAIL = 1       # operator failed -> the driver discards this generation
EXIT_USAGE = 2      # bad invocation (argparse convention; also: forged flags)
EXIT_NOT_WIRED = 3  # capability lands at a later milestone -> driver aborts loudly

ALLOWED_STATUS = ("keep", "discard")
ALLOWED_AUDIT = ("clean", "exploit", "pending")

# ---------------------------------------------------------------------------
# output types — required keys closed, extra keys open (put them in `extras`)
# ---------------------------------------------------------------------------


@dataclass
class SelectOutput:
    parent: int  # genid that exists in the archive and is a valid_parent
    extras: dict = field(default_factory=dict)


@dataclass
class RolloutOutput:
    ok: bool
    lane: str  # always "dev" — the canonical lane is FROZEN's, not an operator's
    extras: dict = field(default_factory=dict)


@dataclass
class MutateOutput:
    note: str
    predicted_fixes: list  # falsifiable claims; reflect verifies them next gen
    used_insights: list    # playbook ids injected into the prompt (credit backfill)
    cost: dict             # {"tokens": int, "eval_minutes": float}
    extras: dict = field(default_factory=dict)


@dataclass
class NoveltyOutput:
    novelty: float
    accept: bool
    extras: dict = field(default_factory=dict)


@dataclass
class GateOutput:
    status: str
    valid_parent: bool
    extras: dict = field(default_factory=dict)

    CHOICES = {"status": ALLOWED_STATUS}


@dataclass
class ReflectOutput:
    ops: list  # playbook delta operations (ADD/UPDATE/RETIRE) — never a rewrite
    extras: dict = field(default_factory=dict)


@dataclass
class DistillOutput:
    ok: bool
    manifest: str  # manifests/<name>.jsonl — every sample traces to (genid, task, hash)
    sft: int
    dpo: int
    extras: dict = field(default_factory=dict)


@dataclass
class Stamp:
    """Written only by FROZEN/stamp.sh (invariant #2). record.py copies these
    fields verbatim into the ledger and accepts them from nowhere else."""
    genid: int
    score: float
    score_ci: list
    task_vector: str
    harness_version: str
    audit: str

    CHOICES = {"audit": ALLOWED_AUDIT}


@dataclass
class LedgerEntry:
    """archive.jsonl line — schema v2 (design §08). Append-only; every key is
    present from M0 so later milestones fill values, never rework the schema."""
    genid: int
    parent: Optional[int]
    tag: str
    # -- frozen-stamped (copied from Stamp, never from args) --
    score: float
    score_ci: list
    task_vector: str
    harness_version: str
    audit: str
    # -- lineage & cost --
    cost: dict
    mutated: list
    operator_diff: Optional[str]
    operator_reverted: bool
    # -- weights-gen fields (filled from M6) --
    weights_ref: Optional[dict]
    train: Optional[dict]
    # -- evolvable judgement & memory --
    status: str
    valid_parent: bool
    used_insights: list
    predicted_fixes: list
    verified_fixes: list
    novelty: Optional[float]
    note: str
    extras: dict = field(default_factory=dict)

    CHOICES = {"status": ALLOWED_STATUS, "audit": ALLOWED_AUDIT}


# ---------------------------------------------------------------------------
# operator registry — CLI + output type + write scope per operator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArgDef:
    flag: str       # e.g. "--gen"
    kind: str       # "int" | "str" | "flag"
    required: bool = False


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    script: str
    cli: tuple
    output: type
    write_scope: tuple  # tracked-path prefixes this operator may modify.
    #                     This is the protocol BOUND (max allowed), not current
    #                     behavior. Untracked state (runs/gen-<id>/ scratch,
    #                     insights/, archive.jsonl append via record) is
    #                     governed by convention in PROTOCOL.md; FROZEN/ is
    #                     never writable and is guarded by digest everywhere.


_GEN = ArgDef("--gen", "int", required=True)
_PARENT = ArgDef("--parent", "int", required=True)

# mutate's bound is the M3 self-reference set; the M0 default only uses candidate/.
MUTATE_SCOPE = ("candidate/", "operators/", "meta/", "program.md")

OPERATORS = {
    "select": OperatorSpec("select", "operators/select.py",
                           cli=(), output=SelectOutput, write_scope=()),
    "rollout": OperatorSpec("rollout", "operators/rollout.py",
                            cli=(_GEN, _PARENT), output=RolloutOutput, write_scope=()),
    "mutate": OperatorSpec("mutate", "operators/mutate.py",
                           cli=(_GEN, _PARENT, ArgDef("--attempt", "int", required=False)),
                           output=MutateOutput, write_scope=MUTATE_SCOPE),
    "novelty": OperatorSpec("novelty", "operators/novelty.py",
                            cli=(_GEN, _PARENT), output=NoveltyOutput, write_scope=()),
    "gate": OperatorSpec("gate", "operators/gate.py",
                         cli=(_GEN, ArgDef("--parent", "int", required=False)),
                         output=GateOutput, write_scope=()),
    "record": OperatorSpec("record", "operators/record.py",
                           cli=(_GEN,
                                ArgDef("--parent", "int", required=False),
                                ArgDef("--genesis", "flag"),
                                ArgDef("--note", "str", required=False)),
                           output=LedgerEntry, write_scope=()),
    "reflect": OperatorSpec("reflect", "operators/reflect.py",
                            cli=(_GEN,), output=ReflectOutput, write_scope=()),
    # outer loop T2: trajectories -> training data (manifests/ is untracked state)
    "distill": OperatorSpec("distill", "operators/distill.py",
                            cli=(), output=DistillOutput, write_scope=()),
}

# environment variables that are part of the public interface
PUBLIC_ENV = ("HARNESS_STUB", "EVOLVE_SEED", "EVOLVE_SELECT_ALPHA")


# ---------------------------------------------------------------------------
# serialization + validation (the only JSON machinery anyone should write)
# ---------------------------------------------------------------------------


def payload(out) -> dict:
    """Dataclass -> wire dict. extras merge flat; protocol fields win on clash."""
    fields = {f.name: getattr(out, f.name)
              for f in dataclasses.fields(out) if f.name != "extras"}
    return {**getattr(out, "extras", {}), **fields}


def _type_ok(value, ann) -> bool:
    origin = get_origin(ann)
    if origin is Union:
        return any(_type_ok(value, a) for a in get_args(ann))
    if ann is type(None):
        return value is None
    if ann is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ann is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if ann is bool:
        return isinstance(value, bool)
    if ann is str:
        return isinstance(value, str)
    if ann is list or origin is list:
        return isinstance(value, list)
    if ann is dict or origin is dict:
        return isinstance(value, dict)
    return True  # unknown annotations don't fail closed — extend _type_ok instead


def validate(data: dict, cls) -> list:
    """Check a wire dict against an output type. Required keys closed
    (missing/mistyped fails), extra keys open (ignored)."""
    errs = []
    if not isinstance(data, dict):
        return [f"output is not a JSON object: {type(data).__name__}"]
    choices = getattr(cls, "CHOICES", {})
    for f in dataclasses.fields(cls):
        if f.name == "extras":
            continue
        if f.name not in data:
            errs.append(f"missing required key: {f.name}")
            continue
        if not _type_ok(data[f.name], f.type):
            errs.append(f"key {f.name!r}: {data[f.name]!r} does not match {f.type}")
        if f.name in choices and data[f.name] not in choices[f.name]:
            errs.append(f"key {f.name!r}: {data[f.name]!r} not in {choices[f.name]}")
    return errs
