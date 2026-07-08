# program.md — loop rules (the orchestration manual for agent mode)

In driver mode this file is documentation; in agent mode, the orchestrating
agent reads it to decide when to call which operator. Operator invocation
conventions / output schemas / write scopes / exit codes are governed by
PROTOCOL.md (authority: FROZEN/contracts/protocol.py) — agent orchestration
is bound by them too.

## The standard beat of one generation (same as driver.py)

1. `operators/select.py` picks a parent from archive.jsonl (default: parent-balancing).
2. `git checkout gen/<P>` restores the parent snapshot (code + weights via weights_ref).
3. `operators/rollout.py` samples the dev lane (advisory, never canonical).
4. `operators/mutate.py` mutates the candidate, guided by feedback + playbook
   (M3+: may include operators/ = self-reference).
5. `operators/novelty.py` rejects near-duplicate mutations (≤2 retries).
6. `git commit` + `git tag gen/<id>`.
7. `FROZEN/eval.sh` → `FROZEN/stamp.sh`: canonical scoring + stamping
   (score / task_vector / CI).
8. `operators/gate.py` judges status / valid_parent.
9. `operators/record.py` appends the ledger (frozen fields only from stamp.json).
10. `operators/reflect.py` verifies predictions + updates the playbook (delta ops).

## Hard rules (agents may not route around them)

- FROZEN/ is read-only. Edits are caught by the driver's frozen guard; the
  generation is voided.
- score / task_vector / best-ever always come from the frozen stamp; no
  participant may pass them as arguments.
- A diff touching operators/ must pass FROZEN/contracts + the meta_eval
  admission gate (enforced from M3).
- Training data may only come from dev-lane trajectories and must carry a
  decontam stamp (enforced from M5).

## Outer-loop trigger (from M7)

best-ever stagnant for K gens / distill sample threshold / fixed cadence →
dispatch an async training job; the checkpoint queues through canonical eval
and enters the archive like any candidate.

## Stopping conditions

Any of: target score | max_iter | budget.
