#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from harbor_artifacts import candidate_error_code


def _results(jobs_dir: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for path in sorted(jobs_dir.rglob("result.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            results.append(payload)
    return results


def _classify(results: list[dict[str, object]], harbor_rc: int) -> tuple[str, str, str, int]:
    for result in results:
        code = candidate_error_code(result.get("exception_info"))
        if code:
            return "candidate_invalid", "candidate", code, 2
    has_exception = any(isinstance(result.get("exception_info"), dict) for result in results)
    if harbor_rc or not results or has_exception:
        return "infrastructure_failed", "infrastructure", "setup_failed", 3
    return "passed", "none", "none", 0


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        raise SystemExit("usage: parse_smoke.py <jobs_dir> <output> <harbor_rc>")
    jobs_dir = Path(argv[1])
    output = Path(argv[2])
    harbor_rc = int(argv[3])
    results = _results(jobs_dir)
    status, owner, category, exit_code = _classify(results, harbor_rc)
    payload = {
        "schema_version": 1,
        "status": status,
        "owner": owner,
        "category": category,
        "harbor_returncode": harbor_rc,
        "trial_results_seen": len(results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
