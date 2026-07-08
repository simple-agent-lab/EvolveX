#!/usr/bin/env python3
"""mutate — change the candidate given dev feedback + playbook insights.

Variants (config.json "mutate", env EVOLVE_MUTATE_VARIANT wins):
  fixed (default) — deterministic tweak, no LLM; consults the playbook
        mechanically so the used_insights -> credit-backfill loop is
        exercised end to end. Cheap idle mode.
  agent — AGENTIC mutation: spawn a coding agent (headless `claude` CLI, or
        any command via EVOLVE_MUTATOR_CMD) with file-editing tools, cwd at
        the workspace. The agent reads the mutation brief, explores, edits
        files within the mutation scope, and writes a structured report to
        runs/gen-<id>/mutation_report.json. This operator only assembles the
        brief and collects the result — judgement lives in the agent.
        Misbehavior is contained downstream: the driver's FROZEN digest
        guard + mutation-scope check discard the generation.
  noop — control arm.

Write scope (protocol bound): candidate/, operators/, meta/, program.md,
config.json. Never FROZEN/.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import (OperatorError, config, operator_main,  # noqa: E402
                                    playbook_active, read_json, run_dir, ws_path)
from FROZEN.contracts.protocol import MUTATE_SCOPE, MutateOutput  # noqa: E402

TOP_K = 3


def retrieve_insights(failed_tasks):
    """Top-K active insights ranked by overlap with the current failure set,
    then utility. Returns (ids, entries)."""
    failed_names = {f"task_{t}" for t in failed_tasks}
    scored = []
    for e in playbook_active():
        overlap = len(failed_names & set(e.get("target_tasks", [])))
        if overlap > 0:
            scored.append((overlap, e["support"] - e["refute"], e))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    picked = [e for _, _, e in scored[:TOP_K]]
    return [e["id"] for e in picked], picked


# ---------------------------------------------------------------- variants

def mutate_fixed(args, failed, insights):
    params_path = ws_path("candidate", "params.json")
    params = json.loads(params_path.read_text())
    attempt = getattr(args, "attempt", None) or 0
    params["retries"] = max(0, int(params.get("retries", 0)) + (1 if args.gen % 2 else -1))
    params["temperature"] = round(min(1.0, max(0.0,
        float(params.get("temperature", 0.2))
        + (0.05 if args.gen % 3 == 0 else -0.02) + 0.013 * attempt)), 3)
    params.setdefault("tweak_seq", []).append([args.gen, attempt])
    if insights:
        params["focus_tasks"] = sorted({t for e in insights
                                        for t in e.get("target_tasks", [])})[:4]
    params_path.write_text(json.dumps(params, indent=1) + "\n")
    note = (f"fixed tweak: retries={params['retries']} temperature={params['temperature']}"
            + (f", guided by {len(insights)} insight(s)" if insights else ""))
    return note, [f"task_{t}" for t in failed[:2]], [e["id"] for e in insights], \
        {"tokens": 0, "eval_minutes": 0}


def build_brief(args) -> str:
    """The mutation brief is a MAP, not a digest: all inter-operator
    communication goes through workspace files, and the agent reads them with
    its own tools. No pre-chewed insights — retrieval judgement belongs to the
    agent (and to meta/mutate.md, which is evolvable), not to this launcher."""
    attempt = getattr(args, "attempt", None) or 0
    retry_hint = ""
    if attempt:
        retry_hint = (f"\n## 重试提示(第 {attempt} 次)\n"
                      f"上一次变异被查重打回,原因在 runs/gen-{args.gen}/novelty.json —— "
                      f"读它,然后换一个明显不同的方向。\n")
    return f"""# 变异任务(gen {args.gen},parent {args.parent})

你是这个进化 workspace 的 mutator。你的唯一目标:改动文件,让 candidate 在
冻结评测上的分数比父代更高。当前目录就是 workspace 根。

## 情报都在文件里,用你的工具自己读(workspace 就是算子间的通信介质)
- `runs/gen-{args.gen}/dev/feedback.json` — 本代 dev 采样:失败任务、失败簇、逐任务结果
- `insights/playbook.jsonl` — 跨谱系经验池:每行一条 op,按 id 折叠(同 id 取最后一行),
  只信 status=="active" 的条目;按 target_tasks 与你要修的任务的重叠度自行挑选
- `meta/mutate.md` — 变异策略 prose
- `archive.jsonl` — 谱系账本(要看父代分数、历史尝试时查它)
- `candidate/` — 你要改的对象本体
{retry_hint}
## 硬约束(机制会强制执行,违反 = 整代作废)
- 只允许改动:{list(MUTATE_SCOPE)}(本阶段建议只改 candidate/)
- 禁止触碰:FROZEN/、runs/、archive.jsonl、best_ever.json、driver.py、evolve、.claude/
- 不要 git add/commit/tag,不要运行 ./evolve —— 记账是机制的事,你只负责变异
- 一次只验证一个假设,diff 越小归因越干净

## 完成后必须做的最后一件事
把报告写到 runs/gen-{args.gen}/mutation_report.json,格式:
{{"note": "改了什么、为什么(一句话)",
  "predicted_fixes": ["task_N", ...],   ← 你预测会修好的任务,下代会核对,别乱说
  "used_insights": ["ins_...", ...]}}   ← 你真正读过并采纳的经验 id
"""


def mutate_agent(args):
    run = run_dir(args.gen)
    prompt_path = run / "mutation_prompt.md"
    report_path = run / "mutation_report.json"
    # a discarded attempt at this genid may have left a stale report — a reused
    # genid must never inherit the previous agent's claims
    report_path.unlink(missing_ok=True)
    prompt = build_brief(args)
    prompt_path.write_text(prompt)

    env = dict(os.environ,
               MUTATION_PROMPT=str(prompt_path),
               MUTATION_REPORT=str(report_path),
               MUTATION_GEN=str(args.gen))
    timeout = int(os.environ.get("EVOLVE_MUTATOR_TIMEOUT", "600"))
    cost = {"tokens": 0, "eval_minutes": 0}

    custom = os.environ.get("EVOLVE_MUTATOR_CMD")
    if custom:
        p = subprocess.run(["bash", "-c", custom], cwd=ws_path(), env=env,
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            raise OperatorError(f"mutator command failed (exit {p.returncode}): "
                                f"{p.stderr.strip()[:200]}")
    else:
        if shutil.which("claude") is None:
            raise OperatorError(
                "agent variant needs the `claude` CLI on the host, or set "
                "EVOLVE_MUTATOR_CMD to any command that reads $MUTATION_PROMPT, "
                "edits files, and writes $MUTATION_REPORT "
                "(EVOLVE_MUTATE_VARIANT=fixed to fall back)")
        p = subprocess.run(
            ["claude", "-p", prompt,
             "--output-format", "json",
             "--permission-mode", "acceptEdits",
             "--allowedTools", "Read,Glob,Grep,Edit,Write"],
            cwd=ws_path(), env=env, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            raise OperatorError(f"claude agent failed (exit {p.returncode}): "
                                f"{p.stderr.strip()[:200]}")
        try:
            meta = json.loads(p.stdout)
            usage = meta.get("usage") or {}
            cost = {"tokens": int(usage.get("input_tokens", 0))
                    + int(usage.get("output_tokens", 0)),
                    "usd": meta.get("total_cost_usd"),
                    "eval_minutes": 0}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass  # cost stays zeroed; the mutation itself is judged by eval anyway

    report = read_json(report_path, None)
    if report is None:
        note = "agentic mutation (agent did not write mutation_report.json)"
        predicted, used = [], []
    else:
        note = str(report.get("note", "agentic mutation"))[:200]
        predicted = [str(x) for x in report.get("predicted_fixes", [])
                     if isinstance(x, str)][:8]
        used = [str(x) for x in report.get("used_insights", [])
                if isinstance(x, str)][:8]
    return note, predicted, used, cost


@operator_main("mutate")
def main(args):
    feedback = read_json(ws_path("runs", f"gen-{args.gen}", "dev", "feedback.json"), {})
    failed = feedback.get("failed_tasks", [])
    _, insights = retrieve_insights(failed)

    variant = os.environ.get("EVOLVE_MUTATE_VARIANT") or config().get("mutate", "fixed")
    if variant == "noop":
        note, predicted, used, cost = "noop (control arm)", [], [], \
            {"tokens": 0, "eval_minutes": 0}
    elif variant in ("agent", "llm"):  # "llm" kept as a legacy alias
        variant = "agent"
        note, predicted, used, cost = mutate_agent(args)
    else:
        variant = "fixed"
        note, predicted, used, cost = mutate_fixed(args, failed, insights)

    with open(ws_path("candidate", "notes.md"), "a") as f:
        f.write(f"- gen {args.gen} (parent {args.parent}, {variant}): {note}\n")

    return MutateOutput(note=note, predicted_fixes=predicted, used_insights=used,
                        cost=cost, extras={"variant": variant})


if __name__ == "__main__":
    main()
