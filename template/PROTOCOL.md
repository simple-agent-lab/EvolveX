# PROTOCOL.md — the operator protocol (human/LLM-readable rendition)

The machine-readable authority is `FROZEN/contracts/protocol.py` (the
interface is mechanism; only implementations evolve — on any conflict,
protocol.py wins). This document travels with the lineage and is injected
into mutation context: **when you edit an operator, you must preserve the
interfaces declared here.**

Current `PROTOCOL_VERSION = 1`.

## Invocation convention

Every operator is a standalone executable script running in a subprocess
(crash isolation). Arguments are scalar flags only; output is a **single
JSON object on stdout**. JSON is just the wire format at the process
boundary — the protocol itself is the set of types in protocol.py.

## Exit codes

| code | meaning | driver's reaction |
|---|---|---|
| 0 | success; stdout carries one JSON object | continue |
| 1 | operator failure | discard this generation, loop continues |
| 2 | usage error (argparse; incl. forged flags like `--score` to record) | discard |
| 3 | capability belongs to a later milestone (not wired) | stop the loop, loudly |

## Per-operator interfaces

| operator | CLI | required output keys | writable (tracked paths) |
|---|---|---|---|
| select | — | `parent: int` (must be a valid_parent genid in the archive) | none |
| rollout | `--gen --parent` | `ok: bool, lane: "dev"` | none |
| mutate | `--gen --parent [--attempt]` | `note, predicted_fixes, used_insights, cost` | `candidate/` (M3+: `operators/ meta/ program.md config.json`) |
| novelty | `--gen --parent` | `novelty: float, accept: bool` | none |
| gate | `--gen [--parent]` | `status: keep\|discard, valid_parent: bool` | none |
| record | `--gen [--parent\|--genesis] [--note]` | all 21 LedgerEntry keys (schema v2) | none |
| reflect | `--gen` | `ops: list` (playbook delta ops — never a rewrite) | none |
| distill | — | `ok, manifest, sft, dpo` (every sample traceable) | none |

**Extension rule: required keys closed, extra keys open.** Operators may
evolve richer outputs (put them in `extras`; they serialize flat) — the
driver relies only on required keys. Adding optional keys or new operators
is always allowed; changing required keys = a human walks through the front
door outside the loop (bump PROTOCOL_VERSION), the same door as harness
versioning.

## Filesystem conventions (state outside git)

- `runs/gen-<id>/` — per-generation scratch; any operator may write; the
  driver persists every operator's stdout as `runs/gen-<id>/<name>.json`
  (inspectable, post-mortem-able).
- `archive.jsonl` — append-only, via record only; frozen fields come only
  from `runs/gen-<id>/stamp.json` (invariant #2).
- `insights/` — written only by reflect (delta ops).
- `FROZEN/` — **read-only for every operator, always**. The driver digests
  it around mutations and voids the generation on any change; contracts
  check it too.

## Public environment variables

| variable | effect |
|---|---|
| `HARNESS_STUB` | 1 = stub harness (real harbor is M1-infra) |
| `EVOLVE_SEED` | reproducible runs |
| `EVOLVE_SELECT_ALPHA` | parent-balancing α (default 1.0) |
| `EVOLVE_MUTATE_VARIANT` | fixed / agent / noop (overrides config.json; `llm` is a legacy alias for agent) |
| `EVOLVE_MUTATOR_CMD` | custom mutator command for the agent variant (reads `$MUTATION_PROMPT`, edits files, writes `$MUTATION_REPORT`); unset = headless claude CLI |
| `EVOLVE_MUTATOR_TIMEOUT` | per-mutation timeout in seconds for the agent variant (default 600) |
| `EVOLVE_NOVELTY_THRESHOLD` | mutation dedup similarity threshold (default 0.98) |
| `EVOLVE_PLAYBOOK_CAP` | max active insight entries (default 80) |
| `EVOLVE_DISTILL_CAP` | per-task sample cap in distill (default 3) |
| `EVOLVE_TRAIN_PLATEAU` | K: trigger the outer loop after best-ever stalls K gens (default off) |
| `EVOLVE_AUDIT_JUMP` | quarantine (audit=pending) any score jumping past the champion by this margin (default off) |
| `META_EVAL_K` / `META_EVAL_MARGIN` | admission replay generations (2) and non-inferiority margin (0.05) |

`EVOLVE_IN_META_EVAL` and `EVOLVE_UV` are internal (replay recursion guard /
uv re-exec guard), not part of the public interface.

## Validation points (all driven by the same protocol.py)

1. **driver**: validates every operator output at the call boundary
   (defense in depth).
2. **oplib**: operators self-validate before emitting — an operator that
   violates its own protocol fails instead of feeding the driver garbage.
3. **contracts** (`./evolve contracts`): the Tier-0 gate every self-modified
   operator must pass; presence / CLI / output shape / write scopes all
   derive from the OPERATORS registry — no hand-written assertions.
