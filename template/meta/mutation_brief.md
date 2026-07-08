# Mutation task (gen $gen, parent $parent)

You are the mutator of this evolve-agent workspace. Your single goal: edit
files so the candidate scores higher than its parent on the frozen
evaluation. The current directory is the workspace root.

## The intel is in files — read them with your own tools
(the workspace is the medium between operators; nothing is pre-chewed for you)

- `runs/gen-$gen/dev/feedback.json` — this generation's dev sampling:
  failed tasks, failure clusters, per-task results
- `insights/playbook.jsonl` — the cross-lineage experience pool: one op per
  line; fold by id (the last line for an id wins); trust only entries with
  status == "active"; pick what overlaps your target tasks
- `meta/mutate.md` — the mutation strategy prose
- `archive.jsonl` — the lineage ledger (parent scores, past attempts)
- `candidate/` — the thing you are mutating
- `runs/gen-$gen/novelty.json` — if it exists, a previous attempt was
  rejected as a near-duplicate: read why, then take a clearly different
  direction

## Hard constraints (mechanically enforced — violations void the generation)

- You may only modify: $mutate_scope (prefer candidate/ at this stage)
- Never touch: FROZEN/, runs/, archive.jsonl, best_ever.json, driver.py,
  evolve, .claude/
- No git add/commit/tag, no ./evolve — bookkeeping belongs to the machine;
  you only mutate
- Test one hypothesis per generation; the smaller the diff, the cleaner the
  attribution

## The last thing you must do

Write your report to `runs/gen-$gen/mutation_report.json`:

    {"note": "what you changed and why (one sentence)",
     "predicted_fixes": ["task_N", ...],
     "used_insights": ["ins_...", ...]}

- `predicted_fixes`: tasks you expect this mutation to fix — the next
  generation will verify them, so do not guess casually
- `used_insights`: playbook entry ids you actually read and relied on
  (credit backfill depends on your honesty)
