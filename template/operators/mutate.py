#!/usr/bin/env python3
"""mutate — change the candidate given dev feedback + playbook insights.

Variants (EVOLVE_MUTATE_VARIANT):
  fixed (default) — deterministic tweak, no LLM; consults the playbook
        mechanically (top-K retrieval by failed-task overlap) so the
        used_insights -> credit-backfill loop is exercised end to end.
  llm  — asks a model (claude CLI) for a JSON param patch conditioned on
        meta/mutate.md + failure clusters + top-K insights. Needs the CLI
        and a key on the host; falls back with a clear error, never silently.
  noop — control arm.

Write scope (protocol bound): candidate/ now; operators/, meta/, program.md
open at M3 behind the contracts + meta_eval admission gates. Never FROZEN/.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FROZEN.contracts.oplib import (OperatorError, config, operator_main,  # noqa: E402
                                    playbook_active, read_json, ws_path)
from FROZEN.contracts.protocol import MutateOutput  # noqa: E402

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


def apply_param_patch(patch: dict) -> dict:
    params_path = ws_path("candidate", "params.json")
    params = json.loads(params_path.read_text())
    for k, v in patch.items():
        if isinstance(v, (int, float, str, bool)):
            params[k] = v
    params_path.write_text(json.dumps(params, indent=1) + "\n")
    return params


def mutate_fixed(args, failed, insights):
    params_path = ws_path("candidate", "params.json")
    params = json.loads(params_path.read_text())
    attempt = getattr(args, "attempt", None) or 0
    params["retries"] = max(0, int(params.get("retries", 0)) + (1 if args.gen % 2 else -1))
    params["temperature"] = round(min(1.0, max(0.0,
        float(params.get("temperature", 0.2))
        + (0.05 if args.gen % 3 == 0 else -0.02) + 0.013 * attempt)), 3)
    params.setdefault("tweak_seq", []).append([args.gen, attempt])
    # a matching tactic biases the tweak toward its target tasks (stub-level)
    if insights:
        params["focus_tasks"] = sorted({t for e in insights
                                        for t in e.get("target_tasks", [])})[:4]
    params_path.write_text(json.dumps(params, indent=1) + "\n")
    return (f"fixed tweak: retries={params['retries']} temperature={params['temperature']}"
            + (f", guided by {len(insights)} insight(s)" if insights else ""))


def mutate_llm(args, failed, insights):
    if shutil.which("claude") is None:
        raise OperatorError("llm variant needs the `claude` CLI on the host "
                            "(EVOLVE_MUTATE_VARIANT=fixed to fall back)")
    strategy = ws_path("meta", "mutate.md").read_text()
    prompt = (
        f"{strategy}\n\n"
        f"当前 candidate/params.json:\n{ws_path('candidate', 'params.json').read_text()}\n"
        f"dev 失败任务: {failed}\n"
        f"相关经验(playbook top-K):\n"
        + "\n".join(f"- [{e['id']}] {e['claim']} (support={e['support']} refute={e['refute']})"
                    for e in insights)
        + "\n\n只输出一个 JSON 对象作为对 params.json 的补丁(仅标量键值),不要其它文字。"
    )
    p = subprocess.run(["claude", "-p", prompt, "--output-format", "text"],
                       capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise OperatorError(f"claude CLI failed: {p.stderr.strip()[:200]}")
    try:
        text = p.stdout.strip()
        patch = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        raise OperatorError(f"llm did not return a JSON patch: {p.stdout.strip()[:120]!r}")
    params = apply_param_patch(patch)
    return f"llm patch: {sorted(patch.keys())} -> {json.dumps(params, ensure_ascii=False)[:80]}"


@operator_main("mutate")
def main(args):
    feedback = read_json(ws_path("runs", f"gen-{args.gen}", "dev", "feedback.json"), {})
    failed = feedback.get("failed_tasks", [])
    used_ids, insights = retrieve_insights(failed)

    variant = os.environ.get("EVOLVE_MUTATE_VARIANT") or config().get("mutate", "fixed")
    if variant == "noop":
        note = "noop (control arm)"
    elif variant == "llm":
        note = mutate_llm(args, failed, insights)
    else:
        note = mutate_fixed(args, failed, insights)

    with open(ws_path("candidate", "notes.md"), "a") as f:
        f.write(f"- gen {args.gen} (parent {args.parent}, {variant}): {note}\n")

    return MutateOutput(
        note=note,
        predicted_fixes=[f"task_{t}" for t in failed[:2]],
        used_insights=used_ids,
        cost={"tokens": 0, "eval_minutes": 0},
        extras={"variant": variant},
    )


if __name__ == "__main__":
    main()
