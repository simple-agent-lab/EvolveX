from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationRunPlan:
    """Authoritative description of one evaluation invocation."""

    schema_version: int
    experiment_id: str
    generation: str
    candidate_commit: str
    purpose: str
    canonical: bool
    tasks: tuple[str, ...]
    attempts_per_task: int
    expected_trials: int
    concurrency: int
    evaluator_fingerprint: str
    task_set_hash: str
    runtime_fingerprint: str
    execution_runtime_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tasks"] = list(self.tasks)
        return payload

    def write(self, path: Path) -> Path:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
        return path

    @classmethod
    def read(cls, path: Path) -> EvaluationRunPlan:
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError("evaluation run plan must be an object")
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or any(not isinstance(task, str) or not task for task in tasks):
            raise ValueError("evaluation run plan tasks must be non-empty strings")
        canonical = payload.get("canonical")
        if not isinstance(canonical, bool):
            raise ValueError("evaluation run plan canonical must be a boolean")
        plan = cls(
            schema_version=int(payload["schema_version"]),
            experiment_id=str(payload["experiment_id"]),
            generation=str(payload["generation"]),
            candidate_commit=str(payload["candidate_commit"]),
            purpose=str(payload["purpose"]),
            canonical=canonical,
            tasks=tuple(tasks),
            attempts_per_task=int(payload["attempts_per_task"]),
            expected_trials=int(payload["expected_trials"]),
            concurrency=int(payload["concurrency"]),
            evaluator_fingerprint=str(payload["evaluator_fingerprint"]),
            task_set_hash=str(payload["task_set_hash"]),
            runtime_fingerprint=str(payload["runtime_fingerprint"]),
            execution_runtime_fingerprint=str(payload["execution_runtime_fingerprint"]),
        )
        if plan.schema_version != 1:
            raise ValueError(f"unsupported evaluation run plan schema: {plan.schema_version}")
        if plan.attempts_per_task < 1 or plan.expected_trials < 1 or plan.concurrency < 1:
            raise ValueError("evaluation run plan counts must be positive")
        if plan.tasks and plan.expected_trials != len(plan.tasks) * plan.attempts_per_task:
            raise ValueError("evaluation run plan expected_trials does not match tasks and attempts")
        return plan
