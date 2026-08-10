from library.mutate._config import RUNNER_KEYS, normalize_runner_config


def test_normalize_runner_config_preserves_supported_runner_values() -> None:
    raw: dict[str, object] = {
        "runner": "harbor",
        "command": "printf accepted",
        "agent": "provider.Agent",
        "model": "provider/model",
        "environment": "provider.Environment",
        "environment_kwargs": {"network": "host"},
        "image": "registry/image:tag",
        "workdir": "/app/task",
        "agent_kwargs": {"reasoning": "high"},
        "agent_env": {"TOKEN": "configured"},
        "agent_pythonpath": "/app/python",
        "jobs_dir": "runs/jobs",
    }

    assert set(raw) == set(RUNNER_KEYS)
    assert normalize_runner_config(raw) == raw


def test_normalize_runner_config_defaults_and_rejects_unknown_runner() -> None:
    assert normalize_runner_config({}) == {"runner": "local"}

    try:
        normalize_runner_config({"runner": "remote"})
    except ValueError as error:
        assert str(error) == "runner must be 'local' or 'harbor'"
    else:
        raise AssertionError("unsupported runner was accepted")
