from __future__ import annotations

import argparse
import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[1]


def load_cases() -> dict[str, dict[str, str]]:
    cases: dict[str, dict[str, str]] = {}
    for line in (EVAL_DIR / "behavior_cases.jsonl").read_text().splitlines():
        case = json.loads(line)
        cases[case["id"]] = case
    return cases


def render(case: dict[str, str], arm: str) -> str:
    prompt = case["prompt"]
    if arm == "control":
        return prompt
    skill = case["skill"]
    skill_path = ROOT / "skills" / skill / "SKILL.md"
    return f"Use ${skill} at {skill_path} to solve this task.\n\n{prompt}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render one leak-free skill evaluation prompt")
    parser.add_argument("case_id")
    parser.add_argument("--arm", choices=("control", "treatment"), required=True)
    args = parser.parse_args()
    cases = load_cases()
    if args.case_id not in cases:
        parser.error(f"unknown case: {args.case_id}")
    print(render(cases[args.case_id], args.arm))


if __name__ == "__main__":
    main()
