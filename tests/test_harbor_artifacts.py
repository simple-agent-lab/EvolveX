import hashlib
import json
import sys
from pathlib import Path

TEMPLATE_EVALUATOR = Path(__file__).resolve().parents[1] / "templates" / "evaluator"
sys.path.insert(0, str(TEMPLATE_EVALUATOR))

from harbor_artifacts import collect_harbor_artifacts, write_harbor_artifacts


def write_trial(
    path: Path,
    *,
    task: str,
    trial: str,
    reward: float | None,
    exception_type: str | None = None,
    exception_message: str = "fixture failure",
    cost_usd: float = 0.0,
) -> None:
    path.mkdir(parents=True)
    payload = {
        "task_name": task,
        "trial_name": trial,
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": (
            {"exception_type": exception_type, "exception_message": exception_message} if exception_type else None
        ),
        "agent_result": {"cost_usd": cost_usd},
    }
    (path / "result.json").write_text(json.dumps(payload))


def test_collect_harbor_artifacts_groups_trials_and_classifies_infra(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    write_trial(jobs / "case-a__one", task="case-a", trial="one", reward=1.0)
    write_trial(jobs / "case-a__two", task="case-a", trial="two", reward=0.0)
    write_trial(
        jobs / "case-b__one",
        task="case-b",
        trial="one",
        reward=None,
        exception_type="VerifierTimeoutError",
    )

    vector, artifacts, scoring_rewards = collect_harbor_artifacts(jobs)

    assert [trial["reward"] for trial in vector["tasks"]["case-a"]["trials"]] == [1.0, 0.0]
    assert vector["tasks"]["case-b"]["trials"][0]["status"] == "infrastructure_failed"
    assert scoring_rewards == [1.0, 0.0]
    assert artifacts["jobs_dir"] == str(jobs.resolve())
    assert "config" not in json.dumps(artifacts).lower()


def test_collect_harbor_artifacts_scores_agent_timeouts_as_zero(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    write_trial(
        jobs / "case-a__one",
        task="case-a",
        trial="one",
        reward=None,
        exception_type="AgentTimeoutError",
    )

    vector, _artifacts, scoring_rewards = collect_harbor_artifacts(jobs)

    trial = vector["tasks"]["case-a"]["trials"][0]
    assert trial["status"] == "timeout"
    assert trial["reward"] == 0.0
    assert trial["owner"] == "benchmark_agent"
    assert scoring_rewards == [0.0]


def test_exception_precedes_reward_and_failed_cost_is_preserved(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    write_trial(
        jobs / "case-a__one",
        task="case-a",
        trial="one",
        reward=0.0,
        exception_type="NonZeroAgentExitCodeError",
        exception_message="ModuleNotFoundError: No module named 'fastapi'",
        cost_usd=0.25,
    )
    run_dir = tmp_path / "run"

    rewards = write_harbor_artifacts(jobs, run_dir)

    trial = json.loads((run_dir / "task_vector.json").read_text())["tasks"]["case-a"]["trials"][0]
    assert trial["status"] == "infrastructure_failed"
    assert trial["reward"] is None
    assert trial["owner"] == "ambiguous"
    assert rewards == []
    assert json.loads((run_dir / "cost.json").read_text()) == {"usd": 0.25}


def test_explicit_candidate_marker_classifies_candidate_invalid(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    write_trial(
        jobs / "case-a__one",
        task="case-a",
        trial="one",
        reward=0.0,
        exception_type="NonZeroAgentExitCodeError",
        exception_message="EVOLVE_CANDIDATE_INVALID: missing declared dependency",
    )

    vector, _artifacts, rewards = collect_harbor_artifacts(jobs)

    trial = vector["tasks"]["case-a"]["trials"][0]
    assert trial["status"] == "candidate_invalid"
    assert trial["reward"] is None
    assert trial["owner"] == "candidate"
    assert rewards == []


def test_collect_harbor_artifacts_omits_traceback_text_from_exception_messages(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    trial = jobs / "case-a__one"
    write_trial(trial, task="case-a", trial="one", reward=None, exception_type="VerifierTimeoutError")
    result_path = trial / "result.json"
    result = json.loads(result_path.read_text())
    result["exception_info"]["exception_message"] = "Traceback (most recent call last):\nsecret-bearing frame"
    result_path.write_text(json.dumps(result))

    vector, _artifacts, _scoring_rewards = collect_harbor_artifacts(jobs)

    assert "exception_message" not in vector["tasks"]["case-a"]["trials"][0]


def test_write_harbor_artifacts_indexes_only_retained_safe_files(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    trial = jobs / "case-a__one"
    write_trial(trial, task="case-a", trial="one", reward=1.0)
    (trial / "trial.log").write_text("retained trace\n")
    (trial / ".env").write_text("EVOLVE_FAKE_SECRET=secret\n")
    (trial / "config.json").write_text('{"proxy": "secret"}\n')
    run_dir = tmp_path / "run"

    assert write_harbor_artifacts(jobs, run_dir) == [1.0]

    artifacts = json.loads((run_dir / "evaluation_artifacts.json").read_text())
    indexed = artifacts["trials"][0]["files"]
    assert indexed == [
        {
            "bytes": len("retained trace\n"),
            "path": "case-a__one/trial.log",
            "sha256": hashlib.sha256(b"retained trace\n").hexdigest(),
        },
        {
            "bytes": len((trial / "result.json").read_bytes()),
            "path": "case-a__one/result.json",
            "sha256": hashlib.sha256((trial / "result.json").read_bytes()).hexdigest(),
        },
    ]
    serialized = json.dumps(artifacts).lower()
    assert ".env" not in serialized
    assert "config" not in serialized
