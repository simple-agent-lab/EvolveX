# SKILL.md — operating this evolution workspace (the agent's manual)

You've landed in an evolve-agent workspace. It evolves a candidate (code +
prompts + config, possibly a weights pointer), scoring each generation with a
frozen ruler (FROZEN/eval.sh). Git is the lineage archive (commit =
candidate, tag `gen/<id>`); `archive.jsonl` is the ledger.
**Everything goes through `./evolve`. Run `./evolve status` first.**

## The golden path (you work one generation as the mutator)

```bash
./evolve status              # where things stand: champion, recent gens, anything pending
./evolve gen begin           # the machine does select/checkout/rollout and prints
                             # a brief: which files to read + where you may write
⟨edit files with your own tools: candidate/ (or operators/ meta/ program.md config.json)⟩
./evolve gen finish --note "what you changed and why" \
    --predict task_3         # tasks you expect to fix (verified next gen — don't guess)
                             # --used-insight <id>: report the insights you relied on
```

`finish` runs the rest for you: novelty dedup, the self-reference admission
gate, frozen eval + stamping, gate, ledger, reflection.
Made a mess or want out: `./evolve gen abort`. Let the loop run itself:
`./evolve run 10`.

## One-agent mode (you own ALL the judgements)

The operator decomposition serves autonomous mode; **for you, operators are
tools, not stations**. If you'd rather make every judgement yourself:

- `./evolve gen begin --parent 7` — your parent choice, no select operator
- `--no-rollout` — skip dev sampling if you don't want it
- mutate: never invoked in this mode — your edits ARE the mutation
- gate: set `"gate": "none"` in config.json (or edit gate.py) to own that
  judgement too

What you can NOT take over, by design: the frozen steps (eval + stamp), the
bookkeeping (commit/tag/record ordering), and the guards. Those aren't
workflow — they're the invariants.

## What you must respect (five invariants — enforced, don't fight them)

1. **FROZEN/ is read-only.** Edits get caught by digest comparison and
   reverted. Want a harness change → write a proposal for the human.
2. **You never report scores.** score/task_vector are stamped into the ledger
   by the frozen side; record has no score argument.
3. **best-ever is recomputed by a frozen rule**, champion changes require a
   replication re-eval. However loose your gate is, it can't touch this.
4. **Training data never contains gate/sealed tasks**; unstamped manifests
   are rejected by train engines.
5. **Checkpoints enter the lineage only through canonical eval.**

Your writable area is the mutation scope: `candidate/ operators/ meta/
program.md config.json`. Touching `operators/` = self-reference — it triggers
contract tests + a meta-eval replay admission gate; failing it reverts only
the operator part of your diff.
**Never hand-edit `archive.jsonl` / `best_ever.json`** — `./evolve verify`
recomputes everything and will expose it; humans and CI run verify.

## When things go wrong

- Any command errored: **read the error** — it names your next command.
- Confused state / previous session crashed: `./evolve doctor`.
- Suspect the ledger: `./evolve verify`.
- What happened in one generation: `./evolve show <gen>`.

## Deeper material (read on demand, not all at once)

- `PROTOCOL.md` — the authoritative operator interfaces / write scopes / exit
  codes (mandatory before editing operators)
- `program.md` — loop orchestration rules; `meta/*.md` — per-operator strategy;
  `meta/mutation_brief.md` — the brief template shown to agentic mutators
- `./evolve report` — diversity health + lineage attribution of operator changes
- Human-only surfaces: `./evolve sealed <gen>` (sealed test), `./evolve audit`
  (quarantine list), FROZEN version bumps — these are not yours.
