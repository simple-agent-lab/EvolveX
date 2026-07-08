#!/usr/bin/env python3
"""driver — mechanism-side conductor for the 10-step inner loop (design §02).

Operators run as isolated subprocesses (crash isolation, small mutation
diffs); orchestration, exit-code semantics, output validation, the FROZEN
guard, novelty retries, and the self-reference admission gate live here in
one readable place. Agent mode replaces this file with an orchestrating
agent reading program.md.

Usage: driver.py [N] [--inject DIR]
  N            generations to run (default 5)
  --inject DIR migration generation: the "mutation" is copying DIR's
               candidate/ over ours (islands exchange champions this way)
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent
sys.path.insert(0, str(WS))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # keep FROZEN digests byte-stable

from FROZEN.contracts import protocol  # noqa: E402

GIT = ["git", "-c", "advice.detachedHead=false"]
OPERATOR_PATHS = ("operators", "meta", "program.md")
NOVELTY_RETRIES = 2


class NotWired(RuntimeError):
    """A capability from a later milestone was hit — abort loudly, don't loop."""


class GenDiscard(RuntimeError):
    """This generation is bad (operator failure / guard trip) — discard, continue."""


class SkillFlowError(RuntimeError):
    """skill-mode error: the workspace is left AS-IS (nothing reverted); the
    message tells the operating agent exactly what to run next."""


STATE_FILE = WS / ".evolve-gen.json"  # pending begin/finish handoff (untracked)


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


def changed_paths() -> list:
    out = sh(["git", "status", "--porcelain"], capture=True)
    return [line[3:].strip().strip('"') for line in out.splitlines() if line.strip()]


def check_mutation_scope() -> None:
    """A mutation (operator-made or agent-made) may only touch MUTATE_SCOPE.
    Everything else — driver.py, evolve, tests, FROZEN/ — is the machine, not
    the genome."""
    scope = protocol.MUTATE_SCOPE
    bad = [p for p in changed_paths() if not p.startswith(scope)]
    if bad:
        raise GenDiscard(
            f"mutation touched paths outside the mutation scope: {bad}. "
            f"Allowed: {list(scope)}. Revert them (git checkout -- <path>) "
            f"or discard the attempt (./evolve gen abort).")


def write_run_json(gen: int, name: str, data: dict) -> None:
    out = WS / "runs" / f"gen-{gen}" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def bootstrap() -> None:
    log("bootstrap: eval + record gen 0")
    sh(GIT + ["checkout", "-q", "gen/0"])
    (WS / "runs" / "gen-0").mkdir(parents=True, exist_ok=True)
    frozen_step("eval.sh", 0)
    frozen_step("stamp.sh", 0)
    run_operator("gate", gen=0)
    run_operator("record", gen=0, genesis=True, note="genesis")


def mutate_with_novelty(gen: int, parent: int) -> dict:
    """Steps 4–5 with the retry loop: novelty bounces a near-duplicate mutation
    back to mutate (≤ NOVELTY_RETRIES) before the gen is discarded."""
    for attempt in range(NOVELTY_RETRIES + 1):
        mutate = run_operator("mutate", gen=gen, parent=parent,
                              attempt=attempt if attempt else None)
        novelty = run_operator("novelty", gen=gen, parent=parent)
        if novelty["accept"]:
            return mutate
        log(f"novelty reject (attempt {attempt}): {novelty.get('hint')}")
        sh(GIT + ["checkout", "-q", "--", "."])
        sh(["git", "clean", "-qfd", "candidate", "operators", "meta"], check=False)
    raise GenDiscard(f"novelty rejected {NOVELTY_RETRIES + 1} mutation attempts")


def admission(gen: int, parent: int) -> None:
    """Self-reference admission gate (design §06-C): a diff touching
    operators/meta/program.md must pass Tier-0 contracts and the frozen
    meta_eval replay; otherwise the operator part of the diff is reverted
    (candidate changes survive). Runs pre-tag, on the committed HEAD."""
    if os.environ.get("EVOLVE_IN_META_EVAL") == "1":
        return  # replays never recurse into admission
    changed = sh(["git", "diff", "--name-only", f"gen/{parent}", "HEAD"],
                 capture=True).splitlines()
    op_changed = [p for p in changed
                  if p.startswith(("operators/", "meta/")) or p == "program.md"]
    if not op_changed:
        return

    log(f"admission gate: operator diff detected ({len(op_changed)} paths)")
    verdict = {"checked": True, "paths": op_changed}

    contracts = subprocess.run(
        [sys.executable, str(WS / "FROZEN" / "contracts" / "run_contracts.py"),
         "--workspace", str(WS)],
        cwd=WS, capture_output=True, text=True)
    if contracts.returncode != 0:
        verdict.update(admitted=False, reverted=True,
                       reason="Tier-0 contracts rejected the operator change")
        log("admission: contracts REJECTED — reverting operator paths")
    else:
        me = subprocess.run(
            ["bash", str(WS / "FROZEN" / "meta_eval.sh"),
             "--old", f"gen/{parent}", "--new", "HEAD"],
            cwd=WS, capture_output=True, text=True)
        try:
            replay = json.loads(me.stdout)
        except json.JSONDecodeError:
            replay = {"admitted": False, "error": me.stderr.strip()[:200]}
        verdict["meta_eval"] = replay
        if replay.get("admitted"):
            verdict.update(admitted=True, reverted=False)
            log(f"admission: ADMITTED (old_best={replay.get('old_best')} "
                f"new_best={replay.get('new_best')})")
        else:
            verdict.update(admitted=False, reverted=True,
                           reason=replay.get("error", "meta_eval replay: inferior"))
            log("admission: meta_eval REJECTED — reverting operator paths")

    if verdict["reverted"]:
        sh(GIT + ["checkout", f"gen/{parent}", "--", *OPERATOR_PATHS])
        sh(["git", "add", "-A"])
        sh(["git", "commit", "-q", "--amend", "--no-edit"])
    write_run_json(gen, "admission", verdict)


def inject_candidate(gen: int, source: Path) -> dict:
    """Migration 'mutation': overwrite candidate/ with a champion from another
    island. Same lineage rules apply — commit, canonical eval, gate, record."""
    target = WS / "candidate"
    shutil.rmtree(target)
    shutil.copytree(source / "candidate", target)
    info = {"note": f"migrant candidate injected from {source}",
            "predicted_fixes": [], "used_insights": [],
            "cost": {"tokens": 0, "eval_minutes": 0}, "migrant": True}
    write_run_json(gen, "mutate", info)
    return info


def generation(inject: Path = None) -> None:
    selected = run_operator("select")                               # (1)
    parent = selected["parent"]
    gen = next_id()
    log(f"gen {gen} <- parent {parent}" + (" [inject]" if inject else ""))

    sh(GIT + ["checkout", "-q", f"gen/{parent}"])                   # (2)
    (WS / "runs" / f"gen-{gen}").mkdir(parents=True, exist_ok=True)
    write_run_json(gen, "select", selected)
    fz_before = frozen_digest()

    try:
        if inject:
            mutate = inject_candidate(gen, inject)                  # migration arm
        else:
            run_operator("rollout", gen=gen, parent=parent)         # (3)
            mutate = mutate_with_novelty(gen, parent)               # (4)(5)
        if frozen_digest() != fz_before:
            raise GenDiscard("mutation touched FROZEN/ — the frozen core is "
                             "read-only; propose harness changes to the human "
                             "outside the loop")
        check_mutation_scope()
    except GenDiscard:
        cleanup_worktree()
        raise

    sh(["git", "add", "-A"])                                        # (6)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=WS).returncode == 0:
        raise GenDiscard("empty mutation — tree identical to parent, nothing to commit")
    sh(["git", "commit", "-qm", f"gen {gen} (parent {parent}): {mutate['note']}"])
    admission(gen, parent)                                          # (6b) §06-C gate
    sh(["git", "tag", f"gen/{gen}"])

    frozen_step("eval.sh", gen)                                     # (7)
    frozen_step("stamp.sh", gen)
    run_operator("gate", gen=gen, parent=parent)                    # (8)
    run_operator("record", gen=gen, parent=parent)                  # (9)
    run_operator("reflect", gen=gen)                                # (10)


# ---------------------------------------------------------------------------
# skill mode: the operating agent IS the mutator (gen begin / finish / abort).
# The mechanism keeps its monopoly on bookkeeping and invariants; the agent
# only occupies the one step where it adds value — making the mutation.
# ---------------------------------------------------------------------------


def read_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else None


def preflight_or_raise() -> None:
    p = subprocess.run(["bash", str(WS / "operators" / "preflight.sh")],
                       cwd=WS, capture_output=True, text=True)
    if p.returncode != 0:
        raise SkillFlowError(p.stderr.strip())


def mutation_brief(gen: int, parent: int) -> dict:
    """A MAP, not a digest: all inter-operator communication goes through
    workspace files, and the mutator reads them with its own tools. Retrieval
    judgement (which insights matter, what history to check) belongs to the
    agent, not to the machine."""
    return {
        "gen": gen, "parent": parent,
        "read_these": {
            f"runs/gen-{gen}/dev/feedback.json":
                "本代 dev 采样:失败任务、失败簇、逐任务结果",
            "insights/playbook.jsonl":
                "跨谱系经验池:每行一条 op,按 id 折叠取最后一行,只信 "
                "status==active;按 target_tasks 重叠度自行挑选",
            "meta/mutate.md": "变异策略 prose",
            "archive.jsonl": "谱系账本(父代分数、历史尝试)",
            "candidate/": "你要改的对象本体",
        },
        "write_scope": list(protocol.MUTATE_SCOPE),
        "next": "read the files above with your own tools, edit within "
                "write_scope, then: ./evolve gen finish "
                "--note '<what you changed and why>' [--predict task_N ...] "
                "[--used-insight <id> ...]   (or ./evolve gen abort)",
    }


def begin_generation() -> dict:
    if read_state():
        raise SkillFlowError("a generation is already in progress — run "
                             "`./evolve gen finish --note ...` or `./evolve gen abort` first")
    if changed_paths():
        raise SkillFlowError("working tree is dirty with no generation in progress — "
                             "run `./evolve doctor` first")
    preflight_or_raise()
    if next_id() == 0:
        bootstrap()

    selected = run_operator("select")                               # (1)
    parent = selected["parent"]
    gen = next_id()
    sh(GIT + ["checkout", "-q", f"gen/{parent}"])                   # (2)
    (WS / "runs" / f"gen-{gen}").mkdir(parents=True, exist_ok=True)
    write_run_json(gen, "select", selected)
    fz = frozen_digest()
    run_operator("rollout", gen=gen, parent=parent)                 # (3)

    STATE_FILE.write_text(json.dumps(
        {"gen": gen, "parent": parent, "fz_digest": fz, "phase": "begun"}) + "\n")
    return mutation_brief(gen, parent)                              # (4) is YOURS


def finish_generation(note: str, predicted=(), used_insights=()) -> dict:
    state = read_state()
    if not state:
        raise SkillFlowError("no generation in progress — run `./evolve gen begin` first")
    gen, parent = state["gen"], state["parent"]

    if frozen_digest() != state["fz_digest"]:
        sh(GIT + ["checkout", "-q", "--", "FROZEN"])
        raise SkillFlowError("your edits touched FROZEN/ — reverted just those paths. "
                             "The frozen core is read-only (invariants #1–#5); adjust "
                             "your mutation and re-run `./evolve gen finish`")
    bad = [p for p in changed_paths() if not p.startswith(protocol.MUTATE_SCOPE)]
    if bad:
        raise SkillFlowError(f"edits outside the mutation scope: {bad}. Allowed: "
                             f"{list(protocol.MUTATE_SCOPE)}. Revert them "
                             f"(git checkout -- <path>) and re-run `./evolve gen finish`")
    if not changed_paths():
        raise SkillFlowError("nothing changed — make a mutation within "
                             f"{list(protocol.MUTATE_SCOPE)}, or `./evolve gen abort`")

    write_run_json(gen, "mutate", {
        "note": note, "predicted_fixes": list(predicted),
        "used_insights": list(used_insights),
        "cost": {"tokens": 0, "eval_minutes": 0}, "variant": "agent"})

    novelty = run_operator("novelty", gen=gen, parent=parent)       # (5)
    if not novelty["accept"]:
        raise SkillFlowError(f"novelty reject: {novelty.get('hint')} — your edits are "
                             "kept; change direction and re-run `./evolve gen finish`")

    sh(["git", "add", "-A"])                                        # (6)
    sh(["git", "commit", "-qm", f"gen {gen} (parent {parent}): {note}"])
    admission(gen, parent)                                          # (6b)
    sh(["git", "tag", f"gen/{gen}"])

    frozen_step("eval.sh", gen)                                     # (7)
    frozen_step("stamp.sh", gen)
    run_operator("gate", gen=gen, parent=parent)                    # (8)
    entry = run_operator("record", gen=gen, parent=parent)          # (9)
    run_operator("reflect", gen=gen)                                # (10)
    STATE_FILE.unlink(missing_ok=True)
    outer_loop_check()
    return entry


def abort_generation() -> dict:
    state = read_state()
    if not state:
        raise SkillFlowError("no generation in progress — nothing to abort")
    cleanup_worktree()
    latest = next_id() - 1
    if latest >= 0:
        sh(GIT + ["checkout", "-q", f"gen/{latest}"])
    STATE_FILE.unlink(missing_ok=True)
    return {"aborted_gen": state["gen"], "back_at": f"gen/{latest}"}


def outer_loop_check() -> None:
    """Outer loop T1–T4 (design §03): on a best-ever plateau, distill dev
    trajectories, pass the frozen decontamination gate, and dispatch the train
    engine as a background-able job. The produced checkpoint re-enters the
    inner loop as a candidate (M6, engine currently infra-blocked) — the
    trigger, data, and stamping mechanics are live now.

    Armed via EVOLVE_TRAIN_PLATEAU=<K> (off when unset/0)."""
    k = int(os.environ.get("EVOLVE_TRAIN_PLATEAU", "0") or 0)
    best_path = WS / "best_ever.json"
    if not k or not best_path.exists():
        return
    best = json.loads(best_path.read_text())
    latest = next_id() - 1
    if latest - best["genid"] < k:
        return

    state_path = WS / "runs" / "train-requests" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if latest - state.get("last_request_gen", -10**9) < k:
        return  # cooldown: one request per plateau window

    log(f"outer loop: plateau detected (best gen {best['genid']} unchallenged "
        f"for {latest - best['genid']} gens) — T2 distill")
    request = {"trigger_gen": latest, "plateau_k": k, "champion": best}
    try:
        distilled = run_operator("distill")                              # T2
        request["manifest"] = distilled["manifest"]
        request["samples"] = {"sft": distilled["sft"], "dpo": distilled["dpo"]}

        p = subprocess.run([sys.executable, str(WS / "FROZEN" / "decontam.py"),
                            "stamp", distilled["manifest"]],
                           cwd=WS, capture_output=True, text=True)      # T3
        request["stamped"] = p.returncode == 0
        if p.returncode != 0:
            request["engine"] = "skipped"
            log(f"outer loop: decontam rejected the manifest — {p.stderr.strip()[:200]}")
        else:
            p = subprocess.run(
                ["bash", str(WS / "operators" / "engines" / "train_tinker.sh"),
                 "ckpts/base", distilled["manifest"],
                 "operators/train/recipe.yaml", f"ckpts/req-{latest}"],
                cwd=WS, capture_output=True, text=True)                 # T4
            if p.returncode == protocol.EXIT_NOT_WIRED:
                request["engine"] = "not-wired"
                log("outer loop: armed and data staged — train engine backend "
                    "is M6 (open-weights model + GPU/API)")
            elif p.returncode == 0:
                request["engine"] = "ok"
                log("outer loop: train job dispatched")  # M6: checkpoint re-entry
            else:
                request["engine"] = f"failed:{p.returncode}"
                log(f"outer loop: engine failed — {p.stderr.strip()[:200]}")
    except (GenDiscard, NotWired) as e:
        request["error"] = str(e)[:200]
        log(f"outer loop: aborted — {e}")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    (state_path.parent / f"req-{latest}.json").write_text(
        json.dumps(request, indent=1) + "\n")
    state_path.write_text(json.dumps({"last_request_gen": latest}) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=5)
    ap.add_argument("--inject", type=Path, default=None,
                    help="run one migration generation from this workspace dir")
    a = ap.parse_args(argv)

    if read_state():
        log("a skill-mode generation is in progress — run `./evolve gen finish` "
            "or `./evolve gen abort` before autonomous runs")
        return 1
    p = subprocess.run(["bash", str(WS / "operators" / "preflight.sh")],
                       cwd=WS, capture_output=True, text=True)
    if p.returncode != 0:
        log(p.stderr.strip())
        return 1

    if next_id() == 0:
        bootstrap()

    n = 1 if a.inject else a.n
    done = discarded = 0
    for _ in range(n):
        try:
            generation(inject=a.inject)
            done += 1
        except GenDiscard as e:
            log(f"discard: {e}")
            discarded += 1
        except NotWired as e:
            log(f"abort: {e}")
            return protocol.EXIT_NOT_WIRED
        outer_loop_check()  # T1: plateau trigger (no-op unless armed)

    best = "n/a"
    best_path = WS / "best_ever.json"
    if best_path.exists():
        best = json.loads(best_path.read_text())["score"]
    total = len((WS / "archive.jsonl").read_text().splitlines())
    log(f"done: {done} gens ({discarded} discarded), {total} ledger entries, best-ever={best}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
